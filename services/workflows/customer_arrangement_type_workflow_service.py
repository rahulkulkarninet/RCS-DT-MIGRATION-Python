import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from arrangement_type_service import ArrangementTypeService
from result_types import ArrangementTypeCheckResult, ArrangementTypeUpdateResult


class CustomerArrangementTypeWorkflowService:
    """Coordinates Arrangement_Type normalization/update and arrangement type checks."""

    def _ensure_arrangement_type_service(self, processor: Any) -> ArrangementTypeService:
        if not getattr(processor, 'arrangement_type_service', None):
            processor.arrangement_type_service = ArrangementTypeService(
                processor.shared_db_helper
            )
        return processor.arrangement_type_service

    def update_arrangement_types(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> ArrangementTypeUpdateResult:
        # This module lives in services/workflows; resolve variables from repo root.
        mapping_file_path = (
            Path(__file__).resolve().parents[2] / 'variables' / 'arrangement_type_codes.json'
        )

        result: ArrangementTypeUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'default_label': '',
            'default_applied': False,
            'total_codes_loaded': 0,
            'duplicate_codes_skipped': 0,
            'resolved_types': 0,
            'rows_updated': 0,
            'rows_defaulted': 0,
            'invalid_types': [],
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
                result['error'] = 'arrangement_type_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            # The default label is configuration, not a hardcoded constant, so it can be
            # changed without touching code. Blank/absent switches defaulting off.
            configured_default = file_contents.get('default') or ''
            type_mapping = file_contents.get('mapping')

            if not isinstance(type_mapping, dict):
                result['error'] = (
                    "arrangement_type_codes.json must contain a 'mapping' object "
                    "of {label: [codes]}"
                )
                customer_logger.error(result['error'])
                return result

            result['default_label'] = str(configured_default).strip()

            mapping_frame, duplicate_codes = self.load_arrangement_type_mapping_frame(
                processor, type_mapping
            )
            result['total_codes_loaded'] = len(mapping_frame)
            result['duplicate_codes_skipped'] = duplicate_codes

            # Unlike the status and payment method transforms, an empty mapping is not a
            # reason to stop: the NULL default still has to be applied.
            default_label = self.resolve_default_label(processor, configured_default)
            if configured_default and not default_label:
                result['error'] = (
                    f"Default arrangement type '{configured_default}' from "
                    'arrangement_type_codes.json is not present in tblArrangementType'
                )
                customer_logger.error(result['error'])
                return result

            result['default_applied'] = bool(default_label)
            if default_label:
                result['default_label'] = default_label
            else:
                customer_logger.info(
                    'No default arrangement type configured; NULL/blank '
                    'Arrangement_Type values will be left as-is'
                )

            resolution_frame, _ = self.build_arrangement_type_resolution_frame(
                processor, mapping_frame
            )
            rows_updated, rows_defaulted = self.bulk_update_arrangement_types(
                processor, resolution_frame, default_label
            )
            invalid_types = self.get_invalid_arrangement_types_from_db(processor)

            result['resolved_types'] = len(resolution_frame)
            result['rows_updated'] = rows_updated
            result['rows_defaulted'] = rows_defaulted
            result['invalid_types'] = invalid_types
            result['status_message'] = (
                f"Invalid arrangement types found: {', '.join(invalid_types)}"
                if invalid_types
                else 'All arrangement types are valid.'
            )
            result['success'] = True

            customer_logger.info(
                'Updated RC_ARRANGEMENT.Arrangement_Type using arrangement_type_codes.json: '
                f'{rows_updated} rows updated, '
                f"{rows_defaulted} NULL/blank rows defaulted to '{default_label or 'n/a'}', "
                f'{len(mapping_frame)} codes loaded, '
                f'{duplicate_codes} duplicate code entries skipped'
            )

            if invalid_types:
                customer_logger.warning(
                    'Unresolved RC_ARRANGEMENT.Arrangement_Type values after normalization: '
                    + ', '.join(invalid_types)
                )

            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to update RC_ARRANGEMENT.Arrangement_Type: {e}')
            return result

    def check_arrangement_types_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        type_update_result: Optional[ArrangementTypeUpdateResult] = None,
    ) -> ArrangementTypeCheckResult:
        customer_logger.info('Checking arrangement types...')

        status_message = 'All arrangement types are valid.'
        invalid_types: List[str] = []

        if type_update_result is None:
            invalid_types = self.get_invalid_arrangement_types_from_db(processor)
        else:
            invalid_types = sorted(set(type_update_result.get('invalid_types', [])))

        if invalid_types:
            status_message = f"Invalid arrangement types found: {', '.join(invalid_types)}"

        customer_logger.info(f'Arrangement type check result: {status_message}')

        if invalid_types:
            customer_logger.warning(
                f'Found {len(invalid_types)} arrangement type value(s) not present in '
                'tblArrangementType. Add them to '
                "variables/arrangement_type_codes.json under 'mapping' before migrating."
            )

        return {
            'status_message': status_message,
            'invalid_types': invalid_types,
        }

    def load_arrangement_type_mapping_frame(
        self,
        processor: Any,
        type_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        service = self._ensure_arrangement_type_service(processor)
        return service.load_arrangement_type_mapping_frame(type_mapping)

    def resolve_default_label(
        self,
        processor: Any,
        default_label: Optional[str],
    ) -> Optional[str]:
        service = self._ensure_arrangement_type_service(processor)
        return service.resolve_default_label(default_label)

    def build_arrangement_type_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        service = self._ensure_arrangement_type_service(processor)
        return service.build_arrangement_type_resolution_frame(mapping_frame)

    def bulk_update_arrangement_types(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
        default_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        service = self._ensure_arrangement_type_service(processor)
        return service.bulk_update_arrangement_types(resolution_frame, default_label)

    def get_invalid_arrangement_types_from_db(self, processor: Any) -> List[str]:
        service = self._ensure_arrangement_type_service(processor)
        return service.get_invalid_arrangement_types_from_db()
