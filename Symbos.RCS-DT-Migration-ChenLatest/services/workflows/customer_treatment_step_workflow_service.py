import json
import logging
from pathlib import Path
from typing import Any

from result_types import TreatmentStepUpdateResult
from treatment_step_service import (
    MAP_TABLE,
    SOURCE_TABLE,
    TARGET_COLUMN,
    TreatmentStepService,
)


class CustomerTreatmentStepWorkflowService:
    """Derives RC_ACCOUNT_EXTRACT.Treatment_NewStep before the SQL batch (78 reads it)."""

    def _ensure_treatment_step_service(self, processor: Any) -> TreatmentStepService:
        if not getattr(processor, 'treatment_step_service', None):
            processor.treatment_step_service = TreatmentStepService(processor.shared_db_helper)
        return processor.treatment_step_service

    def update_rc_account_extract_treatment_step(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> TreatmentStepUpdateResult:
        mapping_file_path = Path(__file__).resolve().parents[2] / 'variables' / 'treatment_step_codes.json'

        result: TreatmentStepUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'total_codes_loaded': 0,
            'duplicate_codes_skipped': 0,
            'treated_rows': 0,
            'untreated_rows': 0,
            'closed_rows': 0,
            'unmapped_codes': [],
            'status_message': '',
            'error': None,
        }

        try:
            if not mapping_file_path.exists():
                result['error'] = f'Mapping file not found: {mapping_file_path}'
                customer_logger.error(result['error'])
                return result

            with open(mapping_file_path, 'r', encoding='utf-8') as file_handle:
                config = json.load(file_handle)

            service = self._ensure_treatment_step_service(processor)
            problem = service.validate_config(config)
            if problem:
                result['error'] = problem
                customer_logger.error(result['error'])
                return result

            added = service.ensure_target_columns()
            if added:
                customer_logger.warning(
                    f'{SOURCE_TABLE}: added derived column(s) {", ".join(added)} '
                    '(the schema file and Migrations/008 carry them; this environment predated them)')

            map_frame, duplicates = service.load_code_map_frame(config)
            result['total_codes_loaded'] = len(map_frame)
            result['duplicate_codes_skipped'] = duplicates
            map_rows = service.write_code_map(map_frame)
            customer_logger.info(f'{MAP_TABLE}: {map_rows} RCS treatment codes written')

            counts = service.assign_steps(config)
            result['treated_rows'] = counts['treated']
            result['untreated_rows'] = counts['untreated']
            result['closed_rows'] = counts['closed']

            unmapped = service.unmapped_treatment_codes(config)
            result['unmapped_codes'] = [code for code, _ in unmapped]
            result['status_message'] = (
                'Unknown RCS treatment codes (fell to the untreated rule): '
                + ', '.join(f'{code} ({n})' for code, n in unmapped)
                if unmapped
                else 'All RCS treatment codes are known.'
            )
            result['success'] = True

            customer_logger.info(
                f'Assigned {SOURCE_TABLE}.{TARGET_COLUMN} using treatment_step_codes.json: '
                f"{counts['treated']} on a mapped treatment, {counts['untreated']} untreated open, "
                f"{counts['closed']} closed (no treatment); {len(map_frame)} codes loaded, "
                f'{duplicates} duplicate code entries skipped'
            )
            for code, step, n in service.step_summary():
                customer_logger.info(f'  {code} step {step}: {n} accounts')
            if unmapped:
                customer_logger.warning(result['status_message'])
            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to assign {SOURCE_TABLE}.{TARGET_COLUMN}: {e}')
            return result
