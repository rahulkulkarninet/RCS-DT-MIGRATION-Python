import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from cost_service import CostService, STAGING_SCHEMA_FILE, STAGING_TABLE
from result_types import CostCheckResult, CostUpdateResult


class CustomerCostWorkflowService:
    """Coordinates cost code resolution, the RC_STAGING_COSTS rebuild, and its checks."""

    def _ensure_cost_service(self, processor: Any) -> CostService:
        if not getattr(processor, 'cost_service', None):
            processor.cost_service = CostService(processor.shared_db_helper)
        return processor.cost_service

    @staticmethod
    def _mapping_file_path() -> Path:
        # This module lives in services/workflows; resolve variables from repo root.
        return Path(__file__).resolve().parents[2] / 'variables' / 'cost_codes.json'

    @classmethod
    def _read_excluded_codes(cls) -> Dict[str, Any]:
        """The 'not_costs' block on its own, for the check step run without an update.

        Without it that path would report every excluded code as unmapped - DEB carries
        a value on nearly every row, so the report would be useless.
        """
        mapping_file_path = cls._mapping_file_path()
        if not mapping_file_path.exists():
            return {}

        with open(mapping_file_path, 'r', encoding='utf-8') as file_handle:
            file_contents = json.load(file_handle)

        if not isinstance(file_contents, dict):
            return {}

        excluded_codes = file_contents.get('not_costs') or {}
        return excluded_codes if isinstance(excluded_codes, dict) else {}

    def update_costs(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> CostUpdateResult:
        mapping_file_path = self._mapping_file_path()

        result: CostUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'default_master_cost': '',
            'total_codes_loaded': 0,
            'duplicate_codes_skipped': 0,
            'rejected_codes': [],
            'excluded_codes': [],
            'resolved_codes': 0,
            'rows_inserted': 0,
            'unresolved_cost_types': [],
            'unresolved_master_costs': [],
            'missing_columns': [],
            'unmapped_charged_codes': [],
            'status_message': '',
            'error': None,
        }

        try:
            if not mapping_file_path.exists():
                result['error'] = f'Mapping file not found: {mapping_file_path}'
                customer_logger.error(result['error'])
                return result

            with open(mapping_file_path, 'r', encoding='utf-8') as file_handle:
                file_contents = json.load(file_handle)

            if not isinstance(file_contents, dict):
                result['error'] = 'cost_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            cost_type_mapping = file_contents.get('cost_types')
            if not isinstance(cost_type_mapping, dict):
                result['error'] = (
                    "cost_codes.json must contain a 'cost_types' object of "
                    '{tblCostType label: [codes]}'
                )
                customer_logger.error(result['error'])
                return result

            master_cost_mapping = file_contents.get('master_costs') or {}
            if not isinstance(master_cost_mapping, dict):
                result['error'] = (
                    "cost_codes.json 'master_costs' must be an object of "
                    '{tblMasterCost label: [codes]}'
                )
                customer_logger.error(result['error'])
                return result

            excluded_codes = file_contents.get('not_costs') or {}
            if not isinstance(excluded_codes, dict):
                result['error'] = (
                    "cost_codes.json 'not_costs' must be an object of "
                    '{code: reason}'
                )
                customer_logger.error(result['error'])
                return result

            default_master_cost = str(
                file_contents.get('default_master_cost') or ''
            ).strip()
            result['default_master_cost'] = default_master_cost
            result['excluded_codes'] = sorted(excluded_codes)

            # Unlike the value-rewriting domains this writes to a table of its own, so
            # a missing table is a deployment step nobody has run rather than bad data.
            if not self.staging_table_exists(processor):
                result['error'] = (
                    f'{STAGING_TABLE} does not exist. Deploy '
                    f'{STAGING_SCHEMA_FILE} before migrating costs.'
                )
                customer_logger.error(result['error'])
                return result

            mapping_frame, duplicate_codes, rejected_codes = (
                self.load_cost_mapping_frame(
                    processor,
                    cost_type_mapping,
                    master_cost_mapping,
                    default_master_cost,
                )
            )
            result['total_codes_loaded'] = len(mapping_frame)
            result['duplicate_codes_skipped'] = duplicate_codes
            result['rejected_codes'] = rejected_codes

            if rejected_codes:
                result['error'] = (
                    'Cost codes in cost_codes.json are not valid code names '
                    f"(letters, digits and underscore only): {', '.join(rejected_codes)}"
                )
                customer_logger.error(result['error'])
                return result

            resolution_frame, problems = self.build_cost_resolution_frame(
                processor, mapping_frame, excluded_codes
            )
            result['resolved_codes'] = len(resolution_frame)
            result['unresolved_cost_types'] = problems['unresolved_cost_types']
            result['unresolved_master_costs'] = problems['unresolved_master_costs']
            result['missing_columns'] = problems['missing_columns']

            if problems['unresolved_cost_types']:
                result['error'] = (
                    'Cost type labels in cost_codes.json are not present in '
                    'tblCostType: '
                    + ', '.join(problems['unresolved_cost_types'])
                )
                customer_logger.error(result['error'])
                return result

            if problems['unresolved_master_costs']:
                result['error'] = (
                    'Master cost labels in cost_codes.json are not present in '
                    'tblMasterCost: '
                    + ', '.join(problems['unresolved_master_costs'])
                )
                customer_logger.error(result['error'])
                return result

            # Not fatal: a configured code with no Chg_ column cannot be carrying a
            # charge, so nothing is lost. If the column was renamed rather than
            # removed, the money moved to a column nothing maps and the unmapped
            # check below stops the customer anyway.
            if problems['missing_columns']:
                customer_logger.warning(
                    'Cost codes in cost_codes.json with no matching column on '
                    'RC_COSTS_EXTRACT (nothing to migrate for them): '
                    + ', '.join(problems['missing_columns'])
                )

            rows_inserted = self.rebuild_staging_costs(
                processor,
                resolution_frame,
                int(processor.current_load_id),
                int(processor.current_session_id),
            )
            result['rows_inserted'] = rows_inserted

            unmapped_charged_codes = self.get_unmapped_charged_codes_from_db(
                processor, int(processor.current_load_id), excluded_codes
            )
            result['unmapped_charged_codes'] = unmapped_charged_codes

            customer_logger.info(
                f'Rebuilt {STAGING_TABLE} from cost_codes.json: '
                f'{rows_inserted} charge row(s) staged, '
                f'{len(resolution_frame)} code(s) resolved of '
                f'{len(mapping_frame)} configured, '
                f'{duplicate_codes} duplicate code entries skipped, '
                f'{len(excluded_codes)} code(s) excluded as not costs'
            )

            # The whole reason this domain exists. A charged code nothing maps used to
            # be dropped by an INNER JOIN with no error at all - on dev load 238 that
            # was $403,234.13 of COL charges and an empty tblCost - so it stops the
            # customer instead of migrating a knowingly incomplete set of costs.
            if unmapped_charged_codes:
                result['error'] = (
                    'RC_COSTS_EXTRACT carries charges under cost codes that '
                    'cost_codes.json neither maps nor excludes, so they would not '
                    'migrate: '
                    + '; '.join(unmapped_charged_codes)
                    + ". Add each to 'cost_types' with its tblCostType label, or to "
                    "'not_costs' with the reason it is not a cost."
                )
                customer_logger.error(result['error'])
                return result

            result['status_message'] = 'All charged cost codes are mapped.'
            result['success'] = True
            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to rebuild {STAGING_TABLE}: {e}')
            return result

    def check_costs_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        cost_update_result: Optional[CostUpdateResult] = None,
    ) -> CostCheckResult:
        customer_logger.info('Checking cost codes...')

        if cost_update_result is None:
            unmapped_charged_codes = self.get_unmapped_charged_codes_from_db(
                processor,
                int(processor.current_load_id),
                self._read_excluded_codes(),
            )
        else:
            unmapped_charged_codes = sorted(
                set(cost_update_result.get('unmapped_charged_codes', []))
            )

        status_message = 'All charged cost codes are mapped.'
        if unmapped_charged_codes:
            status_message = (
                'Charged cost codes with no mapping: '
                + '; '.join(unmapped_charged_codes)
            )

        customer_logger.info(f'Cost code check result: {status_message}')

        if unmapped_charged_codes:
            customer_logger.warning(
                f'Found {len(unmapped_charged_codes)} charged cost code(s) that '
                'would not migrate. Add them to variables/cost_codes.json under '
                "'cost_types', or to 'not_costs' if they are not costs, before "
                'migrating.'
            )

        return {
            'status_message': status_message,
            'unmapped_charged_codes': unmapped_charged_codes,
        }

    def load_cost_mapping_frame(
        self,
        processor: Any,
        cost_type_mapping: Dict[str, Any],
        master_cost_mapping: Optional[Dict[str, Any]] = None,
        default_master_cost: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, int, List[str]]:
        service = self._ensure_cost_service(processor)
        return service.load_cost_mapping_frame(
            cost_type_mapping, master_cost_mapping, default_master_cost
        )

    def build_cost_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
        excluded_codes: Optional[Dict[str, Any]] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
        service = self._ensure_cost_service(processor)
        return service.build_cost_resolution_frame(mapping_frame, excluded_codes)

    def rebuild_staging_costs(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
        load_id: int,
        session_id: int,
    ) -> int:
        service = self._ensure_cost_service(processor)
        return service.rebuild_staging_costs(resolution_frame, load_id, session_id)

    def staging_table_exists(self, processor: Any) -> bool:
        service = self._ensure_cost_service(processor)
        return service.staging_table_exists()

    def get_unmapped_charged_codes_from_db(
        self,
        processor: Any,
        load_id: int,
        excluded_codes: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        service = self._ensure_cost_service(processor)
        return service.get_unmapped_charged_codes_from_db(load_id, excluded_codes)
