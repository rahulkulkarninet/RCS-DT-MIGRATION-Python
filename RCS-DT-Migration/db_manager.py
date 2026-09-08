import os
import pyodbc
import re
import shutil
import subprocess
import logging
import getpass
import tempfile
import threading
import time
import traceback
from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Dict, Any, List, Tuple, Iterable, Iterator
import numpy as np
from sqlalchemy import MetaData, Table, create_engine, text, inspect
from sqlalchemy.pool import QueuePool
from sqlalchemy.engine import Engine
from urllib.parse import quote_plus
import pandas as pd
from dotenv import load_dotenv

# --- Load sizing -----------------------------------------------------------
# pyodbc's fast_executemany pre-allocates a client-side buffer sized by each
# column's *declared* width, not by the data actually present. On a 267-column
# nvarchar(1000)-heavy staging table that is ~400 KB per row, so the historic
# 10,000-row chunk tried to allocate ~4 GB and raised MemoryError. Batches are
# therefore sized by estimated bytes, not by row count.
DEFAULT_MAX_BATCH_BYTES = 64 * 1024 * 1024   # 64 MB client buffer ceiling
MAX_BATCH_ROWS = 10000                       # never exceed this regardless of width
MIN_BATCH_ROWS = 20                          # nor go below it; tiny batches thrash
NVARCHAR_MAX_ESTIMATE_CHARS = 4000           # nvarchar(max) has no declared width
_BYTES_PER_CHAR = 2                          # nvarchar is UCS-2
_PER_COLUMN_OVERHEAD = 8                     # length/indicator per bound column
_NON_TEXT_COLUMN_BYTES = 16                  # int/decimal/datetime binding cost

# --- Transient fault handling ----------------------------------------------
# Azure SQL Database disconnects and throttles as normal operation, so every
# call needs retry. Codes below are the documented retryable set plus deadlock.
TRANSIENT_ERROR_CODES = {
    4060, 4221, 40197, 40501, 40613, 40143, 49918, 49919, 49920,
    10928, 10929, 10053, 10054, 10060, 11001, 233, 64, 20, 1205, 3960, 8645,
}
TRANSIENT_SQLSTATES = {"08S01", "08001", "08003", "08006", "40001", "40197", "HYT00", "HYT01"}
TRANSIENT_MESSAGE_TOKENS = (
    "timeout", "connection is closed", "connection was recovered",
    "transport-level error", "semaphore timeout", "not currently available",
    "please retry", "too many operations", "deadlock",
)
DEFAULT_RETRY_ATTEMPTS = 5

# --- Staging archive ---------------------------------------------------------
# Database holding the long-lived copy of the RC_* staging tables, on the same
# server as the environment's DATABASE. Every environment names its own, in
# ARCHIVE_DATABASE in its env file - test-migration-data on testse, and so on.
# This is only the fallback for an env file that does not say, and being wrong
# about it surfaces as "<name> has no table dbo.RC_..." from the archive step.
DEFAULT_ARCHIVE_DATABASE = 'migration_data'

# --- bcp sink ---------------------------------------------------------------
# bcp binds nothing client-side, so declared column widths stop mattering and
# throughput is not limited by per-row Python work. Terminators are control
# characters that cannot occur in CSV-sourced text, so embedded commas, quotes
# and newlines need no escaping. Values containing them are sanitised and
# reported rather than silently corrupting the row layout.
BCP_FIELD_TERMINATOR = '\x1f'   # ASCII unit separator
BCP_ROW_TERMINATOR = '\x1e'     # ASCII record separator
BCP_CODE_PAGE = '65001'         # UTF-8
BCP_BATCH_SIZE = 10000          # -b: commit granularity, keeps log bursts small
BCP_MAX_ERRORS = 10             # -m: abort after this many rejected rows

