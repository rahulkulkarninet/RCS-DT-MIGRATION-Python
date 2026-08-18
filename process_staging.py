import re
import os
import csv
import gc
import logging
import time
import pandas as pd
from pathlib import Path
from typing import Dict, Any, Iterator, Optional, List
from db_manager import DatabaseHelper
from config_parser import ConfigParser
from charset_normalizer import from_bytes
from sqlalchemy import create_engine,text,inspect
from text_normalization import normalize_text_series



# Bytes read from the head of a file for encoding detection. Enough to cover a
# BOM and a representative sample, without loading a multi-GB extract into RAM.
ENCODING_SAMPLE_BYTES = 256 * 1024

# Default sink for load_staging_file_group. 
#
# Still unexercised against Azure SQL with Entra authentication (bcp -G). If that
# path fails, set this back to False; load_staging_file_group also falls back to the
# pandas sink automatically when the bcp utility is not present at all.
PREFER_BCP = True


# Setting this True makes staging mirror the source exactly, which is the better
# end state, but the null-sensitive transform sites must be updated first (for
# example `NULLIF(NULLIF(C.A_B_N, 'NA'), '')`). tools/verify_load_fidelity.py
# reports every value affected either way, so the coercion is visible rather than
# silent.
PRESERVE_NA_TEXT = False


def na_read_options() -> Dict[str, Any]:
    """pandas read_csv options controlling what counts as a missing value."""
    if PRESERVE_NA_TEXT:
        return {'keep_default_na': False, 'na_values': ['']}
    return {}   # pandas defaults: NA/N/A/NULL/None/nan read as missing


class FinancialAccumulator:
    """Accumulate calculate_financials metrics across streamed chunks.

    Chunk-wise aggregation has to be exact, not approximate: sum/count/max/min
    compose directly, but an average of per-chunk averages is wrong when chunks
    differ in size, so avg tracks running sum and count and divides at the end.
    """

    def __init__(self, config: Any, table_name: str):
        self.table_name = table_name
        self.logger = logging.getLogger(__name__)
        self._metrics: List[Dict[str, Any]] = []
        self._state: Dict[str, Dict[str, Any]] = {}

        table_config = {}
        if config and getattr(config, 'staging_metrics', None):
            table_config = config.staging_metrics.get(table_name.upper(), {}) or {}

        if isinstance(table_config, dict) and isinstance(table_config.get('metrics'), list):
            for metric in table_config['metrics']:
                if not isinstance(metric, dict):
                    continue
                column = metric.get('column')
                key = metric.get('result_column') or column
                if column and key:
                    self._metrics.append(
                        {'column': column, 'key': key,
                         'type': str(metric.get('type', 'sum')).lower()}
                    )
        elif isinstance(table_config, dict):
            for name, column in table_config.items():
                if name != 'base_config' and isinstance(column, str):
                    self._metrics.append({'column': column, 'key': name, 'type': 'sum'})

        for metric in self._metrics:
            self._state[metric['key']] = {
                'sum': 0.0, 'count': 0, 'max': None, 'min': None, 'seen': False
            }

    @property
    def active(self) -> bool:
        return bool(self._metrics)

    def update(self, frame: pd.DataFrame) -> None:
        if not self._metrics or frame.empty:
            return
        lowered = {str(c).lower(): c for c in frame.columns}
        for metric in self._metrics:
            state = self._state[metric['key']]
            actual = lowered.get(str(metric['column']).lower())
            if actual is None:
                continue
            state['seen'] = True
            try:
                series = pd.to_numeric(frame[actual], errors='coerce').dropna()
            except Exception as e:
                self.logger.warning(
                    f'{self.table_name}: could not aggregate {metric["column"]}: {e}'
                )
                continue
            if series.empty:
                continue
            state['sum'] += float(series.sum())
            state['count'] += int(series.count())
            chunk_max, chunk_min = float(series.max()), float(series.min())
            state['max'] = chunk_max if state['max'] is None else max(state['max'], chunk_max)
            state['min'] = chunk_min if state['min'] is None else min(state['min'], chunk_min)

    def result(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}
        for metric in self._metrics:
            key, kind = metric['key'], metric['type']
            state = self._state[key]
            if not state['seen']:
                summary[key] = 0.00
                self.logger.warning(
                    f'{self.table_name} - Column "{metric["column"]}" not found for {key}'
                )
                continue
            if kind == 'count':
                summary[key] = state['count']
            elif kind in ('avg', 'average'):
                summary[key] = round(state['sum'] / state['count'], 2) if state['count'] else 0.00
            elif kind == 'max':
                summary[key] = round(state['max'], 2) if state['max'] is not None else 0.00
            elif kind == 'min':
                summary[key] = round(state['min'], 2) if state['min'] is not None else 0.00
            else:
                summary[key] = round(state['sum'], 2)
        return summary


