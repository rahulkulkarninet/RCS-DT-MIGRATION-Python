import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from incident_type_service import IncidentTypeService
from result_types import IncidentTypeCheckResult, IncidentTypeUpdateResult


class CustomerIncidentTypeWorkflowService:
    """Coordinates Cause_Description classification/update and incident type checks."""

    def _ensure_incident_type_service(self, processor: Any) -> IncidentTypeService:
        if not getattr(processor, 'incident_type_service', None):
            processor.incident_type_service = IncidentTypeService(
                processor.shared_db_helper
            )
        return processor.incident_type_service

    def update_incident_types(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> IncidentTypeUpdateResult:
        # This module lives in services/workflows; resolve variables from repo root.
        mapping_file_path = (
            Path(__file__).resolve().parents[2] / 'variables' / 'incident_type_codes.json'
        )

        result: IncidentTypeUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'default_label': '',
            'default_applied': False,
            'rules_loaded': 0,
            'rules_skipped': 0,
            'resolved_descriptions': 0,
            'rows_updated': 0,
            'rows_defaulted': 0,
            'unresolved_labels': [],
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
                result['error'] = 'incident_type_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            configured_default = file_contents.get('default') or ''
            rules = file_contents.get('rules')

            if not isinstance(rules, list):
                result['error'] = (
                    "incident_type_codes.json must contain a 'rules' array of "
                    '{contains, incident_type} objects'
                )
                customer_logger.error(result['error'])
                return result

            if not configured_default:
                result['error'] = (
                    "incident_type_codes.json must contain a 'default' incident type; "
                    'the CASE it replaces always produced a value'
                )
                customer_logger.error(result['error'])
                return result

            result['default_label'] = str(configured_default).strip()

            loaded_rules, skipped = self.load_incident_type_rules(processor, rules)
            result['rules_loaded'] = len(loaded_rules)
            result['rules_skipped'] = skipped

            default_label = self.resolve_label(processor, configured_default)
            if not default_label:
                result['error'] = (
                    f"Default incident type '{configured_default}' from "
                    'incident_type_codes.json is not present in tblIncidentType'
                )
                customer_logger.error(result['error'])
                return result

            result['default_applied'] = True
            result['default_label'] = default_label

            resolution_frame, unresolved_labels = self.build_incident_type_resolution_frame(
                processor, loaded_rules
            )
            result['unresolved_labels'] = unresolved_labels

            if unresolved_labels:
                result['error'] = (
                    'Incident types from incident_type_codes.json not present in '
                    f"tblIncidentType: {', '.join(unresolved_labels)}"
                )
                customer_logger.error(result['error'])
                return result

            rows_updated, rows_defaulted = self.bulk_update_incident_types(
                processor, resolution_frame, default_label
            )
            invalid_types = self.get_invalid_incident_types_from_db(processor)

            result['resolved_descriptions'] = len(resolution_frame)
            result['rows_updated'] = rows_updated
            result['rows_defaulted'] = rows_defaulted
            result['invalid_types'] = invalid_types
            result['status_message'] = (
                f"Invalid incident types found: {', '.join(invalid_types)}"
                if invalid_types
                else 'All incident types are valid.'
            )
            result['success'] = True

            customer_logger.info(
                'Updated RC_ACCOUNT_EXTRACT.Cause_Description using '
                f'incident_type_codes.json: {rows_updated} rows classified by keyword, '
                f"{rows_defaulted} rows swept to the default '{default_label}', "
                f'{len(loaded_rules)} keyword rules loaded, '
                f'{skipped} malformed rules skipped'
            )

            if invalid_types:
                customer_logger.warning(
                    'Unresolved RC_ACCOUNT_EXTRACT.Cause_Description values after '
                    'classification: ' + ', '.join(invalid_types)
                )

            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(
                f'Failed to update RC_ACCOUNT_EXTRACT.Cause_Description: {e}'
            )
            return result

    def check_incident_types_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        incident_type_update_result: Optional[IncidentTypeUpdateResult] = None,
    ) -> IncidentTypeCheckResult:
        customer_logger.info('Checking incident types...')

        unresolved_labels: List[str] = []
        invalid_types: List[str] = []

        if incident_type_update_result is None:
            invalid_types = self.get_invalid_incident_types_from_db(processor)
        else:
            unresolved_labels = sorted(
                set(incident_type_update_result.get('unresolved_labels', []))
            )
            invalid_types = sorted(
                set(incident_type_update_result.get('invalid_types', []))
            )

        if unresolved_labels:
            status_message = (
                f"Incident types missing from tblIncidentType: {', '.join(unresolved_labels)}"
            )
        elif invalid_types:
            status_message = f"Invalid incident types found: {', '.join(invalid_types)}"
        else:
            status_message = 'All incident types are valid.'

        customer_logger.info(f'Incident type check result: {status_message}')

        if invalid_types:
            customer_logger.warning(
                f'Found {len(invalid_types)} cause description(s) not present in '
                'tblIncidentType, which migrate as a NULL IncidentTypeID. Add a keyword '
                "rule to variables/incident_type_codes.json, or check its 'default'."
            )

        return {
            'status_message': status_message,
            'unresolved_labels': unresolved_labels,
            'invalid_types': invalid_types,
        }

    def load_incident_type_rules(
        self,
        processor: Any,
        rules: List[Any],
    ) -> Tuple[List[Dict[str, str]], int]:
        service = self._ensure_incident_type_service(processor)
        return service.load_incident_type_rules(rules)

    def resolve_label(self, processor: Any, label: Optional[str]) -> Optional[str]:
        service = self._ensure_incident_type_service(processor)
        return service.resolve_label(label)

    def build_incident_type_resolution_frame(
        self,
        processor: Any,
        rules: List[Dict[str, str]],
    ) -> Tuple[pd.DataFrame, List[str]]:
        service = self._ensure_incident_type_service(processor)
        return service.build_incident_type_resolution_frame(rules)

    def bulk_update_incident_types(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
        default_label: Optional[str] = None,
    ) -> Tuple[int, int]:
        service = self._ensure_incident_type_service(processor)
        return service.bulk_update_incident_types(resolution_frame, default_label)

    def get_invalid_incident_types_from_db(self, processor: Any) -> List[str]:
        service = self._ensure_incident_type_service(processor)
        return service.get_invalid_incident_types_from_db()
