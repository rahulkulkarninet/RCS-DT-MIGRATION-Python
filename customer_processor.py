import logging
import uuid
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from services.io.customer_file_service import CustomerFileService
from db_manager import DatabaseHelper
from services.orchestration.customer_lifecycle_service import CustomerLifecycleService
from services.io.customer_io_service import CustomerIOService
from services.execution.migration_execution_service import MigrationExecutionService
from services.setup.migration_setup_service import MigrationSetupService
from services.workflows.customer_sql_workflow_service import CustomerSQLWorkflowService
from services.workflows.customer_status_workflow_service import CustomerStatusWorkflowService
from services.workflows.customer_staging_workflow_service import CustomerStagingWorkflowService
from services.workflows.customer_summary_service import CustomerSummaryService
from process_staging import StagingProcessor
from memory_manager import MemoryManager
from result_types import MixedExecutionResult, StatusCheckResult, StatusUpdateResult
from status_service import StatusService
from config_parser import ConfigParser
from interaction import ApprovalPolicy, GATE_SQL, GATE_STAGING


class CustomerProcessor:
    """Process migration files on a customer-by-customer basis with full migration infrastructure."""
    
    def __init__(self, environment: str, approval_policy: Optional[ApprovalPolicy] = None,
                 resume_load_id: Optional[int] = None):
        self.environment = environment
        self.logger = logging.getLogger(__name__)


        self.resume_load_id = resume_load_id


        self.approval_policy = approval_policy or ApprovalPolicy(logger=self.logger)

        # SHARED DATABASE CONNECTION - Initialize first
        self.shared_db_helper = None
        
        # Initialize config parser
        self.config_parser = None
        
        # Core components
        self.staging_processor = None
        self.memory_manager = MemoryManager(max_memory_percent=80.0)
        self.sql_manager = None
        self.status_service: Optional[StatusService] = None
        self.migration_execution_service = MigrationExecutionService()
        self.migration_setup_service = MigrationSetupService()
        self.customer_io_service = CustomerIOService()
        self.customer_file_service = CustomerFileService()
        self.customer_sql_workflow_service = CustomerSQLWorkflowService()
        self.customer_status_workflow_service = CustomerStatusWorkflowService()
        self.customer_staging_workflow_service = CustomerStagingWorkflowService()
        self.customer_lifecycle_service = CustomerLifecycleService()
        self.customer_summary_service = CustomerSummaryService()

        # Entity and session management
        self.staging_load_id = None
        self.entity_mapping = {}
        self.entity_id = None
        self.current_load_id = None
        self.current_session_id = None
        self.user = None

        # Database connections
        self.pyodbc_conn = None


        self.processing_stats = []
        self._migration_processing_stats = []

        self.run_id = str(uuid.uuid4())

        # Client code / group data extracted from RC_ACCOUNT_EXTRACT
        self.client_codes_df: Optional[pd.DataFrame] = None
        self._account_status_lookup_cache: Optional[Dict[str, str]] = None


    def initialize(self) -> bool:
        """Initialize the customer processor."""
        try:
            # Initialize database connections
            self.shared_db_helper = DatabaseHelper(environment=self.environment)

            # Get PyODBC connection reference for load/session management
            self.shared_db_helper.connect_pyodbc()
            self.shared_db_helper.connect_sqlalchemy()
            self.pyodbc_conn = self.shared_db_helper.pyodbc_connection
            self.sqlalchemy_engine = self.shared_db_helper.sqlalchemy_engine
            if not self.pyodbc_conn or not self.sqlalchemy_engine:
                self.logger.error("Database connections not available")
                return False
            
            self.logger.info(f"Shared database connections established")

            # Initialize config parser with shared connection
            self.config_parser = ConfigParser(
                db_environment=self.environment, 
                shared_db_helper=self.shared_db_helper
            )
            self.config_parser.load_configs()
            self.status_service = StatusService(self.shared_db_helper)

            # Set user using db_manager function
            user = self.shared_db_helper._get_current_username()
            if user:
                self.user = user.split('@')[0]
            else :
                self.user = None
             
            # Initialize staging processor with shared connection
            self.staging_processor = StagingProcessor(
                environment=self.environment,
                shared_db_helper=self.shared_db_helper,
                shared_config_parser=self.config_parser
            )
            if not self.staging_processor.initialize():
                self.logger.error("Failed to initialize staging processor")
                return False
            
            # Load entity mapping
            self.load_entity_mapping()
            
            self.logger.info(f"Customer processor initialized for environment: {self.environment}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize customer processor: {e}")
            return False
    
    def load_entity_mapping(self) -> Dict[str, int]:
        """
        Get entity mapping from database.
        Returns dictionary mapping customer codes to entity IDs.
        """
        return self.migration_setup_service.load_entity_mapping(self)

    def create_migration_load_record(self, entity_id: int) -> str:
        """
        Insert a new record into tblLoad for migration and return the LoadID.
        """
        return self.migration_setup_service.create_migration_load_record(self, entity_id)
    
    def rollback_load_record(self, load_id: str) -> bool:
        """
        Delete the load record from tblLoad to rollback the migration setup.
        """
        return self.migration_setup_service.rollback_load_record(self, load_id)

    def create_migration_session(self) -> int:
        """
        Create a new session record for the migration and return the SessionID.
        
        Returns:
            int: SessionID if successful, None if failed
        """
        return self.migration_setup_service.create_migration_session(self)
        
    def close_migration_session(self, session_id: int) -> bool:
        """
        Close the migration session by updating LogoutTime.
        """
        return self.migration_setup_service.close_migration_session(self, session_id)
        
    def generate_staging_load_id(self, customer_code: str, db: str) -> str:
        """Generate a unique load ID using db, customer code and timestamp."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_suffix = str(uuid.uuid4())[:6]
        return f"{db}_{customer_code}_{timestamp}_{unique_suffix}"

    def get_client_codes_from_account_extract(self, files: List[str]) -> pd.DataFrame:
        """
        Read and concatenate all RC_ACCOUNT_EXTRACT files for a customer and return
        a DataFrame of unique (Client_Code, Client_Group) pairs.
        The result is stored in self.client_codes_df.
        """
        try:
            account_files = [
                f for f in files
                if self.staging_processor.match_file(f)[1] == 'RC_ACCOUNT_EXTRACT'
            ]

            if not account_files:
                self.logger.error("No RC_ACCOUNT_EXTRACT files found in the provided file list")
                self.client_codes_df = pd.DataFrame(columns=['Client_Code', 'Client_Group'])
                return self.client_codes_df

            combined_df = self.staging_processor.concat_files(account_files)

            if combined_df.empty:
                self.logger.error("RC_ACCOUNT_EXTRACT files produced an empty DataFrame")
                self.client_codes_df = pd.DataFrame(columns=['Client_Code', 'Client_Group'])
                return self.client_codes_df

            missing = [c for c in ['Client_Code', 'Client_Group'] if c not in combined_df.columns]
            if missing:
                self.logger.error(f"RC_ACCOUNT_EXTRACT is missing expected columns: {missing}")
                self.client_codes_df = pd.DataFrame(columns=['Client_Code', 'Client_Group'])
                return self.client_codes_df

            self.client_codes_df = (
                combined_df[['Client_Code', 'Client_Group']]
                .drop_duplicates()
                .reset_index(drop=True)
            )
            self.logger.info(
                f"Extracted {len(self.client_codes_df)} unique Client_Code/Client_Group pairs "
                f"from {len(account_files)} RC_ACCOUNT_EXTRACT file(s)"
            )
            return self.client_codes_df

        except Exception as e:
            self.logger.error(f"Error extracting client codes from RC_ACCOUNT_EXTRACT: {e}")
            self.client_codes_df = pd.DataFrame(columns=['Client_Code', 'Client_Group'])
            return self.client_codes_df

    def setup_customer_migration(self, customer_code: str, db: str) -> Dict[str, Any]:
        """
        Set up migration infrastructure for a customer (LoadID and SessionID).
        """
        return self.migration_setup_service.setup_customer_migration(self, customer_code, db)

    def create_customer_directories(self, customer_code: str, db: str, base_path: str,
                                     entity_id: int, load_id: int, session_id: int) -> dict:
        """
        Create customer-specific directories and return paths.
        """
        return self.customer_io_service.create_customer_directories(
            customer_code=customer_code,
            db=db,
            base_path=base_path,
            entity_id=entity_id,
            load_id=load_id,
            session_id=session_id,
        )

    def setup_customer_logger(self, customer_code: str, db: str, customer_paths: dict, 
                              entity_id: int, load_id: int, session_id: int) -> logging.Logger:
        """
        Set up customer-specific logger that writes to customer's folder.

        """
        return self.customer_io_service.setup_customer_logger(
            customer_code=customer_code,
            db=db,
            customer_paths=customer_paths,
            entity_id=entity_id,
            load_id=load_id,
            session_id=session_id,
        )
    
    def cleanup_customer_logger(self, customer_logger: logging.Logger):
        """
        Clean up customer-specific logger by closing file handlers.
        """
        self.customer_io_service.cleanup_customer_logger(self, customer_logger)
    
    def cleanup_customer_migration(self, load_id: str = None, session_id: int = None, rollback: bool = False) -> bool:
        """
        Clean up migration infrastructure after customer processing.
        """
        return self.migration_setup_service.cleanup_customer_migration(
            self,
            load_id=load_id,
            session_id=session_id,
            rollback=rollback,
        )

    def set_entity_id_from_customer_code(self, customer_code: str) -> bool:
        """
        Resolve entity_id for customer_code using Client_Group as the parent entity lookup.

        Logic:
          1. Look up the customer_code in self.client_codes_df to obtain its Client_Group(s).
          2. For each Client_Group, query tblentity for child entities whose Parent_EntityID matches the Client_Group's EntityID.
          3. Match a child EntityCode to customer_code (Client_Code) to get EntityID.
          4. Fail hard (return False) if any step in the chain does not resolve.
        """
        if self.client_codes_df is None or self.client_codes_df.empty:
            self.logger.error(
                f"client_codes_df is empty — call get_client_codes_from_account_extract "
                f"before set_entity_id_from_customer_code for customer '{customer_code}'"
            )
            self.entity_id = None
            return False

        # Filter rows for this customer's Client_Code
        customer_rows = self.client_codes_df[
            self.client_codes_df['Client_Code'].astype(str).str.strip() == str(customer_code).strip()
        ]

        if customer_rows.empty:
            self.logger.error(
                f"Customer code '{customer_code}' not found in RC_ACCOUNT_EXTRACT data"
            )
            self.entity_id = None
            return False

        client_groups = customer_rows['Client_Group'].dropna().astype(str).str.strip().unique().tolist()
        self.logger.info(
            f"Customer '{customer_code}' has Client_Group(s): {client_groups}"
        )

        for client_group in client_groups:
            try:
                query = """
                            SELECT child.EntityCode, child.EntityID
                            FROM tblentity parent
                            JOIN tblentity child ON child.Parent_EntityID = parent.EntityID
                            WHERE parent.EntityCode = :entity_code
                        """
                result = self.config_parser.db_helper.execute_query(query, params={'entity_code': client_group})

                if result.empty:
                    self.logger.warning(
                        f"No child entities found under parent EntityCode '{client_group}'"
                    )
                    continue

                match = result[
                    result['EntityCode'].astype(str).str.strip() == str(customer_code).strip()
                ]

                if not match.empty:
                    entity_id = int(match.iloc[0]['EntityID'])
                    self.entity_id = entity_id
                    self.entity_mapping[customer_code] = entity_id
                    self.logger.info(
                        f"Resolved entity_id={entity_id} for customer '{customer_code}' "
                        f"via Client_Group '{client_group}'"
                    )
                    return True

                self.logger.warning(
                    f"Customer code '{customer_code}' not found among children of '{client_group}' "
                    f"(available: {result['EntityCode'].tolist()})"
                )

            except Exception as e:
                self.logger.error(
                    f"Error querying entity children for Client_Group '{client_group}': {e}"
                )

        self.logger.error(
            f"Failed to resolve entity_id for customer '{customer_code}': "
            f"no matching child entity found for Client_Group(s) {client_groups}"
        )
        self.entity_id = None
        return False
    
    def extract_customer_code_from_filename(self, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract db and customer code from filename.
        Returns (db, customer_code) where db is the first part and customer_code is the second part.
        Example: "SMAUS_SM9596_RC_ACCOUNT_EXTRACT_0001.csv" -> ("SMAUS", "SM9596")
        """
        return self.customer_file_service.extract_customer_code_from_filename(self, filename)
    
    def group_files_by_customer(self) -> Dict[str, Dict[str, Any]]:
        """
        Group staging files by customer code.
        Returns dictionary mapping customer codes to {'db': db, 'files': [...]}.
        """
        return self.customer_file_service.group_files_by_customer(self)
    
    def validate_customers_against_entity_mapping(self, customer_groups: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """
        Validate that all customer codes exist in entity mapping.
        Returns dictionary mapping customer codes to validation status.
        """
        return self.customer_file_service.validate_customers_against_entity_mapping(self, customer_groups)
    
    def validate_customer_files(self, customer_code: str, db: str, files: List[str]) -> Dict[str, Any]:
        """Validate customer files before processing."""
        return self.customer_file_service.validate_customer_files(self, customer_code, db, files)
    
    def move_files_to_customer_folder(self, files: list[str], success: bool, rows_processed: int = 0, 
                                 customer_paths: dict = None, error_message: str = ''):
        """Move files to customer-specific folders based on processing results."""
        self.customer_file_service.move_files_to_customer_folder(
            self,
            files=files,
            success=success,
            rows_processed=rows_processed,
            customer_paths=customer_paths,
            error_message=error_message,
        )

    def process_customer_staging(self, customer_code: str, db: str, files: List[str], customer_logger: logging.Logger, customer_paths: dict) -> Dict[str, any]:
        """
        Main staging process with user prompts for each step.
        """
        return self.customer_staging_workflow_service.process_customer_staging(
            self,
            customer_code=customer_code,
            db=db,
            files=files,
            customer_logger=customer_logger,
            customer_paths=customer_paths,
        )

    def _validate_customer_files_step(self, customer_code: str, db: str, files: List[str], customer_logger: logging.Logger) -> Dict[str, Any]:
        """Step 1: Validate customer files."""
        return self.customer_staging_workflow_service.validate_customer_files_step(
            self,
            customer_code=customer_code,
            db=db,
            files=files,
            customer_logger=customer_logger,
        )

    def _truncate_staging_tables_step(self, customer_code: str, db: str, customer_logger: logging.Logger) -> bool:
        """Step 2: Truncate staging tables."""
        return self.customer_staging_workflow_service.truncate_staging_tables_step(
            self,
            customer_code=customer_code,
            db=db,
            customer_logger=customer_logger,
        )

    def _process_customer_tables_step(self, customer_code: str, db: str, files: List[str], customer_logger: logging.Logger, 
                                    customer_paths: dict, validation: Dict[str, Any]) -> Dict[str, Any]:
        """Step 3: Process customer tables."""
        return self.customer_staging_workflow_service.process_customer_tables_step(
            self,
            customer_code=customer_code,
            db=db,
            files=files,
            customer_logger=customer_logger,
            customer_paths=customer_paths,
            validation=validation,
        )

    def _create_staging_failure_result(self, customer_code: str, db: str, reason: str, validation: Dict = None, error: str = '') -> Dict[str, Any]:
        """Create standardized failure result for staging."""
        return self.customer_staging_workflow_service.create_staging_failure_result(
            self,
            customer_code=customer_code,
            db=db,
            reason=reason,
            validation=validation,
            error=error,
        )

    def update_rc_account_extract_ma_status(self, customer_logger: logging.Logger) -> StatusUpdateResult:
        """
        Replace RC_ACCOUNT_EXTRACT.MA_Status codes with standardized labels
        using variables/account_status_codes.json.
        """
        return self.customer_status_workflow_service.update_rc_account_extract_ma_status(
            self,
            customer_logger,
        )

    def _load_account_status_mapping_frame(self, status_mapping: Dict[str, Any]) -> Tuple[pd.DataFrame, int]:
        return self.customer_status_workflow_service.load_account_status_mapping_frame(
            self,
            status_mapping,
        )

    def _build_ma_status_resolution_frame(self, mapping_frame: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        return self.customer_status_workflow_service.build_ma_status_resolution_frame(
            self,
            mapping_frame,
        )

    def _bulk_update_rc_account_extract_ma_status(self, resolution_frame: pd.DataFrame) -> int:
        return self.customer_status_workflow_service.bulk_update_rc_account_extract_ma_status(
            self,
            resolution_frame,
        )

    def _get_invalid_ma_statuses_from_db(self) -> List[str]:
        return self.customer_status_workflow_service.get_invalid_ma_statuses_from_db(self)

    def _status_match_key(self, value: str) -> str:
        return self.customer_status_workflow_service.status_match_key(self, value)

    def _status_match_key_series(self, series: pd.Series) -> pd.Series:
        return self.customer_status_workflow_service.status_match_key_series(self, series)

    def _normalize_status_lookup_key(self, value: str) -> str:
        return self.customer_status_workflow_service.normalize_status_lookup_key(self, value)

    def _normalize_status_lookup_series(self, series: pd.Series) -> pd.Series:
        return self.customer_status_workflow_service.normalize_status_lookup_series(self, series)
    
        
    def execute_mixed_sql_methods(self, customer_code: str, db: str, customer_logger: logging.Logger,
                             customer_paths: dict, staging_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main SQL execution process with user prompts for each step.
        """
        return self.customer_sql_workflow_service.execute_mixed_sql_methods(
            self,
            customer_code,
            db,
            customer_logger,
            customer_paths,
            staging_result,
        )

    def _initialize_sql_manager_step(self, customer_code: str, db: str, customer_logger: logging.Logger) -> bool:
        """Step 1: Initialize SQL Migration Manager."""
        return self.customer_sql_workflow_service.initialize_sql_manager_step(
            self,
            customer_code,
            db,
            customer_logger,
        )

    def _check_status_codes_step(self, customer_code: str, db: str, customer_logger: logging.Logger,
                                 status_update_result: Optional[StatusUpdateResult] = None) -> StatusCheckResult:
        """Step 3: Check status codes and report missing values."""
        return self.customer_status_workflow_service.check_status_codes_step(
            self,
            customer_code,
            db,
            customer_logger,
            status_update_result,
        )

    def _prepare_sql_files_step(self, customer_code: str, db: str, customer_logger: logging.Logger) -> Dict[str, Any]:
        """Step 3: Prepare SQL files with variable replacement."""
        return self.customer_sql_workflow_service.prepare_sql_files_step(
            self,
            customer_code,
            db,
            customer_logger,
        )

    def _export_sql_files_step(self, customer_code: str, db: str, customer_logger: logging.Logger, 
                              customer_paths: dict, prepared_sql: Dict[str, Any]) -> str:
        """Step 4: Export SQL files to customer folder."""
        return self.customer_sql_workflow_service.export_sql_files_step(
            self,
            customer_code,
            db,
            customer_logger,
            customer_paths,
            prepared_sql,
        )

    def _execute_sql_files_step(self, customer_code: str, db: str, customer_logger: logging.Logger, 
                               sql_export_path: str) -> Dict[str, Any]:
        """Step 5: Execute SQL files using mixed methods."""
        return self.customer_sql_workflow_service.execute_sql_files_step(
            self,
            customer_code,
            db,
            customer_logger,
            sql_export_path,
        )

    def _collect_migration_metrics_step(self, customer_code: str, db: str, customer_logger: logging.Logger) -> Dict[str, Any]:
        """Step 6: Collect migration metrics."""
        return self.customer_sql_workflow_service.collect_migration_metrics_step(
            self,
            customer_code,
            db,
            customer_logger,
        )

    def _process_sql_execution_results_step(self, customer_code: str, db: str, customer_logger: logging.Logger,
                                          mixed_execution_results: Dict[str, Any], migration_stats: Dict[str, Any],
                                          sql_export_path: str, customer_paths: dict) -> Dict[str, Any]:
        """Step 7: Process SQL execution results and create summary."""
        return self.customer_sql_workflow_service.process_sql_execution_results_step(
            self,
            customer_code,
            db,
            customer_logger,
            mixed_execution_results,
            migration_stats,
            sql_export_path,
            customer_paths,
        )

    def _create_sql_failure_result(self, customer_code: str, db: str, customer_paths: dict, reason: str, error: str = '') -> Dict[str, Any]:
        """Create standardized failure result for SQL execution."""
        return self.customer_sql_workflow_service.create_sql_failure_result(
            customer_code,
            db,
            customer_paths,
            reason,
            error,
        )
        
    def _get_financial_tables_from_metrics(self, table_metrics: dict) -> dict:
        """
        Dynamically identify which tables have financial data based on metrics.
        Similar to Testing_Staging.py get_financial_tables_from_metrics function.
        """
        return self.customer_sql_workflow_service.get_financial_tables_from_metrics(self, table_metrics)

    def _execute_mixed_sql_methods_internal(self, export_folder_path: str, customer_logger: logging.Logger) -> MixedExecutionResult:
        """
        Internal method to execute SQL files using mixed methods.
        Files 1-75: PyODBC with transaction control
        File 76: SQLCMD for compatibility
        Preserves connections for stats extraction.
        """
        return self.migration_execution_service.execute_mixed_sql_methods_internal(
            self.sql_manager,
            export_folder_path,
            customer_logger,
        )
            

    def process_staging_to_migration(self, validate_only: bool = False) -> Dict[str, Dict]:
        """
        Process from staging area to migration area for all customers.
        """
        return self.customer_lifecycle_service.process_staging_to_migration(self, validate_only=validate_only)
    
    def _print_customer_completion_summary(self, customer_code: str, db: str, result: Dict[str, Any], 
                                  customer_logger: logging.Logger) -> str:
        """Print completion summary for a single customer."""
        return self.customer_summary_service.print_customer_completion_summary(
            customer_code=customer_code,
            db=db,
            result=result,
            customer_logger=customer_logger,
            entity_id=self.entity_id,
            current_load_id=self.current_load_id,
            current_session_id=self.current_session_id,
            staging_load_id=self.staging_load_id,
        )

    
    def cleanup(self):
        """Clean up resources."""
        # Close any remaining sessions or rollback loads if needed
        if self.current_session_id:
            self.close_migration_session(self.current_session_id)
        
        if self.staging_processor:
            self.staging_processor.cleanup()

        if self.sql_manager:
            self.sql_manager.cleanup()

        if self.shared_db_helper:
            self.shared_db_helper.close_connections()
            self.logger.info("Shared database connections closed")

# # Example usage
# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
#     # Initialize customer processor
#     processor = CustomerProcessor('v10')
    
#     if processor.initialize():
#         print("Customer Processor initialized successfully")

#         processor.process_staging_to_migration()

        
        
        