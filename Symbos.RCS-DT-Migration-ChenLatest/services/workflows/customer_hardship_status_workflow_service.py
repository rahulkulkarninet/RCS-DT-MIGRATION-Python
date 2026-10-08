import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from hardship_status_service import HardshipStatusService
from result_types import HardshipStatusCheckResult, HardshipStatusUpdateResult


class CustomerHardshipStatusWorkflowService:
    """Coordinates RC_HARDSHIP_EXTRACT.Status normalization/update and status checks."""

    def _ensure_hardship_status_service(self, processor: Any) -> HardshipStatusService:
        if not getattr(processor, 'hardship_status_service', None):
            processor.hardship_status_service = HardshipStatusService(processor.shared_db_helper)
        return processor.hardship_status_service

    def update_hardship_statuses(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> HardshipStatusUpdateResult:
        # This module lives in services/workflows; resolve variables from repo root.
        mapping_file_path = (
            Path(__file__).resolve().parents[2] / 'variables' / 'hardship_status_codes.json'
        )

        result: HardshipStatusUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'fallback_label': '',
            'fallback_applied': False,
            'total_codes_loaded': 0,
            'duplicate_codes_skipped': 0,
            'resolved_statuses': 0,
            'rows_updated': 0,
            'rows_defaulted': 0,
            'defaulted_values': [],
            'invalid_statuses': [],
            'status_message': '',
            'error': None,
        }

        try:
            service = self._ensure_hardship_status_service(processor)
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
                result['error'] = 'hardship_status_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            configured_fallback = file_contents.get('default_for_unmapped') or ''
            status_mapping = file_contents.get('mapping')

            if not isinstance(status_mapping, dict):
                result['error'] = (
                    "hardship_status_codes.json must contain a 'mapping' object "
                    "of {label: [codes]}"
                )
                customer_logger.error(result['error'])
                return result

            result['fallback_label'] = str(configured_fallback).strip()

            mapping_frame, duplicate_codes = self.load_hardship_status_mapping_frame(
                processor, status_mapping
            )
            result['total_codes_loaded'] = len(mapping_frame)
            result['duplicate_codes_skipped'] = duplicate_codes

            fallback_label = self.resolve_fallback_label(processor, configured_fallback)
            if configured_fallback and not fallback_label:
                result['error'] = (
                    f"Fallback hardship status '{configured_fallback}' from "
                    'hardship_status_codes.json is not present in tblHardshipStatus'
                )
                customer_logger.error(result['error'])
                return result

            result['fallback_applied'] = bool(fallback_label)
            if fallback_label:
                result['fallback_label'] = fallback_label
            else:
                customer_logger.info(
                    'No fallback hardship status configured; unmapped Status '
                    'values will be left as-is and reported as invalid'
                )

            resolution_frame, unmapped_statuses = self.build_hardship_status_resolution_frame(
                processor, mapping_frame
            )
            rows_updated, rows_defaulted = self.bulk_update_hardship_statuses(
                processor, resolution_frame, fallback_label
            )
            invalid_statuses = self.get_invalid_hardship_statuses_from_db(processor)

            result['resolved_statuses'] = len(resolution_frame)
            result['rows_updated'] = rows_updated
            result['rows_defaulted'] = rows_defaulted
            result['defaulted_values'] = unmapped_statuses if fallback_label else []
            result['invalid_statuses'] = invalid_statuses
            result['status_message'] = self._build_status_message(
                unmapped_statuses if fallback_label else [],
                invalid_statuses,
                fallback_label,
            )
            result['success'] = True

            customer_logger.info(
                'Updated RC_HARDSHIP_EXTRACT.Status using hardship_status_codes.json: '
                f'{rows_updated} rows updated, '
                f"{rows_defaulted} unmapped rows defaulted to '{fallback_label or 'n/a'}', "
                f'{len(mapping_frame)} codes loaded, '
                f'{duplicate_codes} duplicate code entries skipped '
                '(NULL/blank values left untouched)'
            )

            if fallback_label and unmapped_statuses:
                customer_logger.warning(
                    f"{len(unmapped_statuses)} Status value(s) fell back to "
                    f"'{fallback_label}': " + ', '.join(unmapped_statuses)
                )

            if invalid_statuses:
                customer_logger.warning(
                    'Unresolved RC_HARDSHIP_EXTRACT.Status values after normalization: '
                    + ', '.join(invalid_statuses)
                )

            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to update RC_HARDSHIP_EXTRACT.Status: {e}')
            return result

    def _build_status_message(
        self,
        defaulted_values: List[str],
        invalid_statuses: List[str],
        fallback_label: Optional[str],
    ) -> str:
        if invalid_statuses:
            return f"Invalid hardship statuses found: {', '.join(invalid_statuses)}"
        if defaulted_values:
            return (
                f"{len(defaulted_values)} hardship status(es) defaulted to "
                f"'{fallback_label}': {', '.join(defaulted_values)}"
            )
        return 'All hardship statuses are valid.'

    def check_hardship_statuses_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        status_update_result: Optional[HardshipStatusUpdateResult] = None,
    ) -> HardshipStatusCheckResult:
        customer_logger.info('Checking hardship statuses...')

        defaulted_values: List[str] = []
        fallback_label = ''

        if status_update_result is None:
            invalid_statuses = self.get_invalid_hardship_statuses_from_db(processor)
        else:
            invalid_statuses = sorted(set(status_update_result.get('invalid_statuses', [])))
            defaulted_values = sorted(set(status_update_result.get('defaulted_values', [])))
            fallback_label = status_update_result.get('fallback_label', '')

        status_message = self._build_status_message(
            defaulted_values, invalid_statuses, fallback_label
        )

        customer_logger.info(f'Hardship status check result: {status_message}')

        if defaulted_values:
            customer_logger.warning(
                f'{len(defaulted_values)} hardship status value(s) had no mapping and were '
                f"swept to '{fallback_label}'. Add them to "
                "variables/hardship_status_codes.json under 'mapping' to map them properly."
            )

        if invalid_statuses:
            customer_logger.warning(
                f'Found {len(invalid_statuses)} hardship status value(s) not present in '
                'tblHardshipStatus and not defaulted.'
            )

        return {
            'status_message': status_message,
            'defaulted_values': defaulted_values,
            'invalid_statuses': invalid_statuses,
        }

    def load_hardship_status_mapping_frame(
        self,
        processor: Any,
        status_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        service = self._ensure_hardship_status_service(processor)
        return service.load_hardship_status_mapping_frame(status_mapping)

    def resolve_fallback_label(
        self,
        processor: Any,
        fallback_label: Optional[str],
    ) -> Optional[str]:
        service = self._ensure_hardship_status_service(processor)
        return service.resolve_fallback_label(fallback_label)

    def build_hardship_status_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        service = self._ensure_hardship_status_service(processor)
        return service.build_hardship_status_resolution_frame(mapping_frame)

    def bulk_update_hardship_statuses(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
        fallback_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        service = self._ensure_hardship_status_service(processor)
        return service.bulk_update_hardship_statuses(resolution_frame, fallback_label)

    def get_invalid_hardship_statuses_from_db(self, processor: Any) -> List[str]:
        service = self._ensure_hardship_status_service(processor)
        return service.get_invalid_hardship_statuses_from_db()
