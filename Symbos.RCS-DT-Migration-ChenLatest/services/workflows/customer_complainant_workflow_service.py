import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from complainant_service import ComplainantService
from result_types import ComplainantCheckResult, ComplainantUpdateResult


class CustomerComplainantWorkflowService:
    """Coordinates CMP_Source normalization/update and complainant checks."""

    def _ensure_complainant_service(self, processor: Any) -> ComplainantService:
        if not getattr(processor, 'complainant_service', None):
            processor.complainant_service = ComplainantService(processor.shared_db_helper)
        return processor.complainant_service

    def update_complainants(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> ComplainantUpdateResult:
        # This module lives in services/workflows; resolve variables from repo root.
        mapping_file_path = (
            Path(__file__).resolve().parents[2] / 'variables' / 'complainant_codes.json'
        )

        result: ComplainantUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'fallback_label': '',
            'fallback_applied': False,
            'total_codes_loaded': 0,
            'duplicate_codes_skipped': 0,
            'resolved_complainants': 0,
            'rows_updated': 0,
            'rows_defaulted': 0,
            'defaulted_values': [],
            'invalid_complainants': [],
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
                result['error'] = 'complainant_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            configured_fallback = file_contents.get('default_for_unmapped') or ''
            complainant_mapping = file_contents.get('mapping')

            if not isinstance(complainant_mapping, dict):
                result['error'] = (
                    "complainant_codes.json must contain a 'mapping' object "
                    "of {label: [codes]}"
                )
                customer_logger.error(result['error'])
                return result

            result['fallback_label'] = str(configured_fallback).strip()

            mapping_frame, duplicate_codes = self.load_complainant_mapping_frame(
                processor, complainant_mapping
            )
            result['total_codes_loaded'] = len(mapping_frame)
            result['duplicate_codes_skipped'] = duplicate_codes

            fallback_label = self.resolve_fallback_label(processor, configured_fallback)
            if configured_fallback and not fallback_label:
                result['error'] = (
                    f"Fallback complainant '{configured_fallback}' from "
                    'complainant_codes.json is not present in tblComplainant'
                )
                customer_logger.error(result['error'])
                return result

            result['fallback_applied'] = bool(fallback_label)
            if fallback_label:
                result['fallback_label'] = fallback_label
            else:
                customer_logger.info(
                    'No fallback complainant configured; unmapped CMP_Source values '
                    'will be left as-is and reported as invalid'
                )

            resolution_frame, unmapped_values = self.build_complainant_resolution_frame(
                processor, mapping_frame
            )
            rows_updated, rows_defaulted = self.bulk_update_complainants(
                processor, resolution_frame, fallback_label
            )
            invalid_complainants = self.get_invalid_complainants_from_db(processor)

            result['resolved_complainants'] = len(resolution_frame)
            result['rows_updated'] = rows_updated
            result['rows_defaulted'] = rows_defaulted
            result['defaulted_values'] = unmapped_values if fallback_label else []
            result['invalid_complainants'] = invalid_complainants
            result['status_message'] = self._build_status_message(
                unmapped_values if fallback_label else [],
                invalid_complainants,
                fallback_label,
            )
            result['success'] = True

            customer_logger.info(
                'Updated RC_COMPLAINT_EXTRACT.CMP_Source using complainant_codes.json: '
                f'{rows_updated} rows updated, '
                f"{rows_defaulted} unmapped rows defaulted to '{fallback_label or 'n/a'}', "
                f'{len(mapping_frame)} codes loaded, '
                f'{duplicate_codes} duplicate code entries skipped'
            )

            if fallback_label and unmapped_values:
                customer_logger.warning(
                    f"{len(unmapped_values)} CMP_Source value(s) fell back to "
                    f"'{fallback_label}': " + ', '.join(unmapped_values)
                )

            if invalid_complainants:
                customer_logger.warning(
                    'Unresolved RC_COMPLAINT_EXTRACT.CMP_Source values after normalization: '
                    + ', '.join(invalid_complainants)
                )

            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to update RC_COMPLAINT_EXTRACT.CMP_Source: {e}')
            return result

    def _build_status_message(
        self,
        defaulted_values: List[str],
        invalid_complainants: List[str],
        fallback_label: Optional[str],
    ) -> str:
        if invalid_complainants:
            return f"Invalid complainant sources found: {', '.join(invalid_complainants)}"
        if defaulted_values:
            return (
                f"{len(defaulted_values)} complainant source(s) defaulted to "
                f"'{fallback_label}': {', '.join(defaulted_values)}"
            )
        return 'All complainant sources are valid.'

    def check_complainants_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        complainant_update_result: Optional[ComplainantUpdateResult] = None,
    ) -> ComplainantCheckResult:
        customer_logger.info('Checking complainant sources...')

        defaulted_values: List[str] = []
        fallback_label = ''

        if complainant_update_result is None:
            invalid_complainants = self.get_invalid_complainants_from_db(processor)
        else:
            invalid_complainants = sorted(set(complainant_update_result.get('invalid_complainants', [])))
            defaulted_values = sorted(set(complainant_update_result.get('defaulted_values', [])))
            fallback_label = complainant_update_result.get('fallback_label', '')

        status_message = self._build_status_message(
            defaulted_values, invalid_complainants, fallback_label
        )

        customer_logger.info(f'Complainant check result: {status_message}')

        if defaulted_values:
            customer_logger.warning(
                f'{len(defaulted_values)} CMP_Source value(s) had no mapping and were '
                f"swept to '{fallback_label}'. Add them to "
                "variables/complainant_codes.json under 'mapping' to map them properly."
            )

        if invalid_complainants:
            customer_logger.warning(
                f'Found {len(invalid_complainants)} CMP_Source value(s) not present in '
                'tblComplainant and not defaulted. Add a real tblComplainant row plus a '
                'complainant_codes.json entry (or default_for_unmapped) before migrating.'
            )

        return {
            'status_message': status_message,
            'defaulted_values': defaulted_values,
            'invalid_complainants': invalid_complainants,
        }

    def load_complainant_mapping_frame(
        self,
        processor: Any,
        complainant_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        service = self._ensure_complainant_service(processor)
        return service.load_complainant_mapping_frame(complainant_mapping)

    def resolve_fallback_label(
        self,
        processor: Any,
        fallback_label: Optional[str],
    ) -> Optional[str]:
        service = self._ensure_complainant_service(processor)
        return service.resolve_fallback_label(fallback_label)

    def build_complainant_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        service = self._ensure_complainant_service(processor)
        return service.build_complainant_resolution_frame(mapping_frame)

    def bulk_update_complainants(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
        fallback_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        service = self._ensure_complainant_service(processor)
        return service.bulk_update_complainants(resolution_frame, fallback_label)

    def get_invalid_complainants_from_db(self, processor: Any) -> List[str]:
        service = self._ensure_complainant_service(processor)
        return service.get_invalid_complainants_from_db()
