import time
from collections import OrderedDict
from typing import Any, Dict

from result_types import MixedExecutionResult


class MigrationExecutionService:
    """Encapsulates mixed SQL execution orchestration across PyODBC and SQLCMD."""

    def execute_mixed_sql_methods_internal(
        self,
        sql_manager: Any,
        export_folder_path: str,
        customer_logger: Any,
    ) -> MixedExecutionResult:
        """
        Internal method to execute SQL files using mixed methods.
        Files 1-75: PyODBC with transaction control.
        File 76: SQLCMD for compatibility.
        """

        try:
            # Get all SQL files and organize them.
            sql_files = sql_manager._scan_exported_sql_files(export_folder_path)

            # Separate files by execution method.
            pyodbc_files = OrderedDict()
            sqlcmd_files = OrderedDict()

            for key, file_info in sql_files.items():
                sequence = file_info.get('sequence', 0)

                if sequence == 76:
                    sqlcmd_files[key] = file_info
                elif sequence >= 1:
                    pyodbc_files[key] = file_info
                else:
                    customer_logger.warning(
                        f"File sequence {sequence} is not a valid positive sequence: {file_info.get('filename', 'unknown')}"
                    )

            customer_logger.info(
                f"Split files: {len(pyodbc_files)} for PyODBC, {len(sqlcmd_files)} for SQLCMD (76)"
            )

            combined_results = {
                'execution_results': OrderedDict(),
                'pyodbc_executed': 0,
                'sqlcmd_executed': 0,
                'total_execution_time': 0,
                'method_breakdown': {
                    'pyodbc': {'files': len(pyodbc_files), 'success': 0, 'failed': 0},
                    'sqlcmd': {'files': len(sqlcmd_files), 'success': 0, 'failed': 0},
                },
            }

            total_start_time = time.time()

            # Phase 1: Execute files 1-75 using PyODBC with transaction control.
            if pyodbc_files:
                customer_logger.info(
                    f"Phase 1: Executing {len(pyodbc_files)} files (sequences 1-75) using PyODBC..."
                )

                pyodbc_results = sql_manager._execute_with_pyodbc(
                    pyodbc_files, dry_run=False, continue_on_error=False
                )

                # Add PyODBC results to combined results.
                for key, result in pyodbc_results.items():
                    combined_results['execution_results'][key] = result

                    if result.get('executed', False) and not result.get('error'):
                        combined_results['method_breakdown']['pyodbc']['success'] += 1
                        combined_results['pyodbc_executed'] += 1
                    else:
                        combined_results['method_breakdown']['pyodbc']['failed'] += 1

                # Check if PyODBC phase succeeded.
                pyodbc_success = all(
                    r.get('executed', False) and not r.get('error') for r in pyodbc_results.values()
                )

                if not pyodbc_success:
                    customer_logger.error("PyODBC phase (files 1-75) failed - stopping execution")
                    failed_pyodbc = [
                        f"Seq {r.get('sequence', '?')}: {r.get('table_name', 'unknown')}"
                        for r in pyodbc_results.values()
                        if r.get('error') or not r.get('executed', False)
                    ]
                    customer_logger.error(f"Failed PyODBC files: {failed_pyodbc}")

                    # Mark SQLCMD files as skipped.
                    for key, file_info in sqlcmd_files.items():
                        combined_results['execution_results'][key] = {
                            'execution_order': None,
                            'sequence': file_info['sequence'],
                            'table_name': file_info['table_name'],
                            'subfolder': file_info['subfolder'],
                            'file_path': file_info['file_path'],
                            'method': 'sqlcmd_skipped',
                            'executed': False,
                            'rows_affected': 0,
                            'execution_time': 0,
                            'error': 'Skipped due to PyODBC phase failure',
                            'skipped': True,
                        }
                        combined_results['method_breakdown']['sqlcmd']['failed'] += 1

                    total_end_time = time.time()
                    combined_results['total_execution_time'] = total_end_time - total_start_time
                    return combined_results

                customer_logger.info(
                    f"Phase 1 SUCCESS: All {len(pyodbc_files)} PyODBC files executed successfully"
                )

            # Phase 2: Execute file 76 using SQLCMD.
            if sqlcmd_files:
                customer_logger.info(
                    f"Phase 2: Executing {len(sqlcmd_files)} files (sequence 76) using SQLCMD..."
                )

                # Brief delay to ensure PyODBC transaction is fully committed.
                time.sleep(2)

                # go-sqlcmd handles this on Azure: it is the only sqlcmd with
                # --authentication-method ActiveDirectoryServicePrincipal, and
                # db_helper.sqlcmd_executable() resolves it explicitly because
                # installing it does not displace the classic build on PATH.
                sqlcmd_results = sql_manager._execute_with_sqlcmd(
                    sqlcmd_files, dry_run=False, continue_on_error=False,
                    use_master_file=False
                )

                # Add SQLCMD results to combined results.
                for key, result in sqlcmd_results.items():
                    combined_results['execution_results'][key] = result

                    if result.get('executed', False) and not result.get('error'):
                        combined_results['method_breakdown']['sqlcmd']['success'] += 1
                        combined_results['sqlcmd_executed'] += 1
                    else:
                        combined_results['method_breakdown']['sqlcmd']['failed'] += 1

                sqlcmd_success = all(
                    r.get('executed', False) and not r.get('error') for r in sqlcmd_results.values()
                )

                if sqlcmd_success:
                    customer_logger.info(
                        f"Phase 2 SUCCESS: All {len(sqlcmd_files)} SQLCMD files executed successfully"
                    )
                else:
                    customer_logger.error("Phase 2 FAILED: SQLCMD execution failed")
                    failed_sqlcmd = [
                        f"Seq {r.get('sequence', '?')}: {r.get('table_name', 'unknown')}"
                        for r in sqlcmd_results.values()
                        if r.get('error') or not r.get('executed', False)
                    ]
                    customer_logger.error(f"Failed SQLCMD files: {failed_sqlcmd}")

            total_end_time = time.time()
            combined_results['total_execution_time'] = total_end_time - total_start_time

            # Log method breakdown.
            customer_logger.info("Execution method breakdown:")
            customer_logger.info(
                f"  PyODBC (1-75): {combined_results['method_breakdown']['pyodbc']['success']} success, "
                f"{combined_results['method_breakdown']['pyodbc']['failed']} failed"
            )
            customer_logger.info(
                f"  SQLCMD (76): {combined_results['method_breakdown']['sqlcmd']['success']} success, "
                f"{combined_results['method_breakdown']['sqlcmd']['failed']} failed"
            )

            return combined_results

        except Exception as e:
            customer_logger.error(f"Error in mixed SQL execution: {e}")
            return {
                'execution_results': OrderedDict(),
                'pyodbc_executed': 0,
                'sqlcmd_executed': 0,
                'total_execution_time': 0,
                'error': str(e),
                'method_breakdown': {
                    'pyodbc': {'files': 0, 'success': 0, 'failed': 0},
                    'sqlcmd': {'files': 0, 'success': 0, 'failed': 0},
                },
            }
