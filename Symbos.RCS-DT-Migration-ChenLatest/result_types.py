from typing import Any, Dict, List, Optional, TypedDict


class StatusUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    total_codes_loaded: int
    duplicate_codes_skipped: int
    resolved_statuses: int
    rows_updated: int
    invalid_statuses: List[str]
    status_message: str
    error: str


class StatusCheckResult(TypedDict):
    status_message: str
    invalid_statuses: List[str]


class BankTransactionMethodUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    total_codes_loaded: int
    duplicate_codes_skipped: int
    resolved_methods: int
    rows_updated: int
    rows_updated_by_table: Dict[str, int]
    invalid_methods: List[str]
    invalid_methods_by_table: Dict[str, List[str]]
    status_message: str
    error: str


class BankTransactionMethodCheckResult(TypedDict):
    status_message: str
    invalid_methods: List[str]


class ArrangementTypeUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    default_label: str
    default_applied: bool
    total_codes_loaded: int
    duplicate_codes_skipped: int
    resolved_types: int
    rows_updated: int
    rows_defaulted: int
    invalid_types: List[str]
    status_message: str
    error: str


class ArrangementTypeCheckResult(TypedDict):
    status_message: str
    invalid_types: List[str]


class FrequencyUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    total_codes_loaded: int
    duplicate_codes_skipped: int
    resolved_frequencies: int
    rows_updated: int
    invalid_frequencies: List[str]
    status_message: str
    error: str


class FrequencyCheckResult(TypedDict):
    status_message: str
    invalid_frequencies: List[str]


class RelatedPartyTypeUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    fallback_label: str
    fallback_applied: bool
    total_codes_loaded: int
    duplicate_codes_skipped: int
    resolved_types: int
    rows_updated: int
    rows_defaulted: int
    invalid_types: List[str]
    status_message: str
    error: str


class RelatedPartyTypeCheckResult(TypedDict):
    status_message: str
    invalid_types: List[str]


class IncidentTypeUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    default_label: str
    default_applied: bool
    rules_loaded: int
    rules_skipped: int
    resolved_descriptions: int
    rows_updated: int
    rows_defaulted: int
    unresolved_labels: List[str]
    invalid_types: List[str]
    status_message: str
    error: str


class IncidentTypeCheckResult(TypedDict):
    status_message: str
    unresolved_labels: List[str]
    invalid_types: List[str]


class StateUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    total_synonyms_loaded: int
    duplicate_synonyms_skipped: int
    resolved_states: int
    rows_updated: int
    unresolved_labels: List[str]
    invalid_states: List[str]
    status_message: str
    error: str


class StateCheckResult(TypedDict):
    status_message: str
    unresolved_labels: List[str]
    invalid_states: List[str]


class ClosureReasonUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    fallback_label: str
    fallback_applied: bool
    total_codes_loaded: int
    duplicate_codes_skipped: int
    resolved_reasons: int
    rows_updated: int
    rows_defaulted: int
    defaulted_values: List[str]
    invalid_reasons: List[str]
    status_message: str
    error: str


class ClosureReasonCheckResult(TypedDict):
    status_message: str
    defaulted_values: List[str]
    invalid_reasons: List[str]


class HardshipStatusUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    fallback_label: str
    fallback_applied: bool
    total_codes_loaded: int
    duplicate_codes_skipped: int
    resolved_statuses: int
    rows_updated: int
    rows_defaulted: int
    defaulted_values: List[str]
    invalid_statuses: List[str]
    status_message: str
    error: str


class HardshipStatusCheckResult(TypedDict):
    status_message: str
    defaulted_values: List[str]
    invalid_statuses: List[str]


class HardshipCauseUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    fallback_label: str
    fallback_applied: bool
    total_codes_loaded: int
    duplicate_codes_skipped: int
    resolved_causes: int
    rows_updated: int
    rows_defaulted: int
    defaulted_values: List[str]
    invalid_causes: List[str]
    status_message: str
    error: str


class HardshipCauseCheckResult(TypedDict):
    status_message: str
    defaulted_values: List[str]
    invalid_causes: List[str]


class CostUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    default_master_cost: str
    total_codes_loaded: int
    duplicate_codes_skipped: int
    rejected_codes: List[str]
    excluded_codes: List[str]
    resolved_codes: int
    rows_inserted: int
    unresolved_cost_types: List[str]
    unresolved_master_costs: List[str]
    missing_columns: List[str]
    unmapped_charged_codes: List[str]
    status_message: str
    error: Optional[str]


class CostCheckResult(TypedDict):
    status_message: str
    unmapped_charged_codes: List[str]


class OperatorContactUpdateResult(TypedDict, total=False):
    success: bool
    resolved_codes: int
    rows_updated: int
    rows_updated_by_table: Dict[str, int]
    fallback_contact: str
    unresolved_contacts: List[str]
    ambiguous_contacts: List[str]
    unresolved_operator_codes: List[str]
    status_message: str
    error: Optional[str]


class OperatorContactCheckResult(TypedDict):
    status_message: str
    unresolved_contacts: List[str]
    ambiguous_contacts: List[str]
    unresolved_operator_codes: List[str]


class MethodBreakdown(TypedDict):
    files: int
    success: int
    failed: int


class MixedExecutionMethodBreakdown(TypedDict):
    pyodbc: MethodBreakdown
    sqlcmd: MethodBreakdown


class MixedExecutionResult(TypedDict, total=False):
    execution_results: Dict[str, Dict[str, Any]]
    pyodbc_executed: int
    sqlcmd_executed: int
    total_execution_time: float
    method_breakdown: MixedExecutionMethodBreakdown
    error: str

class TreatmentStepUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    total_codes_loaded: int
    duplicate_codes_skipped: int
    treated_rows: int
    untreated_rows: int
    closed_rows: int
    unmapped_codes: List[str]
    status_message: str
    error: str


class ArrangementStatusUpdateResult(TypedDict, total=False):
    success: bool
    rules_file: str
    in_scope_rows: int
    active_instalment_rows: int
    active_deal_rows: int
    no_arrangement_rows: int
    treated_to_status_rows: int
    young_to_step_rows: int
    old_no_treatment_rows: int
    status_message: str
    error: str
