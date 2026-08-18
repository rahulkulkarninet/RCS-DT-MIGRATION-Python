import os
import re
import logging
import inspect
import time
import re
import traceback
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from collections import OrderedDict
from config_parser import ConfigParser
from sqlalchemy import text
from process_staging import StagingProcessor



class SQLMigrationManager:
    """Manage SQL migration files with variable replacement and sequenced execution."""
    
    def __init__(self, environment: str, load_id: int = None, session_id: int = None,
                 entity_id: int = None,user: str = None, shared_db_helper=None,
                 shared_config_parser=None, customer_code: str = None,
                 db_name: str = None, run_id: str = None,
                 resume_load_id: int = None):

        self.environment = environment
        self.load_id = load_id
        self.session_id = session_id
        self.entity_id = entity_id
        self.user = user
        self.logger = logging.getLogger(__name__)

        # Provenance stamped on DT_Migration_SQLProgress checkpoint rows.
        self.customer_code = customer_code
        self.db_name = db_name
        self.run_id = run_id
        # When set, files already recorded complete for this LoadID are skipped.
        self.resume_load_id = resume_load_id

        # Use shared connections if provided
        if shared_config_parser is not None:
            self.logger.info("Using shared config parser for SQL Migration Manager")
            self.config_parser = shared_config_parser
            self._owns_config = False

            if not getattr(self.config_parser, '_database_vars_resolved', False):
                self.logger.info("Ensuring database variables are resolved with shared connection...")
                self.config_parser.resolve_database_vars()
        else:
            # Only create new config parser if none provided
            self.logger.info("Creating new config parser for SQL Migration Manager")
            self.config_parser = ConfigParser(
                db_environment=environment,
                shared_db_helper=shared_db_helper
            )
            self.config_parser.load_configs()
            self._owns_config = True

            if shared_db_helper is None:
                if self.config_parser.init_database():
                    self.config_parser.resolve_database_vars()
            else:
                # Even with shared helper, ensure variables are resolved
                self.config_parser.resolve_database_vars()
        
        # Validate that we have database variables
        self._validate_database_variables()

        # SQL file storage
        self.sql_files = OrderedDict()
        self.sql_base_path = None
        self.variable_pattern = re.compile(r'\{\{(\w+)\}\}')
        
        # Get metafield variables for dynamic file generation
        self.metafield_variables = self.config_parser.get_category_variables('metafield_variables')

        # Export path
        self.export_path = None

    def initialize(self) -> bool:
        """Initialize the SQL migration manager."""
        try:
            # Get SQL base path from config
            sql_path = self.config_parser.get_variable('SQL_PATH', 'path')
            if not sql_path:
                # Fallback to default location
                script_dir = os.path.dirname(os.path.abspath(__file__))
                sql_path = os.path.join(script_dir, 'SQL')
            
            self.sql_base_path = Path(sql_path)
            migration_queries_path = self.sql_base_path / 'Migration queries'
            
            if not migration_queries_path.exists():
                self.logger.error(f"Migration queries path not found: {migration_queries_path}")
                return False
            
            #self.logger.info(f"SQL migration path: {migration_queries_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize SQL migration manager: {e}")
            return False
        
    def _validate_database_variables(self):
        """Validate that essential database variables are resolved."""
        try:
            # Check if we have any lookup variables
            lookup_vars = self.config_parser.get_category_variables('lookup_variables')
            metafield_vars = self.config_parser.get_category_variables('metafield_variables')
            vwhost_vars = self.config_parser.get_category_variables('vwHost')

            total_db_vars = len(lookup_vars) + len(metafield_vars) + len(vwhost_vars)
            
            if total_db_vars == 0:
                self.logger.warning("No database variables resolved - this may cause missing variable warnings")
                self.logger.warning("Attempting to resolve database variables now...")
                
                # Force resolution if we have a database connection
                if self.config_parser.db_helper:
                    self.config_parser.resolve_database_vars()
                    
                    # Re-check
                    lookup_vars = self.config_parser.get_category_variables('lookup_variables')
                    metafield_vars = self.config_parser.get_category_variables('metafield_variables')
                    vwhost_vars = self.config_parser.get_category_variables('vwHost')
                    total_db_vars = len(lookup_vars) + len(metafield_vars) + len(vwhost_vars)
                    
                    if total_db_vars > 0:
                        self.logger.info(f"Successfully resolved {total_db_vars} database variables")
                    else:
                        self.logger.error("Still no database variables after forced resolution")
                else:
                    self.logger.error("No database helper available for variable resolution")
            else:
                self.logger.info(f"Database variables validation passed: {total_db_vars} variables resolved")
                
        except Exception as e:
            self.logger.error(f"Error validating database variables: {e}")

    def _log_variable_status(self):
        """Log the status of variable resolution for debugging."""
        try:
            categories = ['vwHost', 'lookup_variables', 'metafield_variables', 'constant_variables', 'path']
            
            self.logger.info("=== VARIABLE RESOLUTION STATUS ===")
            for category in categories:
                variables = self.config_parser.get_category_variables(category)
                self.logger.info(f"{category:20}: {len(variables):3d} variables")
                
                # Log first few variables for debugging
                if variables:
                    sample_vars = list(variables.items())[:3]
                    for name, value in sample_vars:
                        self.logger.debug(f"  {name}: {value}")
                    if len(variables) > 3:
                        self.logger.debug(f"  ... and {len(variables) - 3} more")
            
            # Check for common missing variables
            missing_critical_vars = []
            critical_vars = [
                'AccountStatusID_Creation', 'ContactTypeID_3PDM', 'RelationshipID_3PDM',
                'ContactDetailTypeID_Mobile', 'ContactDetailTypeID_Email', 
                'AddressTypeID_Home', 'DefaultCountryID'
            ]
            
            for var_name in critical_vars:
                if self.config_parser.get_variable(var_name) is None:
                    missing_critical_vars.append(var_name)
            
            if missing_critical_vars:
                self.logger.warning(f"Missing critical variables: {missing_critical_vars}")
            else:
                self.logger.info("All critical variables resolved successfully")
                
            self.logger.info("=== END VARIABLE STATUS ===")
            
        except Exception as e:
            self.logger.error(f"Error logging variable status: {e}")

        
    def check_status_codes(self) -> Tuple[str, List[str]]:
        """Fallback check for RC Debts with invalid status codes."""
        self.logger.info("Checking RC Debts with invalid status codes...")

        try:
            db_helper = self.config_parser.db_helper
            if not db_helper:
                raise RuntimeError("Shared database connection not available")

            rc_statuses = db_helper.execute_query(
                """
                SELECT DISTINCT CAST(MA_Status AS NVARCHAR(4000)) AS MA_Status
                FROM RC_ACCOUNT_EXTRACT
                WHERE MA_Status IS NOT NULL
                """
            )
            lookup_statuses = db_helper.execute_query(
                """
                SELECT DISTINCT CAST(AccountStatus AS NVARCHAR(4000)) AS AccountStatus
                FROM tblAccountStatus
                WHERE AccountStatus IS NOT NULL
                """
            )

            if rc_statuses.empty:
                return "All status codes are valid.", []

            rc_statuses['MA_Status'] = rc_statuses['MA_Status'].astype(str).str.strip()
            rc_statuses = rc_statuses[rc_statuses['MA_Status'] != ''].copy()
            rc_statuses['normalized'] = self._normalize_status_lookup_series(rc_statuses['MA_Status'])
            rc_statuses['status_key'] = self._status_match_key_series(rc_statuses['normalized'])

            if lookup_statuses.empty:
                invalid_statuses = rc_statuses['MA_Status'].drop_duplicates().tolist()
            else:
                lookup_statuses['AccountStatus'] = lookup_statuses['AccountStatus'].astype(str).str.strip()
                lookup_statuses = lookup_statuses[lookup_statuses['AccountStatus'] != ''].copy()
                lookup_statuses['normalized'] = self._normalize_status_lookup_series(lookup_statuses['AccountStatus'])
                lookup_statuses['status_key'] = self._status_match_key_series(lookup_statuses['normalized'])
                lookup_keys = set(lookup_statuses['status_key'].dropna().tolist())
                invalid_statuses = (
                    rc_statuses[~rc_statuses['status_key'].isin(lookup_keys)]['MA_Status']
                    .drop_duplicates()
                    .tolist()
                )

            if invalid_statuses:
                self.logger.warning(f"Found invalid status codes: {', '.join(invalid_statuses)}")
                return f"Invalid status codes found: {', '.join(invalid_statuses)}", invalid_statuses

            return "All status codes are valid.", []

        except Exception as e:
            self.logger.warning(f"Error checking status codes: {e}")
            return f"Error checking status codes: {e}", []

    def _normalize_status_lookup_series(self, series: pd.Series) -> pd.Series:
        normalized = series.fillna('').astype(str).str.strip().str.upper()
        normalized = normalized.str.replace('â€“', '-', regex=False)
        normalized = normalized.str.replace('â€”', '-', regex=False)
        normalized = normalized.str.replace('�', '-', regex=False)
        normalized = normalized.str.replace('Â', ' ', regex=False)
        normalized = normalized.str.replace('\u2013', '-', regex=False)
        normalized = normalized.str.replace('\u2014', '-', regex=False)
        normalized = normalized.str.replace('\u00A0', ' ', regex=False)
        normalized = normalized.str.replace(r'�+', '-', regex=True)
        normalized = normalized.str.replace(r'\s+', ' ', regex=True).str.strip()
        return normalized

    def _status_match_key_series(self, series: pd.Series) -> pd.Series:
        return series.fillna('').astype(str).str.upper().str.replace(r'[^A-Z0-9]+', '', regex=True)

    def scan_sql_files(self) -> Dict[str, Dict[str, Any]]:
        """
        Scan Migration queries folder and organize SQL files by sequence in their respective folders.
        """
        migration_path = self.sql_base_path / 'Migration queries'
        sql_files = OrderedDict()
        
        # Define subfolder processing order
        subfolder_order = ['Direct', 'Loop', 'Metavalue_AccountSpecifics']
        
        for subfolder in subfolder_order:
            subfolder_path = migration_path / subfolder
            if not subfolder_path.exists():
                self.logger.warning(f"Subfolder not found: {subfolder}")
                continue

            #self.logger.info(f"Scanning subfolder: {subfolder}")

            # Get all SQL files in subfolder
            sql_file_paths = list(subfolder_path.glob('*.sql'))
            sql_file_paths.sort()  # Sort alphabetically
            
            for file_path in sql_file_paths:
                try:
                    # Extract sequence number and name from filename
                    filename = file_path.stem
                    sequence_info = self._parse_filename(filename)
                    
                    if sequence_info:
                        sequence_num, table_name = sequence_info
                        
                        # Read file content
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Handle special cases for Loop and Metavalue_AccountSpecifics
                        if subfolder == 'Loop' and sequence_num in [6, 7, 8]:
                            # Generate multiple files for each metafield variable
                            self._generate_loop_files(sql_files, sequence_num, table_name, content, subfolder, str(file_path))
                        elif subfolder == 'Metavalue_AccountSpecifics':
                            # Handle metavalue files with specific variable replacement
                            self._process_metavalue_file(sql_files, sequence_num, table_name, content, subfolder, str(file_path))
                        else:
                            # Standard file processing
                            sequence_key = f"{sequence_num:02d}.{table_name}"
                            sql_files[sequence_key] = {
                                'sequence': sequence_num,
                                'table_name': table_name,
                                'subfolder': subfolder,
                                'filename': filename,
                                'path': str(file_path),
                                'content': content,
                                'variables_found': self._extract_variables(content)
                            }
                        
                        self.logger.debug(f"Processed SQL file: {filename} from {subfolder}")
                    else:
                        self.logger.warning(f"Could not parse filename: {filename}")
                                        
                except Exception as e:
                    self.logger.error(f"Error processing file {file_path}: {e}")
        
        self.sql_files = sql_files

        self.logger.info(f"Found {len(sql_files)} SQL files (including generated variants) across {len(subfolder_order)} subfolders")
        return sql_files
    
    def _generate_loop_files(self, sql_files: OrderedDict, sequence_num: int, table_name: str, 
                            content: str, subfolder: str, original_path: str):
        """
        Generate multiple files for Loop sequences 06, 07, 08 - one for each metafield variable.
        Example: 06.tblentity_AccountSpecifics becomes 06.tblentity_AccountSpecifics_MIMO, etc.
        """
        for metafield_name, metafield_value in self.metafield_variables.items():
            if metafield_value is not None:  # Only generate for variables with values
                # Create new filename with metafield suffix
                new_table_name = f"{table_name}_{metafield_name}"
                sequence_key = f"{sequence_num:02d}.{new_table_name}"
                
                # Replace {{AccountSpecificsGroupID}} with the specific metafield value
                modified_content = content.replace('{{AccountSpecificsGroupID}}', str(metafield_value))
                
                sql_files[sequence_key] = {
                    'sequence': sequence_num,
                    'table_name': new_table_name,
                    'subfolder': subfolder,
                    'filename': f"{sequence_num:02d}.{new_table_name}",
                    'path': original_path,
                    'content': modified_content,
                    'variables_found': self._extract_variables(modified_content),
                    'metafield_variant': metafield_name,
                    'metafield_value': metafield_value,
                    'original_table_name': table_name
                }
                
                self.logger.debug(f"Generated Loop variant: {sequence_key} with {metafield_name}={metafield_value}")
    
    def _process_metavalue_file(self, sql_files: OrderedDict, sequence_num: int, table_name: str, 
                               content: str, subfolder: str, file_path: str):
        """
        Process Metavalue_AccountSpecifics files and replace variables based on filename.
        Example: 11.tblmetavalue_accountspecifics_MIMO replaces {{AccountSpecificsGroupID_MIMO}}
        """
        sequence_key = f"{sequence_num:02d}.{table_name}"
        
        # Extract metafield name from filename if present
        metafield_name = None
        for field_name in self.metafield_variables.keys():
            if field_name.upper() in table_name.upper():
                metafield_name = field_name
                break
        
        # Process the content
        modified_content = content
        variables_found = self._extract_variables(content)
        
        # Replace AccountSpecificsGroupID_[metafield] variables
        if metafield_name and metafield_name in self.metafield_variables:
            metafield_value = self.metafield_variables[metafield_name]
            
            # Look for pattern {{AccountSpecificsGroupID_[metafield_name]}}
            pattern_to_replace = f"{{{{AccountSpecificsGroupID_{metafield_name}}}}}"
            if pattern_to_replace in modified_content:
                modified_content = modified_content.replace(pattern_to_replace, str(metafield_value))
                self.logger.debug(f"Replaced {pattern_to_replace} with {metafield_value} in {sequence_key}")
        
        sql_files[sequence_key] = {
            'sequence': sequence_num,
            'table_name': table_name,
            'subfolder': subfolder,
            'filename': f"{sequence_num:02d}.{table_name}",
            'path': file_path,
            'content': modified_content,
            'variables_found': self._extract_variables(modified_content),
            'metafield_matched': metafield_name,
            'metafield_value': self.metafield_variables.get(metafield_name) if metafield_name else None
        }
    
    def _parse_filename(self, filename: str) -> Optional[Tuple[int, str]]:
        """
        Parse filename to extract sequence number and table name.
        Examples: 
        - '01.tblaccount' -> (1, 'tblaccount')
        - '04.getmedinv_for_tblprincipal' -> (4, 'getmedinv_for_tblprincipal')
        """
        try:
            # Pattern: number.name or just name
            if '.' in filename and filename[0].isdigit():
                parts = filename.split('.', 1)
                sequence_num = int(parts[0])
                table_name = parts[1]
                return (sequence_num, table_name)
            else:
                # No sequence number, assign high number to run last
                return (999, filename)
        except (ValueError, IndexError):
            return None
    
    def _extract_variables(self, sql_content: str) -> List[str]:
        """Extract all {{variable}} patterns from SQL content."""
        return self.variable_pattern.findall(sql_content)
    
    def get_variable_value(self, variable_name: str) -> Any:
        """Get variable value from config parser"""
        if variable_name == 'LoadID':
            return self.load_id
        elif variable_name == 'CurrentSessionID':
            return self.session_id
        elif variable_name == 'EntityID':
            return self.entity_id
        
        # Check if it's a specific AccountSpecificsGroupID variable
        if variable_name.startswith('AccountSpecificsGroupID_'):
            metafield_name = variable_name.replace('AccountSpecificsGroupID_', '')
            
            # Try exact match first
            metafield_value = self.metafield_variables.get(metafield_name)
            if metafield_value is not None:
                return metafield_value
            
            # Try uppercase match (since config parser converts to uppercase)
            metafield_value = self.metafield_variables.get(metafield_name.upper())
            if metafield_value is not None:
                return metafield_value
            
            self.logger.warning(f"Metafield variable not found: {metafield_name} (also tried: {metafield_name.upper()})")
            return None
        
        # Standard variable lookup
        value = self.config_parser.get_variable(variable_name)
        if value is not None:
            return value
        
        self.logger.warning(f"Variable not found: {variable_name}")
        return None
    
    def replace_variables_in_sql(self, sql_content: str) -> str:
        """Replace all {{variable}} patterns in SQL content with actual values."""
        def replace_var(match):
            var_name = match.group(1)
            value = self.get_variable_value(var_name)
            
            if isinstance(value, str):
                if value.startswith("'") and value.endswith("'"):
                    return value
                elif any(keyword in value.upper() for keyword in ['NULL', 'GETDATE()', 'NEWID()']):
                    return value
                else:
                    return f"'{value}'"
            elif value is None:
                return 'NULL'
            else:
                return str(value)
        
        return self.variable_pattern.sub(replace_var, sql_content)
    
    def get_sql_files_in_range(self, start_seq: int = None, end_seq: int = None) -> OrderedDict:
        """
        Get SQL files within a specific sequence range.
        """
        if not self.sql_files:
            self.scan_sql_files()
        
        filtered_files = OrderedDict()
        
        for key, file_info in self.sql_files.items():
            sequence = file_info['sequence']
            
            # Apply range filter
            if start_seq is not None and sequence < start_seq:
                continue
            if end_seq is not None and sequence > end_seq:
                continue
            
            filtered_files[key] = file_info
        
        return filtered_files
    
    def prepare_sql_for_execution(self, sequence_range: Tuple[int, int] = None) -> Dict[str, Dict[str, Any]]:
        """
        Prepare SQL files for execution with variable replacement.
        """
        if sequence_range:
            start_seq, end_seq = sequence_range
            files_to_process = self.get_sql_files_in_range(start_seq, end_seq)
        else:
            files_to_process =  self.scan_sql_files()
        
        prepared_sql = OrderedDict()
        
        for key, file_info in files_to_process.items():
            try:
                # Replace variables in SQL content
                original_content = file_info['content']
                processed_content = self.replace_variables_in_sql(original_content)
                
                # Count replaced variables
                original_vars = len(file_info['variables_found'])
                remaining_vars = len(self._extract_variables(processed_content))
                replaced_vars = original_vars - remaining_vars
                
                prepared_sql[key] = {
                    **file_info,
                    'processed_content': processed_content,
                    'original_variables': file_info['variables_found'],
                    'variables_replaced': replaced_vars,
                    'variables_remaining': remaining_vars,
                    'ready_for_execution': remaining_vars == 0
                }
                
                if remaining_vars > 0:
                    remaining_var_names = self._extract_variables(processed_content)
                    self.logger.warning(f"Unresolved variables in {key}: {remaining_var_names}")
                
            except Exception as e:
                self.logger.error(f"Error preparing SQL for {key}: {e}")
                prepared_sql[key] = {
                    **file_info,
                    'processed_content': file_info['content'],
                    'error': str(e),
                    'ready_for_execution': False
                }
        
        return prepared_sql
    
    def export_prepared_sql(self, prepared_sql: OrderedDict, export_path: str) -> Dict[str, Any]:
        """
        Export prepared SQL files to a single folder in sequential order.
        """        
        export_folder = Path(export_path)
        exported_files = []
        export_errors = []
        master_file_path = None
        
        try:
            self.logger.info(f"Exporting {len(prepared_sql)} SQL files to single folder: {export_folder}")

            for key, sql_info in prepared_sql.items():
                try:
                    # Get sequence and table info
                    sequence = sql_info.get('sequence')
                    table_name = sql_info.get('table_name')
                    original_subfolder = sql_info.get('subfolder')  
                    
                    # Create filename with sequence number for proper ordering
                    filename = f"{sequence:03d}.{table_name}_READY.sql"
                    file_path = export_folder / filename
                    
                    # Prepare file header with metadata
                    header_lines = [
                        f"-- SQL Migration File",
                        f"-- Sequence: {sequence}",
                        f"-- Table: {table_name}",
                        f"-- Original Subfolder: {original_subfolder}",
                        f"-- Export Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        f"-- LoadID: {self.load_id}",
                        f"-- SessionID: {self.session_id}",
                        f"-- EntityID: {self.entity_id}",
                        f"-- Environment: {self.environment}",
                        "-- " + "="*60,
                        ""
                    ]
                    
                    # Get the SQL content
                    sql_content = sql_info.get('processed_content', sql_info.get('content', ''))

                    if not sql_content:
                        self.logger.warning(f"No SQL content found for {key}")
                        sql_content = f"-- No SQL content available for {table_name}\n-- This is a placeholder\n"
                    
                    # Write the complete file
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(header_lines))
                        f.write(sql_content)
                    
                    exported_files.append(str(file_path))
                    self.logger.debug(f"Exported sequence {sequence:03d}: {filename}")
                    
                except Exception as e:
                    error_msg = f"Failed to export {key}: {e}"
                    export_errors.append(error_msg)
                    self.logger.error(error_msg)

            # Create master execution file using :r commands
            master_file_path = self._create_master_execution_file(export_folder, exported_files)
            
            # Log export summary
            self.logger.info(f"Successfully exported {len(exported_files)} SQL files")
            if master_file_path:
                self.logger.info(f"Created master execution file using :r commands: {master_file_path}")
            
            if export_errors:
                self.logger.warning(f"Export errors ({len(export_errors)}):")
                for error in export_errors:
                    self.logger.warning(f"  {error}")
            
            return {
                'exported_files': exported_files,
                'master_file': str(master_file_path) if master_file_path else None,
                'export_errors': export_errors,
                'total_exported': len(exported_files),
                'export_success': len(export_errors) == 0
            }
            
        except Exception as e:
            self.logger.error(f"Critical error during SQL export: {e}")
            return {
                'exported_files': exported_files,
                'master_file': str(master_file_path) if master_file_path else None,
                'export_errors': export_errors + [str(e)],
                'total_exported': len(exported_files),
                'export_success': False
            }

    def debug_master_file_syntax(self, master_file_path: Path, customer_logger: logging.Logger):
        """Debug master file to identify syntax issues around specific line numbers."""
        try:
            with open(master_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            customer_logger.info(f"=== DEBUGGING MASTER FILE SYNTAX ===")
            customer_logger.info(f"Total lines in master file: {len(lines)}")
            customer_logger.info(f"Error reported at line: 7095")
            
            # Show lines around the error
            error_line = 7095
            start_line = max(1, error_line - 10)
            end_line = min(len(lines), error_line + 10)
            
            customer_logger.info(f"Lines {start_line} to {end_line}:")
            for i in range(start_line - 1, end_line):
                line_num = i + 1
                line_content = lines[i].rstrip()
                marker = " <<<< ERROR LINE" if line_num == error_line else ""
                customer_logger.info(f"{line_num:5d}: {line_content}{marker}")
            
            # Check for common syntax issues around that line
            if error_line <= len(lines):
                error_line_content = lines[error_line - 1].strip()
                customer_logger.info(f"Error line content: '{error_line_content}'")
                
                # Check for common issues
                issues = []
                if error_line_content.endswith(';;'):
                    issues.append("Double semicolon detected")
                if "'" in error_line_content and error_line_content.count("'") % 2 != 0:
                    issues.append("Unmatched single quote")
                if '"' in error_line_content and error_line_content.count('"') % 2 != 0:
                    issues.append("Unmatched double quote")
                if error_line_content.startswith(':r') and not error_line_content.startswith(':r "'):
                    issues.append("Invalid :r command format")
                
                if issues:
                    customer_logger.error(f"Potential syntax issues found: {issues}")
                
            # Find which SQL file this line might be in
            current_file = None
            
            for i, line in enumerate(lines, 1):
                if ':r "' in line:
                    # Extract file path from :r command
                    import re
                    match = re.search(r':r\s+"([^"]+)"', line)
                    if match:
                        current_file = match.group(1)
                        customer_logger.info(f"Line {i}: :r command for {Path(current_file).name}")
                
                if i == error_line:
                    if current_file:
                        customer_logger.error(f"Error likely in file: {Path(current_file).name}")
                        # Check the actual SQL file
                        self._debug_individual_sql_file(current_file, customer_logger)
                    break
            
        except Exception as e:
            customer_logger.error(f"Error debugging master file syntax: {e}")

    def _debug_individual_sql_file(self, sql_file_path: str, customer_logger: logging.Logger):
        """Debug individual SQL file for syntax issues."""
        try:
            customer_logger.info(f"=== DEBUGGING SQL FILE: {Path(sql_file_path).name} ===")
            
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            customer_logger.info(f"SQL file has {len(lines)} lines")
            
            # Check for common syntax issues
            issues = []
            
            # Check for unmatched quotes
            single_quotes = content.count("'")
            if single_quotes % 2 != 0:
                issues.append(f"Unmatched single quotes (count: {single_quotes})")
            
            # Check for double semicolons
            double_semicolons = content.count(';;')
            if double_semicolons > 0:
                issues.append(f"Double semicolons found ({double_semicolons} instances)")
            
            # Check for null bytes
            if '\x00' in content:
                issues.append("Null bytes found")
            
            # Check last few lines
            customer_logger.info("Last 10 lines of SQL file:")
            for i, line in enumerate(lines[-10:], len(lines) - 9):
                line_clean = line.rstrip()
                customer_logger.info(f"SQL Line {i:4d}: {line_clean}")
            
            # Check if file ends properly
            if not content.strip().endswith(';'):
                issues.append("File doesn't end with semicolon")
            
            if content.strip().endswith(';;'):
                issues.append("File ends with double semicolon")
            
            if issues:
                customer_logger.error(f"Syntax issues found in {Path(sql_file_path).name}:")
                for issue in issues:
                    customer_logger.error(f"  - {issue}")
            else:
                customer_logger.info(f"No obvious syntax issues found in {Path(sql_file_path).name}")
            
            return issues
            
        except Exception as e:
            customer_logger.error(f"Error debugging SQL file {sql_file_path}: {e}")
            return [f"Debug error: {str(e)}"]

    def validate_individual_sql_files(self, export_folder: Path, customer_logger: logging.Logger) -> Dict[str, Any]:
        """Validate individual SQL files for syntax issues."""
        try:
            # Ensure export_folder is a Path object
            if isinstance(export_folder, (str, list)):
                if isinstance(export_folder, list):
                    # If it's a list, take the parent directory of the first file
                    if export_folder:
                        export_path = Path(export_folder[0]).parent
                    else:
                        customer_logger.error("Empty file list provided")
                        return {'total_files': 0, 'valid_files': 0, 'syntax_errors': [], 'encoding_errors': []}
                else:
                    export_path = Path(export_folder)
            else:
                export_path = Path(export_folder)
            
            customer_logger.info(f"Validating SQL files in: {export_path}")
            
            sql_files = list(export_path.glob('*_READY.sql'))
            validation_results = {
                'total_files': len(sql_files),
                'valid_files': 0,
                'syntax_errors': [],
                'encoding_errors': []
            }
            
            customer_logger.info(f"Found {len(sql_files)} SQL files to validate...")
            
            for sql_file in sql_files:
                try:
                    with open(sql_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Check for basic syntax issues
                    issues = []
                    
                    # Check for unmatched quotes
                    single_quotes = content.count("'")
                    if single_quotes % 2 != 0:
                        issues.append("Unmatched single quotes")
                    
                    # Check for proper statement termination
                    content_stripped = content.strip()
                    if content_stripped and not content_stripped.endswith(';'):
                        issues.append("Missing final semicolon")
                    
                    # Check for double semicolons
                    if ';;' in content:
                        issues.append("Double semicolons found")
                    
                    # Check for common encoding issues
                    if '\x00' in content:
                        issues.append("Null bytes found")
                    
                    # Check for empty or whitespace-only content
                    if not content_stripped:
                        issues.append("Empty file")
                    
                    if issues:
                        validation_results['syntax_errors'].append({
                            'file': sql_file.name,
                            'issues': issues
                        })
                        customer_logger.warning(f"Syntax issues in {sql_file.name}: {issues}")
                    else:
                        validation_results['valid_files'] += 1
                        customer_logger.debug(f"{sql_file.name} - OK")
                    
                except UnicodeDecodeError as e:
                    validation_results['encoding_errors'].append({
                        'file': sql_file.name,
                        'error': str(e)
                    })
                    customer_logger.error(f"Encoding error in {sql_file.name}: {e}")
                
                except Exception as e:
                    validation_results['syntax_errors'].append({
                        'file': sql_file.name,
                        'issues': [f"Read error: {str(e)}"]
                    })
                    customer_logger.error(f"Error reading {sql_file.name}: {e}")
            
            customer_logger.info(f"Validation complete: {validation_results['valid_files']}/{validation_results['total_files']} files OK")
            
            if validation_results['syntax_errors']:
                customer_logger.error("Files with syntax errors:")
                for error in validation_results['syntax_errors']:
                    customer_logger.error(f"  {error['file']}: {error['issues']}")
            
            return validation_results
            
        except Exception as e:
            customer_logger.error(f"Error validating individual SQL files: {e}")
            import traceback
            customer_logger.error(f"Traceback: {traceback.format_exc()}")
            return {'total_files': 0, 'valid_files': 0, 'syntax_errors': [], 'encoding_errors': []}

    def fix_sql_file_syntax_issues(self, export_folder, customer_logger: logging.Logger) -> int:
        """Attempt to fix common syntax issues in SQL files."""
        try:
            # Ensure export_folder is a Path object
            if isinstance(export_folder, (str, list)):
                if isinstance(export_folder, list):
                    if export_folder:
                        export_path = Path(export_folder[0]).parent
                    else:
                        customer_logger.error("Empty file list provided")
                        return 0
                else:
                    export_path = Path(export_folder)
            else:
                export_path = Path(export_folder)
            
            customer_logger.info(f"Attempting to fix syntax issues in: {export_path}")
            
            sql_files = list(export_path.glob('*_READY.sql'))
            fixed_count = 0
            
            customer_logger.info(f"Found {len(sql_files)} SQL files to check...")
            
            for sql_file in sql_files:
                try:
                    with open(sql_file, 'r', encoding='utf-8') as f:
                        original_content = f.read()
                    
                    fixed_content = original_content
                    changes_made = []
                    
                    # Fix double semicolons
                    if ';;' in fixed_content:
                        fixed_content = fixed_content.replace(';;', ';')
                        changes_made.append("Removed double semicolons")
                    
                    # Ensure file ends with single semicolon
                    content_stripped = fixed_content.strip()
                    if content_stripped and not content_stripped.endswith(';'):
                        fixed_content = content_stripped + ';\n'
                        changes_made.append("Added missing final semicolon")
                    elif content_stripped.endswith(';;'):
                        fixed_content = content_stripped[:-1] + '\n'
                        changes_made.append("Fixed double semicolon at end")
                    
                    # Remove null bytes
                    if '\x00' in fixed_content:
                        fixed_content = fixed_content.replace('\x00', '')
                        changes_made.append("Removed null bytes")
                    
                    # If changes were made, write back the file
                    if changes_made:
                        # Create backup
                        backup_path = sql_file.with_suffix('.sql.bak')
                        if not backup_path.exists():  # Don't overwrite existing backup
                            sql_file.rename(backup_path)
                            customer_logger.info(f"Created backup: {backup_path.name}")
                        
                        # Write fixed content
                        with open(sql_file, 'w', encoding='utf-8') as f:
                            f.write(fixed_content)
                        
                        fixed_count += 1
                        customer_logger.info(f"Fixed {sql_file.name}: {', '.join(changes_made)}")
                    
                except Exception as e:
                    customer_logger.error(f"Error fixing {sql_file.name}: {e}")
                    continue
            
            customer_logger.info(f"Fixed syntax issues in {fixed_count} files")
            return fixed_count
            
        except Exception as e:
            customer_logger.error(f"Error fixing SQL file syntax issues: {e}")
            import traceback
            customer_logger.error(f"Traceback: {traceback.format_exc()}")
            return 0
        
    def _build_master_file_content(self, file_info_list: List[Tuple[int, str, str]]) -> str:
        """Build master file content with transaction control and error handling."""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_files = len(file_info_list)
        
        # Build file list for header
        file_list = "\n".join([
            f"    {i:2d}. Sequence {seq:03d}: {Path(file_path).name}" 
            for i, (seq, file_path, filename) in enumerate(file_info_list, 1)
        ])
        
        # Build execution commands with transaction control
        execution_commands = []
        for i, (seq, file_path, filename) in enumerate(file_info_list, 1):
            full_path = str(Path(file_path).resolve())
            escaped_path = full_path.replace('"', '""')
        
            execution_commands.append(f"""-- ========================================
-- File {i}/{total_files}: {filename} (Sequence {seq:03d})
-- ========================================
SET @CurrentFileNum = {i};
SET @CurrentFile = '{filename}';
SET @FileStartTime = GETDATE();

PRINT 'Executing file ' + CAST(@CurrentFileNum AS VARCHAR(10)) + '/' + CAST(@TotalFiles AS VARCHAR(10)) + ': ' + @CurrentFile;

-- Execute SQL file within transaction
:r "{escaped_path}"

-- Check for errors after file execution
IF @@ERROR <> 0
BEGIN
    PRINT 'ERROR: File execution failed for ' + @CurrentFile;
    ROLLBACK TRANSACTION;
    RAISERROR('Transaction rolled back due to error in file execution', 16, 1);
    RETURN;
END

SET @FileEndTime = GETDATE();
PRINT 'Completed ' + @CurrentFile + ' in ' + CAST(DATEDIFF(second, @FileStartTime, @FileEndTime) AS VARCHAR(10)) + ' seconds';
PRINT '';""")
    
        execution_block = "\n".join(execution_commands)
        
        # Create the master file content with transaction control
        return f"""/*
================================================================================
MASTER SQL EXECUTION FILE - TRANSACTION CONTROLLED
================================================================================
Generated: {timestamp}
Environment: {self.environment}
LoadID: {self.load_id}
SessionID: {self.session_id}
EntityID: {self.entity_id}
Total Files: {total_files}

TRANSACTION MODE: Single transaction for all files
ERROR HANDLING: First error causes complete rollback

USAGE:
  sqlcmd -S server -d database -E -i "MASTER_EXECUTE_ALL.sql"

EXECUTION ORDER:
{file_list}
================================================================================
*/

-- SQLCMD Setup
SET NOCOUNT ON;
SET ANSI_WARNINGS OFF;
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET XACT_ABORT ON;  -- Automatically rollback on error

-- Master execution variables
DECLARE @StartTime DATETIME = GETDATE();
DECLARE @CurrentFile VARCHAR(200);
DECLARE @FileStartTime DATETIME;
DECLARE @FileEndTime DATETIME;
DECLARE @TotalFiles INT = {total_files};
DECLARE @CurrentFileNum INT = 0;

-- Begin single transaction for all files
BEGIN TRANSACTION;

-- Header
PRINT '';
PRINT '********************************************************************************';
PRINT 'MASTER SQL EXECUTION STARTING - TRANSACTION CONTROLLED';
PRINT '********************************************************************************';
PRINT 'Environment: {self.environment}';
PRINT 'LoadID: {self.load_id}';
PRINT 'SessionID: {self.session_id}';
PRINT 'EntityID: {self.entity_id}';
PRINT 'Total files: {total_files}';
PRINT 'Start time: ' + CONVERT(VARCHAR, GETDATE(), 120);
PRINT '';

-- Execute all files within single transaction
{execution_block}

-- If we reach here, all files executed successfully
COMMIT TRANSACTION;

-- Final summary
DECLARE @EndTime DATETIME = GETDATE();
DECLARE @TotalSeconds INT = DATEDIFF(second, @StartTime, @EndTime);

PRINT '';
PRINT '********************************************************************************';
PRINT 'MASTER EXECUTION COMPLETED SUCCESSFULLY';
PRINT '********************************************************************************';
PRINT 'Total execution time: ' + CAST(@TotalSeconds AS VARCHAR(10)) + ' seconds';
PRINT 'Files processed: ' + CAST(@TotalFiles AS VARCHAR(10));
PRINT 'Transaction: COMMITTED';
PRINT '';

SELECT 
    'MASTER_EXECUTION_COMPLETE' as ExecutionStatus,
    @TotalFiles as FilesProcessed,
    @TotalSeconds as ExecutionTimeSeconds,
    'COMMITTED' as TransactionStatus,
    GETDATE() as CompletionTime;

PRINT 'All files executed successfully within single transaction.';"""
        
    def _create_master_execution_file(self, export_folder: Path, exported_files: List[str]) -> Optional[Path]:
        """Create master execution file using :r commands with full paths."""
        try:
            master_file_path = export_folder / "MASTER_EXECUTE_ALL.sql"
            
            # Sort and validate files by sequence number
            file_info_list = []
            path_validation_errors = []
            
            for file_path_str in exported_files:
                file_path = Path(file_path_str)
                file_name = file_path.name
                
                # Validate file exists
                if not file_path.exists():
                    path_validation_errors.append(f"File not found: {file_path}")
                    continue
                
                try:
                    sequence_str = file_name.split('.')[0]
                    sequence_num = int(sequence_str)
                    
                    # Get absolute path for :r command
                    absolute_path = file_path.resolve()
                    
                    file_info_list.append((sequence_num, str(absolute_path), file_name))
                    self.logger.debug(f"Added to master file: {file_name} -> {absolute_path}")
                    
                except (ValueError, IndexError):
                    self.logger.warning(f"Could not extract sequence from {file_name}")
                    absolute_path = file_path.resolve()
                    file_info_list.append((999, str(absolute_path), file_name))
            
            if path_validation_errors:
                self.logger.warning(f"Path validation errors: {path_validation_errors}")
            
            if not file_info_list:
                self.logger.error("No valid files found for master execution file")
                return None
            
            file_info_list.sort(key=lambda x: x[0])
            
            # Use :r commands with absolute paths only
            master_content = self._build_master_file_content(file_info_list)
            method_used = ":r commands with absolute paths"
            
            # Write master file with UTF-8 encoding (important for SQLCMD)
            with open(master_file_path, 'w', encoding='utf-8', newline='\r\n') as f:
                f.write(master_content)
            
            # Validate master file was created
            if master_file_path.exists():
                file_size = master_file_path.stat().st_size
                #self.logger.info(f"Created master execution file using {method_used}: {master_file_path}")
                #self.logger.info(f"Master file size: {file_size:,} bytes with {len(file_info_list)} SQL files")
                
                # Log first few paths for verification
                self.logger.debug("First 3 file paths in master file:")
                for i, (seq, path, name) in enumerate(file_info_list[:3], 1):
                    self.logger.debug(f"  {i}. {name} -> {path}")
                
                return master_file_path
            else:
                self.logger.error("Master file was not created successfully")
                return None
                
        except Exception as e:
            self.logger.error(f"Error creating master execution file: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None
        

    def _scan_exported_sql_files(self, export_path: Path, sequence_range: Tuple[int, int] = None) -> OrderedDict:
        """
        Scan exported SQL files from a single folder and organize by sequence number.
        """
        # Ensure export_path is a Path object
        if isinstance(export_path, str):
            export_path = Path(export_path)
        else:
            export_path = Path(export_path)

        sql_files = OrderedDict()
        
        # Get all _READY.sql files directly from the export folder (no subfolders)
        ready_files = list(export_path.glob('*_READY.sql'))
        
        self.logger.info(f"Found {len(ready_files)} ready files in {export_path}")
        
        # Parse and sort all files by sequence number
        file_info_list = []
        parsing_errors = []
        
        for file_path in ready_files:
            try:
                filename = file_path.stem.replace('_READY', '')
                sequence_info = self._parse_filename(filename)
                
                if sequence_info:
                    sequence_num, table_name = sequence_info
                    
                    # Apply sequence range filter if provided
                    if sequence_range:
                        start_seq, end_seq = sequence_range
                        if sequence_num < start_seq or sequence_num > end_seq:
                            self.logger.debug(f"Excluding sequence {sequence_num} (outside range {start_seq}-{end_seq})")
                            continue
                    
                    file_info_list.append({
                        'sequence': sequence_num,
                        'table_name': table_name,
                        'subfolder': 'ExecutedQueries',  # All files are now in the main folder
                        'filename': filename,
                        'file_path': file_path,
                        'original_filename': file_path.name
                    })
                    
                    self.logger.debug(f"Parsed {file_path.name}: sequence={sequence_num}, table={table_name}")
                    
                else:
                    parsing_errors.append(file_path.name)
                    self.logger.warning(f"Could not parse sequence from filename: {file_path.name}")
                    
            except Exception as e:
                parsing_errors.append(f"{file_path.name} ({str(e)})")
                self.logger.error(f"Error processing exported file {file_path}: {e}")
        
        if parsing_errors:
            self.logger.warning(f"Failed to parse {len(parsing_errors)} files: {parsing_errors}")


        file_info_list.sort(key=lambda x: (x['sequence'], str(x.get('filename', ''))))
        
        # Log the sequence order for debugging
        sequences = [info['sequence'] for info in file_info_list]
        #self.logger.info(f"File sequence order after sorting: {sequences}")
        
        # Validate sequence continuity
        if sequences:
            missing_sequences = []
            expected_range = range(min(sequences), max(sequences) + 1)
            for i in expected_range:
                if i not in sequences:
                    missing_sequences.append(i)
            
            if missing_sequences:
                self.logger.warning(f"Missing sequences detected: {missing_sequences}")
            else:
                self.logger.info("No missing sequences detected - perfect continuity")
            
            # Report duplicate sequences with the filenames involved. These are
            # expected (metafield fan-out, and the two sequence-35 files), but the
            # pairing matters: checkpointing keys on filename precisely because
            # sequence cannot identify a file.
            by_sequence: Dict[int, List[str]] = {}
            for info in file_info_list:
                by_sequence.setdefault(info['sequence'], []).append(
                    str(info.get('filename', ''))
                )
            duplicates = {seq: names for seq, names in by_sequence.items()
                          if len(names) > 1}
            if duplicates:
                for seq, names in sorted(duplicates.items()):
                    self.logger.info(
                        f"Sequence {seq:03d} maps to {len(names)} files, executed in "
                        f"this order: {names}"
                    )
        
        # Process sorted files and read content
        for file_info in file_info_list:
            try:
                # Read file content
                with open(file_info['file_path'], 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extract SQL content (skip header comments)
                sql_content = self._extract_sql_content_from_export(content)
                
                # Create unique key for OrderedDict (ensure no duplicates)
                sequence_key = f"{file_info['sequence']:03d}.{file_info['table_name']}"
                
                # Handle duplicate keys by appending suffix
                original_key = sequence_key
                counter = 1
                while sequence_key in sql_files:
                    self.logger.warning(f"Duplicate key detected: {original_key}, using suffix _{counter}")
                    sequence_key = f"{original_key}_{counter}"
                    counter += 1
                
                sql_files[sequence_key] = {
                    'sequence': file_info['sequence'],
                    'table_name': file_info['table_name'],
                    'subfolder': file_info['subfolder'],
                    'filename': file_info['filename'],
                    'original_filename': file_info['original_filename'],
                    'file_path': str(file_info['file_path']),
                    'sql_content': sql_content,
                    'ready_for_execution': True
                }
                
            except Exception as e:
                self.logger.error(f"Error reading file {file_info['file_path']}: {e}")
        
        # Final validation
        final_sequences = [info['sequence'] for info in sql_files.values()]
        self.logger.info(f"Found {len(sql_files)} ready SQL files in sequential order")
        #self.logger.info(f"Final sequence range: {min(final_sequences) if final_sequences else 'N/A'} to {max(final_sequences) if final_sequences else 'N/A'}")
        #self.logger.info(f"Final sequences: {sorted(final_sequences)}")
        
        return sql_files

    def _extract_sql_content_from_export(self, content: str) -> str:
        """Extract actual SQL content from exported file, removing headers/comments."""
        try:
            lines = content.split('\n')
            sql_lines = []
            in_sql_content = False
            
            for line in lines:
                stripped_line = line.strip()
                
                # Skip empty lines and comments at the start
                if not stripped_line or stripped_line.startswith('--'):
                    if in_sql_content:
                        sql_lines.append(line)  # Keep comments within SQL
                    continue
                
                # Start capturing content when we hit actual SQL
                in_sql_content = True
                sql_lines.append(line)
            
            return '\n'.join(sql_lines)
            
        except Exception as e:
            self.logger.error(f"Error extracting SQL content: {e}")
            return content

    def execute_sql_files_from_export(self, export_folder_path: str, execution_method: str, 
                                 dry_run: bool = True, sequence_range: Tuple[int, int] = None,
                                 continue_on_error: bool = False, use_master_file: bool = None) -> Dict[str, Dict[str, Any]]:
        """
        Execute SQL files from an exported folder using specified method in strict sequential order.
        """
        export_path = Path(export_folder_path)
        if not export_path.exists():
            raise FileNotFoundError(f"Export folder not found: {export_folder_path}")
        
        # Check if master file exists
        master_file_path = export_path / "MASTER_EXECUTE_ALL.sql"
        master_file_exists = master_file_path.exists()
        
        if use_master_file and execution_method.lower() == 'sqlcmd' and master_file_exists:
            self.logger.info(f"Master file found: {master_file_path.name}")
            self.logger.info("Will use master file execution (single connection)")
        elif use_master_file and execution_method.lower() == 'sqlcmd' and not master_file_exists:
            self.logger.warning(f"Master file not found: {master_file_path}")
            self.logger.warning("Falling back to individual file execution")
            use_master_file = False
        elif execution_method.lower() != 'sqlcmd':
            if use_master_file:
                self.logger.info(f"Master file only supported with SQLCMD, using individual files with {execution_method.upper()}")
            use_master_file = False
        
        # Get all SQL files from export folder in sequential order
        sql_files_to_execute = self._scan_exported_sql_files(export_path, sequence_range)
        
        if not sql_files_to_execute:
            self.logger.warning("No ready SQL files found for execution")
            return {}
        
        # Log execution order
        sequences = [info['sequence'] for info in sql_files_to_execute.values()]
        #self.logger.info(f"Execution order (sequences): {sequences}")
        
        # Choose execution method with sequential processing
        if execution_method.lower() == 'sqlalchemy':
            return self._execute_with_sqlalchemy(sql_files_to_execute, dry_run, continue_on_error)
        elif execution_method.lower() == 'pyodbc':
            return self._execute_with_pyodbc(sql_files_to_execute, dry_run, continue_on_error)
        elif execution_method.lower() == 'sqlcmd':
            return self._execute_with_sqlcmd(sql_files_to_execute, dry_run, continue_on_error)
        else:
            raise ValueError(f"Invalid execution method: {execution_method}. Use 'sqlalchemy', 'pyodbc', or 'sqlcmd'")
    
    def _execute_with_sqlalchemy(self, sql_files: OrderedDict, dry_run: bool = True, 
                            continue_on_error: bool = False) -> Dict[str, Dict[str, Any]]:
        """Execute SQL files using SQLAlchemy with single transaction for all files."""
        self.logger.info(f"Executing {len(sql_files)} SQL files using SQLAlchemy with single transaction (dry_run={dry_run})")
        
        if not dry_run:
            if not self.config_parser.db_helper:
                raise RuntimeError("Database helper not available")
            
            # Ensure SQLAlchemy connection
            if not self.config_parser.db_helper.sqlalchemy_engine:
                self.config_parser.db_helper.connect_sqlalchemy()
        
        execution_results = OrderedDict()
        
        # Handle dry run separately
        if dry_run:
            for i, (key, file_info) in enumerate(sql_files.items(), 1):
                if 'MASTER_EXECUTE_ALL' in file_info.get('filename', ''):
                    continue
                    
                execution_results[key] = {
                    'execution_order': i,
                    'sequence': file_info['sequence'],
                    'table_name': file_info['table_name'],
                    'subfolder': file_info['subfolder'],
                    'file_path': file_info['file_path'],
                    'method': 'sqlalchemy_single_transaction',
                    'executed': False,
                    'rows_affected': 0,
                    'execution_time': 0,
                    'error': None,
                    'dry_run': True,
                    'sql_preview': file_info.get('sql_content', '')[:200] + '...'
                }
            return execution_results
        
        # Single transaction execution for all files
        total_start_time = time.time()
        successful_executions = 0
        
        try:
            with self.config_parser.db_helper.sqlalchemy_engine.connect() as conn:
                # Start single transaction for ALL files
                trans = conn.begin()
                
                try:
                    self.logger.info("Starting single transaction for all SQL files...")
                    
                    # Execute all files in sequence within the same transaction
                    for i, (key, file_info) in enumerate(sql_files.items(), 1):
                        # Skip MASTER_EXECUTE_ALL.sql for SQLAlchemy
                        if 'MASTER_EXECUTE_ALL' in file_info.get('filename', ''):
                            self.logger.info(f"[{i}/{len(sql_files)}] Skipping {file_info.get('filename')} - not compatible with SQLAlchemy")
                            continue
                        
                        file_start_time = time.time()
                        
                        result = {
                            'execution_order': i,
                            'sequence': file_info['sequence'],
                            'table_name': file_info['table_name'],
                            'subfolder': file_info['subfolder'],
                            'file_path': file_info['file_path'],
                            'method': 'sqlalchemy_single_transaction',
                            'executed': False,
                            'rows_affected': 0,
                            'execution_time': 0,
                            'error': None,
                            'transaction_mode': 'single'
                        }
                        
                        #self.logger.info(f"[{i}/{len(sql_files)}] Executing sequence {file_info['sequence']:02d}: {file_info['table_name']}")
                        
                        try:
                            # Read the SQL file content
                            with open(file_info['file_path'], 'r', encoding='utf-8') as f:
                                sql_content = f.read()
                            
                            # Skip empty files
                            if not sql_content.strip():
                                self.logger.warning(f"[{i}/{len(sql_files)}] Skipping empty file: {file_info['table_name']}")
                                result['executed'] = True
                                result['rows_affected'] = 0
                                result['execution_time'] = time.time() - file_start_time
                                execution_results[key] = result
                                successful_executions += 1
                                continue
                            
                            # Clean and validate SQL content
                            sql_content = sql_content.strip()
                            
                            # Remove any BOM or invisible characters
                            if sql_content.startswith('\ufeff'):
                                sql_content = sql_content[1:]
                            
                            # Check if content is actually executable SQL
                            if not sql_content or len(sql_content) < 10:
                                self.logger.warning(f"[{i}/{len(sql_files)}] File contains insufficient SQL content: {file_info['table_name']}")
                                result['executed'] = True
                                result['rows_affected'] = 0
                                result['execution_time'] = time.time() - file_start_time
                                result['error'] = 'Insufficient SQL content'
                                execution_results[key] = result
                                successful_executions += 1
                                continue
                            
                            # Log SQL preview for debugging
                            self.logger.debug(f"  Executing SQL for {file_info['table_name']} (length: {len(sql_content)} chars)")
                            self.logger.debug(f"  SQL preview: {sql_content[:100]}...")
                            
                            # Execute the entire SQL file content using text() wrapper for safety
                            from sqlalchemy import text
                            db_result = conn.execute(text(sql_content))
                            
                            total_rows = 0
                            if hasattr(db_result, 'rowcount') and db_result.rowcount >= 0:
                                total_rows = db_result.rowcount
                            
                            file_end_time = time.time()
                            
                            result.update({
                                'executed': True,
                                'rows_affected': total_rows,
                                'execution_time': file_end_time - file_start_time
                            })
                            
                            successful_executions += 1
                            self.logger.info(f"[{i}/{len(sql_files)}] {file_info['sequence']:02d} - {file_info['table_name']}: {total_rows:,} rows affected in {file_end_time - file_start_time:.2f}s")
                            
                        except Exception as file_error:
                            # File execution failed - this will cause complete rollback
                            result['error'] = str(file_error)
                            execution_results[key] = result
                            
                            self.logger.error(f"[{i}/{len(sql_files)}] {file_info['sequence']:02d} - {file_info['table_name']} FAILED: {file_error}")
                            self.logger.error(f"ROLLING BACK entire transaction due to error in {file_info['table_name']}")
                            
                            # Log the problematic SQL content for debugging
                            try:
                                with open(file_info['file_path'], 'r', encoding='utf-8') as f:
                                    debug_content = f.read()
                                self.logger.error(f"Problematic SQL content (first 200 chars): {debug_content[:200]}")
                            except:
                                pass
                            
                            # Mark remaining files as not executed due to rollback
                            remaining_files = list(sql_files.items())[i:]
                            for remaining_key, remaining_info in remaining_files:
                                execution_results[remaining_key] = {
                                    'execution_order': None,
                                    'sequence': remaining_info['sequence'],
                                    'table_name': remaining_info['table_name'],
                                    'subfolder': remaining_info['subfolder'],
                                    'file_path': remaining_info['file_path'],
                                    'method': 'sqlalchemy_single_transaction',
                                    'executed': False,
                                    'rows_affected': 0,
                                    'execution_time': 0,
                                    'error': f'Transaction rolled back due to error in {file_info["table_name"]}',
                                    'rolled_back': True,
                                    'transaction_mode': 'single'
                                }
                            
                            # Raise exception to trigger rollback
                            raise Exception(f"File execution failed: {file_error}")
                        
                        execution_results[key] = result
                    
                    # If we get here, all files executed successfully - commit the transaction
                    trans.commit()
                    total_end_time = time.time()
                    
                    self.logger.info(f"Successfully committed transaction for all {successful_executions} files in {total_end_time - total_start_time:.2f}s")
                    
                    # Update all results to show successful commit
                    for result in execution_results.values():
                        if result.get('executed', False):
                            result['committed'] = True
                            result['transaction_committed'] = True
                    
                except Exception as transaction_error:
                    # Rollback the entire transaction
                    trans.rollback()
                    total_end_time = time.time()
                    
                    self.logger.error(f"Transaction ROLLED BACK after {total_end_time - total_start_time:.2f}s due to error: {transaction_error}")
                    
                    # Mark all executed files as rolled back
                    for result in execution_results.values():
                        if result.get('executed', False):
                            result['executed'] = False  # They were executed but rolled back
                            result['rolled_back'] = True
                            result['transaction_committed'] = False
                            if not result.get('error'):
                                result['error'] = f'Rolled back due to transaction failure: {transaction_error}'
                    
                    successful_executions = 0  # No files were actually committed
                    
        except Exception as conn_error:
            self.logger.error(f"Connection error during SQLAlchemy execution: {conn_error}")
            
            # Mark all results as failed due to connection error
            for key, file_info in sql_files.items():
                execution_results[key] = {
                    'execution_order': None,
                    'sequence': file_info['sequence'],
                    'table_name': file_info['table_name'],
                    'subfolder': file_info['subfolder'],
                    'file_path': file_info['file_path'],
                    'method': 'sqlalchemy_single_transaction',
                    'executed': False,
                    'rows_affected': 0,
                    'execution_time': 0,
                    'error': f'Connection error: {conn_error}',
                    'transaction_mode': 'single'
                }
            successful_executions = 0
        
        # Log final execution summary
        failed_executions = len(sql_files) - successful_executions
        self.logger.info(f"SQLAlchemy single transaction execution completed: {successful_executions} committed, {failed_executions} failed/rolled back")
        
        return execution_results

    # ------------------------------------------------------------------
    # Checkpoint / resume for the numbered SQL files
    # ------------------------------------------------------------------

    PROGRESS_TABLE = 'DT_Migration_SQLProgress'

    def _progress_identity(self) -> Dict[str, Any]:
        """LoadID and provenance for checkpoint rows, resolved from the config."""
        get = self.config_parser.get_variable if self.config_parser else lambda *_a, **_k: None
        return {
            'load_id': getattr(self, 'load_id', None) or get('LOADID'),
            'customer_code': getattr(self, 'customer_code', None) or get('CUSTOMERCODE'),
            'db': getattr(self, 'db_name', None) or get('DB'),
            'run_id': getattr(self, 'run_id', None),
        }

    def _record_sql_progress(self, cursor, file_info: Dict[str, Any],
                             rows_affected: int) -> None:
        """Insert this file's checkpoint row. Caller commits it with the file's work.

        Deliberately uses the caller's cursor so the row lands in the same
        transaction as the SQL it records. Committing them separately would let the
        checkpoint claim work that was rolled back, or miss work that was kept.
        """
        identity = self._progress_identity()
        if identity['load_id'] in (None, ''):
            # Without a LoadID a checkpoint row cannot be keyed, so resume is not
            # available for this run. Say so once rather than failing the file.
            if not getattr(self, '_warned_no_load_id', False):
                self.logger.warning(
                    'No LoadID available; SQL progress will not be checkpointed and '
                    '--resume-load-id will not work for this run'
                )
                self._warned_no_load_id = True
            return
        try:
            cursor.execute(
                f"""
                INSERT INTO dbo.[{self.PROGRESS_TABLE}]
                    (LoadID, Customer_Code, db, RunID, Sequence, Filename,
                     Table_Name, Rows_Affected)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                int(identity['load_id']),
                str(identity['customer_code'] or ''),
                identity['db'],
                identity['run_id'],
                int(file_info.get('sequence') or 0),
                str(file_info.get('filename', '')),
                file_info.get('table_name'),
                int(rows_affected or 0),
            )
        except Exception as e:
            # A missing progress table must not stop a migration that is otherwise
            # fine; it only costs resumability.
            self.logger.warning(
                f'Could not record SQL progress for '
                f'{file_info.get("filename", "?")}: {type(e).__name__}: {e}. '
                f'Apply SQL/Schemas/Migrations/002.DT_Migration_SQLProgress.sql to '
                f'enable resume.'
            )

    def _completed_sql_files(self, cursor) -> set:
        """Filenames already completed for the LoadID being resumed."""
        if not getattr(self, 'resume_load_id', None):
            return set()
        load_id = int(self.resume_load_id)
        try:
            cursor.execute(
                f"SELECT Filename FROM dbo.[{self.PROGRESS_TABLE}] WHERE LoadID = ?",
                load_id,
            )
            completed = {row[0] for row in cursor.fetchall()}
        except Exception as e:
            self.logger.error(
                f'Could not read SQL progress for LoadID {load_id}: '
                f'{type(e).__name__}: {e}. Refusing to guess which files ran.'
            )
            raise

        if completed:
            self._assert_checkpoint_matches_data(cursor, load_id, completed)
        return completed

    def _assert_checkpoint_matches_data(self, cursor, load_id: int,
                                       completed: set) -> None:
        """Refuse to resume when the load's data was removed behind the checkpoint.
        """
        seeds_accounts = any(
            name.split('.', 1)[0].lstrip('0') in ('1', '01', '001')
            for name in completed
        )
        if not seeds_accounts:
            return
        try:
            cursor.execute(
                'SELECT COUNT_BIG(*) FROM dbo.tblAccount WHERE LoadID = ?', load_id
            )
            row = cursor.fetchone()
            accounts = int(row[0]) if row and row[0] is not None else 0
        except Exception as e:
            self.logger.warning(
                f'Could not confirm LoadID {load_id} still has data: {e}'
            )
            return

        if accounts == 0:
            raise RuntimeError(
                f'Refusing to resume LoadID {load_id}: the checkpoint records '
                f'{len(completed)} completed file(s), but tblAccount has no rows for '
                f'this load. Its data was deleted outside this pipeline (for example '
                f'by SQL/Procedures/DT Delete Migrated Data.sql, which does not clear '
                f'the progress tables). Resuming would skip work that no longer '
                f'exists. Clear the stale checkpoint first:\n'
                f'    DELETE FROM dbo.{self.PROGRESS_TABLE} WHERE LoadID = {load_id};\n'
                f'    DELETE FROM dbo.DT_Migration_LoopProgress WHERE LoadID = {load_id};\n'
                f'then run without --resume-load-id to migrate the customer afresh.'
            )

    def _log_resume_hint(self, execution_results: Dict[str, Any]) -> None:
        """Tell the operator exactly how to continue from the failure."""
        identity = self._progress_identity()
        failed = [r for r in execution_results.values() if r.get('error')]
        committed = sum(1 for r in execution_results.values()
                        if r.get('executed') and not r.get('error'))
        if failed:
            first = failed[0]
            self.logger.error(
                f"Failed on sequence {first.get('sequence')} "
                f"({first.get('table_name')}): {first.get('error')}"
            )
        self.logger.error(
            f"{committed} file(s) committed and will be skipped on resume."
        )
        if identity['load_id']:
            self.logger.error(
                f"To continue after fixing the cause:  "
                f"Run_Migration.py <env> --resume-load-id {identity['load_id']}"
            )
            self.logger.error(
                f"To abandon this load instead:  "
                f"python tools/discard_load.py --load-id {identity['load_id']} --execute"
            )

    def _log_timing_summary(self, execution_results: Dict[str, Any],
                            top_n: int = 10) -> None:
        """Report where the SQL phase spent its time.
        """
        ran = [r for r in execution_results.values()
               if r.get('executed') and not r.get('error')]
        if not ran:
            return

        total = sum(r.get('execution_time', 0) or 0 for r in ran)
        slowest = sorted(ran, key=lambda r: r.get('execution_time', 0) or 0,
                         reverse=True)[:top_n]

        self.logger.info(f"SQL phase timing: {len(ran)} file(s), {total:.2f}s total")
        for r in slowest:
            seconds = r.get('execution_time', 0) or 0
            share = (seconds / total * 100) if total else 0
            self.logger.info(
                f"    seq {r.get('sequence'):02d} {r.get('table_name')}: "
                f"{seconds:.2f}s ({share:.0f}%), {r.get('rows_affected', 0):,} rows"
            )

        empty = [r for r in ran if not r.get('rows_affected')]
        if empty:
            names = ', '.join(f"{r.get('sequence'):02d} {r.get('table_name')}"
                              for r in empty)
            self.logger.info(
                f"{len(empty)} file(s) affected 0 rows: {names}"
            )

    @staticmethod
    def _total_rows_affected(cursor) -> int:
        """Sum rowcount across every result set the batch produced.
        """
        total = 0
        while True:
            count = cursor.rowcount
            if isinstance(count, int) and count > 0:
                total += count
            if not cursor.nextset():
                break
        return total

    def _execute_with_pyodbc(self, sql_files: OrderedDict, dry_run: bool = True,
                        continue_on_error: bool = False) -> Dict[str, Dict[str, Any]]:
        """Execute SQL files using PyODBC with single transaction for all files."""
        self.logger.info(f"Executing {len(sql_files)} SQL files using PyODBC with single transaction (dry_run={dry_run})")
        
        if not dry_run:
            if not self.config_parser.db_helper:
                raise RuntimeError("Database helper not available")
            
            # Ensure PyODBC connection
            if not self.config_parser.db_helper.pyodbc_connection:
                self.config_parser.db_helper.connect_pyodbc()
        
        execution_results = OrderedDict()
        
        # Handle dry run separately
        if dry_run:
            for i, (key, file_info) in enumerate(sql_files.items(), 1):
                if 'MASTER_EXECUTE_ALL' in file_info.get('filename', ''):
                    self.logger.info(f"Skipping master file in individual execution mode")
                    continue
                    
                execution_results[key] = {
                    'execution_order': i,
                    'sequence': file_info['sequence'],
                    'table_name': file_info['table_name'],
                    'subfolder': file_info['subfolder'],
                    'file_path': file_info['file_path'],
                    'method': 'pyodbc_single_transaction',
                    'executed': False,
                    'rows_affected': 0,
                    'execution_time': 0,
                    'start_time': None,
                    'end_time': None,
                    'rows_per_second': 0,
                    'error': None,
                    'dry_run': True,
                    'sql_preview': file_info.get('sql_content', '')[:200] + '...'
                }
            return execution_results
        
        # Single transaction execution for all files
        total_start_time = time.time()
        successful_executions = 0
        cursor = None
        
        try:
            connection = self.config_parser.db_helper.pyodbc_connection
            prior_autocommit = getattr(connection, 'autocommit', False)
            cursor = connection.cursor()
            # One transaction per file: the loop commits after each file, so a
            # failure costs only that file instead of discarding every earlier one.
            connection.autocommit = False

            # On resume, skip files this LoadID has already completed.
            already_done = self._completed_sql_files(cursor)
            if already_done:
                self.logger.info(
                    f"Resuming LoadID {self.resume_load_id}: {len(already_done)} file(s) "
                    f"already completed and will be skipped"
                )

            try:
                for i, (key, file_info) in enumerate(sql_files.items(), 1):
                    if 'MASTER_EXECUTE_ALL' in file_info.get('filename', ''):
                        self.logger.info(f"Skipping master file in individual execution mode")
                        continue

                    filename = str(file_info.get('filename', key))
                    if filename in already_done:
                        self.logger.info(f"[{i}/{len(sql_files)}] skipping {filename} (already completed)")
                        execution_results[key] = {
                            'execution_order': i,
                            'sequence': file_info['sequence'],
                            'table_name': file_info['table_name'],
                            'subfolder': file_info['subfolder'],
                            'file_path': file_info['file_path'],
                            'method': 'pyodbc_per_file_transaction',
                            'executed': False,
                            'skipped': True,
                            'resumed': True,
                            'rows_affected': 0,
                            'execution_time': 0,
                            'start_time': None,
                            'end_time': None,
                            'rows_per_second': 0,
                            'error': None,
                            'transaction_mode': 'per_file',
                            'transaction_committed': True,
                        }
                        continue

                    file_start_time = time.time()
                    start_datetime = datetime.now()
                    # Emitted before the file runs, not after, so a run that stalls
                    # names the file it is stuck on. ASCII only: the console handler
                    # is cp1252 on Windows and mangles anything else.
                    self.logger.info(
                        f"[{i}/{len(sql_files)}] seq {file_info['sequence']:02d} "
                        f"{filename} - running"
                    )

                    try:
                        sql_content = file_info.get('sql_content', '')
                        if not sql_content:
                            raise ValueError("SQL content is empty")
                        
                        # Execute the SQL content
                        cursor.execute(sql_content)
                        rows_affected = self._total_rows_affected(cursor)
                        
                        file_end_time = time.time()
                        end_datetime = datetime.now()
                        execution_time = file_end_time - file_start_time
                        rows_per_second = round(rows_affected / execution_time, 2) if execution_time > 0 else 0
                        self._record_sql_progress(cursor, file_info, rows_affected)
                        connection.commit()

                        execution_results[key] = {
                            'execution_order': i,
                            'sequence': file_info['sequence'],
                            'table_name': file_info['table_name'],
                            'subfolder': file_info['subfolder'],
                            'file_path': file_info['file_path'],
                            'method': 'pyodbc_per_file_transaction',
                            'executed': True,
                            'rows_affected': rows_affected,
                            'execution_time': round(execution_time, 2),
                            'start_time': start_datetime,
                            'end_time': end_datetime,
                            'rows_per_second': rows_per_second,
                            'error': None,
                            'transaction_mode': 'per_file',
                            'transaction_committed': True,
                        }

                        successful_executions += 1
                        self.logger.info(
                            f"[{i}/{len(sql_files)}] seq {file_info['sequence']:02d} "
                            f"{filename} - OK, {rows_affected:,} rows in "
                            f"{execution_time:.2f}s ({rows_per_second:,.0f} rows/sec)"
                        )

                    except Exception as file_error:
                        file_end_time = time.time()
                        end_datetime = datetime.now()
                        execution_time = file_end_time - file_start_time

                        try:
                            connection.rollback()
                            self.logger.info(
                                f"Rolled back {file_info.get('filename', key)}; "
                                f"{successful_executions} earlier file(s) remain committed"
                            )
                        except Exception as rollback_error:
                            self.logger.error(
                                f"Failed to roll back {file_info.get('filename', key)}: "
                                f"{rollback_error}"
                            )

                        execution_results[key] = {
                            'execution_order': i,
                            'sequence': file_info['sequence'],
                            'table_name': file_info['table_name'],
                            'subfolder': file_info['subfolder'],
                            'file_path': file_info['file_path'],
                            'method': 'pyodbc_single_transaction',
                            'executed': False,
                            'rows_affected': 0,
                            'execution_time': round(execution_time, 2),
                            'start_time': start_datetime,
                            'end_time': end_datetime,
                            'rows_per_second': 0,
                            'error': str(file_error),
                            'transaction_mode': 'single',
                            'transaction_committed': False
                        }
                        
                        self.logger.error(f"[{i}/{len(sql_files)}] {file_info['sequence']:02d} - {file_info['table_name']} FAILED: {file_error}")
                        
                        if not continue_on_error:
                            raise file_error
                
                # Each file committed as it completed; nothing is left open here.
                total_end_time = time.time()
                self.logger.info(
                    f"Committed {successful_executions} file(s) individually in "
                    f"{total_end_time - total_start_time:.2f}s"
                )
                self._log_timing_summary(execution_results)

            except Exception as transaction_error:
                total_end_time = time.time()
                self.logger.error(
                    f"SQL execution stopped after {total_end_time - total_start_time:.2f}s: "
                    f"{transaction_error}"
                )

                self._log_timing_summary(execution_results)
                self._log_resume_hint(execution_results)

            finally:
                if cursor:
                    cursor.close()
                # autocommit was previously set False here and never restored.
                try:
                    connection.autocommit = prior_autocommit
                except Exception:
                    pass
        
        except Exception as conn_error:
            self.logger.error(f"Connection error during PyODBC execution: {conn_error}")
            
            # Mark all results as failed due to connection error
            for key, file_info in sql_files.items():
                execution_results[key] = {
                    'execution_order': None,
                    'sequence': file_info['sequence'],
                    'table_name': file_info['table_name'],
                    'subfolder': file_info['subfolder'],
                    'file_path': file_info['file_path'],
                    'method': 'pyodbc_single_transaction',
                    'executed': False,
                    'rows_affected': 0,
                    'execution_time': 0,
                    'start_time': None,
                    'end_time': None,
                    'rows_per_second': 0,
                    'error': f'Connection error: {conn_error}',
                    'transaction_mode': 'single'
                }
            successful_executions = 0
            
            if cursor:
                cursor.close()
        
        # Log final execution summary
        failed_executions = len(sql_files) - successful_executions
        self.logger.info(f"PyODBC single transaction execution completed: {successful_executions} committed, {failed_executions} failed/rolled back")
        
        return execution_results

    def _execute_with_sqlcmd(self, sql_files: OrderedDict, dry_run: bool = True,
                        continue_on_error: bool = False, use_master_file: bool = True) -> Dict[str, Dict[str, Any]]:
        """Execute SQL files using SQLCMD with transaction control."""
        
        # Override continue_on_error for transaction safety
        if not continue_on_error:
            self.logger.info("Transaction mode: Single failure will stop entire process")
            
        if use_master_file:
            return self._execute_master_file_with_sqlcmd_transaction(sql_files, dry_run, continue_on_error)
        else:
            # For individual files, we can't guarantee true transaction rollback with SQLCMD
            # but we can stop on first error
            #self.logger.warning(" Individual SQLCMD execution cannot guarantee transaction rollback")
            return self._execute_individual_files_with_sqlcmd_strict(sql_files, dry_run)

    def _execute_master_file_with_sqlcmd_transaction(self, sql_files: OrderedDict, dry_run: bool = True,
                                                continue_on_error: bool = False) -> Dict[str, Dict[str, Any]]:
        """Execute master file with transaction control and strict error handling."""
        #self.logger.info(f"Executing {len(sql_files)} SQL files using master file with transaction control (dry_run={dry_run})")
        
        execution_results = OrderedDict()
        
        if dry_run:
            # In dry run, just simulate the master file execution
            for i, (key, file_info) in enumerate(sql_files.items(), 1):
                execution_results[key] = {
                    'execution_order': i,
                    'sequence': file_info['sequence'],
                    'table_name': file_info['table_name'],
                    'subfolder': file_info['subfolder'],
                    'file_path': file_info['file_path'],
                    'method': 'sqlcmd_master_transaction',
                    'executed': False,
                    'rows_affected': 0,
                    'execution_time': 0,
                    'error': None,
                    'dry_run': True,
                    'sql_preview': file_info.get('sql_content', '')[:200] + '...',
                    'transaction_mode': 'master_file'
                }
            
            self.logger.info(f"DRY RUN: Would execute master file with transaction control for {len(sql_files)} included SQL files")
            return execution_results
        
        # Find the master file in the export directory
        export_folder = Path(list(sql_files.values())[0]['file_path']).parent
        master_file_path = export_folder / "MASTER_EXECUTE_ALL.sql"
        
        if not master_file_path.exists():
            self.logger.error(f"Master file not found: {master_file_path}")
            # Create error results for all files
            for key, file_info in sql_files.items():
                execution_results[key] = {
                    'execution_order': None,
                    'sequence': file_info['sequence'],
                    'table_name': file_info['table_name'],
                    'subfolder': file_info['subfolder'],
                    'file_path': file_info['file_path'],
                    'method': 'sqlcmd_master_transaction',
                    'executed': False,
                    'rows_affected': 0,
                    'execution_time': 0,
                    'error': 'Master file not found',
                    'transaction_mode': 'master_file'
                }
            return execution_results
        
        try:
            start_time = time.time()
            
            #self.logger.info(f"Executing master file with transaction control: {master_file_path}")
            
            # Build SQLCMD command with strict error handling (no -r0 for continue on error)
            additional_args = [
                '-b',      # Terminate batch on error (strict mode)
                '-V', '1', # Severity level that causes sqlcmd to exit
                '-w', '65535',  # Set line width
                '-s', ',',      # Set column separator
                '-W'            # Remove trailing spaces
            ]
            
            # Do NOT add -r0 flag - we want sqlcmd to stop on first error
            self.logger.info(" Using strict error mode: execution will stop on first error")
            
            # Execute master file using database helper
            success, output = self.config_parser.db_helper.execute_sqlcmd(
                str(master_file_path), 
                additional_args=additional_args
            )
            
            end_time = time.time()
            total_execution_time = end_time - start_time
            
            if success:
                self.logger.info(f"Master file execution completed successfully in {total_execution_time:.2f}s")
                
                # Parse output to extract per-file results
                file_results = self._parse_master_execution_output(output, sql_files)
                file_results.to_csv('file_results.csv', index=False)  # For debugging
                print(file_results)
                
                # Create successful results for all files
                for i, (key, file_info) in enumerate(sql_files.items(), 1):
                    file_result = file_results.get(file_info['table_name'], {})
                    
                    execution_results[key] = {
                        'execution_order': i,
                        'sequence': file_info['sequence'],
                        'table_name': file_info['table_name'],
                        'subfolder': file_info['subfolder'],
                        'file_path': file_info['file_path'],
                        'method': 'sqlcmd_master_transaction',
                        'executed': True,
                        'rows_affected': file_result.get('rows_affected', 0),
                        'execution_time': file_result.get('execution_time', 0),
                        'error': None,
                        'master_execution': True,
                        'master_execution_time': total_execution_time,
                        'transaction_committed': True,
                        'transaction_mode': 'master_file'
                    }
                
                # Extract total rows from master output
                total_rows = sum(r.get('rows_affected', 0) for r in execution_results.values())
                #self.logger.info(f"Master execution completed: {total_rows:,} total rows affected")
                
            else:
                self.logger.error(f"Master file execution FAILED - all changes should be rolled back")
                self.logger.error(f"Error output: {output[:500]}...")
                
                # Since SQLCMD failed, assume all operations were rolled back
                for i, (key, file_info) in enumerate(sql_files.items(), 1):
                    execution_results[key] = {
                        'execution_order': i,
                        'sequence': file_info['sequence'],
                        'table_name': file_info['table_name'],
                        'subfolder': file_info['subfolder'],
                        'file_path': file_info['file_path'],
                        'method': 'sqlcmd_master_transaction',
                        'executed': False,
                        'rows_affected': 0,
                        'execution_time': 0,
                        'error': f"Master execution failed: {output[:200]}...",
                        'master_execution': True,
                        'master_execution_time': total_execution_time,
                        'transaction_committed': False,
                        'rolled_back': True,
                        'transaction_mode': 'master_file'
                    }
            
            return execution_results
            
        except Exception as e:
            self.logger.error(f"Error executing master file: {e}")
            
            # Create error results for all files
            for i, (key, file_info) in enumerate(sql_files.items(), 1):
                execution_results[key] = {
                    'execution_order': i,
                    'sequence': file_info['sequence'],
                    'table_name': file_info['table_name'],
                    'subfolder': file_info['subfolder'],
                    'file_path': file_info['file_path'],
                    'method': 'sqlcmd_master_transaction',
                    'executed': False,
                    'rows_affected': 0,
                    'execution_time': 0,
                    'error': str(e),
                    'master_execution': True,
                    'transaction_committed': False,
                    'transaction_mode': 'master_file'
                }
            
            return execution_results

    def _execute_individual_files_with_sqlcmd_strict(self, sql_files: OrderedDict, dry_run: bool = True) -> Dict[str, Dict[str, Any]]:
        """Execute SQL files individually with strict error handling (stop on first error)."""
        self.logger.info(f"Executing {len(sql_files)} SQL files individually with strict error handling (dry_run={dry_run})")
        # self.logger.warning(" Individual file execution cannot guarantee transaction rollback between files")

        execution_results = OrderedDict()
        successful_executions = 0
        
        # Execute files in sequential order, stop on first error
        for i, (key, file_info) in enumerate(sql_files.items(), 1):
            result = {
                'execution_order': i,
                'sequence': file_info['sequence'],
                'table_name': file_info['table_name'],
                'subfolder': file_info['subfolder'],
                'file_path': file_info['file_path'],
                'method': 'sqlcmd_individual_strict',
                'executed': False,
                'rows_affected': 0,
                'execution_time': 0,
                'error': None,
                'transaction_mode': 'individual'
            }
            
            self.logger.info(f"[{i}/{len(sql_files)}] Processing sequence {file_info['sequence']:02d}: {file_info['table_name']}")
            
            if dry_run:
                result['dry_run'] = True
                result['sql_preview'] = file_info.get('sql_content', '')[:200] + '...'
                execution_results[key] = result
                continue
            
            try:
                start_time = time.time()
                
                # Execute using SQLCMD with strict error handling
                additional_args = ['-b', '-V', '1']  # Terminate on error
                success, output = self.config_parser.db_helper.execute_sqlcmd(
                    file_info['file_path'],
                    additional_args=additional_args
                )
                
                end_time = time.time()
                
                if success:
                    # Try to extract row count from output
                    rows_affected = self._extract_rows_from_sqlcmd_output(output)
                    
                    result.update({
                        'executed': True,
                        'rows_affected': rows_affected,
                        'execution_time': end_time - start_time,
                        'transaction_committed': True
                    })
                    
                    successful_executions += 1
                    self.logger.info(f"[{i}/{len(sql_files)}] {file_info['sequence']:02d} - {file_info['table_name']}: {rows_affected:,} rows affected in {end_time - start_time:.2f}s")
                else:
                    result['error'] = output
                    self.logger.error(f"[{i}/{len(sql_files)}] {file_info['sequence']:02d} - {file_info['table_name']} FAILED: {output}")
                    self.logger.error(f"STOPPING execution due to error (strict mode)")
                    
                    execution_results[key] = result
                    
                    # Mark remaining files as not executed
                    remaining_files = list(sql_files.items())[i:]
                    for remaining_key, remaining_info in remaining_files:
                        execution_results[remaining_key] = {
                            'execution_order': None,
                            'sequence': remaining_info['sequence'],
                            'table_name': remaining_info['table_name'],
                            'subfolder': remaining_info['subfolder'],
                            'file_path': remaining_info['file_path'],
                            'method': 'sqlcmd_individual_strict',
                            'executed': False,
                            'rows_affected': 0,
                            'execution_time': 0,
                            'error': f'Skipped due to error in {file_info["table_name"]}',
                            'skipped': True,
                            'transaction_mode': 'individual'
                        }
                    break
                    
            except Exception as e:
                result['error'] = str(e)
                self.logger.error(f"[{i}/{len(sql_files)}] {file_info['sequence']:02d} - {file_info['table_name']} FAILED: {e}")
                self.logger.error(f"STOPPING execution due to exception (strict mode)")
                
                execution_results[key] = result
                break
            
            execution_results[key] = result
        
        failed_executions = len(sql_files) - successful_executions
        self.logger.info(f"Individual strict execution completed: {successful_executions} successful, {failed_executions} failed/skipped")
        
        return execution_results

    def _parse_master_execution_output(self, output: str, sql_files: OrderedDict) -> Dict[str, Dict[str, Any]]:
        """Parse master file execution output to extract per-file results."""
        file_results = {}
        
        try:
            lines = output.split('\n')
            current_file = None
            
            for line in lines:
                line = line.strip()
                
                # Look for file execution messages
                if 'Executing file' in line and ':' in line:
                    # Extract filename from message like "Executing file 1/25: 001.tblaccount_READY.sql"
                    parts = line.split(':')
                    if len(parts) >= 2:
                        filename = parts[-1].strip()
                        # Extract table name from filename
                        if '_READY.sql' in filename:
                            table_name = filename.replace('_READY.sql', '').split('.', 1)[-1]
                            current_file = table_name
                            file_results[current_file] = {'rows_affected': 0, 'execution_time': 0}
                
                # Look for rows affected messages
                elif 'Rows affected:' in line and current_file:
                    try:
                        rows_str = line.split('Rows affected:')[-1].strip()
                        rows = int(rows_str)
                        file_results[current_file]['rows_affected'] = rows
                    except (ValueError, IndexError):
                        pass
                
                # Look for execution time messages  
                elif 'File execution time:' in line and current_file:
                    try:
                        time_str = line.split('File execution time:')[-1].replace('seconds', '').strip()
                        exec_time = float(time_str)
                        file_results[current_file]['execution_time'] = exec_time
                    except (ValueError, IndexError):
                        pass
            
            self.logger.debug(f"Parsed results for {len(file_results)} files from master output")
            return file_results
            
        except Exception as e:
            self.logger.error(f"Error parsing master execution output: {e}")
            return {}

    def _extract_rows_from_sqlcmd_output(self, output: str) -> int:
        """Extract number of affected rows from SQLCMD output."""
        
        # Look for patterns like "(123 rows affected)" or "123 rows affected"
        patterns = [
            r'\((\d+) rows? affected\)',
            r'(\d+) rows? affected',
            r'(\d+) row\(s\) affected'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, output, re.IGNORECASE)
            if matches:
                return sum(int(match) for match in matches)
        
        return 0

    def execute_exported_sql_files(self, export_folder_path: str, execution_method: str = None,
                                dry_run: bool = True, sequence_range: Tuple[int, int] = None,
                                continue_on_error: bool = False, use_master_file: bool = None) -> Dict[str, Any]:
        """
        Comprehensive function to execute all SQL files from an exported folder in sequential order.
        """
        try:
            start_time = time.time()
            
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"STARTING SEQUENTIAL SQL EXECUTION")
            self.logger.info(f"{'='*80}")
            self.logger.info(f"Export Folder: {export_folder_path}")
            self.logger.info(f"Execution Method: {execution_method.upper()}")
            self.logger.info(f"Dry Run: {'YES' if dry_run else 'NO'}")
            self.logger.info(f"Continue on Error: {'YES' if continue_on_error else 'NO'}")
            self.logger.info(f"Sequence Range: {sequence_range or 'ALL'}")
            
            # Execute the files in sequential order
            execution_results = self.execute_sql_files_from_export(
                export_folder_path, execution_method, dry_run, sequence_range, continue_on_error
            )
            
            end_time = time.time()
            
            # Calculate summary statistics
            total_files = len(execution_results)
            executed_count = sum(1 for r in execution_results.values() if r.get('executed', False))
            failed_count = sum(1 for r in execution_results.values() if r.get('error') and not r.get('skipped', False))
            skipped_count = sum(1 for r in execution_results.values() if r.get('skipped', False))
            total_rows = sum(r.get('rows_affected', 0) for r in execution_results.values())
            total_execution_time = sum(r.get('execution_time', 0) for r in execution_results.values())
            
            # Log completion summary
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"SEQUENTIAL SQL EXECUTION COMPLETED")
            self.logger.info(f"{'='*80}")
            self.logger.info(f"Total Files: {total_files}")
            self.logger.info(f"Executed Successfully: {executed_count}")
            self.logger.info(f"Failed: {failed_count}")
            
            if failed_count > 0 and not continue_on_error:
                self.logger.warning(f"Execution stopped early due to errors (continue_on_error=False)")
            
            summary = {
                'export_folder': export_folder_path,
                'execution_method': execution_method,
                'dry_run': dry_run,
                'sequence_range': sequence_range,
                'continue_on_error': continue_on_error,
                'total_files': total_files,
                'executed_successfully': executed_count,
                'failed': failed_count,
                'skipped': skipped_count,
                'total_rows_affected': total_rows,
                'total_execution_time': total_execution_time,
                'wall_clock_time': end_time - start_time,
                'execution_results': execution_results,
                'execution_order_maintained': True  # New flag to indicate sequential execution
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Failed to execute exported SQL files sequentially: {e}")
            raise
    
    def extract_migration_stats(self, execution_results: Dict[str, Any], customer_code: str, 
                          customer_logger: logging.Logger) -> List[Dict[str, Any]]:
        """
        Extract migration statistics using the new metrics collection approach.
        Uses processing_stats_metrics.json for dynamic metric generation.
        """
        try:
            customer_logger.info("Extracting migration statistics using metrics collection...")
            
            # Use the new metrics collection approach
            table_metrics = self.collect_migration_metrics(self.load_id, self.session_id, customer_logger)
            
            if not table_metrics:
                customer_logger.warning("No migration metrics collected")
                return []
            
            # Remove summary from table metrics for processing
            summary = table_metrics.pop('_summary', {})
            
            # Convert table metrics to migration stats format
            migration_stats = []
            for table_name, metrics in table_metrics.items():
                if table_name.startswith('_'):  # Skip internal keys
                    continue
                    
                # Convert metrics to migration stats format
                stat = {
                    'table_name': table_name,
                    'from_table': metrics.get('from_table', 'unknown'),
                    'rows_inserted': metrics.get('rows_inserted', 0),
                    'start_time': metrics.get('start_time', datetime.now()),
                    'end_time': metrics.get('end_time', datetime.now()),
                    'success': metrics.get('success', True),
                    'error_message': metrics.get('error_message', ''),
                    'query_successful': metrics.get('query_successful', True),
                    
                    # Financial columns
                    'Total_Debt': metrics.get('total_debt', 0.0),
                    'Total_Paid': metrics.get('total_paid', 0.0),
                    'Total_Costs': metrics.get('total_costs', 0.0),
                    'Total_Overpayments': metrics.get('total_overpayments', 0.0),
                    'Total_Outstanding': metrics.get('total_outstanding', 0.0),
                    'Total_Commission': metrics.get('total_commission', 0.0),
                    'Total_Interest': metrics.get('total_interest', 0.0),
                    
                    # Additional metadata
                    'config_table_name': table_name,
                    'execution_method': 'metrics_collection',
                    'queries_executed': len(metrics.get('queries_executed', [])),
                    'master_execution': True  # This approach is similar to master execution
                }
                
                migration_stats.append(stat)
            
            # Log summary
            total_rows = sum(stat.get('rows_inserted', 0) for stat in migration_stats)
            
            customer_logger.info(f"Migration stats extraction complete:")
            customer_logger.info(f"  Tables processed: {len(migration_stats)}")
            customer_logger.info(f"  Total rows migrated: {total_rows:,}")
            customer_logger.info(f"  Successful queries: {summary.get('successful_queries', 0)}")
            customer_logger.info(f"  Failed queries: {summary.get('failed_queries', 0)}")
            
            # CREATE AND SAVE MIGRATION STATS DATAFRAME
            if migration_stats:
                try:
                    customer_logger.info("Creating migration stats DataFrame for RC_Processing_Stats...")
                    migration_df = self.create_migration_stats_dataframe(migration_stats, customer_code, customer_logger)
                    print(migration_df)
                    if not migration_df.empty:
                        # Save to database
                        migration_df.to_csv('migration_stats.csv', index=False)  # For debugging
                        save_success = self.save_migration_stats_to_database(migration_df, customer_code, customer_logger)
                        
                        if save_success:
                            customer_logger.info("Migration stats successfully saved to RC_Processing_Stats table")
                        else:
                            customer_logger.warning("Failed to save migration stats to database")
                    else:
                        customer_logger.warning("Migration stats DataFrame is empty - nothing to save")
                        
                except Exception as df_error:
                    customer_logger.error(f"Error creating/saving migration stats DataFrame: {df_error}")
            
            return migration_stats
            
        except Exception as e:
            customer_logger.error(f"Error extracting migration stats: {e}")
            return []
        
    def expand_metrics_configuration(self, compact_config: dict) -> dict:
        """
        Expand compact configuration into individual metric entries.
        Uses processing_stats_metrics.json from config_parser.
        """
        expanded_config = {}
        
        for table_key, table_config in compact_config.items():
            base_config = table_config.get('base_config', {})
            metrics = table_config.get('metrics', [])
            
            # Skip tables with no metrics defined
            if not metrics:
                self.logger.debug(f"No metrics defined for table {table_key}, skipping")
                continue
            
            # Generate individual metric entries
            for i, metric in enumerate(metrics):
                # Create unique key for each metric
                metric_key = f"{table_key}_{metric['type']}_{i}"
                
                # Merge base config with specific metric config
                expanded_config[metric_key] = {
                    **base_config,  # Include table, filter_by, from_table
                    'function': metric['type'],
                    'column': metric['column'],
                    'description': metric['description'],
                    'result_column': metric['result_column']
                }
                
                self.logger.debug(f"Generated metric: {metric_key} -> {expanded_config[metric_key]}")
        
        #self.logger.info(f"Expanded metrics configuration completed: {len(expanded_config)} total metrics")
        return expanded_config

    def generate_metrics_query(self, metric_key: str, config: dict, load_id: int, session_id: int) -> str:
        """
        Generate SQL query for a specific metric based on configuration.
        """
        try:
            function = config['function'].upper()
            column = config['column']
            table = config['table']
            filter_by = config.get('filter_by', 'loadid').lower()
            
            # Build the base query
            if function == 'COUNT':
                query = f"SELECT COUNT({column}) FROM {table}"
            elif function == 'SUM':
                query = f"SELECT SUM({column}) FROM {table}"
            elif function == 'AVG':
                query = f"SELECT AVG({column}) FROM {table}"
            elif function == 'MAX':
                query = f"SELECT MAX({column}) FROM {table}"
            elif function == 'MIN':
                query = f"SELECT MIN({column}) FROM {table}"
            else:
                raise ValueError(f"Unsupported function: {function}")
            
            # Add WHERE clause based on filter type
            if filter_by == 'loadid':
                query += f" WHERE LoadID = {load_id}"
            elif filter_by == 'createsessionid':
                query += f" WHERE CreateSessionID = {session_id}"
            elif filter_by == 'sessionid':  # Handle legacy sessionid
                query += f" WHERE SessionID = {session_id}"
            else:
                # Default to loadid if unknown filter type
                self.logger.warning(f"Unknown filter_by '{filter_by}' for {metric_key}, using LoadID")
                query += f" WHERE LoadID = {load_id}"
            
            self.logger.debug(f"Generated query for {metric_key}: {query}")
            return query
            
        except Exception as e:
            self.logger.error(f"Error generating query for {metric_key}: {e}")
            raise

    def collect_migration_metrics(self, load_id: int, session_id: int, customer_logger: logging.Logger) -> dict:
        """
        Collect post-migration metrics using the expanded metrics configuration.
        Pulls configuration from config_parser.processing_stats.
        """
        try:
            # Get compact configuration from config_parser
            compact_config = self.config_parser.processing_stats if hasattr(self.config_parser, 'processing_stats') else {}
            
            if not compact_config:
                customer_logger.warning("No processing_stats configuration found in config_parser")
                return {}
            
            # Expand the compact configuration into individual metrics
            metrics_config = self.expand_metrics_configuration(compact_config)
            table_metrics = {}
            
            if not metrics_config:
                customer_logger.warning("No expanded metrics configuration available")
                return {}
            
            customer_logger.info(f"Collecting migration metrics for LoadID: {load_id}, SessionID: {session_id}")
            #customer_logger.info(f"Processing {len(metrics_config)} individual metrics from {len(compact_config)} table configurations")
            
            successful_queries = 0
            failed_queries = 0
            
            # Use SQLAlchemy engine for queries
            if not self.config_parser.db_helper or not self.config_parser.db_helper.sqlalchemy_engine:
                customer_logger.error("Database connection not available for metrics collection")
                return {}
            
            for metric_key, config in metrics_config.items():
                try:
                    # Generate and execute query 
                    query = self.generate_metrics_query(metric_key, config, load_id, session_id)
                    
                    with self.config_parser.db_helper.sqlalchemy_engine.begin() as conn:
                        result = conn.execute(text(query)).fetchone()
                    
                    # Extract table name and result column
                    table_name = config['table']
                    result_column = config['result_column']
                    from_table = config.get('from_table')  # Extract from_table from config
                    
                    # Initialize table metrics if not exists
                    if table_name not in table_metrics:
                        table_metrics[table_name] = {
                            'table_name': table_name,
                            'from_table': from_table,  # Add from_table to metrics
                            'rows_inserted': 0,
                            'total_debt': 0.0,
                            'total_costs': 0.0,
                            'total_paid': 0.0,
                            'total_overpayments': 0.0,
                            'total_outstanding': 0.0,
                            'total_commission': 0.0,
                            'total_interest': 0.0,
                            'query_successful': True,
                            'queries_executed': [],
                            'start_time': datetime.now(),
                            'end_time': datetime.now(),
                            'success': True
                        }
                    
                    if result and result[0] is not None:
                        value = result[0]
                        
                        try:
                            # For counts, store as integer
                            if result_column == 'rows_inserted':
                                stored_value = int(float(value))
                                table_metrics[table_name][result_column] = stored_value
                            else:
                                # For financial columns, store as float with 2 decimal places
                                stored_value = round(float(value), 2)
                                table_metrics[table_name][result_column] = stored_value
                                
                        except (ValueError, TypeError) as conversion_error:
                            customer_logger.warning(f"Could not convert {value} (type: {type(value).__name__}) to number: {conversion_error}")
                            table_metrics[table_name][result_column] = 0
                            
                        successful_queries += 1
                        #customer_logger.info(f"Metrics: {table_name}.{result_column} = {value:,}")
                    else:
                        # No result or NULL result
                        if result_column == 'rows_inserted':
                            table_metrics[table_name][result_column] = 0
                        else:
                            table_metrics[table_name][result_column] = 0.0
                            
                        successful_queries += 1
                        #customer_logger.info(f"Metrics: {table_name}.{result_column} = 0 (no data)")
                        
                    # Track the query execution
                    table_metrics[table_name]['queries_executed'].append({
                        'metric_key': metric_key,
                        'query': query,
                        'result': result[0] if result else None,
                        'success': True
                    })
                        
                except Exception as e:
                    failed_queries += 1
                    customer_logger.error(f"Failed to collect metric {metric_key}: {e}")
                    
                    # Ensure table exists in metrics with error flag
                    table_name = config['table']
                    from_table = config.get('from_table')
                    
                    if table_name not in table_metrics:
                        table_metrics[table_name] = {
                            'table_name': table_name,
                            'from_table': from_table,
                            'rows_inserted': 0,
                            'total_debt': 0.0,
                            'total_costs': 0.0,
                            'total_paid': 0.0,
                            'total_overpayments': 0.0,
                            'total_outstanding': 0.0,
                            'total_commission': 0.0,
                            'total_interest': 0.0,
                            'query_successful': False,
                            'queries_executed': [],
                            'start_time': datetime.now(),
                            'end_time': datetime.now(),
                            'success': False,
                            'error_message': str(e)
                        }
                    else:
                        table_metrics[table_name]['query_successful'] = False
                        table_metrics[table_name]['success'] = False
                        table_metrics[table_name]['error_message'] = str(e)
                    
                    # Track the failed query
                    table_metrics[table_name]['queries_executed'].append({
                        'metric_key': metric_key,
                        'query': query if 'query' in locals() else 'Query generation failed',
                        'result': None,
                        'success': False,
                        'error': str(e)
                    })
            
            # Add summary metrics
            total_records_migrated = sum(metrics.get('rows_inserted', 0) for metrics in table_metrics.values())
            
            table_metrics['_summary'] = {
                'total_records_migrated': total_records_migrated,
                'successful_queries': successful_queries,
                'failed_queries': failed_queries,
                'tables_processed': len([t for t in table_metrics.keys() if not t.startswith('_')])
            }
            
            # Log metrics summary
            customer_logger.info("Migration metrics summary:")
            #customer_logger.info(f"  Tables processed: {len([t for t in table_metrics.keys() if not t.startswith('_')])}")
            #customer_logger.info(f"  Successful queries: {successful_queries}")
            #customer_logger.info(f"  Failed queries: {failed_queries}")
            customer_logger.info(f"  Total records migrated: {total_records_migrated:,}")
            
            return table_metrics
            
        except Exception as e:
            customer_logger.error(f"Critical error in collect_migration_metrics: {e}")
            return {}

    def _create_error_result(self, customer_code: str, error_message: str) -> Dict[str, Any]:
        """Create standardized error result."""
        return {
            'customer_code': customer_code,
            'entity_id': self.entity_id,
            'validation_failed': False,
            'tables_processed': {},
            'total_rows_processed': 0,
            'total_rows_inserted': 0,
            'processing_success': False,
            'sql_migration_completed': False,
            'error': error_message
        }
    
    def cleanup(self):
        """Clean up resources - only close connections if we own them."""
        if self.config_parser and self._owns_config:
            self.config_parser.cleanup()
            self.logger.info("SQLMigrationManager closed own config connection")
        elif self.config_parser:
            self.logger.debug("SQLMigrationManager using shared config - not closing")


# # Example usage
# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
#     # Initialize SQL migration manager with metafield support
#     sql_manager = SQLMigrationManager(environment='v10', load_id=12345, session_id=67890, entity_id=110)
    
#     if sql_manager.initialize():
#         print("SQL Migration Manager with Metafield Support initialized successfully")
        
#         # Show metafield variables
#         print(f"\nMetafield Variables Available: {len(sql_manager.metafield_variables)}")
#         for name, value in sql_manager.metafield_variables.items():
#             status = "✓" if value is not None else "✗"
#             print(f"  {status} {name:15} : {value}")
        
#         # Scan all SQL files (this will generate metafield variants)
#         sql_files = sql_manager.scan_sql_files()
#         print(f"\nFound {len(sql_files)} SQL files (including metafield variants)")
        
#         # Process files in range that includes Loop and Metavalue
#         print("\n--- PROCESSING WITH METAFIELD VARIANTS ---")
#         prepared_sql = sql_manager.prepare_sql_for_execution()
#         sql_manager.print_sql_summary(prepared_sql)
        
#         # Export to test folder
#         exported_files = sql_manager.export_prepared_sql(prepared_sql)
#         print(f"\nExported {len(exported_files)} files with metafield variants")

#     else:
#         print("Failed to initialize SQL Migration Manager")