import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from frequency_service import FrequencyService
from result_types import FrequencyCheckResult, FrequencyUpdateResult


class CustomerFrequencyWorkflowService:
    """Coordinates RC_ARRANGEMENT.Frequency normalization/update and frequency checks."""

    def _ensure_frequency_service(self, processor: Any) -> FrequencyService:
        if not getattr(processor, 'frequency_service', None):
            processor.frequency_service = FrequencyService(processor.shared_db_helper)
        return processor.frequency_service

    def update_frequencies(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> FrequencyUpdateResult:
        # This module lives in services/workflows; resolve variables from repo root.
        mapping_file_path = (
            Path(__file__).resolve().parents[2] / 'variables' / 'frequency_codes.json'
        )

        result: FrequencyUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'total_codes_loaded': 0,
            'duplicate_codes_skipped': 0,
            'resolved_frequencies': 0,
            'rows_updated': 0,
            'invalid_frequencies': [],
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
                result['error'] = 'frequency_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            # Flat {label: [codes]} shape, matching bank_transaction_method_codes.json.
            # There is deliberately no default: RC_ARRANGEMENT.Frequency is NOT NULL, and
            # defaulting an unknown code would fabricate a payment schedule.
            mapping_frame, duplicate_codes = self.load_frequency_mapping_frame(
                processor, file_contents
            )
            result['total_codes_loaded'] = len(mapping_frame)
            result['duplicate_codes_skipped'] = duplicate_codes

            if mapping_frame.empty:
                result['error'] = (
                    'frequency_codes.json produced no usable code mappings; expected '
                    '{"Label": ["CODE", ...]}'
                )
                customer_logger.error(result['error'])
                return result

            resolution_frame, _ = self.build_frequency_resolution_frame(
                processor, mapping_frame
            )
            rows_updated = self.bulk_update_frequencies(processor, resolution_frame)
            invalid_frequencies = self.get_invalid_frequencies_from_db(processor)

            result['resolved_frequencies'] = len(resolution_frame)
            result['rows_updated'] = rows_updated
            result['invalid_frequencies'] = invalid_frequencies
            result['status_message'] = (
                f"Invalid frequencies found: {', '.join(invalid_frequencies)}"
                if invalid_frequencies
                else 'All frequencies are valid.'
            )
            result['success'] = True

            customer_logger.info(
                'Updated RC_ARRANGEMENT.Frequency using frequency_codes.json: '
                f'{rows_updated} rows updated, '
                f'{len(mapping_frame)} codes loaded, '
                f'{duplicate_codes} duplicate code entries skipped'
            )

            if invalid_frequencies:
                customer_logger.warning(
                    'Unresolved RC_ARRANGEMENT.Frequency values after normalization: '
                    + ', '.join(invalid_frequencies)
                )

            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to update RC_ARRANGEMENT.Frequency: {e}')
            return result

    def check_frequencies_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        frequency_update_result: Optional[FrequencyUpdateResult] = None,
    ) -> FrequencyCheckResult:
        customer_logger.info('Checking frequencies...')

        status_message = 'All frequencies are valid.'
        invalid_frequencies: List[str] = []

        if frequency_update_result is None:
            invalid_frequencies = self.get_invalid_frequencies_from_db(processor)
        else:
            invalid_frequencies = sorted(
                set(frequency_update_result.get('invalid_frequencies', []))
            )

        if invalid_frequencies:
            status_message = f"Invalid frequencies found: {', '.join(invalid_frequencies)}"

        customer_logger.info(f'Frequency check result: {status_message}')

        if invalid_frequencies:
            customer_logger.warning(
                f'Found {len(invalid_frequencies)} frequency value(s) not present in '
                'tblFrequency. Add them to variables/frequency_codes.json before '
                'migrating, or they will land as a NULL FrequencyID on tblArrangement.'
            )

        return {
            'status_message': status_message,
            'invalid_frequencies': invalid_frequencies,
        }

    def load_frequency_mapping_frame(
        self,
        processor: Any,
        frequency_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        service = self._ensure_frequency_service(processor)
        return service.load_frequency_mapping_frame(frequency_mapping)

    def build_frequency_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        service = self._ensure_frequency_service(processor)
        return service.build_frequency_resolution_frame(mapping_frame)

    def bulk_update_frequencies(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
    ) -> int:
        service = self._ensure_frequency_service(processor)
        return service.bulk_update_frequencies(resolution_frame)

    def get_invalid_frequencies_from_db(self, processor: Any) -> List[str]:
        service = self._ensure_frequency_service(processor)
        return service.get_invalid_frequencies_from_db()