class StagingProcessor:
    """Process staging files using database and configuration management."""
    
    def __init__(self, environment: str, shared_db_helper=None, shared_config_parser=None ):
        self.environment = environment
        self.logger = logging.getLogger(__name__)

        # Use shared connections if provided
        self.db_helper = shared_db_helper
        self.config = shared_config_parser
        self._owns_db_connection = shared_db_helper is None
        self._owns_config = shared_config_parser is None
    
        self.file_paths = {}
        self._table_columns_cache: Dict[tuple[str, str], Dict[str, Dict]] = {}

        # Set by the caller to the customer's Errors folder so rows rejected by
        # the tier 3 parser can be written out and re-fed. When unset the rows
        # are still counted and logged, never silently dropped.
        self.reject_dir: Optional[Path] = None
        # Bad lines captured during the current load_staging_file_group call.
        self.bad_line_count = 0

        # Regex pattern for sequence number extraction
        self.seq_re = re.compile(r"_(\d{4})\.csv$", re.I)

    def initialize(self):
        """Initialize database connection and load configuration."""
        try:
            # Initialize config parser
            if self.config is None:
                self.config = ConfigParser(db_environment=self.environment)
                self.config.load_configs()
                self._owns_config = True
            
            # Initialize database if available
            if self.db_helper is None:
                if self.config.init_database():
                    self.config.resolve_database_vars()
                    self.db_helper = self.config.db_helper
                    self._owns_db_connection = True
                else:
                    self.logger.error("Failed to initialize database connection")
                    return False
            else:
                self.logger.info("Using shared database connection for staging processor")
            
                
            # Get file paths from configuration
            self._load_file_paths()
            
            self.logger.info(f"Staging processor initialized for {self.environment}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize staging processor: {e}")
            return False

    def _load_file_paths(self):
        """Load file paths from configuration."""
        try:
            # Get path variables from config
            path_vars = self.config.get_category_variables('path')

            # Get network settings from db_manager config
            network_server = None
            network_share = None
            
            if self.db_helper:
                # Get from database helper config
                db_config = self.db_helper.config
                network_server = db_config.get('NETWORK_SERVER')
                network_share = db_config.get('NETWORK_SHARE')
                #self.logger.info(f"Network settings from db_manager: {network_server}/{network_share}")
            
            # Build file paths using templates from config
            csv_template = path_vars.get('CSV_PATH_TEMPLATE', '//{server}/{share}/Debtrak/')
            output_template = path_vars.get('OUTPUT_PATH_TEMPLATE', '//{server}/{share}/Debtrak/Migration/')
            sql_path = path_vars.get('SQL_FILE_PATH', 'SQL/migration queries/*.sql')

            # Resolve and store file paths
            self.file_paths['csv'] = csv_template.format(server=network_server, share=network_share)
            self.file_paths['output'] = output_template.format(server=network_server, share=network_share)
            self.file_paths['sql'] = sql_path

        except Exception as e:
            self.logger.error(f"Error loading file paths: {e}")

    def get_sequence_number(self, path: Path) -> int:
        """
        Extracts the 4 digit sequence number from the file name.
        If not found, returns 0.
        """
        match = self.seq_re.search(path.name)
        if match:
            return int(match.group(1))
        return 0

    def detect_encoding(self, file_path: Path, sample_bytes: int = ENCODING_SAMPLE_BYTES) -> str:
        """
        Detect the encoding of a file using charset_normalizer.
        Returns the detected encoding or 'utf-8' if detection fails.

        An 'ascii' verdict is widened to cp1252. Detection only ever sees the
        head of the file, so "no non-ASCII byte in the sample" does not mean the
        file is ASCII: the SM9641 extracts carried a cp1252 NBSP (0xA0) megabytes
        in, and reading them as ASCII raised UnicodeDecodeError and cost the whole
        table. cp1252 is a superset of ASCII over 0x00-0x7F, so genuinely-ASCII
        files decode byte-identically and only the padded ones change behaviour.
        """
        try:
            with open(file_path, 'rb') as handle:
                sample = handle.read(sample_bytes)
            if not sample:
                return 'utf-8'
            # No steps/chunk_size throttle: the previous steps=1, chunk_size=1024
            # analysed 1 KB of the 256 KB actually read.
            result = from_bytes(sample).best()
            encoding = result.encoding if result else 'utf-8'
            if encoding.lower().replace('-', '_') in ('ascii', 'us_ascii'):
                return 'cp1252'
            return encoding
        except Exception as e:
            self.logger.warning(f'Encoding detection failed for {file_path}: {e}')
            return 'utf-8'
        
    def truncate_staging_tables(self) -> bool:
        """
        Truncate all staging tables based on table keywords from configuration.
        """
        try:
            if not self.db_helper or not self.db_helper.sqlalchemy_engine:
                self.logger.error("Database connection not available")
                return False
            
            if not self.config:
                self.logger.error("Configuration not available")
                return False
            
            # Get table keywords from configuration
            table_keywords = self.config.table_keywords
            
            if not table_keywords:
                self.logger.warning("No table keywords found in configuration")
                return False
            
            # Truncate each staging table
            with self.db_helper.sqlalchemy_engine.begin() as conn:
                for keyword, table_name in table_keywords.items():
                    if table_name:
                        try:
                            conn.execute(text(f'TRUNCATE TABLE {table_name}'))
                            #self.logger.info(f"Truncated table: {table_name}")
                        except Exception as e:
                            self.logger.error(f"Failed to truncate table {table_name}: {e}")
                            return False
            
            self.logger.info("All staging tables truncated successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error truncating staging tables: {e}")
            return False
        
    def get_table_columns(self, table_name: str, schema: str = 'dbo') -> Dict[str, Dict]:
        """
        Get the columns of a table from the database.
        Returns a dictionary with column names as keys and their data types as values.
        """
        if not self.db_helper or not self.db_helper.sqlalchemy_engine:
            self.logger.error("Database connection not available")
            return {}

        cache_key = (schema.lower(), table_name.lower())
        cached_columns = self._table_columns_cache.get(cache_key)
        if cached_columns is not None:
            return cached_columns
            
        inspector = inspect(self.db_helper.sqlalchemy_engine)
        try:
            columns = inspector.get_columns(table_name, schema=schema)
            column_info = {}
            for col in columns:
                col_name = col['name'].lower()
                original_name = col['name']
                col_type = str(col['type'])

                # Extract max_length if available
                max_length = None
                if hasattr(col['type'], 'length') and col['type'].length:
                    max_length = col['type'].length
                elif 'varchar' in col_type.lower() or 'char' in col_type.lower():
                    length_match = re.search(r'\((\d+)\)', col_type)
                    if length_match:
                        max_length = int(length_match.group(1))
                        
                column_info[col_name] = {
                    'name': original_name,
                    'type': col_type,
                    'max_length': max_length,
                    'nullable': col.get('nullable', True)
                }
            self._table_columns_cache[cache_key] = column_info
            return column_info
        except Exception as e:
            self.logger.warning(f'Failed to get columns for {table_name}: {e}')
            return {}
        
    def get_staging_files(self) -> List[str]:
        """Get list of staging CSV files from input directory using glob."""
        try:
            from glob import glob
            
            csv_path = self.file_paths['csv']

            # Use glob patterns to find *RC_*.csv files
            csv_pattern = os.path.join(csv_path, '*RC_*.csv')
            csv_files = glob(csv_pattern)

            self.logger.info(f"Found {len(csv_files)} staging CSV files matching *RC_*.csv")
            return csv_files
                
        except Exception as e:
            self.logger.error(f"Error accessing staging files: {e}")
            return []
    
    def match_file(self, filename: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Match a filename to a target table name based on the parts after 'RC_' in the filename.
        SMAUS_SM9596_RC_NOTES_EXTRACT_0001.csv -> NOTES_EXTRACT -> mapped table
        """
        parts = Path(filename).stem.split('_')

        try:
            customer_code = parts[1]
            rc_index = parts.index('RC')
        except Exception as e:
            self.logger.error(f'Failed to parse {filename}: {e}')
            return None, None, None

        keyword_parts = []
        for p in parts[rc_index + 1:]:
            if p.isdigit() and len(p) == 4:  # stop at 4 digit sequence number
                break
            keyword_parts.append(p)

        keyword = "_".join(keyword_parts).upper()
        
        # Get table keywords from config
        table_keyword = self.config.get_table_name(keyword) if self.config else None
        
        return keyword, table_keyword, customer_code
    
    def read_csv_file(self, path: Path) -> pd.DataFrame:
        """Read CSV file with encoding detection and error handling."""
        encoding = self.detect_encoding(path)
        headers = pd.read_csv(path, nrows=0, sep=',', encoding=encoding, dtype=str).columns.str.strip().tolist()
        cols = [c for c in headers if c and not str(c).startswith('Unnamed')]

        na_opts = na_read_options()

        try:
            # First attempt with 'warn' - shows problematic lines but continues
            frame = pd.read_csv(
                path, sep=',', usecols=cols, index_col=False, names=cols,
                header=0, encoding=encoding,
                on_bad_lines='warn',  # Keep 'warn' for transparency
                dtype=str,
                **na_opts
            )
            return frame
        # UnicodeDecodeError is a ValueError, so without naming it here an
        # encoding fault skipped recovery entirely and fell to the handler below.
        except (pd.errors.ParserError, UnicodeDecodeError) as e:
            if (isinstance(e, UnicodeDecodeError)
                    or "EOF inside string" in str(e)
                    or "tokenizing data" in str(e)):
                self.logger.warning(f'Parser error in {path.name}: {e}. Attempting recovery with more forgiving parameters...')
                try:
                    # Recovery attempt with 'warn' + more forgiving settings
                    frame = pd.read_csv(
                        path, sep=',', usecols=cols, index_col=False, names=cols,
                        header=0, encoding=encoding,
                        on_bad_lines='warn',  # Still warn about issues
                        dtype=str,
                        quoting=3,  # QUOTE_NONE
                        skipinitialspace=True,
                        engine='python',
                        encoding_errors='replace',  # Replace problematic characters
                        **na_opts
                    )
                    self.logger.info(f'Successfully recovered data from {path.name} with warnings')
                    return frame
                except Exception as recovery_error:
                    self.logger.error(f'Recovery failed for {path.name}: {recovery_error}')
                    self.logger.info(f'Attempting final recovery with skip mode for {path.name}...')
                    bad_lines: List[List[str]] = []

                    def capture_bad_line(line: List[str]) -> None:
                        bad_lines.append(line)
                        return None

                    try:
                        # Final attempt. Bad lines are captured rather than
                        # skipped, so nothing disappears without being counted.
                        frame = pd.read_csv(
                            path, sep=',', usecols=cols, index_col=False, names=cols,
                            header=0, encoding=encoding,
                            on_bad_lines=capture_bad_line,
                            dtype=str,
                            quoting=3,
                            engine='python',
                            **na_opts
                        )
                        if bad_lines:
                            self._record_bad_lines(path, bad_lines)
                        self.logger.warning(f'Final recovery successful for {path.name}')
                        return frame
                    except Exception as final_error:
                        self.logger.error(
                            f'All recovery tiers failed for {path.name}: '
                            f'{type(final_error).__name__}: {final_error}',
                            exc_info=True,
                        )
                        raise
            else:
                raise
        except Exception as e:
            # Previously returned an empty frame here, so an unreadable file
            # loaded as zero rows and reconciled clean. Fail instead.
            self.logger.error(
                f'Unexpected error reading {path.name}: {type(e).__name__}: {e}',
                exc_info=True,
            )
            raise

    def concat_files(self, files: List[str]) -> pd.DataFrame:
        """
        Concatenate multiple CSV files into a single DataFrame.
        """
        parts: List[pd.DataFrame] = []
        ref_cols: List[str] = []
        failures: List[str] = []

        for fp in sorted(map(Path, files), key=self.get_sequence_number):
            try:
                frame = self.read_csv_file(fp)
                if not ref_cols:
                    ref_cols = frame.columns.tolist()
                else:
                    if set(ref_cols) != set(frame.columns):
                        raise ValueError(f'Column mismatch in {fp.name}')
                all_cols = list(dict.fromkeys([*ref_cols, *frame.columns]))
                frame = frame.reindex(columns=all_cols)

                # Drop repeated header rows inside the file
                header_vals = pd.Series({c: c for c in frame.columns}, dtype=str)
                mask = (frame.astype(str).reindex(columns=header_vals.index) == header_vals).all(axis=1)
                frame = frame.loc[~mask]

                parts.append(frame)
            except Exception as e:
                # Keep going so the log names every bad file, not just the first.
                self.logger.error(
                    f'Failed to load {fp.name}: {type(e).__name__}: {e}',
                    exc_info=True,
                )
                failures.append(f'{fp.name} ({type(e).__name__}: {e})')

        if failures:
            # Skipping the file used to leave a partial table that reconciled
            # clean and looked successful. Fail the group instead.
            raise RuntimeError(
                f'{len(failures)} of {len(files)} file(s) could not be read: '
                + '; '.join(failures)
            )

        if not parts:
            return pd.DataFrame()  # if no files were loaded, return empty DataFrame

        all_cols = list(dict.fromkeys(col for d in parts for col in d.columns))  # Union of all columns from all parts
        combined_frame = pd.concat([d.reindex(columns=all_cols) for d in parts], ignore_index=True)  # Concatenate all parts into a single DataFrame
        return combined_frame

    def load_column_mapping(self, mapping_path: str) -> pd.DataFrame:
        """Load column mapping from CSV file."""
        mapping_frame = pd.read_csv(mapping_path, sep=',', index_col=False)
        return mapping_frame

    def rename_columns(self, frame: pd.DataFrame, mapping_dict: Dict) -> pd.DataFrame:
        """Rename DataFrame columns using mapping dictionary."""
        return frame.rename(columns=mapping_dict)

    def validate_columns(self, csv_frame: pd.DataFrame, mapping: pd.DataFrame, table_name: str,
                         sql_columns: Optional[List[str]] = None) -> pd.DataFrame:
        """Validate and align CSV columns with database table columns."""
        if not self.db_helper or not self.db_helper.sqlalchemy_engine:
            self.logger.error("Database connection not available")
            return csv_frame

        if sql_columns is None:
            db_columns = self.get_table_columns(table_name)
            sql_columns = [info['name'] for info in db_columns.values()]

        if not sql_columns:
            self.logger.error(f"Failed to get table columns for {table_name}")
            return csv_frame
            
        mapping_columns = dict(zip(mapping['csv_col_name'].fillna('').str.strip(), mapping['db_col_name'].fillna('').str.strip()))
        unmapped_db_cols = mapping.loc[mapping['db_col_name'].isna() | (mapping['db_col_name'].str.strip() == ''), 'csv_col_name'].tolist()
        frame_renamed = csv_frame.rename(columns=mapping_columns)

        # Check if all columns in the CSV are mapped to the database columns
        db_set = set(sql_columns)
        csv_set = set(frame_renamed.columns)

        missing_db_vs_csv = sorted(db_set - csv_set)
        extra_db_vs_csv = sorted(csv_set - db_set)

        extra_with_db_names = []
        for col in extra_db_vs_csv:
            if col == '' or pd.isna(col):
                extra_with_db_names.extend(unmapped_db_cols)
            else:
                extra_with_db_names.append(col)

        if missing_db_vs_csv:
            self.logger.warning(f'Missing in CSV - {table_name}: {missing_db_vs_csv}')

        if extra_db_vs_csv:
            self.logger.warning(f'Extra in CSV - {table_name}: {extra_with_db_names}')

        frame = frame_renamed.reindex(columns=sql_columns)
        return frame

    def clean_frame(self, frame: pd.DataFrame, db_columns: Dict[str, Dict]) -> pd.DataFrame:
        """
        Clean the DataFrame by converting columns to their appropriate SQL types.
        """
        frame.columns = [col.strip().lower() for col in frame.columns]

        truncation_warnings = []

        for col in frame.columns:
            col_info = db_columns.get(col.lower(), {})
            db_type = col_info.get('type', '').lower()
            max_length = col_info.get('max_length')
            original_dtype = frame[col].dtype

            try:
                # Handle different SQL data types
                if 'int' in db_type or 'tinyint' in db_type or 'smallint' in db_type or 'bigint' in db_type:
                    frame[col] = pd.to_numeric(frame[col], errors='coerce')
                    frame[col] = frame[col].astype('Int64')  # Use nullable integer type
                elif 'float' in db_type or 'decimal' in db_type or 'numeric' in db_type:
                    frame[col] = pd.to_numeric(frame[col], errors='coerce')
                elif 'nvarchar' in db_type or 'varchar' in db_type:

                    populated = frame[col].notna()
                    if not populated.any():

                        frame[col] = None
                        continue

                    text = frame[col][populated].astype(str)
                    # Before the length check, so truncation measures the value
                    # that will actually be stored.
                    text = normalize_text_series(text)
                    if max_length and max_length > 0:
                        long_values = int((text.str.len() > max_length).sum())
                        if long_values:
                            truncation_warnings.append(
                                f'Column {col}: {long_values} values truncated to '
                                f'{max_length} chars')
                            text = text.str.slice(0, max_length)

                    cleaned = pd.Series([None] * len(frame), index=frame.index,
                                        dtype=object)
                    cleaned[populated] = text
                    frame[col] = cleaned
                elif 'bit' in db_type:
                    frame[col] = frame[col].astype('boolean')
                elif 'datetime' in db_type:
                    frame[col] = pd.to_datetime(frame[col], errors='coerce',
                                              format='mixed', dayfirst=True)
                elif 'date' in db_type:
                    frame[col] = pd.to_datetime(frame[col], errors='coerce',
                                              format='mixed', dayfirst=True)
                    frame[col] = frame[col].dt.date

            except Exception as e:
                self.logger.warning(f'Failed to convert column {col} ({original_dtype}) to {db_type}: {e}')
                
        for warning in truncation_warnings:
            self.logger.warning(warning)

        return frame

    def get_row_count(self, table_name: str) -> int:
        """
        Get the row count of a table.
        """
        if not self.db_helper:
            self.logger.error("Database connection not available")
            return -1
            
        try:
            sql = f"SELECT COUNT(*) FROM {table_name}"
            result = self.db_helper.execute_query(sql)
            return result.iloc[0, 0] if not result.empty else 0
        except Exception as e:
            self.logger.warning(f'Failed to get row count for {table_name}: {e}')
            return -1  # Return -1 to indicate failure

    def get_all_possible_financial_columns(self) -> list:
        """
        Get list of all possible financial columns for DataFrame creation.
        """
        all_columns = set()
        
        # Get columns from staging_metrics configuration
        if self.config and self.config.staging_metrics:
            for table_config in self.config.staging_metrics.values():
                if isinstance(table_config, dict):
                    # Handle new nested structure with metrics array
                    if 'metrics' in table_config and isinstance(table_config['metrics'], list):
                        for metric_config in table_config['metrics']:
                            if isinstance(metric_config, dict):
                                result_column = metric_config.get('result_column')
                                if result_column:
                                    all_columns.add(result_column.lower())
                    else:
                        # Handle old format (fallback) - add the metric keys
                        for metric_name in table_config.keys():
                            if metric_name != 'base_config':
                                all_columns.add(metric_name.lower())
        
        # Add migration-specific financial columns that come from collect_migration_metrics
        # These are the column names returned by the metrics collection, NOT staging table mappings
        migration_financial_columns = {
            'total_debt', 
            'total_costs', 
            'total_paid', 
            'total_overpayments', 
            'total_outstanding',
            'total_commission',
            'total_interest'
        }
        all_columns.update(migration_financial_columns)
        
        self.logger.debug(f"All financial columns: {sorted(list(all_columns))}")
        return sorted(list(all_columns))
    
    def calculate_financials(self, frame: pd.DataFrame,table_name:str) -> dict:
        """
        Calculate financial summaries for specific tables using configuration dictionary.
        Returns dictionary with financial metrics or empty dict if not applicable.
        """
        financial_summary = {}
        table_upper = table_name.upper()

        # Check if table has financial metrics defined
        if table_upper not in self.config.staging_metrics:
            return financial_summary  # Return empty if no metrics defined
        
        try:
            table_config = self.config.staging_metrics[table_upper]
            
            # Handle the new nested structure with base_config and metrics array
            if 'metrics' in table_config and isinstance(table_config['metrics'], list):
                metrics_list = table_config['metrics']
                
                for metric_config in metrics_list:
                    if isinstance(metric_config, dict):
                        # Extract information from metric configuration
                        column_name = metric_config.get('column')
                        result_column = metric_config.get('result_column')
                        metric_type = metric_config.get('type', 'sum')
                        description = metric_config.get('description', '')
                        
                        # Use result_column as the key for financial_summary
                        metric_key = result_column if result_column else column_name
                        
                        if column_name and column_name in frame.columns:
                            # Convert to numeric and apply aggregation, handling errors gracefully
                            numeric_series = pd.to_numeric(frame[column_name], errors='coerce')
                            
                            # Apply the specified aggregation type
                            if metric_type.lower() == 'sum':
                                total_value = round(numeric_series.sum(), 2)
                            elif metric_type.lower() == 'avg' or metric_type.lower() == 'average':
                                total_value = round(numeric_series.mean(), 2)
                            elif metric_type.lower() == 'count':
                                total_value = numeric_series.count()
                            elif metric_type.lower() == 'max':
                                total_value = round(numeric_series.max(), 2)
                            elif metric_type.lower() == 'min':
                                total_value = round(numeric_series.min(), 2)
                            else:
                                # Default to sum if type is unknown
                                total_value = round(numeric_series.sum(), 2)
                            
                            financial_summary[metric_key] = total_value
                            
                            #self.logger.debug(f'{table_name} - {metric_key} ({description}): ${total_value:,.2f} '
                            #                f'(from column: {column_name}, type: {metric_type})')
                        
                        elif column_name:
                            # Column not found, set to 0
                            financial_summary[metric_key] = 0.00
                            self.logger.warning(f'{table_name} - Column "{column_name}" not found for {metric_key}')
            
            else:
                # Fallback: Handle old format if still present
                self.logger.warning(f'{table_name} - Using fallback for old staging_metrics format')
                
                for metric_name, column_name in table_config.items():
                    if metric_name == 'base_config':
                        continue  # Skip base_config section
                        
                    if column_name in frame.columns:
                        # Convert to numeric and sum, handling errors gracefully
                        numeric_series = pd.to_numeric(frame[column_name], errors='coerce')
                        total_value = round(numeric_series.sum(), 2)
                        financial_summary[metric_name] = total_value

                        self.logger.debug(f'{table_name} - {metric_name}: ${total_value:,.2f} (from column: {column_name})')
                    else:
                        # Column not found, set to 0
                        financial_summary[metric_name] = 0.00
                        self.logger.warning(f'{table_name} - Column "{column_name}" not found for {metric_name}')

            # Log summary if any values were calculated
            if financial_summary:
                summary_items = [f"{k}: ${v:,.2f}" for k, v in financial_summary.items() if v != 0]
                if summary_items:
                    summary_str = ', '.join(summary_items)
                    self.logger.info(f'{table_name} financial summary: {summary_str}')
                    
        except Exception as e:
            self.logger.warning(f'Failed to calculate financial summary for {table_name}: {e}')
        
        return financial_summary

    # ------------------------------------------------------------------
    # Streaming load path
    # ------------------------------------------------------------------

    def _read_csv_chunks(self, path: Path, chunk_rows: int) -> Iterator[pd.DataFrame]:
        """Yield raw chunks from one CSV, mirroring read_csv_file's fallbacks.

        Same three tiers as read_csv_file, but iterator-based so a file is never
        held whole.

        Tier 3 captures bad lines rather than using on_bad_lines='skip', and
        load_staging_file_group fails the table on a non-zero bad_line_count.
        This is defence in depth, not an active guard: because every tier passes
        names= and usecols=, pandas never classifies a line as bad - short rows
        are padded with NaN and long rows are truncated to the named columns, so
        on_bad_lines does not fire at all. Row count is therefore preserved by
        construction, and the reconciliation in load_staging_file_group is what
        actually protects it. The capture matters only if those kwargs change.

        Note the tiers can disagree on row count for a value containing an
        embedded newline: tier 1 keeps it as one row, tier 2 splits it into two.
        Tier 1 handles all 731 SM9641 files, so this is latent, not active.
        """
        encoding = self.detect_encoding(path)
        headers = pd.read_csv(path, nrows=0, sep=',', encoding=encoding,
                              dtype=str).columns.str.strip().tolist()
        cols = [c for c in headers if c and not str(c).startswith('Unnamed')]

        bad_lines: List[List[str]] = []

        def capture_bad_line(line: List[str]) -> None:
            """Tier 3 on_bad_lines hook: keep the row, do not emit it."""
            bad_lines.append(line)
            return None

        base = dict(sep=',', usecols=cols, index_col=False, names=cols, header=0,
                    encoding=encoding, dtype=str, chunksize=chunk_rows,
                    **na_read_options())
        tiers = (
            dict(base, on_bad_lines='warn'),
            dict(base, on_bad_lines='warn', quoting=3, skipinitialspace=True,
                 engine='python', encoding_errors='replace'),
            dict(base, on_bad_lines=capture_bad_line, quoting=3, engine='python'),
        )

        for tier_index, kwargs in enumerate(tiers, start=1):
            try:
                produced = False
                bad_lines.clear()
                with pd.read_csv(path, **kwargs) as reader:
                    for chunk in reader:
                        produced = True
                        yield chunk
                if tier_index > 1:
                    self.logger.warning(
                        f'{path.name}: parsed with recovery tier {tier_index}'
                    )
                if bad_lines:
                    self._record_bad_lines(path, bad_lines)
                return
            # UnicodeDecodeError is a ValueError, not a ParserError, so it used to
            # escape this loop entirely and tier 2 - the tier that sets
            # encoding_errors='replace' and would have recovered - never ran.
            except (pd.errors.ParserError, UnicodeDecodeError) as e:
                if produced:
                    # Already emitted rows on this tier; restarting would double
                    # them. Surface rather than silently truncate.
                    self.logger.error(
                        f'{path.name}: parser failed mid-file on tier {tier_index} '
                        f'after yielding rows: {type(e).__name__}: {e}'
                    )
                    raise
                if tier_index == len(tiers):
                    self.logger.error(
                        f'{path.name}: all parse tiers failed: {type(e).__name__}: {e}'
                    )
                    raise
                self.logger.warning(
                    f'{path.name}: tier {tier_index} failed ({type(e).__name__}: {e}); '
                    f'trying recovery tier {tier_index + 1}'
                )

    def _record_bad_lines(self, path: Path, bad_lines: List[List[str]]) -> None:
        """Persist and count rows the parser could not parse.

        Counting is what matters: load_staging_file_group folds bad_line_count
        into its reconciliation and fails the table, so these rows can never pass
        as a clean load. Writing them out is so they can actually be recovered.

        Unreachable while the read kwargs pass names=/usecols= (see
        _read_csv_chunks) - it exists so that a future kwargs change cannot
        reintroduce silent row loss.
        """
        self.bad_line_count += len(bad_lines)
        self.logger.error(
            f'{path.name}: {len(bad_lines)} malformed line(s) could not be parsed '
            f'and were NOT loaded'
        )

        if not self.reject_dir:
            for line in bad_lines[:5]:
                self.logger.error(f'  unparsed: {line}')
            if len(bad_lines) > 5:
                self.logger.error(f'  ... and {len(bad_lines) - 5} more')
            return

        try:
            target = Path(self.reject_dir) / f'rejected_{path.stem}.csv'
            with open(target, 'w', encoding='utf-8', newline='') as handle:
                csv.writer(handle).writerows(bad_lines)
            self.logger.error(f'  unparsed rows written to {target}')
        except Exception as e:
            # Never let a reject-file failure mask the rejects themselves.
            self.logger.error(f'  could not write reject file for {path.name}: {e}')
            for line in bad_lines[:5]:
                self.logger.error(f'  unparsed: {line}')

    def iter_clean_chunks(self, files: List[str], table_name: str,
                          chunk_rows: int = 50000) -> Iterator[pd.DataFrame]:
        """Stream files for one table as cleaned, table-aligned chunks.

        Equivalent to concat_files -> validate_columns -> clean_frame, but never
        materialises the whole table. Column metadata and the mapping are
        resolved once and reused for every chunk.
        """
        db_columns = self.get_table_columns(table_name)
        sql_columns = [info['name'] for info in db_columns.values()]

        mapping_frame: Optional[pd.DataFrame] = None
        mapping_path = f'column mapping/{table_name}.csv'
        if os.path.exists(mapping_path):
            try:
                mapping_frame = self.load_column_mapping(mapping_path)
            except Exception as e:
                self.logger.warning(f'Failed to load column mapping for {table_name}: {e}')

        for file_path in sorted(map(Path, files), key=self.get_sequence_number):
            for chunk in self._read_csv_chunks(file_path, chunk_rows):
                if chunk.empty:
                    continue

                # Drop header rows repeated inside the file. Test the first
                # column first: converting the whole chunk with astype(str)
                # materialises a Python string per cell, which on a 268-column
                # chunk is a multi-hundred-MB transient spike for a condition
                # that is almost never true.
                first_col = chunk.columns[0]
                candidates = chunk[first_col].astype(str).str.strip() == str(first_col)
                if candidates.any():
                    header_vals = pd.Series({c: c for c in chunk.columns}, dtype=str)
                    subset = chunk.loc[candidates].astype(str)
                    repeated = (subset.reindex(columns=header_vals.index)
                                == header_vals).all(axis=1)
                    drop_index = repeated[repeated].index
                    if len(drop_index):
                        chunk = chunk.drop(index=drop_index)
                if chunk.empty:
                    continue

                if mapping_frame is not None:
                    chunk = self.validate_columns(chunk, mapping_frame, table_name,
                                                  sql_columns=sql_columns)
                if db_columns:
                    chunk = self.clean_frame(chunk, db_columns)
                yield chunk

    def load_staging_file_group(self, files: List[str], table_name: str,
                                chunk_rows: int = 50000,
                                use_bcp: Optional[bool] = None) -> Dict[str, Any]:
        """Stream a table's files straight into staging, with bounded memory.
        """
        if not self.db_helper:
            raise RuntimeError('load_staging_file_group requires a database connection')

        if use_bcp is None:
            use_bcp = False
            if PREFER_BCP:
                ready, reason = self.db_helper.bcp_ready()
                use_bcp = ready
                if not ready and not getattr(self, '_bcp_fallback_logged', False):

                    self.logger.warning(f'Using the pandas sink because {reason}')
                    self._bcp_fallback_logged = True
        elif use_bcp:
            ready, reason = self.db_helper.bcp_ready()
            if not ready:
                self.logger.warning(
                    f'{table_name}: bcp requested but {reason}; using the pandas sink'
                )
                use_bcp = False

        accumulator = FinancialAccumulator(self.config, table_name)
        rows_read = 0
        rows_inserted = 0
        chunks = 0
        success = True
        error_message = ''
        start = time.time()
        self.bad_line_count = 0

        if use_bcp:
            # Chunks are written to the bcp data file as they are produced, so
            # the whole table is still never held in memory.
            counters = {'rows': 0, 'chunks': 0}

            def tracked_chunks() -> Iterator[pd.DataFrame]:
                for chunk in self.iter_clean_chunks(files, table_name,
                                                    chunk_rows=chunk_rows):
                    counters['rows'] += len(chunk)
                    counters['chunks'] += 1
                    accumulator.update(chunk)
                    yield chunk
                    if counters['chunks'] % 10 == 0:
                        gc.collect()

            success, rows_inserted = self.db_helper.bulk_insert_via_bcp(
                tracked_chunks(), table_name
            )
            rows_read = counters['rows']
            chunks = counters['chunks']
            if not success:
                error_message = 'bcp load failed or rejected rows'
        else:
            for chunk in self.iter_clean_chunks(files, table_name, chunk_rows=chunk_rows):
                chunks += 1
                rows_read += len(chunk)
                accumulator.update(chunk)

                ok, inserted = self.db_helper.bulk_insert_frame(chunk, table_name)
                rows_inserted += inserted
                if not ok:
                    success = False
                    error_message = f'insert failed on chunk {chunks}'
                    self.logger.error(f'{table_name}: {error_message}; aborting stream')
                    break

                del chunk
                if chunks % 10 == 0:
                    gc.collect()

        elapsed = time.time() - start
        if rows_read != rows_inserted and success:
            success = False
            error_message = (f'reconciliation mismatch: read {rows_read}, '
                             f'inserted {rows_inserted}')
            self.logger.error(f'{table_name}: {error_message}')

        # Rows the parser could not read never reach rows_read, so read ==
        # inserted would otherwise reconcile clean while data was missing.
        if self.bad_line_count and success:
            success = False
            error_message = (f'{self.bad_line_count} source line(s) could not be '
                             f'parsed and were not loaded')
            self.logger.error(f'{table_name}: {error_message}')

        self.logger.info(
            f'{table_name}: streamed {chunks} chunk(s), read {rows_read}, '
            f'inserted {rows_inserted} in {elapsed:.1f}s'
            + (f', {self.bad_line_count} unparsed' if self.bad_line_count else '')
        )
        return {
            'success': success,
            'rows_read': rows_read,
            'rows_inserted': rows_inserted,
            'rows_unparsed': self.bad_line_count,
            'chunks': chunks,
            'duration_seconds': round(elapsed, 2),
            'financial_summary': accumulator.result(),
            'error_message': error_message,
        }

    def group_files_by_table(self, files: List[str]) -> Dict[str, List[str]]:
        """Group files by their target table name."""
        table_groups = {}
        
        for file in files:
            keyword, table_name, customer_code = self.match_file(file)
            
            if table_name:
                if table_name not in table_groups:
                    table_groups[table_name] = []
                table_groups[table_name].append(file)
            else:
                self.logger.warning(f"Could not determine table for file: {os.path.basename(file)}")
        
        return table_groups

    def process_staging_file_group(self, files: List[str], table_name:str,mapping_path: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        Process a group of staging files (same table, different sequences).
        """
        try:
            # Concatenate files
            combined_df = self.concat_files(files)
            csv_rows = len(combined_df)
            
            if csv_rows == 0:
                self.logger.warning(f'{table_name} has no data to process')
                error_message = 'No data in files'
                return None

            # Get table info from first file
            first_file = files[0]
            keyword, table_name, customer_code = self.match_file(first_file)
            
            if not table_name:
                self.logger.error(f"Could not determine table name for {first_file}")
                return None

            self.logger.info(f"Processing {len(files)} files for table {table_name}")

            # Get database table columns
            db_columns = self.get_table_columns(table_name)
            sql_columns = [info['name'] for info in db_columns.values()]
            
            # Apply column mapping if provided
            mapping_file_path = f'column mapping/{table_name}.csv'
            if os.path.exists(mapping_file_path):
                try:
                    mapping_df = self.load_column_mapping(mapping_file_path)
                    combined_df = self.validate_columns(combined_df, mapping_df, table_name, sql_columns=sql_columns)
                    self.logger.info(f"Applied column mapping for {table_name}")
                except Exception as e:
                    self.logger.warning(f"Failed to apply column mapping for {table_name}: {e}")

            # Clean and convert data types
            if db_columns:
                combined_df = self.clean_frame(combined_df, db_columns)

            self.logger.info(f"Processed {len(combined_df)} rows for {table_name}")
            return combined_df
            
        except Exception as e:
            self.logger.error(f"Error processing staging file group: {e}")
            return None
           
    def cleanup(self):
        """Clean up resources - only close connections if we own them."""
        if self.config and self._owns_config:
            self.config.cleanup()
            self.logger.info("StagingProcessor closed own config connection")
        elif self.config:
            self.logger.debug("StagingProcessor using shared config - not closing")
            
        if self.db_helper and self._owns_db_connection:
            self.db_helper.close_connections()
            self.logger.info("StagingProcessor closed own database connection")
        elif self.db_helper:
            self.logger.debug("StagingProcessor using shared database connection - not closing")

    


# # Example usage
# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO)
#     # Initialize processor
#     processor = StagingProcessor('v10')
#     if processor.initialize():
#         #print("File paths:", processor.file_paths)
#         staging_metrics = processor.config.staging_metrics['RC_ACCOUNT_EXTRACT'].items()
#         print("Staging metrics config:", staging_metrics)
#         #processor.truncate_staging_tables()
#         # Process all staging files grouped by table
#         #results = processor.process_all_staging_files()
        
#         # Print summary
#         #processor.print_processing_summary(results)
        
   