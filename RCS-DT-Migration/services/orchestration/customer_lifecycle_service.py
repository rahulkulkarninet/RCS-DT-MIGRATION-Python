from typing import Any, Dict


class CustomerLifecycleService:
    """Encapsulates customer-level orchestration for staging and migration flow."""

    def process_staging_to_migration(self, processor: Any, validate_only: bool = False) -> Dict[str, Dict]:
        """
        Process from staging area to migration area for all customers.
        """
        # Group files by customer
        customer_groups = processor.group_files_by_customer()
        processor.logger.info(f"Found {len(customer_groups)} customers to process")

        # Validate customers against entity mapping
        validation_results = processor.validate_customers_against_entity_mapping(customer_groups)
        valid_customers = [code for code, valid in validation_results.items() if valid]
        invalid_customers = [code for code, valid in validation_results.items() if not valid]

        if invalid_customers:
            processor.logger.warning(f"Invalid customers (not in entity mapping): {invalid_customers}")

        if validate_only:
            return {'validation_results': validation_results}

        # Initialize results dictionary to collect all customer results
        customer_results: Dict[str, Dict] = {}

        for i, customer_code in enumerate(valid_customers, 1):
            db = customer_groups[customer_code]['db']
            files = customer_groups[customer_code]['files']

            processor.logger.info(f"\n{'#' * 60}")
            processor.logger.info(f"CUSTOMER {i}/{len(valid_customers)}: [{db}] {customer_code}")
            processor.logger.info(f"{'#' * 60}")

            # Extract Client_Code/Client_Group pairs from this customer's RC_ACCOUNT_EXTRACT files
            processor.get_client_codes_from_account_extract(files)

            # Setup migration infrastructure
            setup_result = processor.setup_customer_migration(customer_code, db)

            # Create customer-specific directories
            output = processor.staging_processor.file_paths['output']
            customer_paths = processor.create_customer_directories(
                customer_code, db, output, processor.entity_id, processor.current_load_id, processor.current_session_id
            )

            # Set up customer-specific logger
            customer_logger = processor.setup_customer_logger(
                customer_code, db, customer_paths, processor.entity_id, processor.current_load_id, processor.current_session_id
            )

            try:
                if not setup_result['setup_success']:
                    customer_results[customer_code] = {
                        'customer_code': customer_code,
                        'db': db,
                        'entity_id': processor.entity_id,
                        'overall_status': 'FAILED',
                        'setup_failed': True,
                        'error': setup_result.get('error', 'Migration setup failed'),
                        'total_rows_processed': 0,
                        'total_rows_inserted': 0,
                        'processing_success': False,
                    }
                    continue

                # Process customer files
                staging_result = processor.process_customer_staging(
                    customer_code,
                    db,
                    files,
                    customer_logger=customer_logger,
                    customer_paths=customer_paths,
                )

                # The SQL phase reads the staging tables, so it is only meaningful
                # once staging has actually filled them for this customer. Every
                # staging bail-out returns before the table loop runs, leaving the
                # tables holding the previous customer's extract - and this call
                # used to be made regardless, silently migrating that instead.
                if staging_result.get('processing_success', False):
                    migration_result = processor.execute_mixed_sql_methods(
                        customer_code,
                        db,
                        customer_logger=customer_logger,
                        customer_paths=customer_paths,
                        staging_result=staging_result,
                    )
                else:
                    reason = staging_result.get('status') or 'staging_failed'
                    customer_logger.error(
                        f'Skipping SQL migration for [{db}] {customer_code}: staging '
                        f'did not complete ({reason}), so the staging tables do not '
                        f"hold this customer's extract. No files were moved, so the "
                        f'customer can be re-run once the cause is fixed.'
                    )
                    migration_result = processor.customer_sql_workflow_service.create_sql_failure_result(
                        customer_code,
                        db,
                        customer_paths,
                        'staging_incomplete',
                        reason,
                    )

                # Store result in results dictionary
                combined_result = {**staging_result, **migration_result}

                # Final step: copy the staging tables into the archive database,
                # while they still hold this customer's extract - the next
                # customer's truncate is what this is racing. Only worth doing,
                # and only trustworthy, when the migration itself succeeded.
                if processor.customer_summary_service.derive_overall_status(
                        combined_result) == 'SUCCESS':
                    combined_result.update(
                        processor.archive_staging_tables(
                            customer_code, db, customer_logger
                        )
                    )
                else:
                    combined_result['archive_attempted'] = False
                    customer_logger.warning(
                        'Staging tables not archived: the migration did not succeed'
                    )

                # Print combined summary
                combined_result['overall_status'] = processor._print_customer_completion_summary(
                    customer_code, db, combined_result, customer_logger
                )

                # Store result in results dictionary
                customer_results[customer_code] = combined_result

            except Exception as e:
                # processor.logger propagates to root, which now also feeds this
                # customer's processing/error logs - so one call reaches the
                # run-wide log, the terminal, and the customer's own files.
                processor.logger.error(
                    f"Unexpected error processing [{db}] customer {customer_code}: "
                    f"{type(e).__name__}: {e}",
                    exc_info=True,
                )

                # Store error result
                customer_results[customer_code] = {
                    'customer_code': customer_code,
                    'db': db,
                    'entity_id': processor.entity_id,
                    'overall_status': 'FAILED',
                    'processing_success': False,
                    'error': str(e),
                    'total_rows_processed': 0,
                    'total_rows_inserted': 0,
                    'sql_migration_completed': False,
                    'sql_migration_error': str(e),
                }

                # Cleanup with rollback on error
                processor.cleanup_customer_migration(
                    setup_result.get('load_id'),
                    setup_result.get('session_id'),
                    rollback=True,
                )
            finally:
                # Clean up customer logger
                processor.cleanup_customer_logger(customer_logger)

        return customer_results
