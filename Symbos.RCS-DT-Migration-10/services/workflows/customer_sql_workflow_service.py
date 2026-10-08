import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from DT_query_processor import SQLMigrationManager
from interaction import GATE_SQL
from phase_timing import get_timer


def assign_files_to_tables(tables, execution_results) -> Dict[str, list]:
    """Map each executed SQL file to the one metrics table it writes.

    A file's name (sequence and _READY stripped, e.g. 'tblentry_notes') belongs
    to the longest table name it starts with, followed by '_' or nothing, with
    an optional plural 's' ('tblcosts' -> tblCost). So 'tblcontactdetail_x' is
    tblContactDetail, not tblContact, and 'tblaccount_contact_x' is
    tblAccount_Contact, not tblAccount. Files matching no table are left out.
    """
    by_length = sorted(tables, key=len, reverse=True)
    patterns = [(t, re.compile(rf'^{re.escape(t.lower())}s?(_|$)')) for t in by_length]
    assigned: Dict[str, list] = {t: [] for t in tables}
    for result in execution_results:
        name = str(result.get('table_name', '')).lower()
        for table, pattern in patterns:
            if pattern.match(name):
                assigned[table].append(result)
                break
    return assigned


class CustomerSQLWorkflowService:
    """Coordinates customer SQL migration orchestration and result aggregation."""

    def execute_mixed_sql_methods(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        customer_paths: dict,
        staging_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        customer_logger.info(f"{'='*60}")
        customer_logger.info(f"STARTING MIXED SQL EXECUTION FOR CUSTOMER [{db}] {customer_code}")
        customer_logger.info('Files 1-77: SQLAlchemy | File 78: SQLCMD')
        customer_logger.info(f"{'='*60}")

        try:
            if not self.initialize_sql_manager_step(processor, customer_code, db, customer_logger):
                return self.create_sql_failure_result(customer_code, db, customer_paths, 'initialization_failed')

            # Each mapping step is an update plus its check; lap() closes one
            # step and opens the next without re-indenting the whole sequence.
            timer = get_timer(processor)

            # Staging disables its nonclustered indexes for the load and rebuilds
            # them after. A run that died in between leaves them off, and these
            # queries depend on them, so make sure before anything reads staging.
            with timer.section('sql.index_guard'):
                try:
                    rebuilt = processor.staging_processor.rebuild_staging_indexes()
                    if rebuilt:
                        customer_logger.warning(
                            f'{rebuilt} staging index(es) were still disabled and have '
                            'been rebuilt before the SQL phase')
                except Exception as e:
                    return self.create_sql_failure_result(
                        customer_code, db, customer_paths, 'staging_indexes_disabled', str(e))

            timer.restart_lap()

            status_update_result = processor.update_rc_account_extract_ma_status(customer_logger)
            if not status_update_result.get('success', False):
                failure_result = self.create_sql_failure_result(
                    customer_code,
                    db,
                    customer_paths,
                    'ma_status_update_failed',
                    status_update_result.get('error', 'Unknown error'),
                )
                failure_result['ma_status_update'] = status_update_result
                return failure_result

            status_check_result = processor._check_status_codes_step(
                customer_code,
                db,
                customer_logger,
                status_update_result,
            )

            # customer_logger has a console handler, so these still show in the
            # terminal - they now land in the processing log as well.
            customer_logger.info(f"{'='*50}")
            customer_logger.info(f'STATUS CHECK COMPLETE FOR CUSTOMER: [{db}] {customer_code}')
            customer_logger.info(f"Result: {status_check_result.get('status_message', 'N/A')}")
            invalid_statuses = status_check_result.get('invalid_statuses', []) or []
            customer_logger.info(f'Invalid statuses found: {len(invalid_statuses)}')
            if invalid_statuses:
                customer_logger.warning(f'Invalid status codes: {invalid_statuses}')
            customer_logger.info(f"{'='*50}")
            timer.lap('mapping.status')

            bank_method_update_result = processor.update_payment_methods(customer_logger)
            if not bank_method_update_result.get('success', False):
                failure_result = self.create_sql_failure_result(
                    customer_code,
                    db,
                    customer_paths,
                    'bank_transaction_method_update_failed',
                    bank_method_update_result.get('error', 'Unknown error'),
                )
                failure_result['ma_status_update'] = status_update_result
                failure_result['status_check'] = status_check_result
                failure_result['bank_transaction_method_update'] = bank_method_update_result
                return failure_result

            bank_method_check_result = processor._check_bank_transaction_methods_step(
                customer_code,
                db,
                customer_logger,
                bank_method_update_result,
            )

            customer_logger.info(f"{'='*50}")
            customer_logger.info(
                f'BANK TRANSACTION METHOD CHECK COMPLETE FOR CUSTOMER: [{db}] {customer_code}')
            customer_logger.info(f"Result: {bank_method_check_result.get('status_message', 'N/A')}")
            invalid_methods = bank_method_check_result.get('invalid_methods', []) or []
            customer_logger.info(f'Invalid methods found: {len(invalid_methods)}')
            if invalid_methods:
                customer_logger.warning(f'Invalid bank transaction methods: {invalid_methods}')
            customer_logger.info(f"{'='*50}")
            timer.lap('mapping.bank_transaction_method')

            arrangement_type_update_result = processor.update_arrangement_types(customer_logger)
            if not arrangement_type_update_result.get('success', False):
                failure_result = self.create_sql_failure_result(
                    customer_code,
                    db,
                    customer_paths,
                    'arrangement_type_update_failed',
                    arrangement_type_update_result.get('error', 'Unknown error'),
                )
                failure_result['ma_status_update'] = status_update_result
                failure_result['status_check'] = status_check_result
                failure_result['bank_transaction_method_update'] = bank_method_update_result
                failure_result['bank_transaction_method_check'] = bank_method_check_result
                failure_result['arrangement_type_update'] = arrangement_type_update_result
                return failure_result

            arrangement_type_check_result = processor._check_arrangement_types_step(
                customer_code,
                db,
                customer_logger,
                arrangement_type_update_result,
            )

            customer_logger.info(f"{'='*50}")
            customer_logger.info(
                f'ARRANGEMENT TYPE CHECK COMPLETE FOR CUSTOMER: [{db}] {customer_code}')
            customer_logger.info(f"Result: {arrangement_type_check_result.get('status_message', 'N/A')}")
            invalid_types = arrangement_type_check_result.get('invalid_types', []) or []
            customer_logger.info(f'Invalid types found: {len(invalid_types)}')
            if invalid_types:
                customer_logger.warning(f'Invalid arrangement types: {invalid_types}')
            customer_logger.info(
                f"Rows defaulted to '{arrangement_type_update_result.get('default_label', 'n/a')}': "
                f"{arrangement_type_update_result.get('rows_defaulted', 0)}")
            customer_logger.info(f"{'='*50}")
            timer.lap('mapping.arrangement_type')

            frequency_update_result = processor.update_frequencies(customer_logger)
            if not frequency_update_result.get('success', False):
                failure_result = self.create_sql_failure_result(
                    customer_code,
                    db,
                    customer_paths,
                    'frequency_update_failed',
                    frequency_update_result.get('error', 'Unknown error'),
                )
                failure_result['ma_status_update'] = status_update_result
                failure_result['status_check'] = status_check_result
                failure_result['bank_transaction_method_update'] = bank_method_update_result
                failure_result['bank_transaction_method_check'] = bank_method_check_result
                failure_result['arrangement_type_update'] = arrangement_type_update_result
                failure_result['arrangement_type_check'] = arrangement_type_check_result
                failure_result['frequency_update'] = frequency_update_result
                return failure_result

            frequency_check_result = processor._check_frequencies_step(
                customer_code,
                db,
                customer_logger,
                frequency_update_result,
            )

            customer_logger.info(f"{'='*50}")
            customer_logger.info(
                f'FREQUENCY CHECK COMPLETE FOR CUSTOMER: [{db}] {customer_code}')
            customer_logger.info(f"Result: {frequency_check_result.get('status_message', 'N/A')}")
            invalid_frequencies = frequency_check_result.get('invalid_frequencies', []) or []
            customer_logger.info(f'Invalid frequencies found: {len(invalid_frequencies)}')
            if invalid_frequencies:
                customer_logger.warning(
                    f'Invalid frequencies (these will migrate as a NULL FrequencyID): '
                    f'{invalid_frequencies}')
            customer_logger.info(f"{'='*50}")
            timer.lap('mapping.frequency')

            related_party_type_update_result = processor.update_related_party_types(
                customer_logger)
            if not related_party_type_update_result.get('success', False):
                failure_result = self.create_sql_failure_result(
                    customer_code,
                    db,
                    customer_paths,
                    'related_party_type_update_failed',
                    related_party_type_update_result.get('error', 'Unknown error'),
                )
                failure_result['ma_status_update'] = status_update_result
                failure_result['status_check'] = status_check_result
                failure_result['bank_transaction_method_update'] = bank_method_update_result
                failure_result['bank_transaction_method_check'] = bank_method_check_result
                failure_result['arrangement_type_update'] = arrangement_type_update_result
                failure_result['arrangement_type_check'] = arrangement_type_check_result
                failure_result['frequency_update'] = frequency_update_result
                failure_result['frequency_check'] = frequency_check_result
                failure_result['related_party_type_update'] = related_party_type_update_result
                return failure_result

            related_party_type_check_result = processor._check_related_party_types_step(
                customer_code,
                db,
                customer_logger,
                related_party_type_update_result,
            )

            customer_logger.info(f"{'='*50}")
            customer_logger.info(
                f'RELATED PARTY TYPE CHECK COMPLETE FOR CUSTOMER: [{db}] {customer_code}')
            customer_logger.info(
                f"Result: {related_party_type_check_result.get('status_message', 'N/A')}")
            invalid_rp_types = related_party_type_check_result.get('invalid_types', []) or []
            customer_logger.info(f'Invalid related party types found: {len(invalid_rp_types)}')
            if invalid_rp_types:
                customer_logger.warning(f'Invalid related party types: {invalid_rp_types}')
            customer_logger.info(
                f"Rows swept to '{related_party_type_update_result.get('fallback_label', 'n/a')}': "
                f"{related_party_type_update_result.get('rows_defaulted', 0)}")
            customer_logger.info(f"{'='*50}")
            timer.lap('mapping.related_party_type')

            incident_type_update_result = processor.update_incident_types(customer_logger)
            if not incident_type_update_result.get('success', False):
                failure_result = self.create_sql_failure_result(
                    customer_code,
                    db,
                    customer_paths,
                    'incident_type_update_failed',
                    incident_type_update_result.get('error', 'Unknown error'),
                )
                failure_result['ma_status_update'] = status_update_result
                failure_result['status_check'] = status_check_result
                failure_result['bank_transaction_method_update'] = bank_method_update_result
                failure_result['bank_transaction_method_check'] = bank_method_check_result
                failure_result['arrangement_type_update'] = arrangement_type_update_result
                failure_result['arrangement_type_check'] = arrangement_type_check_result
                failure_result['frequency_update'] = frequency_update_result
                failure_result['frequency_check'] = frequency_check_result
                failure_result['related_party_type_update'] = related_party_type_update_result
                failure_result['related_party_type_check'] = related_party_type_check_result
                failure_result['incident_type_update'] = incident_type_update_result
                return failure_result

            incident_type_check_result = processor._check_incident_types_step(
                customer_code,
                db,
                customer_logger,
                incident_type_update_result,
            )

            customer_logger.info(f"{'='*50}")
            customer_logger.info(
                f'INCIDENT TYPE CHECK COMPLETE FOR CUSTOMER: [{db}] {customer_code}')
            customer_logger.info(
                f"Result: {incident_type_check_result.get('status_message', 'N/A')}")
            invalid_incident_types = incident_type_check_result.get('invalid_types', []) or []
            customer_logger.info(
                f'Invalid incident types found: {len(invalid_incident_types)}')
            if invalid_incident_types:
                customer_logger.warning(
                    'Cause descriptions with no tblIncidentType match (these migrate as '
                    f'a NULL IncidentTypeID): {invalid_incident_types}')
            customer_logger.info(
                f"Rows swept to the default '{incident_type_update_result.get('default_label', 'n/a')}': "
                f"{incident_type_update_result.get('rows_defaulted', 0)}")
            customer_logger.info(f"{'='*50}")
            timer.lap('mapping.incident_type')

            closure_reason_update_result = processor.update_closure_reasons(customer_logger)
            if not closure_reason_update_result.get('success', False):
                failure_result = self.create_sql_failure_result(
                    customer_code,
                    db,
                    customer_paths,
                    'closure_reason_update_failed',
                    closure_reason_update_result.get('error', 'Unknown error'),
                )
                failure_result['ma_status_update'] = status_update_result
                failure_result['status_check'] = status_check_result
                failure_result['bank_transaction_method_update'] = bank_method_update_result
                failure_result['bank_transaction_method_check'] = bank_method_check_result
                failure_result['arrangement_type_update'] = arrangement_type_update_result
                failure_result['arrangement_type_check'] = arrangement_type_check_result
                failure_result['frequency_update'] = frequency_update_result
                failure_result['frequency_check'] = frequency_check_result
                failure_result['related_party_type_update'] = related_party_type_update_result
                failure_result['related_party_type_check'] = related_party_type_check_result
                failure_result['incident_type_update'] = incident_type_update_result
                failure_result['incident_type_check'] = incident_type_check_result
                failure_result['closure_reason_update'] = closure_reason_update_result
                return failure_result

            closure_reason_check_result = processor._check_closure_reasons_step(
                customer_code,
                db,
                customer_logger,
                closure_reason_update_result,
            )

            customer_logger.info(f"{'='*50}")
            customer_logger.info(
                f'CLOSURE REASON CHECK COMPLETE FOR CUSTOMER: [{db}] {customer_code}')
            customer_logger.info(f"Result: {closure_reason_check_result.get('status_message', 'N/A')}")
            defaulted_values = closure_reason_check_result.get('defaulted_values', []) or []
            customer_logger.info(f'Unmapped values defaulted: {len(defaulted_values)}')
            if defaulted_values:
                customer_logger.warning(f'Unmapped closure reasons defaulted: {defaulted_values}')
            customer_logger.info(
                f"Rows defaulted to '{closure_reason_update_result.get('fallback_label', 'n/a')}': "
                f"{closure_reason_update_result.get('rows_defaulted', 0)}")
            customer_logger.info(f"{'='*50}")
            timer.lap('mapping.closure_reason')

            cost_update_result = processor.update_costs(customer_logger)
            if not cost_update_result.get('success', False):
                failure_result = self.create_sql_failure_result(
                    customer_code,
                    db,
                    customer_paths,
                    'cost_update_failed',
                    cost_update_result.get('error', 'Unknown error'),
                )
                failure_result['ma_status_update'] = status_update_result
                failure_result['status_check'] = status_check_result
                failure_result['bank_transaction_method_update'] = bank_method_update_result
                failure_result['bank_transaction_method_check'] = bank_method_check_result
                failure_result['arrangement_type_update'] = arrangement_type_update_result
                failure_result['arrangement_type_check'] = arrangement_type_check_result
                failure_result['frequency_update'] = frequency_update_result
                failure_result['frequency_check'] = frequency_check_result
                failure_result['related_party_type_update'] = related_party_type_update_result
                failure_result['related_party_type_check'] = related_party_type_check_result
                failure_result['incident_type_update'] = incident_type_update_result
                failure_result['incident_type_check'] = incident_type_check_result
                failure_result['closure_reason_update'] = closure_reason_update_result
                failure_result['closure_reason_check'] = closure_reason_check_result
                failure_result['cost_update'] = cost_update_result
                return failure_result

            cost_check_result = processor._check_costs_step(
                customer_code,
                db,
                customer_logger,
                cost_update_result,
            )

            customer_logger.info(f"{'='*50}")
            customer_logger.info(
                f'COST CODE CHECK COMPLETE FOR CUSTOMER: [{db}] {customer_code}')
            customer_logger.info(f"Result: {cost_check_result.get('status_message', 'N/A')}")
            customer_logger.info(
                'Charge rows staged for 51.tblcosts.sql: '
                f"{cost_update_result.get('rows_inserted', 0)}")
            unmapped_cost_codes = cost_check_result.get('unmapped_charged_codes', []) or []
            if unmapped_cost_codes:
                customer_logger.warning(f'Unmapped charged cost codes: {unmapped_cost_codes}')
            customer_logger.info(f"{'='*50}")
            timer.lap('mapping.cost')

            operator_contact_update_result = processor.update_operator_contacts(customer_logger)
            if not operator_contact_update_result.get('success', False):
                failure_result = self.create_sql_failure_result(
                    customer_code,
                    db,
                    customer_paths,
                    'operator_contact_update_failed',
                    operator_contact_update_result.get('error', 'Unknown error'),
                )
                failure_result['ma_status_update'] = status_update_result
                failure_result['status_check'] = status_check_result
                failure_result['bank_transaction_method_update'] = bank_method_update_result
                failure_result['bank_transaction_method_check'] = bank_method_check_result
                failure_result['arrangement_type_update'] = arrangement_type_update_result
                failure_result['arrangement_type_check'] = arrangement_type_check_result
                failure_result['frequency_update'] = frequency_update_result
                failure_result['frequency_check'] = frequency_check_result
                failure_result['related_party_type_update'] = related_party_type_update_result
                failure_result['related_party_type_check'] = related_party_type_check_result
                failure_result['incident_type_update'] = incident_type_update_result
                failure_result['incident_type_check'] = incident_type_check_result
                failure_result['closure_reason_update'] = closure_reason_update_result
                failure_result['closure_reason_check'] = closure_reason_check_result
                failure_result['cost_update'] = cost_update_result
                failure_result['cost_check'] = cost_check_result
                failure_result['operator_contact_update'] = operator_contact_update_result
                return failure_result

            operator_contact_check_result = processor._check_operator_contacts_step(
                customer_code,
                db,
                customer_logger,
                operator_contact_update_result,
            )

            customer_logger.info(f"{'='*50}")
            customer_logger.info(
                f'OPERATOR CODE CHECK COMPLETE FOR CUSTOMER: [{db}] {customer_code}')
            customer_logger.info(f"Result: {operator_contact_check_result.get('status_message', 'N/A')}")
            customer_logger.info(
                'Operator_ContactID assigned in RC_ACCOUNT_EXTRACT (file 01): '
                f"{operator_contact_update_result.get('rows_updated', 0)}")
            # Counted rather than listed, unlike the cost codes above. Defaulted
            # operator codes are not a fault - the accounts go to the default (TEMS)
            # contact and nothing is lost. The busiest are named in the check's own
            # warning and in its status message.
            unresolved_operator_codes = (
                operator_contact_check_result.get('unresolved_operator_codes', [])
                or [])
            customer_logger.info(
                'Operator codes taking the default contact '
                f"({operator_contact_update_result.get('fallback_contact', 'n/a')}): "
                f'{len(unresolved_operator_codes)}')
            customer_logger.info(f"{'='*50}")
            timer.lap('mapping.operator_contact')

            # Hardship: Status and Hardship_Cause are rewritten in place to the canonical
            # tblHardshipStatus / tblHardshipCause labels before 79.tblHardship.sql joins on
            # them, the same way MA_Status and Reason_Closed are handled above. Both steps
            # no-op when this customer has no RC_HARDSHIP_EXTRACT.
            hardship_status_update_result = processor.update_hardship_statuses(customer_logger)
            if not hardship_status_update_result.get('success', False):
                failure_result = self.create_sql_failure_result(
                    customer_code,
                    db,
                    customer_paths,
                    'hardship_status_update_failed',
                    hardship_status_update_result.get('error', 'Unknown error'),
                )
                failure_result['ma_status_update'] = status_update_result
                failure_result['status_check'] = status_check_result
                failure_result['bank_transaction_method_update'] = bank_method_update_result
                failure_result['bank_transaction_method_check'] = bank_method_check_result
                failure_result['arrangement_type_update'] = arrangement_type_update_result
                failure_result['arrangement_type_check'] = arrangement_type_check_result
                failure_result['frequency_update'] = frequency_update_result
                failure_result['frequency_check'] = frequency_check_result
                failure_result['related_party_type_update'] = related_party_type_update_result
                failure_result['related_party_type_check'] = related_party_type_check_result
                failure_result['incident_type_update'] = incident_type_update_result
                failure_result['incident_type_check'] = incident_type_check_result
                failure_result['closure_reason_update'] = closure_reason_update_result
                failure_result['closure_reason_check'] = closure_reason_check_result
                failure_result['cost_update'] = cost_update_result
                failure_result['cost_check'] = cost_check_result
                failure_result['operator_contact_update'] = operator_contact_update_result
                failure_result['operator_contact_check'] = operator_contact_check_result
                failure_result['hardship_status_update'] = hardship_status_update_result
                return failure_result

            hardship_status_check_result = processor._check_hardship_statuses_step(
                customer_code,
                db,
                customer_logger,
                hardship_status_update_result,
            )

            customer_logger.info(f"{'='*50}")
            customer_logger.info(
                f'HARDSHIP STATUS CHECK COMPLETE FOR CUSTOMER: [{db}] {customer_code}')
            customer_logger.info(f"Result: {hardship_status_check_result.get('status_message', 'N/A')}")
            invalid_hardship_statuses = hardship_status_check_result.get('invalid_statuses', []) or []
            customer_logger.info(f'Invalid hardship status values found: {len(invalid_hardship_statuses)}')
            if invalid_hardship_statuses:
                customer_logger.warning(f'Invalid hardship status values: {invalid_hardship_statuses}')
            customer_logger.info(f"{'='*50}")
            timer.lap('mapping.hardship_status')

            hardship_cause_update_result = processor.update_hardship_causes(customer_logger)
            if not hardship_cause_update_result.get('success', False):
                failure_result = self.create_sql_failure_result(
                    customer_code,
                    db,
                    customer_paths,
                    'hardship_cause_update_failed',
                    hardship_cause_update_result.get('error', 'Unknown error'),
                )
                failure_result['ma_status_update'] = status_update_result
                failure_result['status_check'] = status_check_result
                failure_result['bank_transaction_method_update'] = bank_method_update_result
                failure_result['bank_transaction_method_check'] = bank_method_check_result
                failure_result['arrangement_type_update'] = arrangement_type_update_result
                failure_result['arrangement_type_check'] = arrangement_type_check_result
                failure_result['frequency_update'] = frequency_update_result
                failure_result['frequency_check'] = frequency_check_result
                failure_result['related_party_type_update'] = related_party_type_update_result
                failure_result['related_party_type_check'] = related_party_type_check_result
                failure_result['incident_type_update'] = incident_type_update_result
                failure_result['incident_type_check'] = incident_type_check_result
                failure_result['closure_reason_update'] = closure_reason_update_result
                failure_result['closure_reason_check'] = closure_reason_check_result
                failure_result['cost_update'] = cost_update_result
                failure_result['cost_check'] = cost_check_result
                failure_result['operator_contact_update'] = operator_contact_update_result
                failure_result['operator_contact_check'] = operator_contact_check_result
                failure_result['hardship_status_update'] = hardship_status_update_result
                failure_result['hardship_status_check'] = hardship_status_check_result
                failure_result['hardship_cause_update'] = hardship_cause_update_result
                return failure_result

            hardship_cause_check_result = processor._check_hardship_causes_step(
                customer_code,
                db,
                customer_logger,
                hardship_cause_update_result,
            )

            customer_logger.info(f"{'='*50}")
            customer_logger.info(
                f'HARDSHIP CAUSE CHECK COMPLETE FOR CUSTOMER: [{db}] {customer_code}')
            customer_logger.info(f"Result: {hardship_cause_check_result.get('status_message', 'N/A')}")
            invalid_hardship_causes = hardship_cause_check_result.get('invalid_causes', []) or []
            customer_logger.info(f'Invalid hardship cause values found: {len(invalid_hardship_causes)}')
            if invalid_hardship_causes:
                customer_logger.warning(f'Invalid hardship cause values: {invalid_hardship_causes}')
            customer_logger.info(f"{'='*50}")
            timer.lap('mapping.hardship_cause')

            pending_moves = getattr(processor, 'pending_file_moves', []) or []
            pending_file_count = sum(len(entry['files']) for entry in pending_moves)
            customer_logger.info(f'Files awaiting move (nothing moved yet): {pending_file_count}')

            if not processor.approval_policy.confirm(
                    'Continue after status, payment method, arrangement type, '
                    'frequency, related party type, incident type, closure '
                    'reason, cost code, operator code, hardship status and '
                    'hardship cause checks?',
                    GATE_SQL):
                customer_logger.info(
                    'Not approved after status check; stopping customer. '
                    f'{pending_file_count} file(s) left in place for a re-run'
                )
                failure_result = self.create_sql_failure_result(
                    customer_code,
                    db,
                    customer_paths,
                    'user_stopped_after_status_check',
                )
                failure_result['ma_status_update'] = status_update_result
                failure_result['status_check'] = status_check_result
                failure_result['bank_transaction_method_update'] = bank_method_update_result
                failure_result['bank_transaction_method_check'] = bank_method_check_result
                failure_result['arrangement_type_update'] = arrangement_type_update_result
                failure_result['arrangement_type_check'] = arrangement_type_check_result
                failure_result['frequency_update'] = frequency_update_result
                failure_result['frequency_check'] = frequency_check_result
                failure_result['related_party_type_update'] = related_party_type_update_result
                failure_result['related_party_type_check'] = related_party_type_check_result
                failure_result['incident_type_update'] = incident_type_update_result
                failure_result['incident_type_check'] = incident_type_check_result
                failure_result['closure_reason_update'] = closure_reason_update_result
                failure_result['closure_reason_check'] = closure_reason_check_result
                failure_result['cost_update'] = cost_update_result
                failure_result['cost_check'] = cost_check_result
                failure_result['operator_contact_update'] = operator_contact_update_result
                failure_result['operator_contact_check'] = operator_contact_check_result
                failure_result['hardship_status_update'] = hardship_status_update_result
                failure_result['hardship_status_check'] = hardship_status_check_result
                failure_result['hardship_cause_update'] = hardship_cause_update_result
                failure_result['hardship_cause_check'] = hardship_cause_check_result
                return failure_result

            # All mapping checks are confirmed; only now do the staged files move
            # out of the source folder.
            with timer.section('file_moves'):
                file_move_summary = processor.flush_pending_file_moves(customer_logger)

            with timer.section('sql.prepare_export'):
                prepared_sql = self.prepare_sql_files_step(processor, customer_code, db, customer_logger)
                sql_export_path = None
                if prepared_sql:
                    sql_export_path = self.export_sql_files_step(
                        processor,
                        customer_code,
                        db,
                        customer_logger,
                        customer_paths,
                        prepared_sql,
                    )
            if not prepared_sql:
                return self.create_sql_failure_result(customer_code, db, customer_paths, 'sql_preparation_failed')
            if not sql_export_path:
                return self.create_sql_failure_result(customer_code, db, customer_paths, 'sql_export_failed')

            with timer.section('sql.files'):
                mixed_execution_results = self.execute_sql_files_step(
                    processor,
                    customer_code,
                    db,
                    customer_logger,
                    sql_export_path,
                )

            # Post-batch, unlike the other mapping transforms: tblAddress.State is only
            # populated once files 37-43 have run, so the free-text states that
            # 44.tbladdress_Assign_StateID.sql could not match can only be resolved now.
            # A failure here leaves StateID NULL, exactly as before this step existed, so
            # it is reported rather than treated as a failed migration.
            with timer.section('sql.state_update'):
                state_update_result = processor.update_states(customer_logger)
                state_check_result = processor._check_states_step(
                    customer_code,
                    db,
                    customer_logger,
                    state_update_result,
                )

            customer_logger.info(f"{'='*50}")
            customer_logger.info(
                f'STATE CHECK COMPLETE FOR CUSTOMER: [{db}] {customer_code}')
            customer_logger.info(f"Result: {state_check_result.get('status_message', 'N/A')}")
            customer_logger.info(
                'Addresses resolved that file 44 left NULL: '
                f"{state_update_result.get('rows_updated', 0)}")
            invalid_states = state_check_result.get('invalid_states', []) or []
            if invalid_states:
                customer_logger.warning(
                    f'Address states still carrying a NULL StateID: {invalid_states}')
            if not state_update_result.get('success', False):
                customer_logger.error(
                    'State normalization did not run: '
                    f"{state_update_result.get('error', 'Unknown error')}")
            customer_logger.info(f"{'='*50}")

            with timer.section('sql.metrics'):
                migration_stats = self.collect_migration_metrics_step(
                    processor,
                    customer_code,
                    db,
                    customer_logger,
                )

            final_result = self.process_sql_execution_results_step(
                processor,
                customer_code,
                db,
                customer_logger,
                mixed_execution_results,
                migration_stats,
                sql_export_path,
                customer_paths,
            )
            final_result['ma_status_update'] = status_update_result
            final_result['status_check'] = status_check_result
            final_result['bank_transaction_method_update'] = bank_method_update_result
            final_result['bank_transaction_method_check'] = bank_method_check_result
            final_result['arrangement_type_update'] = arrangement_type_update_result
            final_result['arrangement_type_check'] = arrangement_type_check_result
            final_result['frequency_update'] = frequency_update_result
            final_result['frequency_check'] = frequency_check_result
            final_result['related_party_type_update'] = related_party_type_update_result
            final_result['related_party_type_check'] = related_party_type_check_result
            final_result['incident_type_update'] = incident_type_update_result
            final_result['incident_type_check'] = incident_type_check_result
            final_result['closure_reason_update'] = closure_reason_update_result
            final_result['closure_reason_check'] = closure_reason_check_result
            final_result['cost_update'] = cost_update_result
            final_result['cost_check'] = cost_check_result
            final_result['operator_contact_update'] = operator_contact_update_result
            final_result['operator_contact_check'] = operator_contact_check_result
            final_result['hardship_status_update'] = hardship_status_update_result
            final_result['hardship_status_check'] = hardship_status_check_result
            final_result['hardship_cause_update'] = hardship_cause_update_result
            final_result['hardship_cause_check'] = hardship_cause_check_result
            final_result['state_update'] = state_update_result
            final_result['state_check'] = state_check_result
            final_result['files_moved'] = file_move_summary
            return final_result

        except Exception as e:
            customer_logger.error(
                f'Error during mixed SQL execution for [{db}] customer {customer_code}: '
                f'{type(e).__name__}: {e}',
                exc_info=True,
            )
            return self.create_sql_failure_result(customer_code, db, customer_paths, 'unexpected_error', str(e))

    def initialize_sql_manager_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
    ) -> bool:
        customer_logger.info('Step 1: Initializing SQL Migration Manager...')

        processor.sql_manager = SQLMigrationManager(
            environment=processor.environment,
            load_id=int(processor.current_load_id),
            session_id=processor.current_session_id,
            entity_id=processor.entity_id,
            shared_db_helper=processor.shared_db_helper,
            shared_config_parser=processor.config_parser,
            customer_code=customer_code,
            db_name=db,
            run_id=getattr(processor, 'run_id', None),
            resume_load_id=getattr(processor, 'resume_load_id', None),
        )

        if not processor.sql_manager.initialize():
            customer_logger.error('Failed to initialize SQL Migration Manager')
            return False

        return True

    def prepare_sql_files_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
    ) -> Dict[str, Any]:
        customer_logger.info('Step 3: Preparing SQL files with variable replacement...')

        prepared_sql = processor.sql_manager.prepare_sql_for_execution()
        ready_files = sum(1 for sql_info in prepared_sql.values() if sql_info.get('ready_for_execution', False))
        customer_logger.info(f'Prepared {len(prepared_sql)} files, {ready_files} ready for execution')

        return prepared_sql if ready_files > 0 else None

    def export_sql_files_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        customer_paths: dict,
        prepared_sql: Dict[str, Any],
    ) -> str:
        customer_logger.info('Step 4: Exporting SQL files to customer folder...')

        sql_export_path = customer_paths['executed_queries']
        customer_logger.info(f'Exporting SQL files to: {sql_export_path}')

        try:
            export_result = processor.sql_manager.export_prepared_sql(prepared_sql, str(sql_export_path))

            exported_files = export_result.get('exported_files', [])
            export_success = export_result.get('export_success', False)

            if not export_success or not exported_files:
                customer_logger.error('No files were exported successfully')
                return None

            customer_logger.info(f'Successfully exported {len(exported_files)} SQL files')
            return str(sql_export_path)

        except Exception as export_error:
            customer_logger.error(f'Failed to export SQL files: {export_error}')
            return None

    def execute_sql_files_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        sql_export_path: str,
    ) -> Dict[str, Any]:
        customer_logger.info('Step 5: Executing SQL files using mixed methods...')
        return processor._execute_mixed_sql_methods_internal(sql_export_path, customer_logger)

    def collect_migration_metrics_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
    ) -> Dict[str, Any]:
        customer_logger.info('Step 6: Collecting migration metrics...')
        return processor.sql_manager.collect_migration_metrics(
            processor.current_load_id,
            processor.current_session_id,
            customer_logger,
        )

    def process_sql_execution_results_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        mixed_execution_results: Dict[str, Any],
        migration_stats: Dict[str, Any],
        sql_export_path: str,
        customer_paths: dict,
    ) -> Dict[str, Any]:
        customer_logger.info('Step 7: Processing SQL execution results...')

        if migration_stats:
            financial_columns = processor.staging_processor.get_all_possible_financial_columns()
            financial_tables = self.get_financial_tables_from_metrics(processor, migration_stats)
            total_migration_rows = 0
            execution_results = mixed_execution_results.get('execution_results', {})
            metric_tables = [t for t in migration_stats.keys() if not t.startswith('_')]
            files_by_table = assign_files_to_tables(metric_tables, execution_results.values())
            executed = [r for r in execution_results.values() if r.get('executed')]
            window_start = min((r['start_time'] for r in executed if r.get('start_time')),
                               default=datetime.now())
            window_end = max((r['end_time'] for r in executed if r.get('end_time')),
                             default=datetime.now())

            for table_name, metrics in migration_stats.items():
                if table_name.startswith('_'):
                    continue

                rows_migrated = metrics.get('rows_inserted', 0)
                total_migration_rows += rows_migrated

                # Every SQL file that writes this table, summed: tblEntry is
                # three files, not just the first one a substring match found.
                # A table no file writes on its own (tblLoad, tblSession, the
                # notes fold, what 078 writes) gets 0s over the SQL window
                # rather than an even share of the total, which looked real.
                files = [r for r in files_by_table.get(table_name, []) if r.get('executed')]
                metrics_ok = metrics.get('query_successful', True)
                if files:
                    start_time = min(r.get('start_time') or window_start for r in files)
                    end_time = max(r.get('end_time') or window_end for r in files)
                    duration_seconds = sum(r.get('execution_time', 0) or 0 for r in files)
                    rows_per_second = rows_migrated / duration_seconds if duration_seconds > 0 else 0
                    errors = [str(r['error']) for r in files if r.get('error')]
                    success = metrics_ok and not errors
                    error_message = '; '.join(errors)
                else:
                    start_time, end_time = window_start, window_end
                    duration_seconds = 0
                    rows_per_second = 0
                    success = metrics_ok
                    error_message = ''

                migration_stat = {
                    'RunID': getattr(processor, 'run_id', None),
                    'Staging_LoadID': processor.staging_load_id,
                    'customer_code': customer_code,
                    'db': db,
                    'EntityID': processor.entity_id,
                    'user': processor.user,
                    'from_table': metrics.get('from_table'),
                    'table_name': f'DT_Migration_{table_name}',
                    'files_count': 0,
                    'csv_rows': 0,
                    'rows_inserted': rows_migrated,
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration_seconds': round(duration_seconds, 2),
                    'rows_per_second': round(rows_per_second, 0),
                    'success': success,
                    'error_message': error_message,
                    'Migration_LoadID': processor.current_load_id,
                    'Migration_SessionID': processor.current_session_id,
                }

                for col in financial_columns:
                    if table_name in financial_tables:
                        migration_stat[col] = financial_tables[table_name].get(col)
                    else:
                        migration_stat[col] = None

                processor.processing_stats.append(migration_stat)

                if not hasattr(processor, '_migration_processing_stats'):
                    processor._migration_processing_stats = []
                processor._migration_processing_stats.append(migration_stat)

            summary_metrics = migration_stats.get('_summary', {})

            all_start_times = [
                r.get('start_time')
                for r in execution_results.values()
                if r.get('start_time') and r.get('executed', False)
            ]
            all_end_times = [
                r.get('end_time')
                for r in execution_results.values()
                if r.get('end_time') and r.get('executed', False)
            ]

            if all_start_times and all_end_times:
                migration_start_time = min(all_start_times)
                migration_end_time = max(all_end_times)
                total_duration = (migration_end_time - migration_start_time).total_seconds()
            else:
                total_duration = mixed_execution_results.get('total_execution_time', 0)
                migration_start_time = datetime.now() - pd.Timedelta(seconds=total_duration)
                migration_end_time = datetime.now()

            aggregated_financial = {}
            for col in financial_columns:
                total = 0.0
                has_data = False

                for _, financial_data in financial_tables.items():
                    value = financial_data.get(col)
                    if value is not None and value != 0.0:
                        total += float(value)
                        has_data = True

                aggregated_financial[col] = total if has_data else None

            migration_summary_stat = {
                'RunID': getattr(processor, 'run_id', None),
                'Staging_LoadID': processor.staging_load_id,
                'customer_code': customer_code,
                'db': db,
                'EntityID': processor.entity_id,
                'user': processor.user,
                'from_table': 'Multiple',
                'table_name': 'DT_Migration_Summary',
                'files_count': 0,
                'csv_rows': 0,
                'rows_inserted': summary_metrics.get('total_records_migrated', total_migration_rows),
                'start_time': migration_start_time,
                'end_time': migration_end_time,
                'duration_seconds': round(total_duration, 2),
                'rows_per_second': round(total_migration_rows / total_duration if total_duration > 0 else 0, 0),
                'success': summary_metrics.get('failed_queries', 0) == 0,
                'error_message': (
                    f"Failed queries: {summary_metrics.get('failed_queries', 0)}"
                    if summary_metrics.get('failed_queries', 0) > 0
                    else ''
                ),
                'Migration_LoadID': processor.current_load_id,
                'Migration_SessionID': processor.current_session_id,
            }

            for col in financial_columns:
                migration_summary_stat[col] = aggregated_financial.get(col)

            processor._migration_processing_stats.append(migration_summary_stat)
            customer_logger.info(
                f'Migration metrics processed: {len(metric_tables)} tables, {total_migration_rows:,} total records'
            )

        else:
            customer_logger.warning('No migration metrics collected - creating basic summary')
            if not hasattr(processor, '_migration_processing_stats'):
                processor._migration_processing_stats = []

            fallback_stat = {
                'RunID': getattr(processor, 'run_id', None),
                'Staging_LoadID': processor.staging_load_id,
                'customer_code': customer_code,
                'db': db,
                'EntityID': processor.entity_id,
                'user': processor.user,
                'from_table': None,
                'table_name': 'DT_Migration_NoMetrics',
                'files_count': 0,
                'csv_rows': 0,
                'rows_inserted': 0,
                'start_time': datetime.now(),
                'end_time': datetime.now(),
                'duration_seconds': 0,
                'rows_per_second': 0,
                'success': True,
                'error_message': 'Migration completed but no metrics collected',
                'Migration_LoadID': processor.current_load_id,
                'Migration_SessionID': processor.current_session_id,
            }

            financial_columns = processor.staging_processor.get_all_possible_financial_columns()
            for col in financial_columns:
                fallback_stat[col] = None

            processor._migration_processing_stats.append(fallback_stat)

        all_results = mixed_execution_results.get('execution_results', {})
        sql_executed = sum(1 for r in all_results.values() if r.get('executed', False) and not r.get('error'))
        sql_failed = sum(
            1
            for r in all_results.values()
            if r.get('error') or (not r.get('executed', False) and not r.get('skipped', False))
        )

        actual_migration_rows = 0
        for table_name, metrics in migration_stats.items():
            if not table_name.startswith('_'):
                actual_migration_rows += metrics.get('rows_inserted', 0)

        if actual_migration_rows == 0 and '_summary' in migration_stats:
            actual_migration_rows = migration_stats['_summary'].get('total_records_migrated', 0)

        customer_logger.info(f"\n{'='*60}")
        customer_logger.info(f'MIXED SQL EXECUTION COMPLETED FOR CUSTOMER [{db}] {customer_code}')
        customer_logger.info(f"{'='*60}")
        customer_logger.info(f"Files 1-77 (PyODBC): {mixed_execution_results.get('pyodbc_executed', 0)} executed")
        customer_logger.info(f"File 78 (SQLCMD): {mixed_execution_results.get('sqlcmd_executed', 0)} executed")
        customer_logger.info(f'Total SQL Files Executed: {sql_executed}/{len(all_results)}')
        customer_logger.info(f'Total SQL Files Failed: {sql_failed}')
        customer_logger.info(f'Actual Migration Rows: {actual_migration_rows:,}')
        customer_logger.info(
            f"Migration Tables Processed: {len([t for t in migration_stats.keys() if not t.startswith('_')])}"
        )

        migration_success = sql_failed == 0 and sql_executed > 0

        # End-to-end row for the load, appended last so it is the final record in both
        # RC_Processing_Stats and the exported CSV. The per-table rows cannot be summed
        # into this: staging and SQL overlap with setup, approval gates and file moves,
        # so wall-clock has to come from the anchor set in setup_customer_migration.
        load_start_time = getattr(processor, 'load_start_time', None)
        if load_start_time is not None:
            load_end_time = datetime.now()
            load_duration = (load_end_time - load_start_time).total_seconds()
            staging_rows = [s for s in processor.processing_stats
                            if not str(s.get('table_name', '')).startswith('DT_Migration_')]
            # Rows staged, like files_count and csv_rows beside it. This used to
            # add the DT_Migration_ rows on top - staged plus migrated, a number
            # that measures nothing. Migrated rows are in DT_Migration_Summary.
            total_rows_inserted = sum(s.get('rows_inserted', 0) or 0 for s in staging_rows)
            # Same rule the staging workflow uses for its own overall_success: every
            # table must succeed, and empty tables already count as success.
            staging_success = all(s.get('success', False) for s in staging_rows)

            load_total_stat = {
                'RunID': getattr(processor, 'run_id', None),
                'Staging_LoadID': processor.staging_load_id,
                'customer_code': customer_code,
                'db': db,
                'EntityID': processor.entity_id,
                'user': processor.user,
                'from_table': 'Multiple',
                'table_name': 'DT_Load_Total',
                'files_count': sum(s.get('files_count', 0) or 0 for s in staging_rows),
                'csv_rows': sum(s.get('csv_rows', 0) or 0 for s in staging_rows),
                'rows_inserted': total_rows_inserted,
                'start_time': load_start_time,
                'end_time': load_end_time,
                'duration_seconds': round(load_duration, 2),
                'rows_per_second': round(total_rows_inserted / load_duration if load_duration > 0 else 0, 0),
                'success': staging_success and migration_success,
                'error_message': '' if migration_success else f'Failed SQL files: {sql_failed}',
                'Migration_LoadID': processor.current_load_id,
                'Migration_SessionID': processor.current_session_id,
            }

            # Left NULL rather than aggregated: the financial columns already appear on the
            # staging rows they belong to, and summing them here would double count.
            for col in processor.staging_processor.get_all_possible_financial_columns():
                load_total_stat[col] = None

            processor.processing_stats.append(load_total_stat)
            customer_logger.info(
                f'[{db}] {customer_code} - Total load time: {load_duration:.1f}s '
                f'({load_duration / 60:.1f} min), {total_rows_inserted:,} rows staged'
            )

            # After DT_Load_Total so they are excluded from its sums. Sections
            # still open (the outer 'sql', the archive) only reach the log.
            phase_base = {k: load_total_stat[k] for k in (
                'RunID', 'Staging_LoadID', 'customer_code', 'db', 'EntityID', 'user',
                'Migration_LoadID', 'Migration_SessionID')}
            for col in processor.staging_processor.get_all_possible_financial_columns():
                phase_base[col] = None
            processor.processing_stats.extend(get_timer(processor).stats_rows(phase_base))

        processing_stats_df = pd.DataFrame(processor.processing_stats)
        if len(processing_stats_df) > 0:
            success, _ = processor.shared_db_helper.bulk_insert_frame(processing_stats_df, 'RC_Processing_Stats')
            if success:
                customer_logger.info(
                    f'{customer_code} - Saved {len(processing_stats_df)} processing records to database'
                )

                reports_path = customer_paths.get('reports', customer_paths.get('customer_root', ''))
                csv_file_path = Path(reports_path) / f'{db}_{customer_code}_processing_stats.csv'
                processing_stats_df.to_csv(csv_file_path, index=False)
                customer_logger.info(f'{customer_code} - Exported processing stats to: {csv_file_path}')
            else:
                customer_logger.error(f'{customer_code} - Failed to save processing records to database')

        return {
            'sql_migration_completed': migration_success,
            'sql_execution_results': mixed_execution_results,
            'sql_files_executed': sql_executed,
            'sql_files_failed': sql_failed,
            'sql_total_rows_affected': actual_migration_rows,
            'migration_stats': migration_stats,
            'migration_processing_stats': getattr(processor, '_migration_processing_stats', []),
            'sql_export_path': str(sql_export_path),
            'execution_method': 'mixed_pyodbc_sqlcmd',
            'db': db,
        }

    def create_sql_failure_result(
        self,
        customer_code: str,
        db: str,
        customer_paths: dict,
        reason: str,
        error: str = '',
    ) -> Dict[str, Any]:
        sql_export_path = customer_paths.get('executed_queries', '') if customer_paths else ''

        # Every path that returns a failure does so before the post-check flush, so the
        # staged files are still sitting in the source folder.
        return {
            'files_moved': {'groups': 0, 'files': 0},
            'sql_migration_completed': False,
            'sql_migration_error': f'{reason}: {error}' if error else reason,
            'sql_files_executed': 0,
            'sql_files_failed': 0,
            'sql_total_rows_affected': 0,
            'migration_stats': {},
            'migration_processing_stats': [],
            'sql_export_path': str(sql_export_path),
            'execution_method': 'mixed_pyodbc_sqlcmd',
            'db': db,
        }

    def get_financial_tables_from_metrics(self, processor: Any, table_metrics: dict) -> dict:
        financial_tables = {}
        financial_columns = processor.staging_processor.get_all_possible_financial_columns()

        for table_name, metrics in table_metrics.items():
            if table_name.startswith('_'):
                continue

            table_financial_data = {}
            has_financial_data = False

            for col in financial_columns:
                value = metrics.get(col)
                if value is not None and value != 0.0:
                    table_financial_data[col] = value
                    has_financial_data = True
                else:
                    table_financial_data[col] = value

            if has_financial_data:
                financial_tables[table_name] = table_financial_data
                processor.logger.debug(f'Table {table_name} has financial data: {table_financial_data}')

        return financial_tables
