import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from related_party_type_service import RelatedPartyTypeService
from result_types import RelatedPartyTypeCheckResult, RelatedPartyTypeUpdateResult


class CustomerRelatedPartyTypeWorkflowService:
    """Coordinates Related_Party_Type_Code normalization/update and related checks."""

    def _ensure_related_party_type_service(self, processor: Any) -> RelatedPartyTypeService:
        if not getattr(processor, 'related_party_type_service', None):
            processor.related_party_type_service = RelatedPartyTypeService(
                processor.shared_db_helper
            )
        return processor.related_party_type_service

    def update_related_party_types(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> RelatedPartyTypeUpdateResult:
        # This module lives in services/workflows; resolve variables from repo root.
        mapping_file_path = (
            Path(__file__).resolve().parents[2]
            / 'variables'
            / 'related_party_type_codes.json'
        )

        result: RelatedPartyTypeUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'fallback_label': '',
            'fallback_applied': False,
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
                result['error'] = 'related_party_type_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            # default_for_unmapped reproduces the ELSE {{RelationshipID_Other}} branch of
            # the CASE this replaces. Blank/absent switches the sweep off.
            configured_fallback = file_contents.get('default_for_unmapped') or ''
            type_mapping = file_contents.get('mapping')

            if not isinstance(type_mapping, dict):
                result['error'] = (
                    "related_party_type_codes.json must contain a 'mapping' object "
                    'of {label: [codes]}'
                )
                customer_logger.error(result['error'])
                return result

            result['fallback_label'] = str(configured_fallback).strip()

            mapping_frame, duplicate_codes = self.load_related_party_type_mapping_frame(
                processor, type_mapping
            )
            result['total_codes_loaded'] = len(mapping_frame)
            result['duplicate_codes_skipped'] = duplicate_codes

            fallback_label = self.resolve_fallback_label(processor, configured_fallback)
            if configured_fallback and not fallback_label:
                result['error'] = (
                    f"Fallback relationship '{configured_fallback}' from "
                    'related_party_type_codes.json is not present in tblRelationship'
                )
                customer_logger.error(result['error'])
                return result

            result['fallback_applied'] = bool(fallback_label)
            if fallback_label:
                result['fallback_label'] = fallback_label
            else:
                customer_logger.info(
                    'No fallback relationship configured; unmapped '
                    'Related_Party_Type_Code values will be left as-is'
                )

            resolution_frame, _ = self.build_related_party_type_resolution_frame(
                processor, mapping_frame
            )
            rows_updated, rows_defaulted = self.bulk_update_related_party_types(
                processor, resolution_frame, fallback_label
            )
            invalid_types = self.get_invalid_related_party_types_from_db(processor)

            result['resolved_types'] = len(resolution_frame)
            result['rows_updated'] = rows_updated
            result['rows_defaulted'] = rows_defaulted
            result['invalid_types'] = invalid_types
            result['status_message'] = (
                f"Invalid related party types found: {', '.join(invalid_types)}"
                if invalid_types
                else 'All related party types are valid.'
            )
            result['success'] = True

            customer_logger.info(
                'Updated RC_RELATEDPARTY.Related_Party_Type_Code using '
                f'related_party_type_codes.json: {rows_updated} rows updated, '
                f"{rows_defaulted} unmapped rows swept to '{fallback_label or 'n/a'}', "
                f'{len(mapping_frame)} codes loaded, '
                f'{duplicate_codes} duplicate code entries skipped'
            )

            if invalid_types:
                customer_logger.warning(
                    'Unresolved RC_RELATEDPARTY.Related_Party_Type_Code values after '
                    'normalization: ' + ', '.join(invalid_types)
                )

            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(
                f'Failed to update RC_RELATEDPARTY.Related_Party_Type_Code: {e}'
            )
            return result

    def check_related_party_types_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        type_update_result: Optional[RelatedPartyTypeUpdateResult] = None,
    ) -> RelatedPartyTypeCheckResult:
        customer_logger.info('Checking related party types...')

        status_message = 'All related party types are valid.'
        invalid_types: List[str] = []

        if type_update_result is None:
            invalid_types = self.get_invalid_related_party_types_from_db(processor)
        else:
            invalid_types = sorted(set(type_update_result.get('invalid_types', [])))

        if invalid_types:
            status_message = (
                f"Invalid related party types found: {', '.join(invalid_types)}"
            )

        customer_logger.info(f'Related party type check result: {status_message}')

        if invalid_types:
            customer_logger.warning(
                f'Found {len(invalid_types)} related party type value(s) not present in '
                'tblRelationship. Add them to '
                "variables/related_party_type_codes.json under 'mapping' before migrating."
            )

        return {
            'status_message': status_message,
            'invalid_types': invalid_types,
        }

    def load_related_party_type_mapping_frame(
        self,
        processor: Any,
        type_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        service = self._ensure_related_party_type_service(processor)
        return service.load_related_party_type_mapping_frame(type_mapping)

    def resolve_fallback_label(
        self,
        processor: Any,
        fallback_label: Optional[str],
    ) -> Optional[str]:
        service = self._ensure_related_party_type_service(processor)
        return service.resolve_fallback_label(fallback_label)

    def build_related_party_type_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        service = self._ensure_related_party_type_service(processor)
        return service.build_related_party_type_resolution_frame(mapping_frame)

    def bulk_update_related_party_types(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
        fallback_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        service = self._ensure_related_party_type_service(processor)
        return service.bulk_update_related_party_types(resolution_frame, fallback_label)

    def get_invalid_related_party_types_from_db(self, processor: Any) -> List[str]:
        service = self._ensure_related_party_type_service(processor)
        return service.get_invalid_related_party_types_from_db()
