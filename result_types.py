from typing import Any, Dict, List, TypedDict


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


class ComplainantUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    fallback_label: str
    fallback_applied: bool
    total_codes_loaded: int
    duplicate_codes_skipped: int
    resolved_complainants: int
    rows_updated: int
    rows_defaulted: int
    defaulted_values: List[str]
    invalid_complainants: List[str]
    status_message: str
    error: str


class ComplainantCheckResult(TypedDict):
    status_message: str
    defaulted_values: List[str]
    invalid_complainants: List[str]


class ComplaintRootUpdateResult(TypedDict, total=False):
    success: bool
    mapping_file: str
    total_codes_loaded: int
    duplicate_codes_skipped: int
    resolved_roots: int
    rows_updated: int
    rows_updated_by_column: Dict[str, int]
    invalid_roots: List[str]
    status_message: str
    error: str


class ComplaintRootCheckResult(TypedDict):
    status_message: str
    invalid_roots: List[str]


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
