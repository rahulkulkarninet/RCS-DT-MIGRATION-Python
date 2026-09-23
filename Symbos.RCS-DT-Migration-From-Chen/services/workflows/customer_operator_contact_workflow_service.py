import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from operator_contact_service import (
    FALLBACK_CONTACT_ID_DEFAULT,
    FALLBACK_VARIABLE,
    OperatorContactService,
)
from result_types import OperatorContactCheckResult, OperatorContactUpdateResult

# How many unresolved operator codes a message names before summarising the rest. The
# result carries all of them; this only bounds what a human reads. Unresolved codes are
# the normal case rather than a fault - on testse 557 of the 564 codes in the extracts
# resolve to nothing, all behaving exactly as they did before this step existed - so the
# log names the busiest few and gives a count for the tail.
REPORTED_CODE_LIMIT = 20


class CustomerOperatorContactWorkflowService:
    """Coordinates operator code normalization and operator code checks."""

    def _ensure_operator_contact_service(self, processor: Any) -> OperatorContactService:
        if not getattr(processor, 'operator_contact_service', None):
            processor.operator_contact_service = OperatorContactService(
                processor.shared_db_helper
            )
        return processor.operator_contact_service

    @staticmethod
    def _fallback_contact_id(processor: Any) -> int:
        """The ContactID {{DefaultOperatorContactID}} resolved to for this environment.

        Read from the same resolved variable the migration SQL is given, rather than
        restated here, so a report can never disagree with what the batch does.
        SQLMigrationManager resolves the database-backed variables in
        initialize_sql_manager_step, which runs before this step, so the value is
        present by now; the default below covers a caller that skipped that.
        """
        config_parser = getattr(processor, 'config_parser', None)
        if not config_parser:
            return FALLBACK_CONTACT_ID_DEFAULT

        value = config_parser.get_variable(FALLBACK_VARIABLE, 'lookup_variables')
        try:
            return int(value)
        except (TypeError, ValueError):
            return FALLBACK_CONTACT_ID_DEFAULT

    @staticmethod
    def _mapping_file_path() -> Path:
        # This module lives in services/workflows; resolve variables from repo root.
        return (
            Path(__file__).resolve().parents[2]
            / 'variables'
            / 'operator_contact_codes.json'
        )

    def update_operator_contacts(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> OperatorContactUpdateResult:
        mapping_file_path = self._mapping_file_path()

        result: OperatorContactUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'total_codes_loaded': 0,
            'duplicate_codes_skipped': 0,
            'resolved_codes': 0,
            'rows_updated': 0,
            'rows_updated_by_table': {},
            'fallback_contact': '',
            'unresolved_contacts': [],
            'ambiguous_contacts': [],
            'unresolved_operator_codes': [],
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
                result['error'] = (
                    'operator_contact_codes.json must contain a JSON object of '
                    '{tblContact.UserName: [operator codes]}'
                )
                customer_logger.error(result['error'])
                return result

            mapping_frame, duplicate_codes = self.load_operator_mapping_frame(
                processor, file_contents
            )
            result['total_codes_loaded'] = len(mapping_frame)
            result['duplicate_codes_skipped'] = duplicate_codes

            resolution_frame, problems = self.build_operator_resolution_frame(
                processor, mapping_frame
            )
            result['resolved_codes'] = len(resolution_frame)
            result['unresolved_contacts'] = problems['unresolved_contacts']
            result['ambiguous_contacts'] = problems['ambiguous_contacts']

            # Fatal, because it is a configuration error with a silent consequence: a
            # username nothing matches rewrites nothing, so every code under it falls
            # through the SQL's ISNULL to the fallback without saying so, and a typo would be
            # indistinguishable from a working mapping. The file names a person; if
            # that person is not in tblContact the file is wrong.
            if problems['unresolved_contacts']:
                result['error'] = (
                    'Usernames in operator_contact_codes.json are not present in '
                    'tblContact.UserName: '
                    + ', '.join(problems['unresolved_contacts'])
                )
                customer_logger.error(result['error'])
                return result

            # Pre-flight rather than a mid-rewrite truncation error, the way the
            # frequency domain checks RC_ARRANGEMENT.Frequency.
            width_problems = self.check_source_column_fits(processor, resolution_frame)
            if width_problems:
                result['error'] = (
                    'Operator columns are too narrow for the configured usernames. '
                    + ' '.join(width_problems)
                )
                customer_logger.error(result['error'])
                return result

            rows_updated_by_table = self.bulk_update_operator_codes(
                processor, resolution_frame
            )
            result['rows_updated_by_table'] = rows_updated_by_table
            result['rows_updated'] = sum(rows_updated_by_table.values())

            unresolved_operator_codes = self.get_unresolved_operator_codes_from_db(
                processor
            )
            result['unresolved_operator_codes'] = unresolved_operator_codes

            customer_logger.info(
                'Rewrote operator codes from operator_contact_codes.json: '
                f"{result['rows_updated']} row(s) across "
                f'{len(rows_updated_by_table)} source column(s), '
                f'{len(resolution_frame)} code(s) resolved of '
                f'{len(mapping_frame)} configured, '
                f'{duplicate_codes} duplicate code entries skipped'
            )

            if problems['ambiguous_contacts']:
                customer_logger.warning(
                    'Usernames in operator_contact_codes.json held by more than one '
                    'tblContact row; the active contact with the lowest ContactID '
                    'wins, which is also what the migration SQL picks: '
                    + ', '.join(problems['ambiguous_contacts'])
                )

            # Not fatal, unlike the cost equivalent, and not a fault in the file
            # either. An unresolved operator code costs attribution, not money: the
            # SQL's ISNULL files the row under the configured fallback contact. This
            # is the list a human adds from when that fallback is the wrong answer.
            fallback = self.describe_fallback_contact(processor)
            result['fallback_contact'] = fallback

            if unresolved_operator_codes:
                customer_logger.warning(
                    f'{len(unresolved_operator_codes)} operator code(s) in the '
                    'extracts resolve to no tblContact.UserName; their rows will be '
                    f'attributed to ContactID {fallback}. Busiest first: '
                    + self._summarise(unresolved_operator_codes)
                )

            result['status_message'] = self._status_message(
                unresolved_operator_codes, problems['ambiguous_contacts'], fallback
            )
            result['success'] = True
            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to rewrite operator codes: {e}')
            return result

    def check_operator_contacts_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        operator_contact_update_result: Optional[OperatorContactUpdateResult] = None,
    ) -> OperatorContactCheckResult:
        customer_logger.info('Checking operator codes...')

        unresolved_contacts: List[str] = []
        ambiguous_contacts: List[str] = []

        if operator_contact_update_result is None:
            unresolved_operator_codes = self.get_unresolved_operator_codes_from_db(
                processor
            )
        else:
            unresolved_contacts = sorted(
                set(operator_contact_update_result.get('unresolved_contacts', []))
            )
            ambiguous_contacts = sorted(
                set(operator_contact_update_result.get('ambiguous_contacts', []))
            )
            # Not re-sorted: the service ordered these busiest first, which is the
            # order a human wants to read them in.
            unresolved_operator_codes = list(
                operator_contact_update_result.get('unresolved_operator_codes', [])
            )

        fallback = (
            (operator_contact_update_result or {}).get('fallback_contact')
            or self.describe_fallback_contact(processor)
        )

        status_message = self._status_message(
            unresolved_operator_codes, ambiguous_contacts, fallback
        )
        customer_logger.info(f'Operator code check result: {status_message}')

        if unresolved_operator_codes:
            customer_logger.warning(
                f'Found {len(unresolved_operator_codes)} operator code(s) that '
                f'resolve to nothing; their rows go to ContactID {fallback}, the '
                'contact {{DefaultOperatorContactID}} names. Add any for which that '
                'is the wrong answer to variables/operator_contact_codes.json under '
                'the tblContact.UserName they act as.'
            )

        return {
            'status_message': status_message,
            'unresolved_contacts': unresolved_contacts,
            'ambiguous_contacts': ambiguous_contacts,
            'unresolved_operator_codes': unresolved_operator_codes,
        }

    def describe_fallback_contact(self, processor: Any) -> str:
        """'197 (PRAM)' - the contact unresolved operator codes are attributed to."""
        service = self._ensure_operator_contact_service(processor)
        return service.describe_contact(self._fallback_contact_id(processor))

    @staticmethod
    def _status_message(
        unresolved_operator_codes: List[str],
        ambiguous_contacts: List[str],
        fallback: str,
    ) -> str:
        if unresolved_operator_codes:
            return (
                f'{len(unresolved_operator_codes)} operator code(s) falling back to '
                f'ContactID {fallback}: '
                + CustomerOperatorContactWorkflowService._summarise(
                    unresolved_operator_codes
                )
            )
        if ambiguous_contacts:
            return (
                'All operator codes resolve; usernames resolved by tie-break: '
                + ', '.join(ambiguous_contacts)
            )
        return 'All operator codes resolve to a contact.'

    @staticmethod
    def _summarise(descriptions: List[str]) -> str:
        """The first REPORTED_CODE_LIMIT entries, then a count of what is left."""
        if len(descriptions) <= REPORTED_CODE_LIMIT:
            return '; '.join(descriptions)

        shown = '; '.join(descriptions[:REPORTED_CODE_LIMIT])
        remaining = len(descriptions) - REPORTED_CODE_LIMIT
        return f'{shown}; and {remaining} more'

    def load_operator_mapping_frame(
        self,
        processor: Any,
        contact_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        service = self._ensure_operator_contact_service(processor)
        return service.load_operator_mapping_frame(contact_mapping)

    def build_operator_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
        service = self._ensure_operator_contact_service(processor)
        return service.build_operator_resolution_frame(mapping_frame)

    def check_source_column_fits(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
    ) -> List[str]:
        service = self._ensure_operator_contact_service(processor)
        return service.check_source_column_fits(resolution_frame)

    def bulk_update_operator_codes(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
    ) -> Dict[str, int]:
        service = self._ensure_operator_contact_service(processor)
        return service.bulk_update_operator_codes(resolution_frame)

    def get_unresolved_operator_codes_from_db(self, processor: Any) -> List[str]:
        service = self._ensure_operator_contact_service(processor)
        return service.get_unresolved_operator_codes_from_db()
