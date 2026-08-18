import gc
import logging
from datetime import datetime
from typing import Any, Dict, List

from interaction import GATE_STAGING


class CustomerStagingWorkflowService:
    """Coordinates interactive staging workflow and table-level processing."""

    def process_customer_staging(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        files: List[str],
        customer_logger: logging.Logger,
        customer_paths: dict,
    ) -> Dict[str, Any]:
        customer_logger.info(f"\n{'='*70}")
        customer_logger.info(f"PROCESSING CUSTOMER: [{db}] {customer_code}")
        customer_logger.info(f"{'='*70}")

        validation = self.validate_customer_files_step(processor, customer_code, db, files, customer_logger)
        if not validation['valid_tables']:
            return self.create_staging_failure_result(processor, customer_code, db, 'no_valid_tables', validation)

        print(f"\n{'='*50}")
        print(f"STAGING READY FOR CUSTOMER: [{db}] {customer_code}")
        print(f"Valid tables: {len(validation['valid_tables'])}")
        print(f"Total expected rows: {validation['total_expected_rows']:,}")
        print(f"{'='*50}")

        if not processor.approval_policy.confirm('Continue with staging process?',
                                                GATE_STAGING):
            customer_logger.info('Staging process not approved; skipping customer')
            return self.create_staging_failure_result(processor, customer_code, db, 'user_skipped')

        if not self.truncate_staging_tables_step(processor, customer_code, db, customer_logger):
            return self.create_staging_failure_result(processor, customer_code, db, 'truncate_failed')

        return self.process_customer_tables_step(
            processor,
            customer_code,
            db,
            files,
            customer_logger,
            customer_paths,
            validation,
        )

    def validate_customer_files_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        files: List[str],
        customer_logger: logging.Logger,
    ) -> Dict[str, Any]:
        customer_logger.info('Step 1: Validating customer files...')
        validation = processor.validate_customer_files(customer_code, db, files)

        if validation['invalid_files']:
            customer_logger.warning(
                f"[{db}] Customer {customer_code} has {len(validation['invalid_files'])} invalid files"
            )
            for file_path in validation['invalid_files']:
                customer_logger.warning(f'  Invalid file: {file_path}')

        return validation

    def truncate_staging_tables_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
    ) -> bool:
        customer_logger.info('Step 2: Truncating staging tables...')
        if not processor.staging_processor.truncate_staging_tables():
            customer_logger.error(f'Failed to truncate staging tables for [{db}] customer {customer_code}')
            return False

        customer_logger.info(f'DB: {db}')
        customer_logger.info(f'Customer: {customer_code}')
        customer_logger.info(f'Entity ID: {processor.entity_id}')
        customer_logger.info(f'Migration LoadID: {processor.current_load_id}')
        customer_logger.info(f'Migration SessionID: {processor.current_session_id}')
        customer_logger.info(f'Staging LoadID: {processor.staging_load_id}\n')
        return True

    def process_customer_tables_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        files: List[str],
        customer_logger: logging.Logger,
        customer_paths: dict,
        validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        customer_logger.info('Step 3: Processing customer tables...')

        try:
            table_groups = processor.staging_processor.group_files_by_table(files)
            financial_columns = processor.staging_processor.get_all_possible_financial_columns()

            total_rows_processed = 0
            total_rows_inserted = 0
            tables_with_data = 0
            empty_tables = 0
            overall_success = True

            for table_name, table_files in table_groups.items():
                table_start_time = datetime.now()
                success = False
                rows_inserted = 0
                csv_rows = 0
                error_message = ''
                financial_summary: Dict[str, Any] = {}

                customer_logger.info(
                    f"\nProcessing {table_name} for customer {customer_code} ({len(table_files)} files)"
                )

                try:
                    if not processor.memory_manager.check_memory_limit():
                        customer_logger.warning(f'High memory usage before processing {table_name}')
                        gc.collect()

                    memory_before = processor.memory_manager.get_memory_usage()

                    load_result = processor.staging_processor.load_staging_file_group(
                        table_files,
                        table_name,
                    )
                    memory_after = processor.memory_manager.get_memory_usage()
                    customer_logger.info(
                        f'Memory usage for {table_name}: {memory_before:.1f}% -> {memory_after:.1f}%'
                    )

                    rows_processed = load_result['rows_read']
                    csv_rows = rows_processed
                    rows_inserted = load_result['rows_inserted']
                    financial_summary = load_result['financial_summary']
                    success = load_result['success']
                    error_message = load_result['error_message']

                    if rows_processed == 0:
                        empty_tables += 1
                        success = True
                        rows_inserted = 0
                        error_message = error_message or 'No data in files'
                        processor.logger.info(
                            f'[NO DATA] [{db}] {customer_code} - {table_name}: No data to process (empty files)'
                        )
                        processor.move_files_to_customer_folder(
                            table_files,
                            success=True,
                            rows_processed=0,
                            customer_paths=customer_paths,
                        )

                    else:
                        tables_with_data += 1
                        total_rows_processed += rows_processed

                        if success:
                            total_rows_inserted += rows_inserted
                            processor.logger.info(
                                f'[SUCCESS] [{db}] {customer_code} - {table_name}: {rows_inserted} rows inserted'
                            )
                            processor.move_files_to_customer_folder(
                                table_files,
                                success=True,
                                rows_processed=rows_inserted,
                                customer_paths=customer_paths,
                            )
                        else:
                            overall_success = False
                            error_message = error_message or 'Insert operation failed'
                            processor.logger.error(
                                f'[FAILED] [{db}] {customer_code} - {table_name}: {error_message}'
                            )
                            processor.move_files_to_customer_folder(
                                table_files,
                                success=False,
                                rows_processed=csv_rows,
                                customer_paths=customer_paths,
                                error_message=error_message,
                            )

                except Exception as e:
                    overall_success = False
                    error_message = str(e)
                    success = False
                    processor.logger.error(
                        f'Error processing {table_name} for [{db}] customer {customer_code}: {e}'
                    )
                    processor.move_files_to_customer_folder(
                        table_files,
                        success=False,
                        rows_processed=0,
                        customer_paths=customer_paths,
                        error_message=error_message,
                    )

                    gc.collect()

                table_end_time = datetime.now()
                duration_seconds = (table_end_time - table_start_time).total_seconds()
                rows_per_second = rows_inserted / duration_seconds if duration_seconds > 0 else 0

                stats = {
                    'RunID': getattr(processor, 'run_id', None),
                    'Staging_LoadID': processor.staging_load_id,
                    'customer_code': customer_code,
                    'db': db,
                    'EntityID': processor.entity_id,
                    'user': processor.user,
                    'from_table': None,
                    'table_name': table_name,
                    'files_count': len(table_files),
                    'csv_rows': csv_rows,
                    'rows_inserted': rows_inserted,
                    'start_time': table_start_time,
                    'end_time': table_end_time,
                    'duration_seconds': round(duration_seconds, 2),
                    'rows_per_second': round(rows_per_second, 0),
                    'success': success,
                    'error_message': error_message,
                    'Migration_LoadID': processor.current_load_id,
                    'Migration_SessionID': processor.current_session_id,
                }

                for col in financial_columns:
                    stats[col] = financial_summary.get(col)
                processor.processing_stats.append(stats)

                customer_logger.info(
                    f'[{db}] {customer_code} - Completed {table_name}: {duration_seconds:.1f}s, '
                    f'{rows_per_second:.0f} rows/sec\n'
                )

            if tables_with_data > 0:
                data_table_success = all(
                    stat['success'] for stat in processor.processing_stats if stat['rows_inserted'] > 0
                )
                overall_success = data_table_success
            else:
                overall_success = True

            if overall_success:
                if total_rows_inserted > 0:
                    customer_logger.info(
                        f'[SUCCESS] [{db}] Customer {customer_code} completed successfully: '
                        f'{total_rows_inserted} total rows inserted, {empty_tables} empty tables'
                    )
                else:
                    customer_logger.info(
                        f'[SUCCESS] [{db}] Customer {customer_code} completed successfully: '
                        'No data to process (all tables empty)'
                    )
            else:
                customer_logger.warning(f'[FAILED] [{db}] Customer {customer_code} completed with issues')

            print(f"\n{'='*60}")
            print(f'CUSTOMER [{db}] {customer_code} - STAGING COMPLETE')
            print(f"{'='*60}")
            print(f'Tables processed: {len(table_groups)}')
            print(f"Total rows staged: {sum(stat['rows_inserted'] for stat in processor.processing_stats)}")
            print(f'Entity ID: {processor.entity_id}')
            print(f'Migration LoadID: {processor.current_load_id}')
            print(f'Migration SessionID: {processor.current_session_id}')
            print(f'Staging LoadID: {processor.staging_load_id}')

            return {
                'customer_code': customer_code,
                'db': db,
                'entity_id': processor.entity_id,
                'load_id': processor.current_load_id,
                'session_id': processor.current_session_id,
                'staging_load_id': processor.staging_load_id,
                'tables_processed': {
                    stat['table_name']: {
                        'rows_processed': stat['csv_rows'],
                        'rows_inserted': stat['rows_inserted'],
                        'insert_success': stat['success'],
                        'status': 1 if stat['success'] else 0,
                    }
                    for stat in processor.processing_stats
                },
                'total_rows_processed': total_rows_processed,
                'total_rows_inserted': total_rows_inserted,
                'processing_success': overall_success,
                'tables_with_data': tables_with_data,
                'empty_tables': empty_tables,
                'customer_paths': customer_paths,
                'processing_stats': processor.processing_stats,
            }

        except Exception as e:
            processor.logger.error(f'Unexpected error processing [{db}] customer {customer_code}: {e}')
            return self.create_staging_failure_result(
                processor,
                customer_code,
                db,
                'unexpected_error',
                error=str(e),
            )

    def create_staging_failure_result(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        reason: str,
        validation: Dict = None,
        error: str = '',
    ) -> Dict[str, Any]:
        return {
            'customer_code': customer_code,
            'db': db,
            'entity_id': processor.entity_id,
            'validation_failed': reason == 'no_valid_tables',
            'tables_processed': {},
            'total_rows_processed': 0,
            'total_rows_inserted': 0,
            'processing_success': False,
            'status': reason,
            'validation_details': validation,
            'error': error,
        }
