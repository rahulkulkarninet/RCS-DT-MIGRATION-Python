import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from bank_transaction_method_service import BankTransactionMethodService
from result_types import (
    BankTransactionMethodCheckResult,
    BankTransactionMethodUpdateResult,
)


class CustomerBankTransactionMethodWorkflowService:
    """Coordinates Payment_Method normalization/update and bank transaction method checks."""

    def _ensure_bank_transaction_method_service(self, processor: Any) -> BankTransactionMethodService:
        if not getattr(processor, 'bank_transaction_method_service', None):
            processor.bank_transaction_method_service = BankTransactionMethodService(
                processor.shared_db_helper
            )
        return processor.bank_transaction_method_service

    def update_payment_methods(
        self,
        processor: Any,
        customer_logger: logging.Logger,
    ) -> BankTransactionMethodUpdateResult:
        # This module lives in services/workflows; resolve variables from repo root.
        mapping_file_path = (
            Path(__file__).resolve().parents[2] / 'variables' / 'bank_transaction_method_codes.json'
        )

        result: BankTransactionMethodUpdateResult = {
            'success': False,
            'mapping_file': str(mapping_file_path),
            'total_codes_loaded': 0,
            'duplicate_codes_skipped': 0,
            'resolved_methods': 0,
            'rows_updated': 0,
            'rows_updated_by_table': {},
            'invalid_methods': [],
            'invalid_methods_by_table': {},
            'status_message': '',
            'error': None,
        }

        try:
            if not mapping_file_path.exists():
                result['error'] = f'Mapping file not found: {mapping_file_path}'
                customer_logger.error(result['error'])
                return result

            with open(mapping_file_path, 'r', encoding='utf-8') as file_handle:
                method_mapping = json.load(file_handle)

            if not isinstance(method_mapping, dict):
                result['error'] = 'bank_transaction_method_codes.json must contain a JSON object'
                customer_logger.error(result['error'])
                return result

            mapping_frame, duplicate_codes = self.load_bank_transaction_method_mapping_frame(
                processor, method_mapping
            )
            result['total_codes_loaded'] = len(mapping_frame)
            result['duplicate_codes_skipped'] = duplicate_codes

            if mapping_frame.empty:
                customer_logger.warning(
                    'No bank transaction method codes found in mapping file; nothing to update'
                )
                result['success'] = True
                result['status_message'] = 'No bank transaction method codes found in mapping file.'
                return result

            resolution_frame, _ = self.build_payment_method_resolution_frame(processor, mapping_frame)
            rows_updated_by_table = self.bulk_update_payment_methods(processor, resolution_frame)
            invalid_by_table = self.get_invalid_payment_methods_from_db(processor)

            invalid_methods = sorted(
                {value for values in invalid_by_table.values() for value in values}
            )

            result['resolved_methods'] = len(resolution_frame)
            result['rows_updated_by_table'] = rows_updated_by_table
            result['rows_updated'] = sum(rows_updated_by_table.values())
            result['invalid_methods_by_table'] = invalid_by_table
            result['invalid_methods'] = invalid_methods
            result['status_message'] = (
                f"Invalid bank transaction methods found: {', '.join(invalid_methods)}"
                if invalid_methods
                else 'All bank transaction methods are valid.'
            )
            result['success'] = True

            per_table = ', '.join(
                f'{table}={count}' for table, count in sorted(rows_updated_by_table.items())
            ) or 'none'
            customer_logger.info(
                'Updated staging Payment_Method using bank_transaction_method_codes.json: '
                f"{result['rows_updated']} rows updated ({per_table}), "
                f'{len(mapping_frame)} codes loaded, '
                f'{duplicate_codes} duplicate code entries skipped'
            )

            for table, values in sorted(invalid_by_table.items()):
                customer_logger.warning(
                    f'Unresolved {table}.Payment_Method values after normalization: '
                    + ', '.join(values)
                )

            return result

        except Exception as e:
            result['error'] = str(e)
            customer_logger.error(f'Failed to update staging Payment_Method values: {e}')
            return result

    def check_bank_transaction_methods_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
        method_update_result: Optional[BankTransactionMethodUpdateResult] = None,
    ) -> BankTransactionMethodCheckResult:
        customer_logger.info('Checking bank transaction methods...')

        status_message = 'All bank transaction methods are valid.'
        invalid_methods: List[str] = []
        invalid_by_table: Dict[str, List[str]] = {}

        if method_update_result is None:
            invalid_by_table = self.get_invalid_payment_methods_from_db(processor)
            invalid_methods = sorted(
                {value for values in invalid_by_table.values() for value in values}
            )
        else:
            invalid_by_table = method_update_result.get('invalid_methods_by_table', {})
            invalid_methods = sorted(set(method_update_result.get('invalid_methods', [])))

        if invalid_methods:
            status_message = f"Invalid bank transaction methods found: {', '.join(invalid_methods)}"

        customer_logger.info(f'Bank transaction method check result: {status_message}')

        if invalid_methods:
            customer_logger.warning(
                f'Found {len(invalid_methods)} payment method value(s) not present in '
                'tblBankTransactionMethod. Add them to '
                'variables/bank_transaction_method_codes.json before migrating.'
            )
            for table, values in sorted(invalid_by_table.items()):
                customer_logger.warning(f'  {table}: ' + ', '.join(values))

        return {
            'status_message': status_message,
            'invalid_methods': invalid_methods,
        }

    def load_bank_transaction_method_mapping_frame(
        self,
        processor: Any,
        method_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        service = self._ensure_bank_transaction_method_service(processor)
        return service.load_bank_transaction_method_mapping_frame(method_mapping)

    def build_payment_method_resolution_frame(
        self,
        processor: Any,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        service = self._ensure_bank_transaction_method_service(processor)
        return service.build_payment_method_resolution_frame(mapping_frame)

    def bulk_update_payment_methods(
        self,
        processor: Any,
        resolution_frame: pd.DataFrame,
    ) -> Dict[str, int]:
        service = self._ensure_bank_transaction_method_service(processor)
        return service.bulk_update_payment_methods(resolution_frame)

    def get_invalid_payment_methods_from_db(self, processor: Any) -> Dict[str, List[str]]:
        service = self._ensure_bank_transaction_method_service(processor)
        return service.get_invalid_payment_methods_from_db()
