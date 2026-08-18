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
