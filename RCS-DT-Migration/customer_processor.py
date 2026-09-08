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
from services.workflows.customer_archive_workflow_service import (
    CustomerArchiveWorkflowService,
)
from services.workflows.customer_arrangement_type_workflow_service import (
    CustomerArrangementTypeWorkflowService,
)
from services.workflows.customer_bank_transaction_method_workflow_service import (
    CustomerBankTransactionMethodWorkflowService,
)
from services.workflows.customer_closure_reason_workflow_service import (
    CustomerClosureReasonWorkflowService,
)
from services.workflows.customer_frequency_workflow_service import (
    CustomerFrequencyWorkflowService,
)
from services.workflows.customer_incident_type_workflow_service import (
    CustomerIncidentTypeWorkflowService,
)
from services.workflows.customer_related_party_type_workflow_service import (
    CustomerRelatedPartyTypeWorkflowService,
)
from services.workflows.customer_state_workflow_service import (
    CustomerStateWorkflowService,
)
from services.workflows.customer_sql_workflow_service import CustomerSQLWorkflowService
from services.workflows.customer_status_workflow_service import CustomerStatusWorkflowService
from services.workflows.customer_staging_workflow_service import CustomerStagingWorkflowService
from services.workflows.customer_summary_service import CustomerSummaryService
from process_staging import StagingProcessor
from memory_manager import MemoryManager
from result_types import (
    ArrangementTypeCheckResult,
    ArrangementTypeUpdateResult,
    ClosureReasonCheckResult,
    ClosureReasonUpdateResult,
    BankTransactionMethodCheckResult,
    BankTransactionMethodUpdateResult,
    FrequencyCheckResult,
    FrequencyUpdateResult,
    IncidentTypeCheckResult,
    IncidentTypeUpdateResult,
    MixedExecutionResult,
    RelatedPartyTypeCheckResult,
    RelatedPartyTypeUpdateResult,
    StateCheckResult,
    StateUpdateResult,
    StatusCheckResult,
    StatusUpdateResult,
)
from arrangement_type_service import ArrangementTypeService
from bank_transaction_method_service import BankTransactionMethodService
from closure_reason_service import ClosureReasonService
from frequency_service import FrequencyService
from incident_type_service import IncidentTypeService
from related_party_type_service import RelatedPartyTypeService
from state_service import StateService
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

        # Second connection, to the staging archive database on the same server.
        # Created on first use, because a run that never reaches the archive step
        # should not open it.
        self.archive_db_helper = None

        # Initialize config parser
        self.config_parser = None
        
        # Core components
        self.staging_processor = None
        self.memory_manager = MemoryManager(max_memory_percent=80.0)
        self.sql_manager = None
        self.status_service: Optional[StatusService] = None
        self.bank_transaction_method_service: Optional[BankTransactionMethodService] = None
        self.arrangement_type_service: Optional[ArrangementTypeService] = None
        self.closure_reason_service: Optional[ClosureReasonService] = None
        self.frequency_service: Optional[FrequencyService] = None
        self.related_party_type_service: Optional[RelatedPartyTypeService] = None
        self.incident_type_service: Optional[IncidentTypeService] = None
        self.state_service: Optional[StateService] = None
        self.migration_execution_service = MigrationExecutionService()
        self.migration_setup_service = MigrationSetupService()
        self.customer_io_service = CustomerIOService()
        self.customer_file_service = CustomerFileService()
        self.customer_sql_workflow_service = CustomerSQLWorkflowService()
        self.customer_status_workflow_service = CustomerStatusWorkflowService()
        self.customer_bank_transaction_method_workflow_service = (
            CustomerBankTransactionMethodWorkflowService()
        )
        self.customer_arrangement_type_workflow_service = (
            CustomerArrangementTypeWorkflowService()
        )
        self.customer_closure_reason_workflow_service = (
            CustomerClosureReasonWorkflowService()
        )
        self.customer_frequency_workflow_service = (
            CustomerFrequencyWorkflowService()
        )
        self.customer_related_party_type_workflow_service = (
            CustomerRelatedPartyTypeWorkflowService()
        )
        self.customer_incident_type_workflow_service = (
            CustomerIncidentTypeWorkflowService()
        )
        self.customer_state_workflow_service = CustomerStateWorkflowService()
        self.customer_staging_workflow_service = CustomerStagingWorkflowService()
        self.customer_archive_workflow_service = CustomerArchiveWorkflowService()
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

        # Staged file moves, held until all mapping checks are confirmed.
        self.pending_file_moves: List[Dict[str, Any]] = []

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
            self.bank_transaction_method_service = BankTransactionMethodService(self.shared_db_helper)
            self.arrangement_type_service = ArrangementTypeService(self.shared_db_helper)
            self.closure_reason_service = ClosureReasonService(self.shared_db_helper)
            self.frequency_service = FrequencyService(self.shared_db_helper)
            self.related_party_type_service = RelatedPartyTypeService(self.shared_db_helper)
            self.incident_type_service = IncidentTypeService(self.shared_db_helper)
            self.state_service = StateService(self.shared_db_helper)

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

    def queue_files_for_move(self, files: list[str], success: bool, rows_processed: int = 0,
                             customer_paths: dict = None, error_message: str = ''):
        """Queue a file move to run once all mapping checks have been confirmed."""
        self.customer_file_service.queue_files_for_move(
            self,
            files=files,
            success=success,
            rows_processed=rows_processed,
            customer_paths=customer_paths,
            error_message=error_message,
        )

    def flush_pending_file_moves(self, customer_logger: logging.Logger = None) -> Dict[str, int]:
        """Perform every queued file move."""
        return self.customer_file_service.flush_pending_file_moves(self, customer_logger)

    def reset_pending_file_moves(self) -> None:
        """Clear any queued moves left over from a previous customer."""
        self.customer_file_service.reset_pending_file_moves(self)

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

    def get_archive_db_helper(self) -> DatabaseHelper:
        """Connection to the staging archive database, opened once per run."""
        if self.archive_db_helper is None:
            helper = self.shared_db_helper.archive_database_helper()
            helper.connect_pyodbc()
            helper.connect_sqlalchemy()
            self.archive_db_helper = helper
            self.logger.info(
                f"Archive connection established to {helper.config['DATABASE']}"
            )
        return self.archive_db_helper

    def archive_staging_tables(self, customer_code: str, db: str,
                               customer_logger: logging.Logger) -> Dict[str, Any]:
        """
        Final step: copy this customer's staging tables into the archive database.
        """
        return self.customer_archive_workflow_service.archive_staging_tables_step(
            self,
            customer_code=customer_code,
            db=db,
            customer_logger=customer_logger,
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

    def update_payment_methods(
        self,
        customer_logger: logging.Logger,
    ) -> BankTransactionMethodUpdateResult:
        """
        Replace staging Payment_Method codes with standardized
        tblBankTransactionMethod labels using
        variables/bank_transaction_method_codes.json.
        """
        return self.customer_bank_transaction_method_workflow_service.update_payment_methods(
            self,
            customer_logger,
        )

    def _check_bank_transaction_methods_step(
        self,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        method_update_result: Optional[BankTransactionMethodUpdateResult] = None,
    ) -> BankTransactionMethodCheckResult:
        """Check bank transaction methods and report unmapped values."""
        return self.customer_bank_transaction_method_workflow_service.check_bank_transaction_methods_step(
            self,
            customer_code,
            db,
            customer_logger,
            method_update_result,
        )

    def _load_bank_transaction_method_mapping_frame(
        self,
        method_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        return self.customer_bank_transaction_method_workflow_service.load_bank_transaction_method_mapping_frame(
            self,
            method_mapping,
        )

    def _build_payment_method_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        return self.customer_bank_transaction_method_workflow_service.build_payment_method_resolution_frame(
            self,
            mapping_frame,
        )

    def _bulk_update_payment_methods(self, resolution_frame: pd.DataFrame) -> Dict[str, int]:
        return self.customer_bank_transaction_method_workflow_service.bulk_update_payment_methods(
            self,
            resolution_frame,
        )

    def _get_invalid_payment_methods_from_db(self) -> Dict[str, List[str]]:
        return self.customer_bank_transaction_method_workflow_service.get_invalid_payment_methods_from_db(self)

    def update_arrangement_types(
        self,
        customer_logger: logging.Logger,
    ) -> ArrangementTypeUpdateResult:
        """
        Replace RC_ARRANGEMENT.Arrangement_Type codes with standardized
        tblArrangementType labels using variables/arrangement_type_codes.json,
        defaulting NULL/blank values to the label configured in that file.
        """
        return self.customer_arrangement_type_workflow_service.update_arrangement_types(
            self,
            customer_logger,
        )

    def _check_arrangement_types_step(
        self,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        type_update_result: Optional[ArrangementTypeUpdateResult] = None,
    ) -> ArrangementTypeCheckResult:
        """Check arrangement types and report unmapped values."""
        return self.customer_arrangement_type_workflow_service.check_arrangement_types_step(
            self,
            customer_code,
            db,
            customer_logger,
            type_update_result,
        )

    def _load_arrangement_type_mapping_frame(
        self,
        type_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        return self.customer_arrangement_type_workflow_service.load_arrangement_type_mapping_frame(
            self,
            type_mapping,
        )

    def _resolve_arrangement_type_default_label(self, default_label: Optional[str]) -> Optional[str]:
        return self.customer_arrangement_type_workflow_service.resolve_default_label(
            self,
            default_label,
        )

    def _build_arrangement_type_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        return self.customer_arrangement_type_workflow_service.build_arrangement_type_resolution_frame(
            self,
            mapping_frame,
        )

    def _bulk_update_arrangement_types(
        self,
        resolution_frame: pd.DataFrame,
        default_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        return self.customer_arrangement_type_workflow_service.bulk_update_arrangement_types(
            self,
            resolution_frame,
            default_label,
        )

    def _get_invalid_arrangement_types_from_db(self) -> List[str]:
        return self.customer_arrangement_type_workflow_service.get_invalid_arrangement_types_from_db(self)

    def update_frequencies(
        self,
        customer_logger: logging.Logger,
    ) -> FrequencyUpdateResult:
        """
        Replace RC_ARRANGEMENT.Frequency codes with standardized tblFrequency labels
        using variables/frequency_codes.json, so 76.final loops and sps to run.sql can
        resolve FrequencyID by a label JOIN instead of a hardcoded CASE.
        """
        return self.customer_frequency_workflow_service.update_frequencies(
            self,
            customer_logger,
        )

    def _check_frequencies_step(
        self,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        frequency_update_result: Optional[FrequencyUpdateResult] = None,
    ) -> FrequencyCheckResult:
        """Check frequencies and report unmapped values."""
        return self.customer_frequency_workflow_service.check_frequencies_step(
            self,
            customer_code,
            db,
            customer_logger,
            frequency_update_result,
        )

    def _load_frequency_mapping_frame(
        self,
        frequency_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        return self.customer_frequency_workflow_service.load_frequency_mapping_frame(
            self,
            frequency_mapping,
        )

    def _build_frequency_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        return self.customer_frequency_workflow_service.build_frequency_resolution_frame(
            self,
            mapping_frame,
        )

    def _bulk_update_frequencies(self, resolution_frame: pd.DataFrame) -> int:
        return self.customer_frequency_workflow_service.bulk_update_frequencies(
            self,
            resolution_frame,
        )

    def _get_invalid_frequencies_from_db(self) -> List[str]:
        return self.customer_frequency_workflow_service.get_invalid_frequencies_from_db(self)

    def update_related_party_types(
        self,
        customer_logger: logging.Logger,
    ) -> RelatedPartyTypeUpdateResult:
        """
        Replace RC_RELATEDPARTY.Related_Party_Type_Code codes with standardized
        tblRelationship labels using variables/related_party_type_codes.json, sweeping
        unmapped codes to the fallback configured in that file.
        """
        return self.customer_related_party_type_workflow_service.update_related_party_types(
            self,
            customer_logger,
        )

    def _check_related_party_types_step(
        self,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        type_update_result: Optional[RelatedPartyTypeUpdateResult] = None,
    ) -> RelatedPartyTypeCheckResult:
        """Check related party types and report unmapped values."""
        return self.customer_related_party_type_workflow_service.check_related_party_types_step(
            self,
            customer_code,
            db,
            customer_logger,
            type_update_result,
        )

    def _load_related_party_type_mapping_frame(
        self,
        type_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        return self.customer_related_party_type_workflow_service.load_related_party_type_mapping_frame(
            self,
            type_mapping,
        )

    def _build_related_party_type_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        return self.customer_related_party_type_workflow_service.build_related_party_type_resolution_frame(
            self,
            mapping_frame,
        )

    def _bulk_update_related_party_types(
        self,
        resolution_frame: pd.DataFrame,
        fallback_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        return self.customer_related_party_type_workflow_service.bulk_update_related_party_types(
            self,
            resolution_frame,
            fallback_label,
        )

    def _get_invalid_related_party_types_from_db(self) -> List[str]:
        return self.customer_related_party_type_workflow_service.get_invalid_related_party_types_from_db(self)

    def update_incident_types(
        self,
        customer_logger: logging.Logger,
    ) -> IncidentTypeUpdateResult:
        """
        Classify RC_ACCOUNT_EXTRACT.Cause_Description into standardized tblIncidentType
        labels using the ordered keyword rules in variables/incident_type_codes.json,
        sweeping unmatched text to the default configured in that file.
        """
        return self.customer_incident_type_workflow_service.update_incident_types(
            self,
            customer_logger,
        )

    def _check_incident_types_step(
        self,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        incident_type_update_result: Optional[IncidentTypeUpdateResult] = None,
    ) -> IncidentTypeCheckResult:
        """Check incident types and report unclassified cause descriptions."""
        return self.customer_incident_type_workflow_service.check_incident_types_step(
            self,
            customer_code,
            db,
            customer_logger,
            incident_type_update_result,
        )

    def _load_incident_type_rules(
        self,
        rules: List[Any],
    ) -> Tuple[List[Dict[str, str]], int]:
        return self.customer_incident_type_workflow_service.load_incident_type_rules(
            self,
            rules,
        )

    def _build_incident_type_resolution_frame(
        self,
        rules: List[Dict[str, str]],
    ) -> Tuple[pd.DataFrame, List[str]]:
        return self.customer_incident_type_workflow_service.build_incident_type_resolution_frame(
            self,
            rules,
        )

    def _bulk_update_incident_types(
        self,
        resolution_frame: pd.DataFrame,
        default_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        return self.customer_incident_type_workflow_service.bulk_update_incident_types(
            self,
            resolution_frame,
            default_label,
        )

    def _get_invalid_incident_types_from_db(self) -> List[str]:
        return self.customer_incident_type_workflow_service.get_invalid_incident_types_from_db(self)

    def update_states(
        self,
        customer_logger: logging.Logger,
        load_id: Optional[int] = None,
    ) -> StateUpdateResult:
        """
        Resolve the StateIDs that 44.tbladdress_Assign_StateID.sql leaves NULL, mapping
        free-text tblAddress.State values with variables/state_codes.json. Runs after the
        SQL batch, since files 37-43 populate that column mid-batch.
        """
        return self.customer_state_workflow_service.update_states(
            self,
            customer_logger,
            load_id if load_id is not None else self.current_load_id,
        )

    def _check_states_step(
        self,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        state_update_result: Optional[StateUpdateResult] = None,
        load_id: Optional[int] = None,
    ) -> StateCheckResult:
        """Check state mappings and report address states that will not resolve."""
        return self.customer_state_workflow_service.check_states_step(
            self,
            customer_code,
            db,
            customer_logger,
            state_update_result,
            load_id if load_id is not None else self.current_load_id,
        )

    def _load_state_mapping_frame(
        self,
        state_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        return self.customer_state_workflow_service.load_state_mapping_frame(
            self,
            state_mapping,
        )

    def _build_state_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
        load_id: Optional[int] = None,
    ) -> Tuple[pd.DataFrame, List[str]]:
        return self.customer_state_workflow_service.build_state_resolution_frame(
            self,
            mapping_frame,
            load_id if load_id is not None else self.current_load_id,
        )

    def _bulk_update_address_states(
        self,
        resolution_frame: pd.DataFrame,
        load_id: Optional[int] = None,
    ) -> int:
        return self.customer_state_workflow_service.bulk_update_address_states(
            self,
            resolution_frame,
            load_id if load_id is not None else self.current_load_id,
        )

    def _get_invalid_states_from_db(self, load_id: Optional[int] = None) -> List[str]:
        return self.customer_state_workflow_service.get_invalid_states_from_db(
            self,
            load_id if load_id is not None else self.current_load_id,
        )

    def update_closure_reasons(
        self,
        customer_logger: logging.Logger,
    ) -> ClosureReasonUpdateResult:
        """
        Replace RC_ACCOUNT_EXTRACT.Reason_Closed codes with standardized
        tblClosureReason labels using variables/closure_reason_codes.json, sweeping
        unmapped values to the configured fallback label. NULL/blank are left as-is.
        """
        return self.customer_closure_reason_workflow_service.update_closure_reasons(
            self,
            customer_logger,
        )

    def _check_closure_reasons_step(
        self,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        reason_update_result: Optional[ClosureReasonUpdateResult] = None,
    ) -> ClosureReasonCheckResult:
        """Check closure reasons and report defaulted and unmapped values."""
        return self.customer_closure_reason_workflow_service.check_closure_reasons_step(
            self,
            customer_code,
            db,
            customer_logger,
            reason_update_result,
        )

    def _load_closure_reason_mapping_frame(
        self,
        reason_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        return self.customer_closure_reason_workflow_service.load_closure_reason_mapping_frame(
            self,
            reason_mapping,
        )

    def _resolve_closure_reason_fallback_label(self, fallback_label: Optional[str]) -> Optional[str]:
        return self.customer_closure_reason_workflow_service.resolve_fallback_label(
            self,
            fallback_label,
        )

    def _build_closure_reason_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        return self.customer_closure_reason_workflow_service.build_closure_reason_resolution_frame(
            self,
            mapping_frame,
        )

    def _bulk_update_closure_reasons(
        self,
        resolution_frame: pd.DataFrame,
        fallback_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        return self.customer_closure_reason_workflow_service.bulk_update_closure_reasons(
            self,
            resolution_frame,
            fallback_label,
        )

    def _get_invalid_closure_reasons_from_db(self) -> List[str]:
        return self.customer_closure_reason_workflow_service.get_invalid_closure_reasons_from_db(self)


        
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

        if self.archive_db_helper:
            self.archive_db_helper.close_connections()
            self.logger.info("Archive database connections closed")

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

        
        
        