class DatabaseHelper:
    def __init__(self, environment: str , config_path: str = None):
        """
        Initialize database helper for the specified environment.
        """
        self.environment = environment.lower()
        if config_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, 'config' )
        
        self.config_path = config_path
        self.config = self._load_config()
        self.pyodbc_connection = None
        self.sqlalchemy_engine = None
        self.connection_timeout = 900  # 15 minutes
        self.last_activity = time.time()
        # (schema, table) -> {column: declared char length or None}
        self._column_width_cache: Dict[Tuple[str, str], Dict[str, Optional[int]]] = {}
        # (schema, table) -> {lowercased column: fractional-second digits}
        self._datetime_scale_cache: Dict[Tuple[str, str], Dict[str, int]] = {}
        # (schema, table) -> reflected Table, so the INSERT compiles only once
        self._reflected_table_cache: Dict[Tuple[str, str], Table] = {}
        self._bcp_available: Optional[bool] = None
        self._bcp_version_major: Optional[int] = None
        # Verified CLI authentication, resolved once per tool. Keyed by tool
        # because bcp and classic sqlcmd do not support the same methods: bcp can
        # carry a service principal through a DSN, sqlcmd cannot. They are spawned
        # per table and per file, so without this an auth problem surfaces dozens
        # of times per run.
        self._cli_auth_winner: Dict[str, Tuple[str, List[str]]] = {}
        self._cli_auth_resolved: set = set()
        self._cli_auth_error: Dict[str, str] = {}
        self._cli_auth_attempts: Dict[str, List[Tuple[str, str]]] = {}
        # Resolved sqlcmd binary and whether it is go-sqlcmd. Installing
        # go-sqlcmd does not displace the classic ODBC build on PATH, so the
        # binary is chosen explicitly rather than by name.
        self._sqlcmd_path: Optional[str] = None
        self._sqlcmd_is_go: Optional[bool] = None
        # sqlcmd timeouts. Idle-based, because file 76's loops legitimately run
        # for hours at volume while PRINTing a heartbeat every 1000 iterations.
        # sqlcmd_max_total = None means no absolute cap for file execution.
        self.sqlcmd_idle_timeout = 900          # 15 minutes of total silence
        self.sqlcmd_max_total: Optional[int] = None

        # SQLAlchemy connection pool. Passed to create_engine as kwargs; putting
        # them in the URL silently did nothing (see connect_sqlalchemy).
        self.pool_size = 5
        self.pool_max_overflow = 10
        self.pool_timeout = 30                  # seconds to wait for a connection
        self.pool_recycle = 1800                # under Azure SQL's idle cutoff
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def _get_current_username(self) -> str:
        """Get the current user's UPN or fallback to getpass."""
        try:
            # Try to get UPN first
            username = subprocess.check_output('whoami /upn', shell=True).decode().strip()
            return username
        except (subprocess.CalledProcessError, FileNotFoundError, Exception) as e:
            self.logger.warning(f"whoami /upn failed: {str(e)}, falling back to getpass")
            try:
                # Fallback to getpass
                username = getpass.getuser()
                return username
            except Exception as e:
                self.logger.error(f"Both whoami /upn and getpass failed: {str(e)}")
                raise ValueError("Unable to determine current username")
    
    def _load_config(self) -> Dict[str, str]:
        """Load configuration from environment file using python-dotenv."""
        env_file = os.path.join(self.config_path, f"{self.environment}.env")
        
        if not os.path.exists(env_file):
            raise FileNotFoundError(f"Environment file not found: {env_file}")
        
        # Clear any existing environment variables to avoid conflicts
        # BCP_* included so switching environment inside one process cannot carry
        # a previous environment's credential over. load_dotenv(override=True)
        # replaces what the new file defines, but says nothing about keys the new
        # file omits.
        env_vars_to_clear = ['SERVER', 'DATABASE', 'USERNAME',
                             'CLIENT_ID', 'CLIENT_SECRET',
                             'BCP_AUTH', 'BCP_DSN', 'BCP_USERNAME',
                             'ARCHIVE_DATABASE',
                             ]
        for var in env_vars_to_clear:
            if var in os.environ:
                del os.environ[var]
        
        # Load the .env file
        load_dotenv(env_file,override=True)

        # Get required configuration values
        config = {
            'SERVER': os.getenv('SERVER', ''),
            'DATABASE': os.getenv('DATABASE', ''),
            'DRIVER': os.getenv('DRIVER', 'ODBC Driver 17 for SQL Server'),
            'NETWORK_SERVER': os.getenv('NETWORK_SERVER', ''),
            'NETWORK_SHARE': os.getenv('NETWORK_SHARE', ''),
            # Generic auth keys used by pyodbc/sqlalchemy/sqlcmd paths.
            # Fallback to BCP_* keeps existing env files working.
            # Name of an ODBC DSN whose Authentication is
            # ActiveDirectoryServicePrincipal. This is the only way to give bcp a
            # client id and secret, verified against Azure SQL; bcp's -G options
            # cannot express service-principal auth. The DSN must be created with
            # the same driver major version as the installed bcp.
            'BCP_DSN': os.getenv('BCP_DSN', ''),
            'CLIENT_ID': os.getenv('CLIENT_ID', ''),
            'CLIENT_SECRET': os.getenv('CLIENT_SECRET', ''),
            # Long-lived copy of the RC_* staging tables, on the same server as
            # DATABASE. Named per environment - the names differ, so every env
            # file sets this rather than relying on the fallback.
            'ARCHIVE_DATABASE': os.getenv('ARCHIVE_DATABASE', DEFAULT_ARCHIVE_DATABASE),
        }
        
        # Retained for compatibility with callers that still inspect USERNAME.
        config['USERNAME'] = ''

        # Validate required fields
        if not config['SERVER']:
            raise ValueError(f"SERVER not found in {env_file}")
        if not config['DATABASE']:
            raise ValueError(f"DATABASE not found in {env_file}")
        # Keyed on the target, not on the environment's name. Adding an env file
        # for a new Azure database used to be insufficient: every branch tested
        # `environment == 'uat'`, so a new name such as testse silently took the
        # trusted-connection path and never used its service principal.
        if self._is_azure_sql(config['SERVER']):
            if not config['CLIENT_ID']:
                raise ValueError(
                    f"CLIENT_ID not found in {env_file}; it is required for the "
                    f"Azure SQL server {config['SERVER']}"
                )
            if not config['CLIENT_SECRET']:
                raise ValueError(
                    f"CLIENT_SECRET not found in {env_file}; it is required for the "
                    f"Azure SQL server {config['SERVER']}"
                )

        return config

    # Hosts that mean "Azure SQL", so authentication follows the target rather
    # than the environment's name. Covers public, China, US Gov and Fabric.
    AZURE_SQL_HOST_SUFFIXES = (
        '.database.windows.net',
        '.database.chinacloudapi.cn',
        '.database.usgovcloudapi.net',
        '.datawarehouse.fabric.microsoft.com',
        '.database.fabric.microsoft.com',
    )

    @classmethod
    def _is_azure_sql(cls, server: str) -> bool:
        """True when this server is Azure SQL, judged by hostname."""
        host = (server or '').strip().lower()
        # Strip any tcp: prefix and ,port suffix before matching.
        if host.startswith('tcp:'):
            host = host[4:]
        host = host.split(',', 1)[0].strip()
        return host.endswith(cls.AZURE_SQL_HOST_SUFFIXES)

    def is_azure(self) -> bool:
        """True when this environment targets Azure SQL."""
        return self._is_azure_sql(self.config.get('SERVER', ''))

    def for_database(self, database: str) -> 'DatabaseHelper':
        """A second helper on the same server, pointed at another database.

        Everything except DATABASE is this environment's own configuration, so
        the sibling authenticates identically - including bcp, which takes
        `-d <database>` from the config rather than from the DSN.

        The returned helper owns its own connections; whoever asks for it is
        responsible for closing it.
        """
        if not database:
            raise ValueError('for_database needs a database name')

        sibling = DatabaseHelper(self.environment, config_path=self.config_path)
        sibling.config['DATABASE'] = database
        return sibling

    def archive_database_helper(self) -> 'DatabaseHelper':
        """Helper for this environment's staging archive database."""
        return self.for_database(
            self.config.get('ARCHIVE_DATABASE') or DEFAULT_ARCHIVE_DATABASE
        )

    def _get_connection_string(self) -> str:
        """Generate connection string based on the target, not the env name."""
        server = self.config['SERVER']
        database = self.config['DATABASE']
        driver = self.config['DRIVER']

        if self.is_azure():
            # Azure SQL: Entra service principal via client id and secret. Never an
            # interactive or integrated flow - those authenticate the operator, so
            # they prompt (blocking unattended runs) and make the audit trail the
            # person rather than the application. _load_config refuses an Azure
            # target with no CLIENT_ID/CLIENT_SECRET, so there is no path back to a
            # user identity here.
            client_id = self.config['CLIENT_ID']
            client_secret = self.config['CLIENT_SECRET']

            conn_str = (
                f"DRIVER={{{driver}}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"UID={client_id};"
                f"PWD={client_secret};"
                "Authentication=ActiveDirectoryServicePrincipal;"
                "Encrypt=yes;"
                # Validate the certificate: Azure SQL presents a publicly trusted
                # one, and these servers were verified to connect with validation
                # on. Trusting any certificate on a public endpoint would leave the
                # connection open to interception.
                "TrustServerCertificate=no;"
            )
        else:
            # On-premises: Windows authentication. Certificates here are typically
            # self-signed, so validation stays off - unlike the Azure branch.
            conn_str = (
                f"DRIVER={{{driver}}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                "Trusted_Connection=yes;"
                "Encrypt=yes;"
                "TrustServerCertificate=yes;"
            )

        return conn_str

    def describe_identity(self) -> str:
        """How this environment authenticates, for the log. Never the secret.

        Logged on connect so a regression to a user identity is visible at a
        glance instead of only surfacing as an interactive prompt on a machine
        where someone happens to be watching.
        """
        if self.is_azure():
            return (f"Entra service principal {self.config.get('CLIENT_ID')} "
                    f"on {self.config.get('SERVER')}")
        return f"Windows authentication on {self.config.get('SERVER')}"
    
    
    def refresh_connection_if_needed(self):
        current_time = time.time()
        if current_time - self.last_activity > self.connection_timeout:
            self.logger.info("Refreshing database connection due to timeout")
            self.close_connections()
            self.connect_sqlalchemy()
            self.connect_pyodbc()
        self.last_activity = current_time

    def connect_pyodbc(self) -> pyodbc.Connection:
        """Establish PyODBC connection with fastexecutemany support."""
        try:
            conn_str = self._get_connection_string()
            self.pyodbc_connection = pyodbc.connect(conn_str)
            
           
            self.pyodbc_connection.setdecoding(pyodbc.SQL_CHAR, encoding='utf-8')
            self.pyodbc_connection.setdecoding(pyodbc.SQL_WCHAR, encoding='utf-8')
            self.pyodbc_connection.setencoding(encoding='utf-8')
            
            self.logger.info(
                f"PyODBC connection established to {self.environment} using "
                f"{self.describe_identity()}"
            )
            return self.pyodbc_connection
            
        except Exception as e:
            self.logger.error(f"Failed to establish PyODBC connection: {str(e)}")
            raise
    
    def connect_sqlalchemy(self) -> Engine:
        """Establish SQLAlchemy engine connection."""
        try:
            conn_str = self._get_connection_string()
            sqlalchemy_conn_str = f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}"

            self.sqlalchemy_engine = create_engine(
                sqlalchemy_conn_str,
                fast_executemany=True,
                echo=False,
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=self.pool_max_overflow,
                pool_timeout=self.pool_timeout,
                pool_recycle=self.pool_recycle,
                pool_pre_ping=True,
            )
            
            # Test connection
            with self.sqlalchemy_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            self.logger.info(
                f"SQLAlchemy engine created for {self.environment} using "
                f"{self.describe_identity()}"
            )
            return self.sqlalchemy_engine
            
        except Exception as e:
            self.logger.error(f"Failed to create SQLAlchemy engine: {str(e)}")
            raise
    
    def _server_side_activity(self) -> Optional[Tuple[int, int]]:
        """Total CPU and reads for sqlcmd sessions in this database.
        """
        query = """
            SELECT ISNULL(SUM(CAST(r.cpu_time AS BIGINT)), 0) AS cpu_ms,
                   ISNULL(SUM(CAST(r.logical_reads AS BIGINT)), 0) AS reads
            FROM sys.dm_exec_requests r
            JOIN sys.dm_exec_sessions s ON s.session_id = r.session_id
            WHERE s.program_name LIKE 'SQLCMD%'
              AND r.database_id = DB_ID()
        """
        connection = None
        try:
            connection = pyodbc.connect(self._get_connection_string(), timeout=15)
            cursor = connection.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
            cursor.close()
            if row is None:
                return None
            return int(row[0] or 0), int(row[1] or 0)
        except Exception as e:
            self.logger.debug(f'server-side activity probe failed: {e}')
            return None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    def _run_sqlcmd_streamed(self, cmd: List[str], idle_timeout_seconds: int,
                             max_total_seconds: Optional[int] = None,
                             progress_callback: Optional[Any] = None,
                             monitor_server: bool = True,
                             poll_seconds: int = 30,
                             ) -> Tuple[bool, str, float]:

        start = time.time()
        lines: List[str] = []
        last_output = time.time()
        last_progress = time.time()
        last_activity: Optional[Tuple[int, int]] = None
        # The probe must run several times within the idle window, or the kill
        # fires before liveness is ever sampled.
        poll_seconds = max(2, min(poll_seconds, idle_timeout_seconds // 3))
        next_poll = time.time() + min(2, poll_seconds)   # sample early for a baseline
        timed_out_reason: Optional[str] = None

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # one ordered stream
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,                  # line buffered
        )

        def pump() -> None:
            nonlocal last_output
            try:
                assert process.stdout is not None
                for raw in process.stdout:
                    line = raw.rstrip('\r\n')
                    last_output = time.time()
                    lines.append(line)
                    if line.strip():
                        self.logger.info(f'  sqlcmd | {line.strip()[:200]}')
                        if progress_callback is not None:
                            try:
                                progress_callback(line)
                            except Exception:
                                pass  # never let telemetry break the load
            except Exception as e:                       # pragma: no cover
                self.logger.debug(f'sqlcmd reader stopped: {e}')

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()

        while True:
            if process.poll() is not None:
                break
            now = time.time()

            if monitor_server and now >= next_poll:
                next_poll = now + poll_seconds
                activity = self._server_side_activity()
                if activity is not None:
                    if last_activity is None or activity != last_activity:
                        last_progress = now
                        cpu_ms, reads = activity
                        self.logger.info(
                            f'  sqlcmd still working after {now - start:.0f}s '
                            f'(server cpu {cpu_ms:,}ms, reads {reads:,})'
                        )
                    last_activity = activity
                else:
                    # Probe failed: unknown is not the same as stuck.
                    last_progress = now

            if now - last_output < now - last_progress:
                last_progress = last_output

            if now - last_progress > idle_timeout_seconds:
                timed_out_reason = (
                    f'no server-side progress or output for {idle_timeout_seconds}s '
                    f'after {now - start:.0f}s; killing sqlcmd'
                )
                break
            if max_total_seconds and now - start > max_total_seconds:
                timed_out_reason = (
                    f'exceeded hard cap of {max_total_seconds}s; killing sqlcmd'
                )
                break
            time.sleep(0.5)

        if timed_out_reason:
            self.logger.error(timed_out_reason)
            try:
                process.kill()
            except Exception:
                pass
            reader.join(timeout=5)
            elapsed = time.time() - start
            return False, '\n'.join(lines + [timed_out_reason]), elapsed

        reader.join(timeout=30)
        returncode = process.wait()
        elapsed = time.time() - start
        return returncode == 0, '\n'.join(lines), elapsed

    def execute_sqlcmd(self, sql_script: str, variables: Dict[str, Any] = None,
                   additional_args: List[str] = None,
                   idle_timeout_seconds: Optional[int] = None,
                   max_total_seconds: Optional[int] = None,
                   progress_callback: Optional[Any] = None) -> Tuple[bool, str]:
        """
        Execute SQL script using sqlcmd with enhanced support for master files and additional arguments.
        """
        try:
            server = self.config['SERVER']
            database = self.config['DATABASE']
            
            # Build base sqlcmd command
            if self.is_azure():
                # Same verified switches bcp uses, so file 76 cannot fail on
                # authentication after the pyodbc files have already run. This
                # used to hard-code -U <client id> -P <secret> -G, which classic
                # sqlcmd maps to ActiveDirectoryPassword: it rejects an app id
                # because that is a user flow, and it put -U ahead of -G, which
                # the sqlcmd docs call out as a cause of login failure on its own.
                # Resolved for sqlcmd specifically: it cannot use bcp's DSN
                # candidate, so its winner may differ or not exist at all. Raising
                # here means a uat run stops up front instead of failing at file 76
                # after the 111 pyodbc files have already committed.
                auth_args = self.cli_auth_args('sqlcmd')
                if auth_args is None:
                    _ready, reason = self.cli_ready('sqlcmd')
                    raise RuntimeError(
                        f'sqlcmd cannot authenticate to {self.environment}: {reason}'
                    )
                cmd = [
                    self.sqlcmd_executable(),
                ] + auth_args + [       # carries -S/-d, and -G before any -U/-P
                    '-I',  # Set QUOTED_IDENTIFIER ON for the SQLCMD session
                    '-l', '30',  # Login timeout
                    '-t', '0'    # Query timeout (0 = no timeout)
                ]
            else:
                cmd = [
                    self.sqlcmd_executable(),
                    '-S', server,
                    '-d', database,
                    '-E',  # Use Windows authentication
                    '-I',  # Set QUOTED_IDENTIFIER ON for the SQLCMD session
                    '-l', '30',  # Login timeout
                    '-t', '0'    # Query timeout (0 = no timeout)
                ]
            
            # Add additional arguments if provided (like -r0 for continue on error)
            if additional_args:
                cmd.extend(additional_args)
                self.logger.debug(f"Added additional SQLCMD args: {additional_args}")
            
            # Add variables if provided
            if variables:
                for key, value in variables.items():
                    cmd.extend(['-v', f'{key}={value}'])
                self.logger.debug(f"Added SQLCMD variables: {list(variables.keys())}")
            
            # Determine if sql_script is a file path or script content
            is_file = False
            if os.path.isfile(sql_script):
                is_file = True
                self.logger.info(f"Executing SQL file: {sql_script}")
                cmd.extend(['-i', sql_script])
                input_data = None
            else:
                # Check if it looks like a file path but doesn't exist
                if (sql_script.endswith('.sql') or '\\' in sql_script or '/' in sql_script) and not os.path.isfile(sql_script):
                    self.logger.warning(f"SQL script appears to be a file path but file not found: {sql_script}")
                    return False, f"SQL file not found: {sql_script}"
                
                self.logger.info("Executing SQL content directly")
                cmd.extend(['-Q', sql_script])
                input_data = None
            
            # Log the command (without sensitive info)
            cmd_display = []
            hide_next = False
            for arg in cmd:
                if hide_next:
                    cmd_display.append('***')
                    hide_next = False
                    continue
                if arg.upper() == '-P':
                    cmd_display.append(arg)
                    hide_next = True
                    continue
                if any(sensitive in arg.lower() for sensitive in ['password', 'pwd', 'client_secret', 'secret']):
                    cmd_display.append('***')
                else:
                    cmd_display.append(arg)
            self.logger.debug(f"SQLCMD command: {' '.join(cmd_display)}")
            

            if idle_timeout_seconds is None:
                idle_timeout_seconds = self.sqlcmd_idle_timeout if is_file else 300
            if max_total_seconds is None:
                max_total_seconds = self.sqlcmd_max_total if is_file else 600

            self.logger.info(
                f"Starting SQLCMD execution (idle timeout: {idle_timeout_seconds}s"
                + (f", hard cap: {max_total_seconds}s)..." if max_total_seconds
                   else ", no hard cap)...")
            )
            start_time = time.time()

            success, output, execution_time = self._run_sqlcmd_streamed(
                cmd,
                idle_timeout_seconds=idle_timeout_seconds,
                max_total_seconds=max_total_seconds,
                progress_callback=progress_callback,
            )
            end_time = start_time + execution_time
            
            # Enhanced logging and output parsing
            if success:
                self.logger.info(f"SQLCMD execution completed successfully in {execution_time:.2f}s")
                
                # Try to extract useful information from output
                if output:
                    # Count rows affected mentions
                    rows_mentions = len([line for line in output.split('\n') if 'rows affected' in line.lower()])
                    # if rows_mentions > 0:
                    #     self.logger.info(f"Found {rows_mentions} 'rows affected' mentions in output")
                    
                    # # Check for completion indicators
                    # if 'MASTER_EXECUTION_COMPLETE' in output:
                    #     self.logger.info("✓ Master execution completion confirmed in output")
                    
                    # Log any error messages even in successful execution
                    error_lines = [line.strip() for line in output.split('\n') 
                                if any(keyword in line.lower() for keyword in ['error', 'failed', 'exception'])
                                and 'error: 0' not in line.lower()]
                    
                    if error_lines:
                        self.logger.warning(f"Potential issues found in output:")
                        for error_line in error_lines[:5]:  # Show first 5 error lines
                            self.logger.warning(f"  {error_line}")
            else:
                self.logger.error(f"SQLCMD execution failed in {execution_time:.2f}s")
                self.logger.error(f"Error output: {output[:500]}...")  # First 500 chars of error
                
                # Try to identify common error types
                if output:
                    if 'login failed' in output.lower():
                        self.logger.error("Authentication failure detected")
                    elif 'incorrect syntax' in output.lower():
                        self.logger.error("SQL syntax error detected")
                    elif 'cannot open' in output.lower() and 'file' in output.lower():
                        self.logger.error("File access error detected")
                    elif 'timeout' in output.lower():
                        self.logger.error("Timeout error detected")
            
            return success, output
            
        except subprocess.TimeoutExpired as e:
            error_msg = f"SQLCMD execution timed out: {e}"
            self.logger.error(error_msg)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"SQLCMD execution error: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
        
    def execute_sqlcmd_with_retry(self, sql_script: str, variables: Dict[str, Any] = None,
                                additional_args: List[str] = None, max_retries: int = 3) -> Tuple[bool, str]:
        """
        Execute SQLCMD with retry logic for transient failures.
        """
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info(f"SQLCMD execution attempt {attempt}/{max_retries}")
                
                success, output = self.execute_sqlcmd(sql_script, variables, additional_args)
                
                if success:
                    if attempt > 1:
                        self.logger.info(f"SQLCMD succeeded on attempt {attempt}")
                    return success, output
                else:
                    last_error = output
                    
                    # Check if this is a retryable error
                    retryable_errors = [
                        'timeout', 'connection', 'network', 'transient',
                        'deadlock', 'lock timeout', 'server is not available'
                    ]
                    
                    is_retryable = any(error_type in output.lower() for error_type in retryable_errors)
                    
                    if not is_retryable or attempt == max_retries:
                        self.logger.error(f"SQLCMD failed (attempt {attempt}): {output[:200]}...")
                        if not is_retryable:
                            self.logger.error("Error is not retryable, aborting")
                        break
                    else:
                        wait_time = attempt * 2  # Exponential backoff
                        self.logger.warning(f"Retryable error on attempt {attempt}, waiting {wait_time}s before retry")
                        time.sleep(wait_time)
                        
            except Exception as e:
                last_error = str(e)
                self.logger.error(f"SQLCMD attempt {attempt} failed with exception: {e}")
                
                if attempt < max_retries:
                    wait_time = attempt * 2
                    self.logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
        
        return False, last_error or "All retry attempts failed"
    
    def execute_query(self, query: str, params: Dict[str, Any] = None) -> pd.DataFrame:
        """Execute SELECT query and return results as DataFrame."""
        try:
            if self.sqlalchemy_engine is None:
                self.connect_sqlalchemy()
            
            with self.sqlalchemy_engine.connect() as conn:
                if params:
                    result = pd.read_sql(text(query), conn, params=params)
                else:
                    result = pd.read_sql(text(query), conn)
            
            self.last_activity = time.time()
            #self.logger.info(f"Query executed successfully, returned {len(result)} rows")
            return result
            

        except Exception as e:
            self.logger.error(f"Query execution failed: {str(e)}")
            raise


    def execute_non_query(self, query: str, params: Dict[str, Any] = None) -> int:
        """Execute INSERT/UPDATE/DELETE query and return affected rows."""
        try:
            if self.pyodbc_connection is None:
                self.connect_pyodbc()
            
            cursor = self.pyodbc_connection.cursor()
            cursor.fast_executemany = True
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            affected_rows = cursor.rowcount
            self.pyodbc_connection.commit()
            cursor.close()

            self.last_activity = time.time()
            #self.logger.info(f"Non-query executed successfully, {affected_rows} rows affected")
            return affected_rows
            
        except Exception as e:
            self.logger.error(f"Non-query execution failed: {str(e)}")
            if self.pyodbc_connection:
                self.pyodbc_connection.rollback()
            raise

    def bulk_insert(self, data: pd.DataFrame, table_name: str, schema: str = 'dbo', 
                   if_exists: str = 'append', method: str = 'multi') -> None:
        """
        Bulk insert DataFrame to database table.
        """
        try:
            if self.sqlalchemy_engine is None:
                self.connect_sqlalchemy()
            
            data.to_sql(
                name=table_name,
                con=self.sqlalchemy_engine,
                schema=schema,
                if_exists=if_exists,
                index=False,
                method=method
            )
            
            self.logger.info(f"Bulk insert completed: {len(data)} rows inserted into {schema}.{table_name}")
            
        except Exception as e:
            self.logger.error(f"Bulk insert failed: {str(e)}")
            raise

    # ------------------------------------------------------------------
    # Load sizing and transient-fault helpers
    # ------------------------------------------------------------------

    def get_declared_column_widths(self, table_name: str, schema: str = 'dbo') -> Dict[str, Optional[int]]:
        """Map column name -> declared character length (None for non-text/max)."""
        cache_key = (schema.lower(), table_name.lower())
        cached = self._column_width_cache.get(cache_key)
        if cached is not None:
            return cached

        if self.sqlalchemy_engine is None:
            self.connect_sqlalchemy()

        widths: Dict[str, Optional[int]] = {}
        try:
            for col in inspect(self.sqlalchemy_engine).get_columns(table_name, schema=schema):
                length = getattr(col.get('type'), 'length', None)
                widths[str(col['name'])] = length
        except Exception as e:
            self.logger.warning(f'Could not read declared widths for {schema}.{table_name}: {e}')
        self._column_width_cache[cache_key] = widths
        return widths

    # Fractional-second scale of the columns declared with one. Read from the
    # catalog because SQLAlchemy's mssql reflection does not carry it: a
    # datetime2(3) column comes back as DATETIME2() with precision None, which
    # is indistinguishable from datetime2(7) and four digits too generous for
    # the character literal bcp has to write.
    _DATETIME_SCALE_QUERY = """
    SELECT c.name  AS column_name,
           c.scale AS scale_value
    FROM sys.columns c
    JOIN sys.types ty
      ON ty.user_type_id = c.user_type_id
    WHERE c.object_id = OBJECT_ID(:qualified_name)
      AND ty.name IN ('datetime2', 'time', 'datetimeoffset')
    """

    def get_datetime_scales(self, table_name: str,
                            schema: str = 'dbo') -> Dict[str, int]:
        """Map column name -> declared fractional-second digits, lowercased."""
        cache_key = (schema.lower(), table_name.lower())
        cached = self._datetime_scale_cache.get(cache_key)
        if cached is not None:
            return cached

        scales: Dict[str, int] = {}
        try:
            frame = self.execute_query(
                self._DATETIME_SCALE_QUERY,
                params={'qualified_name': f'{schema}.{table_name}'},
            )
            for _, row in frame.iterrows():
                scales[str(row['column_name']).lower()] = int(row['scale_value'])
        except Exception as e:
            self.logger.warning(
                f'Could not read datetime scales for {schema}.{table_name}: {e}. '
                f'bcp will write full microsecond precision, which a column '
                f'declared with fewer digits rejects as "Invalid time format".')
        self._datetime_scale_cache[cache_key] = scales
        return scales

    def estimate_row_bytes(self, table_name: str, schema: str = 'dbo',
                           columns: Optional[Iterable[str]] = None) -> int:
        """Estimate the client-side buffer cost of one bound row, in bytes.

        Uses *declared* widths because that is what fast_executemany allocates.
        """
        widths = self.get_declared_column_widths(table_name, schema=schema)
        if not widths:
            return 0  # unknown; caller falls back to a row-count cap

        names = list(columns) if columns is not None else list(widths)
        total = 0
        for name in names:
            if name in widths:
                length = widths[name]
            else:  # case-insensitive fallback
                length = next((w for n, w in widths.items() if n.lower() == str(name).lower()), None)
                if length is None and not any(n.lower() == str(name).lower() for n in widths):
                    total += _NON_TEXT_COLUMN_BYTES
                    continue
            if length is None:
                # Non-text, or nvarchar(max) which reports no length.
                total += _NON_TEXT_COLUMN_BYTES
            elif length < 0:
                total += NVARCHAR_MAX_ESTIMATE_CHARS * _BYTES_PER_CHAR + _PER_COLUMN_OVERHEAD
            else:
                total += length * _BYTES_PER_CHAR + _PER_COLUMN_OVERHEAD
        return total

    def calculate_batch_rows(self, table_name: str, schema: str = 'dbo',
                             columns: Optional[Iterable[str]] = None,
                             max_batch_bytes: int = DEFAULT_MAX_BATCH_BYTES) -> int:
        """Rows per batch such that the bound buffer stays under max_batch_bytes."""
        row_bytes = self.estimate_row_bytes(table_name, schema=schema, columns=columns)
        if row_bytes <= 0:
            return MAX_BATCH_ROWS
        rows = max_batch_bytes // row_bytes
        return max(MIN_BATCH_ROWS, min(MAX_BATCH_ROWS, int(rows)))

    @staticmethod
    def is_transient_error(exc: BaseException) -> bool:
        """True if exc looks like an Azure SQL transient fault worth retrying."""
        seen = []
        cur: Optional[BaseException] = exc
        while cur is not None and cur not in seen:
            seen.append(cur)
            for arg in getattr(cur, 'args', ()) or ():
                if isinstance(arg, int) and arg in TRANSIENT_ERROR_CODES:
                    return True
                if isinstance(arg, str):
                    if arg.strip().upper() in TRANSIENT_SQLSTATES:
                        return True
            text_repr = str(cur).lower()
            if any(tok in text_repr for tok in TRANSIENT_MESSAGE_TOKENS):
                return True
            for match in re.findall(r'\d{4,5}', text_repr):
                if int(match) in TRANSIENT_ERROR_CODES:
                    return True
            cur = getattr(cur, 'orig', None) or cur.__cause__
        return False

    def _run_with_retry(self, operation, description: str,
                        max_attempts: int = DEFAULT_RETRY_ATTEMPTS):
        """Run operation(), retrying transient faults with exponential backoff."""
        for attempt in range(1, max_attempts + 1):
            try:
                return operation()
            except MemoryError:
                raise
            except Exception as e:
                if attempt >= max_attempts or not self.is_transient_error(e):
                    raise
                wait = min(2 ** (attempt - 1), 30)
                self.logger.warning(
                    f'{description}: transient {type(e).__name__} on attempt '
                    f'{attempt}/{max_attempts}, retrying in {wait}s: {str(e)[:200]}'
                )
                time.sleep(wait)
                try:  # a dropped pool connection must not poison the retry
                    if self.sqlalchemy_engine is not None:
                        self.sqlalchemy_engine.dispose()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Inserts
    # ------------------------------------------------------------------

    def _get_reflected_table(self, table_name: str, schema: str = 'dbo') -> Table:
        """Reflect a table once and cache it, so the INSERT compiles once."""
        key = (schema.lower(), table_name.lower())
        table = self._reflected_table_cache.get(key)
        if table is None:
            if self.sqlalchemy_engine is None:
                self.connect_sqlalchemy()
            table = Table(table_name, MetaData(), schema=schema,
                          autoload_with=self.sqlalchemy_engine)
            self._reflected_table_cache[key] = table
        return table

    def _align_frame_to_table(self, frame: pd.DataFrame, table: Table,
                              table_name: str) -> Tuple[List[str], List[Any]]:
        """Match frame columns to table columns case-insensitively.
        """
        table_by_lower = {c.name.lower(): c.name for c in table.columns}
        target_names: List[str] = []
        frame_cols: List[Any] = []
        unmatched: List[str] = []
        for col in frame.columns:
            actual = table_by_lower.get(str(col).lower())
            if actual is None:
                unmatched.append(str(col))
                continue
            target_names.append(actual)
            frame_cols.append(col)
        if unmatched:
            self.logger.warning(
                f'{table_name}: {len(unmatched)} frame column(s) not in the table, '
                f'skipped: {unmatched[:10]}{"..." if len(unmatched) > 10 else ""}'
            )
        return target_names, frame_cols

    def bulk_insert_frame(self, frame: pd.DataFrame, table_name: str, schema: str = 'dbo') -> Tuple[bool, int]:
        """Single entry point for dataframe inserts used by the migration flow."""
        return self.bulk_insert_chunked(frame, table_name, schema=schema)

    # ------------------------------------------------------------------
    # bcp sink
    # ------------------------------------------------------------------

    def bcp_available(self) -> bool:
        """True if the bcp utility can be invoked."""
        if self._bcp_available is None:
            try:
                result = subprocess.run(['bcp', '-v'], capture_output=True, text=True,
                                        timeout=30)
                self._bcp_available = result.returncode == 0 or 'bcp' in (
                    result.stdout or ''
                ).lower()
                if self._bcp_available:
                    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
                    match = re.search(r'Version:\s*(\d+)', combined, re.IGNORECASE)
                    if match:
                        self._bcp_version_major = int(match.group(1))
            except Exception as e:
                self.logger.debug(f'bcp not available: {e}')
                self._bcp_available = False
        return bool(self._bcp_available)

    # Known install locations for go-sqlcmd, which unlike classic sqlcmd supports
    # --authentication-method ActiveDirectoryServicePrincipal.
    GO_SQLCMD_PATHS = (
        r'C:\Program Files\sqlcmd\sqlcmd.exe',
        r'C:\Program Files (x86)\sqlcmd\sqlcmd.exe',
    )

    def sqlcmd_executable(self) -> str:
        """Path to the sqlcmd to invoke, preferring go-sqlcmd when installed.

        Resolved explicitly rather than relying on PATH: installing go-sqlcmd does
        NOT displace the classic one, which ships with the ODBC tools and usually
        wins the PATH order. Verified on this machine - bare `sqlcmd` resolved to
        the ODBC 17 build even with go-sqlcmd present, which is why the service
        principal kept failing.

        Override with SQLCMD_PATH if a specific binary is wanted.
        """
        if self._sqlcmd_path is not None:
            return self._sqlcmd_path

        override = (os.getenv('SQLCMD_PATH') or '').strip()
        if override and os.path.exists(override):
            self._sqlcmd_path = override
        else:
            self._sqlcmd_path = next(
                (p for p in self.GO_SQLCMD_PATHS if os.path.exists(p)), 'sqlcmd')

        if self._sqlcmd_path != 'sqlcmd':
            self.logger.debug(f'sqlcmd resolved to {self._sqlcmd_path}')
        return self._sqlcmd_path

    def sqlcmd_is_go(self) -> bool:
        """True when the resolved sqlcmd is go-sqlcmd rather than the ODBC build.

        Distinguished by --version: go-sqlcmd prints a semantic version, classic
        sqlcmd rejects the flag outright.
        """
        if self._sqlcmd_is_go is not None:
            return self._sqlcmd_is_go
        try:
            result = subprocess.run([self.sqlcmd_executable(), '--version'],
                                    capture_output=True, text=True, timeout=30)
            self._sqlcmd_is_go = bool(
                re.search(r'\bv?\d+\.\d+\.\d+', result.stdout or '')
                and 'Sqlcmd: Error' not in (result.stdout or ''))
        except Exception as e:                                   # noqa: BLE001
            self.logger.debug(f'could not determine sqlcmd variant: {e}')
            self._sqlcmd_is_go = False
        return bool(self._sqlcmd_is_go)

    @staticmethod
    def dsn_server(dsn: str) -> Optional[str]:
        """The Server a DSN points at, or None if it cannot be read.

        Needed because a DSN carries its own server. A config referencing the
        wrong DSN sends bcp to a different database than every other client in the
        same run - testse.env initially pointed at the uat DSN, which would have
        loaded test data into the dev database with nothing to flag it.
        """
        try:
            import winreg
        except ImportError:
            return None
        for root, path in ((winreg.HKEY_CURRENT_USER, r'Software\ODBC\ODBC.INI'),
                           (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\ODBC\ODBC.INI')):
            try:
                with winreg.OpenKey(root, f'{path}\\{dsn}') as key:
                    return str(winreg.QueryValueEx(key, 'Server')[0])
            except OSError:
                continue
        return None

    def _dsn_targets_this_server(self, dsn: str) -> bool:
        """Whether the DSN's server matches this environment's SERVER."""
        actual = self.dsn_server(dsn)
        if actual is None:
            self.logger.warning(
                f'Could not read the Server of DSN {dsn!r}; using it unverified')
            return True

        def norm(host: str) -> str:
            host = (host or '').strip().lower()
            if host.startswith('tcp:'):
                host = host[4:]
            return host.split(',', 1)[0].strip()

        expected = norm(self.config.get('SERVER', ''))
        if norm(actual) == expected:
            return True
        self.logger.error(
            f'DSN {dsn!r} points at {actual!r} but this environment '
            f'({self.environment}) targets {self.config.get("SERVER")!r}. '
            f'Refusing to use it, so bcp cannot load into the wrong database.'
        )
        return False

    def _cli_auth_candidates(self, tool: str) -> List[Tuple[str, List[str]]]:
        """Ordered (name, args) connection candidates for one CLI tool.

        Args carry the whole connection, `-S`/`-D`/`-d` included, because the
        candidates differ in shape and not only in credentials.

        bcp and classic sqlcmd do NOT have the same authentication support, which
        is why this takes a tool. Measured against Azure SQL with an Entra app
        registration:

            bcp   -D -S <dsn>   with a DSN whose Authentication is
                                ActiveDirectoryServicePrincipal          WORKS
            bcp   -G -U -P      resolves to ActiveDirectoryPassword,
                                which rejects an app id                 FA004
            bcp   -G            integrated, needs a federated tenant    HY000
            sqlcmd              has no -D, so no service-principal path at all

        So a DSN is the only way to give bcp a client id and secret. Classic
        sqlcmd cannot use one; it needs a SQL login, go-sqlcmd, or for its work to
        move onto pyodbc.
        """
        server = self.config['SERVER']
        database = self.config['DATABASE']
        client_id = self.config.get('CLIENT_ID', '')
        secret = self.config.get('CLIENT_SECRET', '')
        dsn = self.config.get('BCP_DSN', '')
        sql_login = os.getenv('BCP_USERNAME', '')
        mode = (os.getenv('BCP_AUTH') or '').strip().lower()

        target = ['-S', server, '-d', database]
        via_dsn = ['-D', '-S', dsn, '-d', database]

        def named(name: str) -> List[Tuple[str, List[str]]]:
            """One explicitly requested candidate, or none if unusable here."""
            if name in ('dsn', 'dsn-service-principal'):
                if tool != 'bcp':
                    self.logger.warning(
                        f'BCP_AUTH={name} applies to bcp only; {tool} has no -D')
                    return []
                if dsn and client_id and secret:
                    return [('dsn-service-principal',
                             via_dsn + ['-U', client_id, '-P', secret])]
                self.logger.warning(
                    'BCP_AUTH=dsn needs BCP_DSN, CLIENT_ID and CLIENT_SECRET')
                return []
            if name in ('service-principal', 'entra-service-principal'):
                if client_id and secret:
                    return [('service-principal',
                             target + ['-G', '-U', client_id, '-P', secret])]
                return []
            if name in ('integrated', 'entra-integrated', 'managed-identity'):
                return [('entra-integrated', target + ['-G'])]
            if name == 'sql':
                login = sql_login or client_id
                if login and secret:
                    return [('sql', target + ['-U', login, '-P', secret])]
                self.logger.warning(
                    'BCP_AUTH=sql needs BCP_USERNAME (or CLIENT_ID) and CLIENT_SECRET')
                return []
            if name == 'trusted':
                return [('trusted', target + (['-T'] if tool == 'bcp' else ['-E']))]
            self.logger.warning(f'Unrecognised BCP_AUTH mode {name!r}; ignoring it')
            return []

        if mode:
            return named(mode)

        # Not Azure: a trusted connection is already silent. bcp spells it -T,
        # sqlcmd spells it -E.
        if not self.is_azure():
            return [('trusted', target + (['-T'] if tool == 'bcp' else ['-E']))]

        candidates: List[Tuple[str, List[str]]] = []
        # The DSN first: it is the only candidate that carries the service
        # principal all the way through for bcp.
        if (tool == 'bcp' and dsn and client_id and secret
                and self._dsn_targets_this_server(dsn)):
            candidates.append(('dsn-service-principal',
                               via_dsn + ['-U', client_id, '-P', secret]))
        # go-sqlcmd is the only sqlcmd that can use a service principal, via
        # --authentication-method. The secret goes in SQLCMDPASSWORD rather than
        # -P so it stays out of the process command line; it is already in this
        # process's environment, so this exposes nothing new. Verified against
        # Azure SQL, and QUOTED_IDENTIFIER/ANSI_NULLS are ON by default there, so
        # the filtered index on tblWorkflowLineAudit needs no -I.
        if tool == 'sqlcmd' and client_id and secret and self.sqlcmd_is_go():
            os.environ['SQLCMDPASSWORD'] = secret
            candidates.append((
                'go-service-principal',
                target + ['--authentication-method',
                          'ActiveDirectoryServicePrincipal', '-U', client_id],
            ))
        if sql_login and secret:
            candidates.append(('sql', target + ['-U', sql_login, '-P', secret]))
        if client_id and secret:
            candidates.append(('service-principal',
                               target + ['-G', '-U', client_id, '-P', secret]))
        # -G must precede -U; the sqlcmd docs note the reverse order can fail.
        candidates.append(('entra-integrated', target + ['-G']))
        return candidates

    def _probe_command(self, tool: str, args: List[str], out_path: str) -> List[str]:
        """A minimal command that connects and authenticates, touching no data."""
        if tool == 'bcp':
            return ['bcp', 'SELECT 1', 'queryout', out_path, '-c',
                    '-l', '15'] + args
        return [self.sqlcmd_executable(), '-Q', 'SELECT 1', '-l', '15'] + args

    def _probe_cli_auth(self, tool: str) -> Optional[Tuple[str, List[str]]]:
        """First candidate that actually logs in, cached per tool for the run.

        bcp is spawned once per table and sqlcmd once per file, so an auth problem
        would otherwise surface dozens of times. Probing up front turns it into one
        decision, and each tool is probed with its own binary so the answer is true
        for that tool rather than inferred from the other.
        """
        if tool in self._cli_auth_resolved:
            return self._cli_auth_winner.get(tool)

        self._cli_auth_resolved.add(tool)
        self._cli_auth_attempts[tool] = []

        if tool == 'bcp' and not self.bcp_available():
            self._cli_auth_error[tool] = 'the bcp utility is not on PATH'
            return None

        candidates = self._cli_auth_candidates(tool)
        if not candidates:
            self._cli_auth_error[tool] = (
                f'no non-interactive credential is configured for {self.environment}')
            return None

        for name, args in candidates:
            work_dir = tempfile.mkdtemp(prefix='rcscliauth_')
            out_path = os.path.join(work_dir, 'probe.dat')
            try:
                result = subprocess.run(
                    self._probe_command(tool, args, out_path),
                    capture_output=True, text=True, encoding='utf-8',
                    errors='replace', timeout=120,
                )
                if result.returncode == 0:
                    self._cli_auth_winner[tool] = (name, args)
                    self.logger.info(
                        f'{tool} authentication for {self.environment}: {name} '
                        f'(verified by a login probe)')
                    return self._cli_auth_winner[tool]
                # stdout/stderr carry SQLState and the driver message, never the
                # command, so this cannot leak the secret.
                detail = ' '.join(
                    f'{result.stdout or ""} {result.stderr or ""}'.split())[:300]
            except Exception as e:                              # noqa: BLE001
                detail = str(e)
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)

            self._cli_auth_attempts[tool].append((name, detail))
            self.logger.debug(f'{tool} candidate {name} failed: {detail}')

        self._cli_auth_error[tool] = '; '.join(
            f'{n}: {d}' for n, d in self._cli_auth_attempts[tool])
        return None

    def cli_auth_args(self, tool: str = 'bcp') -> Optional[List[str]]:
        """Verified connection and auth switches for one CLI tool."""
        winner = self._probe_cli_auth(tool)
        return list(winner[1]) if winner else None

    def bcp_auth_args(self) -> Optional[List[str]]:
        """Verified connection and auth switches for bcp."""
        return self.cli_auth_args('bcp')

    def cli_ready(self, tool: str = 'bcp') -> Tuple[bool, str]:
        """(usable, reason). reason is empty when the tool can connect silently."""
        if tool == 'bcp' and not self.bcp_available():
            return False, 'the bcp utility is not on PATH'
        if self._probe_cli_auth(tool) is not None:
            return True, ''

        attempts = self._cli_auth_attempts.get(tool) or []
        error = self._cli_auth_error.get(tool, 'no candidate was usable')
        if not attempts:
            return False, (
                f'{error}. {tool} runs as a separate process, so interactive Entra '
                f'auth would mean one login per table or file. Set CLIENT_ID and '
                f'CLIENT_SECRET in config/{self.environment}.env, plus BCP_DSN for '
                f'bcp, or BCP_AUTH=sql with BCP_USERNAME for a SQL login')

        hints = []
        if any('FA004' in d or 'ActiveDirectoryPassword' in d for _, d in attempts):
            hints.append(
                '-G -U -P resolves to ActiveDirectoryPassword, which expects a user '
                'rather than an app id.')
        if any(n == 'entra-integrated' and ('HY000' in d or 'unknown error' in d)
               for n, d in attempts):
            hints.append(
                'Integrated auth returned no detail, which is what happens when the '
                'tenant is cloud-managed rather than federated.')
        if tool == 'bcp' and not self.config.get('BCP_DSN'):
            hints.append(
                'bcp CAN use the service principal, but only through a DSN: create '
                'one whose Authentication is ActiveDirectoryServicePrincipal, with '
                'the same driver major version as bcp, then set BCP_DSN to its name.')
        if tool != 'bcp':
            hints.append(
                'Classic sqlcmd has no -D, so it cannot use a DSN and has no '
                'service-principal option. It needs a SQL login, go-sqlcmd, or for '
                'this work to run through pyodbc instead.')

        tried = ', '.join(n for n, _ in attempts)
        return False, (
            f'no {tool} login succeeded for {self.environment} (tried {tried}). '
            f'{error}. ' + ' '.join(hints))

    def bcp_ready(self) -> Tuple[bool, str]:
        """(usable, reason) for the bcp sink."""
        return self.cli_ready('bcp')

    @staticmethod
    def _format_bcp_value(value: Any) -> str:
        """Render one value for bcp character mode.

        Dates are emitted as unambiguous ISO-8601 so the server's DATEFORMAT
        cannot swap day and month — the worst failure mode for a financial
        migration, because it is silent.
        """
        if value is None:
            return ''
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return '1' if value else '0'
        try:
            if pd.isna(value):
                return ''
        except (TypeError, ValueError):
            pass
        if isinstance(value, (pd.Timestamp, datetime)):

            if getattr(value, 'microsecond', 0):
                return value.strftime('%Y%m%d %H:%M:%S.%f')[:26]
            return value.strftime('%Y%m%d %H:%M:%S')
        if isinstance(value, date):

            return value.strftime('%Y-%m-%d')
        if isinstance(value, (int, np.integer)):
            return str(int(value))
        if isinstance(value, (float, np.floating)):

            return np.format_float_positional(float(value), trim='-')
        if isinstance(value, Decimal):
            return format(value, 'f')
        if isinstance(value, (bytes, bytearray)):
            return value.decode('utf-8', errors='replace')
        return str(value)

    # Fractional-second digits each SQL Server date/time type accepts, for the
    # ones that do not carry their own precision.
    _FIXED_FRACTIONAL_DIGITS = {
        'SMALLDATETIME': 0,     # minute resolution
        'DATETIME': 3,
        'TIMESTAMP': 3,         # the SQLAlchemy generic, reflected as datetime
    }
    # A DATE column takes no time part at all, whatever the value carries.
    _DATE_ONLY_TYPES = ('DATE',)
    # ...and the ones declared as TYPE(n), where n is that many digits.
    _SCALED_DATETIME_TYPES = ('DATETIME2', 'TIME', 'DATETIMEOFFSET')

    @staticmethod
    def _is_missing(value: Any) -> bool:
        """True for None, NaN and NaT - anything that should be written NULL."""
        if value is None:
            return True
        try:
            return bool(pd.isna(value))
        except (TypeError, ValueError):
            return False

    @classmethod
    def _fractional_digits(cls, column: Any,
                           catalog_scales: Optional[Dict[str, int]] = None
                           ) -> Optional[int]:
        """Fractional-second digits this column accepts, or None if not a time.

        bcp's character mode hands the literal to the driver, which parses it
        against the column's declared scale and rejects anything longer -
        SQLState 22008, "Invalid time format" - rather than rounding the way
        T-SQL CONVERT would. So the value has to be rendered to fit the column
        before it is written: microsecond precision into a DATETIME2(3) is a
        rejected row, not a rounded one.

        The scale comes from the catalog (get_datetime_scales) because
        reflection loses it; the reflected precision is the fallback, and 7 -
        the type's own default, more than a Python datetime can carry - is the
        fallback for that.
        """
        column_type = getattr(column, 'type', None)
        if column_type is None:
            return None
        name = type(column_type).__name__.upper()
        if name in cls._SCALED_DATETIME_TYPES:
            declared = (catalog_scales or {}).get(str(column.name).lower())
            if declared is not None:
                return int(declared)
            precision = getattr(column_type, 'precision', None)
            return 7 if precision is None else int(precision)
        return cls._FIXED_FRACTIONAL_DIGITS.get(name)

    @staticmethod
    def _format_bcp_datetime(value: Any, digits: int, time_only: bool = False) -> str:
        """Render a datetime with at most `digits` fractional-second digits.

        Rounded half-up rather than truncated, so a value one microsecond short
        of the next millisecond does not lose it, and carrying past .999999
        moves the second along.

        time_only drops the date, for a TIME column - which will not take a
        literal carrying one.
        """
        microsecond = getattr(value, 'microsecond', 0)
        fraction = 0

        if digits <= 0:
            if microsecond >= 500000:
                value = value + timedelta(seconds=1)
        elif digits < 6:
            unit = 10 ** (6 - digits)
            fraction = (microsecond + unit // 2) // unit
            if fraction * unit >= 1000000:
                value = value + timedelta(seconds=1)
                fraction = 0
        else:
            fraction = microsecond
            digits = 6

        base = value.strftime('%H:%M:%S' if time_only else '%Y%m%d %H:%M:%S')
        if fraction:
            base = f'{base}.{fraction:0{digits}d}'

        # DATETIMEOFFSET: keep the offset the value carries. Dropping it would
        # silently re-point the instant at the server's own offset.
        if not time_only and getattr(value, 'tzinfo', None) is not None:
            offset = value.strftime('%z')
            if offset:
                base = f'{base} {offset[:3]}:{offset[3:]}'
        return base

    def _build_bcp_formatters(self, table: Table, column_order: List[str],
                              stats: Optional[Dict[str, int]] = None,
                              datetime_scales: Optional[Dict[str, int]] = None
                              ) -> List[Any]:
        """One value formatter per column, aware of decimal and datetime scale.
        """
        counters = stats if stats is not None else {}
        if datetime_scales is None:
            datetime_scales = self.get_datetime_scales(table.name,
                                                       table.schema or 'dbo')
        by_name = {c.name: c for c in table.columns}
        formatters: List[Any] = []
        for name in column_order:
            column = by_name.get(name)

            # NaT is an instance of datetime, so every date branch has to let
            # the general formatter answer for it - it is a NULL, not a time.
            type_name = type(getattr(column, 'type', None)).__name__.upper()
            if type_name in self._DATE_ONLY_TYPES:
                def fmt_date(value):
                    if (isinstance(value, (pd.Timestamp, datetime))
                            and not self._is_missing(value)):
                        return value.strftime('%Y-%m-%d')
                    return self._format_bcp_value(value)
                formatters.append(fmt_date)
                continue

            digits = self._fractional_digits(column, datetime_scales)
            if digits is not None:
                time_only = type_name == 'TIME'

                def fmt_datetime(value, _digits=digits, _time_only=time_only):
                    if (isinstance(value, (pd.Timestamp, datetime))
                            and not self._is_missing(value)):
                        return self._format_bcp_datetime(value, _digits, _time_only)
                    if _time_only and isinstance(value, dt_time):
                        return self._format_bcp_datetime(
                            datetime.combine(date(1900, 1, 1), value),
                            _digits, True)
                    return self._format_bcp_value(value)
                formatters.append(fmt_datetime)
                continue

            scale = getattr(getattr(column, 'type', None), 'scale', None)
            if isinstance(scale, int) and scale >= 0:
                quantum = Decimal(1).scaleb(-scale)

                def fmt(value, _quantum=quantum, _scale=scale):
                    if isinstance(value, (float, np.floating, Decimal)):
                        try:
                            if pd.isna(value):
                                return ''
                        except (TypeError, ValueError):
                            pass
                        try:

                            exact = value if isinstance(value, Decimal) else Decimal(str(value))
                            if -exact.as_tuple().exponent > _scale:
                                counters['rescaled'] = counters.get('rescaled', 0) + 1
                            return format(exact.quantize(_quantum, rounding=ROUND_HALF_UP), 'f')
                        except (InvalidOperation, ValueError):
                            return self._format_bcp_value(value)
                    return self._format_bcp_value(value)
                formatters.append(fmt)
            else:
                formatters.append(self._format_bcp_value)
        return formatters

    def _write_bcp_file(self, chunks: Iterable[pd.DataFrame], path: str,
                        column_order: List[str], formatters: List[Any],
                        table_name: str) -> Tuple[int, int]:
        """Write chunks to a bcp data file. Returns (rows, sanitised cells)."""
        rows = 0
        sanitised = 0
        field_term = BCP_FIELD_TERMINATOR
        row_term = BCP_ROW_TERMINATOR

        with open(path, 'w', encoding='utf-8', newline='') as handle:
            for chunk in chunks:
                if chunk is None or chunk.empty:
                    continue
                lines = []
                for record in chunk.itertuples(index=False, name=None):
                    fields = []
                    for fmt, value in zip(formatters, record):
                        rendered = fmt(value)
                        if field_term in rendered or row_term in rendered:
                            rendered = (rendered.replace(field_term, ' ')
                                                .replace(row_term, ' '))
                            sanitised += 1
                        fields.append(rendered)
                    lines.append(field_term.join(fields))
                handle.write(row_term.join(lines))
                handle.write(row_term)
                rows += len(chunk)

        if sanitised:
            self.logger.warning(
                f'{table_name}: replaced control characters in {sanitised} cell(s) '
                f'that collided with bcp terminators'
            )
        return rows, sanitised

    def bulk_insert_via_bcp(self, chunks: Any, table_name: str, schema: str = 'dbo',
                            batch_size: int = BCP_BATCH_SIZE,
                            temp_dir: Optional[str] = None,
                            keep_temp: bool = False) -> Tuple[bool, int]:
        """Load a frame, or an iterable of frames, using the bcp utility.
        """
        if isinstance(chunks, pd.DataFrame):
            chunks = [chunks]

        if not self.bcp_available():
            self.logger.error('bcp utility not available')
            return False, 0

        table = self._get_reflected_table(table_name, schema)
        column_order = [c.name for c in table.columns]

        work_dir = tempfile.mkdtemp(prefix='rcsbcp_', dir=temp_dir)
        data_path = os.path.join(work_dir, f'{table_name}.dat')
        error_path = os.path.join(work_dir, f'{table_name}.err')

        try:
            first = True
            target_names: List[str] = []
            frame_cols: List[Any] = []

            def aligned(source: Iterable[pd.DataFrame]) -> Iterator[pd.DataFrame]:
                nonlocal first, target_names, frame_cols
                for chunk in source:
                    if chunk is None or chunk.empty:
                        continue
                    if first:
                        target_names, frame_cols = self._align_frame_to_table(
                            chunk, table, table_name
                        )
                        first = False
                    present = {n.lower() for n in target_names}
                    missing = [c for c in column_order if c.lower() not in present]
                    reindexed = chunk[frame_cols].copy()
                    reindexed.columns = target_names
                    for col in missing:
                        reindexed[col] = None
                    yield reindexed[column_order]

            format_stats: Dict[str, int] = {}
            formatters = self._build_bcp_formatters(table, column_order, format_stats)
            try:
                # `chunks` is a lazy generator from the CSV reader, consumed here.
                # Without its own handler a read failure lands in the outer
                # `except` and gets reported as a bcp failure when bcp has not
                # even been invoked yet - which is exactly how a CSV
                # UnicodeDecodeError once surfaced as "bcp load failed".
                rows_written, _ = self._write_bcp_file(
                    aligned(chunks), data_path, column_order, formatters, table_name
                )
            except Exception as read_error:
                self.logger.error(
                    f'Failed reading source data for {schema}.{table_name} before '
                    f'bcp was invoked: {type(read_error).__name__}: {read_error}',
                    exc_info=True,
                )
                keep_temp = True
                return False, 0
            if format_stats.get('rescaled'):
                self.logger.warning(
                    f'{table_name}: {format_stats["rescaled"]} value(s) had more '
                    f'decimal places than the target column and were rounded '
                    f'half-up. Verify these against the source if they are money.'
                )
            if rows_written == 0:
                self.logger.info(f'Nothing to load into {table_name} (no rows)')
                return True, 0

            size_mb = os.path.getsize(data_path) / 1024 / 1024
            self.logger.info(
                f'bcp: wrote {rows_written} rows ({size_mb:.1f} MB) for {table_name}'
            )

            # -S/-d come from the verified auth candidate, because a DSN
            # candidate passes -D -S <dsn> instead of -S <server>.
            cmd = [
                'bcp', f'{schema}.[{table_name}]', 'in', data_path,
                '-c',
                '-C', BCP_CODE_PAGE,
                '-t', BCP_FIELD_TERMINATOR,
                '-r', BCP_ROW_TERMINATOR,
                '-k',                      # empty field -> NULL
                '-b', str(batch_size),
                '-m', str(BCP_MAX_ERRORS),
                '-e', error_path,
                '-l', '30',
            ]
            auth_args = self.bcp_auth_args()
            if auth_args is None:

                _usable, reason = self.bcp_ready()
                raise RuntimeError(reason)
            cmd += auth_args     

            start = time.time()
            result = self._run_with_retry(
                lambda: subprocess.run(cmd, capture_output=True, text=True,
                                       encoding='utf-8', errors='replace',
                                       timeout=None),
                description=f'bcp load into {table_name}',
            )
            elapsed = time.time() - start

            output = f'{result.stdout or ""}\n{result.stderr or ""}'
            copied = self._parse_bcp_rows_copied(output)

            rejected = max(0, rows_written - copied)

            if result.returncode != 0:
                self.logger.error(
                    f'bcp failed for {table_name} (exit {result.returncode}): '
                    f'{output.strip()[:1000]}'
                )
                keep_temp = True
                return False, copied

            rate = (copied / elapsed) if elapsed > 0 and copied else 0
            self.logger.info(
                f'bcp loaded {copied}/{rows_written} rows into {table_name} in '
                f'{elapsed:.2f}s ({rate:.0f} rows/sec)'
            )
            self.last_activity = time.time()

            if rejected:

                self.logger.error(
                    f'{table_name}: bcp rejected {rejected} of {rows_written} row(s). '
                    f'Rejected rows and reasons kept at {error_path}'
                )
                keep_temp = True
                return False, copied
            return True, copied

        except Exception as e:
            # exc_info rather than logger.debug: root runs at INFO, so the
            # traceback that would have named the real failure was being
            # discarded exactly when it was needed.
            self.logger.error(
                f'bcp load failed for {schema}.{table_name}: '
                f'{type(e).__name__}: {e or "(no message)"}',
                exc_info=True,
            )
            return False, 0
        finally:
            if keep_temp:
                self.logger.info(f'bcp working files kept at {work_dir}')
            else:
                shutil.rmtree(work_dir, ignore_errors=True)

    @staticmethod
    def _parse_bcp_rows_copied(output: str) -> int:
        """Pull the copied-row count out of bcp's summary line."""
        match = re.search(r'(\d+)\s+rows copied', output, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 0

    def _count_bcp_rejects(self, error_path: str) -> int:
        """Count rows bcp wrote to the ERRORFILE, if any."""
        try:
            if not os.path.exists(error_path) or os.path.getsize(error_path) == 0:
                return 0
            with open(error_path, 'r', encoding='utf-8', errors='replace') as handle:
                return sum(1 for line in handle if line.strip())
        except Exception as e:
            self.logger.warning(f'Could not read bcp error file {error_path}: {e}')
            return 0

    def bulk_insert_chunked(self, frame: pd.DataFrame, table_name: str, schema: str = 'dbo',
                            max_batch_bytes: int = DEFAULT_MAX_BATCH_BYTES) -> Tuple[bool, int]:
        """Bulk insert a frame in byte-bounded batches, retrying transient faults.

        """
        if self.sqlalchemy_engine is None:
            self.connect_sqlalchemy()

        total_rows = len(frame)
        if total_rows == 0:
            self.logger.info(f'Nothing to insert for {table_name} (empty frame)')
            return True, 0

        batch_rows = self.calculate_batch_rows(
            table_name, schema=schema, columns=frame.columns, max_batch_bytes=max_batch_bytes
        )
        row_bytes = self.estimate_row_bytes(table_name, schema=schema, columns=frame.columns)
        self.logger.info(
            f'Starting bulk insert for {table_name}: {total_rows} rows, '
            f'~{row_bytes:,} bytes/row declared, batch={batch_rows} rows '
            f'(~{batch_rows * row_bytes / 1024 / 1024:.0f} MB buffer)'
        )

        start_time = time.time()
        rows_inserted = 0
        batches = (total_rows + batch_rows - 1) // batch_rows

        table = self._get_reflected_table(table_name, schema)
        statement = table.insert()
        target_names, frame_cols = self._align_frame_to_table(frame, table, table_name)
        if not frame_cols:
            self.logger.error(
                f'No frame columns match {schema}.{table_name}; nothing to insert'
            )
            return False, 0

        try:
            for index, start in enumerate(range(0, total_rows, batch_rows), start=1):

                chunk = frame.iloc[start:start + batch_rows][frame_cols]
                chunk = chunk.astype(object).where(pd.notnull(chunk), None)
                records = [
                    dict(zip(target_names, row))
                    for row in chunk.itertuples(index=False, name=None)
                ]

                def run_batch(rows=records):
                    with self.sqlalchemy_engine.begin() as conn:
                        conn.execute(statement, rows)

                self._run_with_retry(
                    run_batch,
                    description=f'insert batch {index}/{batches} into {table_name}',
                )
                rows_inserted += len(chunk)
                del chunk, records
                if index % 25 == 0 or index == batches:
                    self.logger.info(
                        f'  {table_name}: {rows_inserted}/{total_rows} rows '
                        f'({rows_inserted / total_rows * 100:.1f}%)'
                    )

            elapsed = time.time() - start_time
            rate = rows_inserted / elapsed if elapsed > 0 else 0
            self.logger.info(
                f'Bulk insert completed for {table_name} in {elapsed:.2f}s ({rate:.0f} rows/sec)'
            )
            self.last_activity = time.time()
            return True, rows_inserted
        except Exception as e:

            self.logger.error(
                f'Bulk insert failed for {schema}.{table_name} after {rows_inserted}/{total_rows} '
                f'rows: {type(e).__name__}: {e or "(no message)"}'
            )
            self.logger.debug('Traceback:\n%s', traceback.format_exc())
            return False, rows_inserted

    def test_connection(self) -> Dict[str, bool]:
        """Test all connection types and return status."""
        results = {
            'pyodbc': False,
            'sqlalchemy': False,
            'sqlcmd': False
        }
        
        # Test PyODBC
        try:
            conn = self.connect_pyodbc()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            results['pyodbc'] = True
            self.logger.info("PyODBC connection test passed")
        except Exception as e:
            self.logger.error(f"PyODBC connection test failed: {str(e)}")
        
        # Test SQLAlchemy
        try:
            engine = self.connect_sqlalchemy()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            results['sqlalchemy'] = True
            self.logger.info("SQLAlchemy connection test passed")
        except Exception as e:
            self.logger.error(f"SQLAlchemy connection test failed: {str(e)}")
        
        # Test SQLCMD
        try:
            success, output = self.execute_sqlcmd("SELECT 1")
            results['sqlcmd'] = success
            if success:
                self.logger.info("SQLCMD connection test passed")
            else:
                self.logger.error(f"SQLCMD connection test failed: {output}")
        except Exception as e:
            self.logger.error(f"SQLCMD connection test failed: {str(e)}")
        
        return results
    
    def close_connections(self) -> None:
        """Close all database connections safely."""
        if hasattr(self, 'pyodbc_connection') and self.pyodbc_connection:
            try:
                self.pyodbc_connection.close()
                self.logger.info("PyODBC connection closed")
            except Exception:
                pass
            finally:
                self.pyodbc_connection = None
        
        try:
            if hasattr(self, 'sqlalchemy_engine') and self.sqlalchemy_engine:
                self.sqlalchemy_engine.dispose()
                self.logger.info("SQLAlchemy engine disposed")
                self.sqlalchemy_engine = None
        except Exception as e:
            self.logger.error(f"Error disposing SQLAlchemy engine: {e}")

    def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed status of all database connections."""
        status = {
            'pyodbc_connected': False,
            'sqlalchemy_connected': False,
            'environment': self.environment,
            'server': self.config.get('SERVER', 'Unknown'),
            'database': self.config.get('DATABASE', 'Unknown'),
            'client_id': self.config.get('CLIENT_ID', 'N/A'),
            'last_activity': getattr(self, 'last_activity', None),
            'connection_age_seconds': time.time() - getattr(self, 'last_activity', time.time())
        }
        # Check PyODBC connection
        try:
            if self.pyodbc_connection and not getattr(self.pyodbc_connection, 'closed', True):
                cursor = self.pyodbc_connection.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                status['pyodbc_connected'] = True
        except:
            status['pyodbc_connected'] = False
        
        # Check SQLAlchemy connection
        try:
            if self.sqlalchemy_engine:
                with self.sqlalchemy_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                status['sqlalchemy_connected'] = True
        except:
            status['sqlalchemy_connected'] = False
        
        return status
    
    def is_healthy(self) -> bool:
        """Check if database connections are healthy."""
        status = self.get_connection_status()
        return status['pyodbc_connected'] and status['sqlalchemy_connected']
         
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connections."""
        self.close_connections()

# # Example usage
# if __name__ == "__main__":
#     # Test V10 environment
#     print("Testing V10 environment...")
#     helper = DatabaseHelper('v10')
    
#     with DatabaseHelper('v10') as db_v10:
#         results = db_v10.test_connection()
#         print(f"V10 Connection Results: {results}")
        
#         if results['sqlalchemy']:
#             df = db_v10.execute_query("SELECT TOP 5 * FROM INFORMATION_SCHEMA.TABLES")
#             print(f"Sample query result: {len(df)} rows")
    
#     # Test UAT environment
#     print("\nTesting UAT environment...")
#     with DatabaseHelper('uat') as db_uat:
#         results = db_uat.test_connection()
#         print(f"UAT Connection Results: {results}")