import json
import logging
from pathlib import Path
from typing import Any

from arrangement_status_service import (
    SOURCE_TABLE,
    TARGET_COLUMN,
    ArrangementStatusService,
)
from result_types import ArrangementStatusUpdateResult


class CustomerArrangementStatusWorkflowService:
    """Applies the no-active-arrangement rule after the status and treatment step mappings."""

    def _ensure_service(self, processor: Any) -> ArrangementStatusService:
        if not getattr(processor, 'arrangement_status_service', None):
            processor.arrangement_status_service = ArrangementStatusService(processor.shared_db_helper)
        return processor.arrangement_status_service

    def update_rc_account_extract_arrangement_status(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> ArrangementStatusUpdateResult:
        rules_file_path = Path(__file__).resolve().parents[2] / 'variables' / 'arrangement_status_rules.json'

        result: ArrangementStatusUpdateResult = {
            'success': False,
            'rules_file': str(rules_file_path),
            'in_scope_rows': 0,
            'active_instalment_rows': 0,
            'active_deal_rows': 0,
            'no_arrangement_rows': 0,
            'treated_to_status_rows': 0,
            'young_to_step_rows': 0,
            'old_no_treatment_rows': 0,
            'status_message': '',
            'error': None,
        }

        try:
            if not rules_file_path.exists():
                result['error'] = f'Rules file not found: {rules_file_path}'
                customer_logger.error(result['error'])
                return result

            with open(rules_file_path, 'r', encoding='utf-8') as file_handle:
                config = json.load(file_handle)

            service = self._ensure_service(processor)
            problem = service.validate_config(config)
            if problem:
                result['error'] = problem
                customer_logger.error(result['error'])
                return result

            added = service.ensure_target_column()
            if added:
                customer_logger.warning(
                    f'{SOURCE_TABLE}: added derived column {", ".join(added)} '
                    '(the schema file and Migrations/009 carry it; this environment predated it)')

            status_ids, missing = service.resolve_status_ids(config)
            if missing:
                result['error'] = (
                    'arrangement_status_rules.json names status label(s) not in tblAccountStatus: '
                    + ', '.join(missing))
                customer_logger.error(result['error'])
                return result

            counts = service.apply(config, status_ids)
            result['in_scope_rows'] = counts['in_scope']
            result['active_instalment_rows'] = counts['active_instalment']
            result['active_deal_rows'] = counts['active_deal']
            result['no_arrangement_rows'] = counts['none']
            result['treated_to_status_rows'] = counts['treated_to_status']
            result['young_to_step_rows'] = counts['young_to_step']
            result['old_no_treatment_rows'] = counts['old_no_treatment']
            result['status_message'] = (
                f"{counts['in_scope']} open accounts in an arrangement-type RCS status: "
                f"{counts['active_instalment']} with an instalment plan, {counts['active_deal']} with a deal due, "
                f"{counts['none']} with neither -> {counts['treated_to_status']} re-statused on their treatment, "
                f"{counts['young_to_step']} to Treatment Allocated at the untreated step, "
                f"{counts['old_no_treatment']} to End of Process with no treatment"
            )
            result['success'] = True

            customer_logger.info(f'Assigned {SOURCE_TABLE}.{TARGET_COLUMN} using arrangement_status_rules.json: '
                                 + result['status_message'])
            for active, rcs_status, n in service.summary():
                customer_logger.info(f'  {active} {rcs_status}: {n} accounts')
            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to assign {SOURCE_TABLE}.{TARGET_COLUMN}: {e}')
            return result
