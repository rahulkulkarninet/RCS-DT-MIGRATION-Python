import logging
from typing import Any, List, Optional

from operator_contact_service import (
    DEFAULT_OPERATOR_Z_REF,
    FALLBACK_CONTACT_ID_DEFAULT,
    FALLBACK_VARIABLE,
    LOOKUP_REF_COLUMN,
    LOOKUP_TABLE,
    SCHEMA_FILE,
    SOURCE_COLUMN,
    SOURCE_TABLE,
    TARGET_COLUMN,
    OperatorContactService,
)
from result_types import OperatorContactCheckResult, OperatorContactUpdateResult

# How many defaulted operator codes a message names before summarising the rest. The
# result carries all of them; this only bounds what a human reads.
REPORTED_CODE_LIMIT = 20


class CustomerOperatorContactWorkflowService:
    """Coordinates the RC_ACCOUNT_EXTRACT operator mapping and its check."""

    def _ensure_operator_contact_service(self, processor: Any) -> OperatorContactService:
        if not getattr(processor, 'operator_contact_service', None):
            processor.operator_contact_service = OperatorContactService(
                processor.shared_db_helper
            )
        return processor.operator_contact_service

    @staticmethod
    def _fallback_contact_id(processor: Any) -> int:
        """The ContactID {{DefaultOperatorContactID}} resolved to for this environment.

        Read from the same resolved variable the migration SQL is given, so the account
        rewrite can be checked against the fallback 58, 60, 64, 65 and 67 use.
        SQLMigrationManager resolves the database-backed variables in
        initialize_sql_manager_step, which runs before this step.
        """
        config_parser = getattr(processor, 'config_parser', None)
        if not config_parser:
            return FALLBACK_CONTACT_ID_DEFAULT

        value = config_parser.get_variable(FALLBACK_VARIABLE, 'lookup_variables')
        try:
            return int(value)
        except (TypeError, ValueError):
            return FALLBACK_CONTACT_ID_DEFAULT

    def update_operator_contacts(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> OperatorContactUpdateResult:
        result: OperatorContactUpdateResult = {
            'success': False,
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
            service = self._ensure_operator_contact_service(processor)

            # Fatal: 01 reads this column, so the batch would fail at file 01 anyway.
            # Say so here, with the fix, before anything is written.
            if not service.target_column_exists():
                result['error'] = (
                    f'{SOURCE_TABLE}.{TARGET_COLUMN} does not exist; the staging '
                    'schema predates it. Run: python tools/deploy_schemas.py <env> '
                    f'--file "{SCHEMA_FILE}"'
                )
                customer_logger.error(result['error'])
                return result

            # Fatal: without it there is no contact to give an unmatched account, and
            # {{DefaultOperatorContactID}} would quietly fall to its configured default.
            default_contact = service.resolve_default_contact()
            if default_contact is None:
                result['unresolved_contacts'] = [DEFAULT_OPERATOR_Z_REF]
                result['error'] = (
                    f'No {LOOKUP_TABLE} user has {LOOKUP_REF_COLUMN} = '
                    f"'{DEFAULT_OPERATOR_Z_REF}'; it is the default contact for "
                    f'{SOURCE_TABLE}.{SOURCE_COLUMN} and for {FALLBACK_VARIABLE}.'
                )
                customer_logger.error(result['error'])
                return result

            default_id, default_username = default_contact
            fallback = f'{default_id} ({default_username})'
            result['fallback_contact'] = fallback

            variable_id = self._fallback_contact_id(processor)
            if variable_id != default_id:
                customer_logger.warning(
                    f'{FALLBACK_VARIABLE} resolved to '
                    f'{service.describe_contact(variable_id)}, not the '
                    f"{LOOKUP_REF_COLUMN} '{DEFAULT_OPERATOR_Z_REF}' contact {fallback}. "
                    'Unmatched SMS, email, document, letter and note operators will go '
                    'to the former; check migration_variables.json.'
                )

            summary = service.summarise_resolution(
                service.read_account_operator_resolution()
            )
            result['resolved_codes'] = summary['matched']
            result['ambiguous_contacts'] = summary['ambiguous']
            result['unresolved_operator_codes'] = summary['defaulted']

            rows_updated = service.assign_account_operator_contacts(default_id)
            result['rows_updated'] = rows_updated
            result['rows_updated_by_table'] = {
                f'{SOURCE_TABLE}.{TARGET_COLUMN}': rows_updated
            }

            customer_logger.info(
                f'Assigned {SOURCE_TABLE}.{TARGET_COLUMN} from {SOURCE_COLUMN}: '
                f'{rows_updated} row(s), '
                f"{summary['matched']} code(s) matched by {LOOKUP_TABLE}."
                f'{LOOKUP_REF_COLUMN}, {len(summary["defaulted"])} defaulted to '
                f'{fallback}'
            )

            if summary['ambiguous']:
                customer_logger.warning(
                    f'Operator codes held as {LOOKUP_REF_COLUMN} by more than one user; '
                    'the active contact with the lowest ContactID wins: '
                    + ', '.join(summary['ambiguous'])
                )

            if summary['defaulted']:
                customer_logger.warning(
                    f"{len(summary['defaulted'])} operator code(s) match no "
                    f'{LOOKUP_TABLE}.{LOOKUP_REF_COLUMN}; their accounts go to '
                    f'{fallback}. Busiest first: '
                    + self._summarise(summary['defaulted'])
                )

            result['status_message'] = self._status_message(
                summary['defaulted'], summary['ambiguous'], fallback
            )
            result['success'] = True
            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to map operator codes: {e}')
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
            # Not re-sorted: the service ordered these busiest first.
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
                f'Found {len(unresolved_operator_codes)} account operator code(s) '
                f'that match no {LOOKUP_TABLE}.{LOOKUP_REF_COLUMN}; their accounts go '
                f'to {fallback}. Set the user\'s {LOOKUP_REF_COLUMN} in {LOOKUP_TABLE} '
                'for any that should be attributed to someone else.'
            )

        return {
            'status_message': status_message,
            'unresolved_contacts': unresolved_contacts,
            'ambiguous_contacts': ambiguous_contacts,
            'unresolved_operator_codes': unresolved_operator_codes,
        }

    def describe_fallback_contact(self, processor: Any) -> str:
        """'150849 (temoului_soro@...)' - the contact unmatched operator codes go to."""
        service = self._ensure_operator_contact_service(processor)
        default_contact = service.resolve_default_contact()
        if default_contact is None:
            return f"none ({LOOKUP_REF_COLUMN} '{DEFAULT_OPERATOR_Z_REF}' not found)"
        return f'{default_contact[0]} ({default_contact[1]})'

    @staticmethod
    def _status_message(
        unresolved_operator_codes: List[str],
        ambiguous_contacts: List[str],
        fallback: str,
    ) -> str:
        if unresolved_operator_codes:
            return (
                f'{len(unresolved_operator_codes)} operator code(s) defaulting to '
                f'ContactID {fallback}: '
                + CustomerOperatorContactWorkflowService._summarise(
                    unresolved_operator_codes
                )
            )
        if ambiguous_contacts:
            return (
                f'All operator codes match a {LOOKUP_REF_COLUMN}; resolved by '
                'tie-break: ' + ', '.join(ambiguous_contacts)
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

    def get_unresolved_operator_codes_from_db(self, processor: Any) -> List[str]:
        service = self._ensure_operator_contact_service(processor)
        return service.get_unresolved_operator_codes_from_db()
