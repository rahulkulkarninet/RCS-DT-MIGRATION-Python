import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from result_types import StatusCheckResult, StatusUpdateResult
from status_service import StatusService


class CustomerStatusWorkflowService:
    """Coordinates status normalization/update and status code checks."""

    def _ensure_status_service(self, processor: Any) -> StatusService:
        if not processor.status_service:
            processor.status_service = StatusService(processor.shared_db_helper)
        return processor.status_service

    def update_rc_account_extract_ma_status(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> StatusUpdateResult:
        # This module now lives in services/workflows; resolve variables from repo root.
        mapping_file_path = Path(__file__).resolve().parents[2] / 'variables' / 'account_status_codes.json'

        result: StatusUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'total_codes_loaded': 0,
            'duplicate_codes_skipped': 0,
            'resolved_statuses': 0,
            'rows_updated': 0,
            'invalid_statuses': [],
            'status_message': '',
            'error': None,
        }

        try:
            if not mapping_file_path.exists():
                result['error'] = f'Mapping file not found: {mapping_file_path}'
                customer_logger.error(result['error'])
                return result

            with open(mapping_file_path, 'r', encoding='utf-8') as file_handle:
                status_mapping = json.load(file_handle)

            if not isinstance(status_mapping, dict):
                result['error'] = 'account_status_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            mapping_frame, duplicate_codes = self.load_account_status_mapping_frame(processor, status_mapping)
            result['total_codes_loaded'] = len(mapping_frame)
            result['duplicate_codes_skipped'] = duplicate_codes

            if mapping_frame.empty:
                customer_logger.warning('No status codes found in mapping file; nothing to update')
                result['success'] = True
                result['status_message'] = 'No status codes found in mapping file.'
                return result

            resolution_frame, _ = self.build_ma_status_resolution_frame(processor, mapping_frame)
            rows_updated = self.bulk_update_rc_account_extract_ma_status(processor, resolution_frame)
            db_invalid_statuses = self.get_invalid_ma_statuses_from_db(processor)

            result['resolved_statuses'] = len(resolution_frame)
            result['rows_updated'] = rows_updated
            result['invalid_statuses'] = db_invalid_statuses
            result['status_message'] = (
                f"Invalid status codes found: {', '.join(db_invalid_statuses)}"
                if db_invalid_statuses
                else 'All status codes are valid.'
            )
            result['success'] = True

            customer_logger.info(
                'Updated RC_ACCOUNT_EXTRACT.MA_Status using account_status_codes.json: '
                f"{rows_updated} rows updated, {len(mapping_frame)} codes loaded, "
                f'{duplicate_codes} duplicate code entries skipped'
            )

            if db_invalid_statuses:
                customer_logger.warning(
                    'Unresolved MA_Status values after normalization: '
                    + ', '.join(db_invalid_statuses)
                )

            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to update RC_ACCOUNT_EXTRACT.MA_Status: {e}')
            return result

    def check_status_codes_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        status_update_result: Optional[StatusUpdateResult] = None,
    ) -> StatusCheckResult:
        customer_logger.info('Step 3: Checking status codes...')

        status_message = 'All status codes are valid.'
        invalid_statuses: List[str] = []

        if processor.sql_manager is not None:
            status_message, invalid_statuses = processor.sql_manager.check_status_codes()
        elif status_update_result is None:
            invalid_statuses = self.get_invalid_ma_statuses_from_db(processor)
            if invalid_statuses:
                status_message = f"Invalid status codes found: {', '.join(invalid_statuses)}"

        if status_update_result is not None:
            mapped_invalid = status_update_result.get('invalid_statuses', [])
            merged_invalid = sorted(set(invalid_statuses) | set(mapped_invalid))
            invalid_statuses = merged_invalid
            if invalid_statuses:
                status_message = f"Invalid status codes found: {', '.join(invalid_statuses)}"
            else:
                status_message = 'All status codes are valid.'

        customer_logger.info(f'Status check result: {status_message}')

        if invalid_statuses:
            customer_logger.warning(
                f'Found {len(invalid_statuses)} status code(s) not present in target lookup. '
                'Auto-insert of missing statuses has been removed and will be skipped.'
            )

        return {
            'status_message': status_message,
            'invalid_statuses': invalid_statuses,
        }

    def load_account_status_mapping_frame(
        self,
        processor: Any,
        status_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        status_service = self._ensure_status_service(processor)
        return status_service.load_account_status_mapping_frame(status_mapping)

    def build_ma_status_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        status_service = self._ensure_status_service(processor)
        return status_service.build_ma_status_resolution_frame(mapping_frame)

    def bulk_update_rc_account_extract_ma_status(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
    ) -> int:
        status_service = self._ensure_status_service(processor)
        return status_service.bulk_update_rc_account_extract_ma_status(resolution_frame)

    def get_invalid_ma_statuses_from_db(self, processor: Any) -> List[str]:
        status_service = self._ensure_status_service(processor)
        return status_service.get_invalid_ma_statuses_from_db()

    def status_match_key(self, processor: Any, value: str) -> str:
        status_service = self._ensure_status_service(processor)
        return status_service.status_match_key(value)

    def status_match_key_series(self, processor: Any, series: pd.Series) -> pd.Series:
        status_service = self._ensure_status_service(processor)
        return status_service.status_match_key_series(series)

    def normalize_status_lookup_key(self, processor: Any, value: str) -> str:
        status_service = self._ensure_status_service(processor)
        return status_service.normalize_status_lookup_key(value)

    def normalize_status_lookup_series(self, processor: Any, series: pd.Series) -> pd.Series:
        status_service = self._ensure_status_service(processor)
        return status_service.normalize_status_lookup_series(series)
