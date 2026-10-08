import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from hardship_cause_service import HardshipCauseService
from result_types import HardshipCauseCheckResult, HardshipCauseUpdateResult


class CustomerHardshipCauseWorkflowService:
    """Coordinates RC_HARDSHIP_EXTRACT.Hardship_Cause normalization/update and checks."""

    def _ensure_hardship_cause_service(self, processor: Any) -> HardshipCauseService:
        if not getattr(processor, 'hardship_cause_service', None):
            processor.hardship_cause_service = HardshipCauseService(processor.shared_db_helper)
        return processor.hardship_cause_service

    def update_hardship_causes(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> HardshipCauseUpdateResult:
        # This module lives in services/workflows; resolve variables from repo root.
        mapping_file_path = (
            Path(__file__).resolve().parents[2] / 'variables' / 'hardship_cause_codes.json'
        )

        result: HardshipCauseUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'fallback_label': '',
            'fallback_applied': False,
            'total_codes_loaded': 0,
            'duplicate_codes_skipped': 0,
            'resolved_causes': 0,
            'rows_updated': 0,
            'rows_defaulted': 0,
            'defaulted_values': [],
            'invalid_causes': [],
            'status_message': '',
            'error': None,
        }

        try:
            service = self._ensure_hardship_cause_service(processor)
            if not service.source_table_exists():
                result['success'] = True
                result['status_message'] = 'No RC_HARDSHIP_EXTRACT for this customer; skipped.'
                return result

            if not mapping_file_path.exists():
                result['error'] = f'Mapping file not found: {mapping_file_path}'
                customer_logger.error(result['error'])
                return result

            with open(mapping_file_path, 'r', encoding='utf-8') as file_handle:
                file_contents = json.load(file_handle)

            if not isinstance(file_contents, dict):
                result['error'] = 'hardship_cause_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            configured_fallback = file_contents.get('default_for_unmapped') or ''
            cause_mapping = file_contents.get('mapping')

            if not isinstance(cause_mapping, dict):
                result['error'] = (
                    "hardship_cause_codes.json must contain a 'mapping' object "
                    "of {label: [codes]}"
                )
                customer_logger.error(result['error'])
                return result

            result['fallback_label'] = str(configured_fallback).strip()

            mapping_frame, duplicate_codes = self.load_hardship_cause_mapping_frame(
                processor, cause_mapping
            )
            result['total_codes_loaded'] = len(mapping_frame)
            result['duplicate_codes_skipped'] = duplicate_codes

            fallback_label = self.resolve_fallback_label(processor, configured_fallback)
            if configured_fallback and not fallback_label:
                result['error'] = (
                    f"Fallback hardship cause '{configured_fallback}' from "
                    'hardship_cause_codes.json is not present in tblHardshipCause'
                )
                customer_logger.error(result['error'])
                return result

            result['fallback_applied'] = bool(fallback_label)
            if fallback_label:
                result['fallback_label'] = fallback_label
            else:
                customer_logger.info(
                    'No fallback hardship cause configured; unmapped Hardship_Cause '
                    'values will be left as-is and reported as invalid'
                )

            resolution_frame, unmapped_causes = self.build_hardship_cause_resolution_frame(
                processor, mapping_frame
            )
            rows_updated, rows_defaulted = self.bulk_update_hardship_causes(
                processor, resolution_frame, fallback_label
            )
            invalid_causes = self.get_invalid_hardship_causes_from_db(processor)

            result['resolved_causes'] = len(resolution_frame)
            result['rows_updated'] = rows_updated
            result['rows_defaulted'] = rows_defaulted
            result['defaulted_values'] = unmapped_causes if fallback_label else []
            result['invalid_causes'] = invalid_causes
            result['status_message'] = self._build_status_message(
                unmapped_causes if fallback_label else [],
                invalid_causes,
                fallback_label,
            )
            result['success'] = True

            customer_logger.info(
                'Updated RC_HARDSHIP_EXTRACT.Hardship_Cause using hardship_cause_codes.json: '
                f'{rows_updated} rows updated, '
                f"{rows_defaulted} unmapped rows defaulted to '{fallback_label or 'n/a'}', "
                f'{len(mapping_frame)} codes loaded, '
                f'{duplicate_codes} duplicate code entries skipped '
                '(NULL/blank values left untouched)'
            )

            if fallback_label and unmapped_causes:
                customer_logger.warning(
                    f"{len(unmapped_causes)} Hardship_Cause value(s) fell back to "
                    f"'{fallback_label}': " + ', '.join(unmapped_causes)
                )

            if invalid_causes:
                customer_logger.warning(
                    'Unresolved RC_HARDSHIP_EXTRACT.Hardship_Cause values after normalization: '
                    + ', '.join(invalid_causes)
                )

            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to update RC_HARDSHIP_EXTRACT.Hardship_Cause: {e}')
            return result

    def _build_status_message(
        self,
        defaulted_values: List[str],
        invalid_causes: List[str],
        fallback_label: Optional[str],
    ) -> str:
        if invalid_causes:
            return f"Invalid hardship causes found: {', '.join(invalid_causes)}"
        if defaulted_values:
            return (
                f"{len(defaulted_values)} hardship cause(s) defaulted to "
                f"'{fallback_label}': {', '.join(defaulted_values)}"
            )
        return 'All hardship causes are valid.'

    def check_hardship_causes_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        cause_update_result: Optional[HardshipCauseUpdateResult] = None,
    ) -> HardshipCauseCheckResult:
        customer_logger.info('Checking hardship causes...')

        defaulted_values: List[str] = []
        fallback_label = ''

        if cause_update_result is None:
            invalid_causes = self.get_invalid_hardship_causes_from_db(processor)
        else:
            invalid_causes = sorted(set(cause_update_result.get('invalid_causes', [])))
            defaulted_values = sorted(set(cause_update_result.get('defaulted_values', [])))
            fallback_label = cause_update_result.get('fallback_label', '')

        status_message = self._build_status_message(
            defaulted_values, invalid_causes, fallback_label
        )

        customer_logger.info(f'Hardship cause check result: {status_message}')

        if defaulted_values:
            customer_logger.warning(
                f'{len(defaulted_values)} hardship cause value(s) had no mapping and were '
                f"swept to '{fallback_label}'. Add them to "
                "variables/hardship_cause_codes.json under 'mapping' to map them properly."
            )

        if invalid_causes:
            customer_logger.warning(
                f'Found {len(invalid_causes)} hardship cause value(s) not present in '
                'tblHardshipCause and not defaulted.'
            )

        return {
            'status_message': status_message,
            'defaulted_values': defaulted_values,
            'invalid_causes': invalid_causes,
        }

    def load_hardship_cause_mapping_frame(
        self,
        processor: Any,
        cause_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        service = self._ensure_hardship_cause_service(processor)
        return service.load_hardship_cause_mapping_frame(cause_mapping)

    def resolve_fallback_label(
        self,
        processor: Any,
        fallback_label: Optional[str],
    ) -> Optional[str]:
        service = self._ensure_hardship_cause_service(processor)
        return service.resolve_fallback_label(fallback_label)

    def build_hardship_cause_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        service = self._ensure_hardship_cause_service(processor)
        return service.build_hardship_cause_resolution_frame(mapping_frame)

    def bulk_update_hardship_causes(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
        fallback_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        service = self._ensure_hardship_cause_service(processor)
        return service.bulk_update_hardship_causes(resolution_frame, fallback_label)

    def get_invalid_hardship_causes_from_db(self, processor: Any) -> List[str]:
        service = self._ensure_hardship_cause_service(processor)
        return service.get_invalid_hardship_causes_from_db()
