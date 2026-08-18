import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from closure_reason_service import ClosureReasonService
from result_types import ClosureReasonCheckResult, ClosureReasonUpdateResult


class CustomerClosureReasonWorkflowService:
    """Coordinates Reason_Closed normalization/update and closure reason checks."""

    def _ensure_closure_reason_service(self, processor: Any) -> ClosureReasonService:
        if not getattr(processor, 'closure_reason_service', None):
            processor.closure_reason_service = ClosureReasonService(processor.shared_db_helper)
        return processor.closure_reason_service

    def update_closure_reasons(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> ClosureReasonUpdateResult:
        # This module lives in services/workflows; resolve variables from repo root.
        mapping_file_path = (
            Path(__file__).resolve().parents[2] / 'variables' / 'closure_reason_codes.json'
        )

        result: ClosureReasonUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'fallback_label': '',
            'fallback_applied': False,
            'total_codes_loaded': 0,
            'duplicate_codes_skipped': 0,
            'resolved_reasons': 0,
            'rows_updated': 0,
            'rows_defaulted': 0,
            'defaulted_values': [],
            'invalid_reasons': [],
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
                result['error'] = 'closure_reason_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            # Named default_for_unmapped rather than 'default' to keep it distinct from
            # arrangement_type_codes.json, where 'default' fills NULL/blank values. Here
            # NULL is left alone and the label catches values that failed to map.
            configured_fallback = file_contents.get('default_for_unmapped') or ''
            reason_mapping = file_contents.get('mapping')

            if not isinstance(reason_mapping, dict):
                result['error'] = (
                    "closure_reason_codes.json must contain a 'mapping' object "
                    "of {label: [codes]}"
                )
                customer_logger.error(result['error'])
                return result

            result['fallback_label'] = str(configured_fallback).strip()

            mapping_frame, duplicate_codes = self.load_closure_reason_mapping_frame(
                processor, reason_mapping
            )
            result['total_codes_loaded'] = len(mapping_frame)
            result['duplicate_codes_skipped'] = duplicate_codes

            fallback_label = self.resolve_fallback_label(processor, configured_fallback)
            if configured_fallback and not fallback_label:
                result['error'] = (
                    f"Fallback closure reason '{configured_fallback}' from "
                    'closure_reason_codes.json is not present in tblClosureReason'
                )
                customer_logger.error(result['error'])
                return result

            result['fallback_applied'] = bool(fallback_label)
            if fallback_label:
                result['fallback_label'] = fallback_label
            else:
                customer_logger.info(
                    'No fallback closure reason configured; unmapped Reason_Closed '
                    'values will be left as-is and reported as invalid'
                )

            # Captured before the update: afterwards these values have all become the
            # fallback label and can no longer be distinguished.
            resolution_frame, unmapped_reasons = self.build_closure_reason_resolution_frame(
                processor, mapping_frame
            )
            rows_updated, rows_defaulted = self.bulk_update_closure_reasons(
                processor, resolution_frame, fallback_label
            )
            invalid_reasons = self.get_invalid_closure_reasons_from_db(processor)

            result['resolved_reasons'] = len(resolution_frame)
            result['rows_updated'] = rows_updated
            result['rows_defaulted'] = rows_defaulted
            result['defaulted_values'] = unmapped_reasons if fallback_label else []
            result['invalid_reasons'] = invalid_reasons
            result['status_message'] = self._build_status_message(
                unmapped_reasons if fallback_label else [],
                invalid_reasons,
                fallback_label,
            )
            result['success'] = True

            customer_logger.info(
                'Updated RC_ACCOUNT_EXTRACT.Reason_Closed using closure_reason_codes.json: '
                f'{rows_updated} rows updated, '
                f"{rows_defaulted} unmapped rows defaulted to '{fallback_label or 'n/a'}', "
                f'{len(mapping_frame)} codes loaded, '
                f'{duplicate_codes} duplicate code entries skipped '
                '(NULL/blank values left untouched)'
            )

            if fallback_label and unmapped_reasons:
                customer_logger.warning(
                    f"{len(unmapped_reasons)} Reason_Closed value(s) fell back to "
                    f"'{fallback_label}': " + ', '.join(unmapped_reasons)
                )

            if invalid_reasons:
                customer_logger.warning(
                    'Unresolved RC_ACCOUNT_EXTRACT.Reason_Closed values after normalization: '
                    + ', '.join(invalid_reasons)
                )

            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to update RC_ACCOUNT_EXTRACT.Reason_Closed: {e}')
            return result

    def _build_status_message(
        self,
        defaulted_values: List[str],
        invalid_reasons: List[str],
        fallback_label: Optional[str],
    ) -> str:
        if invalid_reasons:
            return f"Invalid closure reasons found: {', '.join(invalid_reasons)}"
        if defaulted_values:
            return (
                f"{len(defaulted_values)} closure reason(s) defaulted to "
                f"'{fallback_label}': {', '.join(defaulted_values)}"
            )
        return 'All closure reasons are valid.'

    def check_closure_reasons_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        reason_update_result: Optional[ClosureReasonUpdateResult] = None,
    ) -> ClosureReasonCheckResult:
        customer_logger.info('Checking closure reasons...')

        defaulted_values: List[str] = []
        fallback_label = ''

        if reason_update_result is None:
            invalid_reasons = self.get_invalid_closure_reasons_from_db(processor)
        else:
            invalid_reasons = sorted(set(reason_update_result.get('invalid_reasons', [])))
            defaulted_values = sorted(set(reason_update_result.get('defaulted_values', [])))
            fallback_label = reason_update_result.get('fallback_label', '')

        status_message = self._build_status_message(
            defaulted_values, invalid_reasons, fallback_label
        )

        customer_logger.info(f'Closure reason check result: {status_message}')

        if defaulted_values:
            customer_logger.warning(
                f'{len(defaulted_values)} closure reason value(s) had no mapping and were '
                f"swept to '{fallback_label}'. Add them to "
                "variables/closure_reason_codes.json under 'mapping' to map them properly."
            )

        if invalid_reasons:
            customer_logger.warning(
                f'Found {len(invalid_reasons)} closure reason value(s) not present in '
                'tblClosureReason and not defaulted.'
            )

        return {
            'status_message': status_message,
            'defaulted_values': defaulted_values,
            'invalid_reasons': invalid_reasons,
        }

    def load_closure_reason_mapping_frame(
        self,
        processor: Any,
        reason_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        service = self._ensure_closure_reason_service(processor)
        return service.load_closure_reason_mapping_frame(reason_mapping)

    def resolve_fallback_label(
        self,
        processor: Any,
        fallback_label: Optional[str],
    ) -> Optional[str]:
        service = self._ensure_closure_reason_service(processor)
        return service.resolve_fallback_label(fallback_label)

    def build_closure_reason_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        service = self._ensure_closure_reason_service(processor)
        return service.build_closure_reason_resolution_frame(mapping_frame)

    def bulk_update_closure_reasons(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
        fallback_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        service = self._ensure_closure_reason_service(processor)
        return service.bulk_update_closure_reasons(resolution_frame, fallback_label)

    def get_invalid_closure_reasons_from_db(self, processor: Any) -> List[str]:
        service = self._ensure_closure_reason_service(processor)
        return service.get_invalid_closure_reasons_from_db()
