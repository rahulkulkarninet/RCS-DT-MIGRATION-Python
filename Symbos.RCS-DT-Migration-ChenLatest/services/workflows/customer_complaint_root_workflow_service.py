import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from complaint_root_service import ComplaintRootService
from result_types import ComplaintRootCheckResult, ComplaintRootUpdateResult


class CustomerComplaintRootWorkflowService:
    """Coordinates CMP_Issue_1/2/3 normalization/update and complaint root checks."""

    def _ensure_complaint_root_service(self, processor: Any) -> ComplaintRootService:
        if not getattr(processor, 'complaint_root_service', None):
            processor.complaint_root_service = ComplaintRootService(processor.shared_db_helper)
        return processor.complaint_root_service

    def update_complaint_roots(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> ComplaintRootUpdateResult:
        # This module lives in services/workflows; resolve variables from repo root.
        mapping_file_path = (
            Path(__file__).resolve().parents[2] / 'variables' / 'complaint_root_codes.json'
        )

        result: ComplaintRootUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'total_codes_loaded': 0,
            'duplicate_codes_skipped': 0,
            'resolved_roots': 0,
            'rows_updated': 0,
            'rows_updated_by_column': {},
            'invalid_roots': [],
            'status_message': '',
            'error': None,
        }

        try:
            if not mapping_file_path.exists():
                result['error'] = f'Mapping file not found: {mapping_file_path}'
                customer_logger.error(result['error'])
                return result

            with open(mapping_file_path, 'r', encoding='utf-8') as file_handle:
                root_mapping = json.load(file_handle)

            if not isinstance(root_mapping, dict):
                result['error'] = 'complaint_root_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            mapping_frame, duplicate_codes = self.load_complaint_root_mapping_frame(
                processor, root_mapping
            )
            result['total_codes_loaded'] = len(mapping_frame)
            result['duplicate_codes_skipped'] = duplicate_codes

            if mapping_frame.empty:
                customer_logger.warning(
                    'No complaint root codes found in mapping file; nothing to update'
                )

            resolution_frame, _ = self.build_complaint_root_resolution_frame(processor, mapping_frame)
            rows_updated_by_column = self.bulk_update_complaint_roots(processor, resolution_frame)
            invalid_roots = self.get_invalid_complaint_roots_from_db(processor)

            result['resolved_roots'] = len(resolution_frame)
            result['rows_updated_by_column'] = rows_updated_by_column
            result['rows_updated'] = sum(rows_updated_by_column.values())
            result['invalid_roots'] = invalid_roots
            result['status_message'] = (
                f"Invalid complaint issue values found: {', '.join(invalid_roots)}"
                if invalid_roots
                else 'All complaint issue values are valid.'
            )
            result['success'] = True

            per_column = ', '.join(
                f'{column}={count}' for column, count in sorted(rows_updated_by_column.items())
            ) or 'none'
            customer_logger.info(
                'Updated RC_COMPLAINT_EXTRACT CMP_Issue_1/2/3 using complaint_root_codes.json: '
                f"{result['rows_updated']} rows updated ({per_column}), "
                f'{len(mapping_frame)} codes loaded, '
                f'{duplicate_codes} duplicate code entries skipped'
            )

            if invalid_roots:
                customer_logger.warning(
                    'Unresolved CMP_Issue values after normalization: ' + ', '.join(invalid_roots)
                )

            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to update RC_COMPLAINT_EXTRACT CMP_Issue values: {e}')
            return result

    def check_complaint_roots_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        root_update_result: Optional[ComplaintRootUpdateResult] = None,
    ) -> ComplaintRootCheckResult:
        customer_logger.info('Checking complaint issue values...')

        if root_update_result is None:
            invalid_roots = self.get_invalid_complaint_roots_from_db(processor)
        else:
            invalid_roots = sorted(set(root_update_result.get('invalid_roots', [])))

        status_message = (
            f"Invalid complaint issue values found: {', '.join(invalid_roots)}"
            if invalid_roots
            else 'All complaint issue values are valid.'
        )

        customer_logger.info(f'Complaint root check result: {status_message}')

        if invalid_roots:
            customer_logger.warning(
                f'Found {len(invalid_roots)} CMP_Issue value(s) not present in '
                'tblComplaintRoot. Add a real tblComplaintRoot row plus a '
                'complaint_root_codes.json entry before migrating.'
            )

        return {
            'status_message': status_message,
            'invalid_roots': invalid_roots,
        }

    def load_complaint_root_mapping_frame(
        self,
        processor: Any,
        root_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        service = self._ensure_complaint_root_service(processor)
        return service.load_complaint_root_mapping_frame(root_mapping)

    def build_complaint_root_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        service = self._ensure_complaint_root_service(processor)
        return service.build_complaint_root_resolution_frame(mapping_frame)

    def bulk_update_complaint_roots(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
    ) -> Dict[str, int]:
        service = self._ensure_complaint_root_service(processor)
        return service.bulk_update_complaint_roots(resolution_frame)

    def get_invalid_complaint_roots_from_db(self, processor: Any) -> List[str]:
        service = self._ensure_complaint_root_service(processor)
        return service.get_invalid_complaint_roots_from_db()
