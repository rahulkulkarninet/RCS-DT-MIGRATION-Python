import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from result_types import StateCheckResult, StateUpdateResult
from state_service import StateService


class CustomerStateWorkflowService:
    """Coordinates post-batch tblAddress.State normalization and state checks.

    Runs after the SQL batch rather than before it: the column it corrects is populated
    mid-batch by files 37-43, so there is nothing to normalize until they have run. See
    the module docstring on state_service.py.
    """

    def _ensure_state_service(self, processor: Any) -> StateService:
        if not getattr(processor, 'state_service', None):
            processor.state_service = StateService(processor.shared_db_helper)
        return processor.state_service

    def update_states(
        self,
        processor: Any,
        customer_logger: logging.Logger,
        load_id: Optional[int] = None,
    ) -> StateUpdateResult:
        # This module lives in services/workflows; resolve variables from repo root.
        mapping_file_path = (
            Path(__file__).resolve().parents[2] / 'variables' / 'state_codes.json'
        )

        result: StateUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'total_synonyms_loaded': 0,
            'duplicate_synonyms_skipped': 0,
            'resolved_states': 0,
            'rows_updated': 0,
            'unresolved_labels': [],
            'invalid_states': [],
            'status_message': '',
            'error': None,
        }

        try:
            if load_id is None:
                result['error'] = 'No LoadID available; cannot normalize address states'
                customer_logger.error(result['error'])
                return result

            if not mapping_file_path.exists():
                result['error'] = f'Mapping file not found: {mapping_file_path}'
                customer_logger.error(result['error'])
                return result

            with open(mapping_file_path, 'r', encoding='utf-8') as file_handle:
                file_contents = json.load(file_handle)

            if not isinstance(file_contents, dict):
                result['error'] = 'state_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            mapping_frame, duplicate_synonyms = self.load_state_mapping_frame(
                processor, file_contents
            )
            result['total_synonyms_loaded'] = len(mapping_frame)
            result['duplicate_synonyms_skipped'] = duplicate_synonyms

            resolution_frame, unresolved_labels = self.build_state_resolution_frame(
                processor, mapping_frame, load_id
            )
            result['unresolved_labels'] = unresolved_labels

            rows_updated = self.bulk_update_address_states(
                processor, resolution_frame, load_id
            )
            invalid_states = self.get_invalid_states_from_db(processor, load_id)

            result['resolved_states'] = len(resolution_frame)
            result['rows_updated'] = rows_updated
            result['invalid_states'] = invalid_states
            result['status_message'] = (
                f"Address states still unresolved: {', '.join(invalid_states)}"
                if invalid_states
                else 'All address states are resolved.'
            )
            result['success'] = True

            customer_logger.info(
                'Normalized tblAddress.State using state_codes.json: '
                f'{rows_updated} rows resolved that '
                '44.tbladdress_Assign_StateID.sql left NULL '
                f'({len(mapping_frame)} configured synonyms, '
                f'{duplicate_synonyms} duplicates skipped)'
            )

            if unresolved_labels:
                customer_logger.warning(
                    'State codes in state_codes.json with no tblState.StateShort match: '
                    + ', '.join(unresolved_labels)
                )

            if invalid_states:
                customer_logger.warning(
                    'tblAddress.State values still carrying a NULL StateID: '
                    + ', '.join(invalid_states)
                )

            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to normalize tblAddress.State: {e}')
            return result

    def check_states_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        state_update_result: Optional[StateUpdateResult] = None,
        load_id: Optional[int] = None,
    ) -> StateCheckResult:
        customer_logger.info('Checking states...')

        unresolved_labels: List[str] = []
        invalid_states: List[str] = []

        if state_update_result is None:
            invalid_states = self.get_invalid_states_from_db(processor, load_id)
        else:
            unresolved_labels = sorted(set(state_update_result.get('unresolved_labels', [])))
            invalid_states = sorted(set(state_update_result.get('invalid_states', [])))

        if unresolved_labels:
            status_message = (
                f"State codes missing from tblState: {', '.join(unresolved_labels)}"
            )
        elif invalid_states:
            status_message = f'Address states still unresolved: {len(invalid_states)}'
        else:
            status_message = 'All address states are resolved.'

        customer_logger.info(f'State check result: {status_message}')

        if invalid_states:
            customer_logger.warning(
                f'Found {len(invalid_states)} tblAddress.State value(s) with a NULL '
                'StateID after normalization: '
                + ', '.join(invalid_states)
                + '. Add them as synonyms in variables/state_codes.json and re-run.'
            )

        return {
            'status_message': status_message,
            'unresolved_labels': unresolved_labels,
            'invalid_states': invalid_states,
        }

    def load_state_mapping_frame(
        self,
        processor: Any,
        state_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        service = self._ensure_state_service(processor)
        return service.load_state_mapping_frame(state_mapping)

    def build_state_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
        load_id: Optional[int],
    ) -> Tuple[pd.DataFrame, List[str]]:
        service = self._ensure_state_service(processor)
        return service.build_state_resolution_frame(mapping_frame, load_id)

    def bulk_update_address_states(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
        load_id: Optional[int],
    ) -> int:
        service = self._ensure_state_service(processor)
        return service.bulk_update_address_states(resolution_frame, load_id)

    def get_invalid_states_from_db(
        self,
        processor: Any,
        load_id: Optional[int] = None,
    ) -> List[str]:
        service = self._ensure_state_service(processor)
        return service.get_invalid_states_from_db(load_id)
