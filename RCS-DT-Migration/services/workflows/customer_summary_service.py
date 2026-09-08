from typing import Any, Dict, Tuple


class CustomerSummaryService:
    """Encapsulates customer completion summary rendering and status derivation."""

    def derive_overall_status(self, result: Dict[str, Any]) -> str:
        """SUCCESS or FAILED for one customer, from staging and migration counts.

        Separate from the summary print because the lifecycle service asks the
        same question before the archive step - the archive only runs when the
        migration itself succeeded - and both must answer it the same way.
        """
        return self._migration_status(result)[1]

    def _migration_status(self, result: Dict[str, Any]) -> Tuple[str, str]:
        """(migration status text, overall status) for one customer."""
        staging_rows = result.get('total_rows_inserted', 0)
        sql_migration_completed = result.get('sql_migration_completed', False)

        migration_rows = 0
        for table_name, metrics in result.get('migration_stats', {}).items():
            if not table_name.startswith('_'):
                migration_rows += metrics.get('rows_inserted', 0)

        if staging_rows > 0 and migration_rows == 0 and sql_migration_completed:
            return 'MIGRATION FAILED - NO ROWS MIGRATED', 'FAILED'
        if staging_rows == 0 and sql_migration_completed:
            return 'SUCCESS - NO DATA TO MIGRATE', 'SUCCESS'
        if staging_rows > 0 and migration_rows > 0 and sql_migration_completed:
            return 'SUCCESS', 'SUCCESS'
        return 'FAILED', 'FAILED'

    def print_customer_completion_summary(
        self,
        customer_code: str,
        db: str,
        result: Dict[str, Any],
        customer_logger: Any,
        entity_id: Any,
        current_load_id: Any,
        current_session_id: Any,
        staging_load_id: Any,
    ) -> str:
        # Extract metrics
        staging_rows = result.get('total_rows_inserted', 0)
        sql_files_executed = result.get('sql_files_executed', 0)
        sql_files_failed = result.get('sql_files_failed', 0)
        tables_processed = len(result.get('processing_stats', []))
        sql_migration_completed = result.get('sql_migration_completed', False)

        # Calculate actual migration rows from migration_stats
        migration_stats = result.get('migration_stats', {})
        migration_rows = 0

        for table_name, metrics in migration_stats.items():
            if not table_name.startswith('_'):
                rows_inserted = metrics.get('rows_inserted', 0)
                migration_rows += rows_inserted

        # Determine actual migration status
        migration_status, overall_status = self._migration_status(result)
        migration_ok = overall_status == 'SUCCESS'

        # The archive is the last step and a required one: the staging tables are
        # truncated for the next customer, so a migration whose extract was not
        # archived cannot be reported as done.
        archive_attempted = result.get('archive_attempted', False)
        archive_success = result.get('archive_success', False)
        if archive_attempted and not archive_success:
            overall_status = 'FAILED'

        print(f"\n{'=' * 60}")
        print(f"CUSTOMER [{db}] {customer_code} - COMPLETE MIGRATION FINISHED")
        print(f"{'=' * 60}")
        print(f"OVERALL STATUS: {overall_status}")
        print(f"Staging Tables processed: {tables_processed}")
        print(f"Staging Total rows: {staging_rows:,}")
        print(f"SQL Files executed: {sql_files_executed}")
        print(f"SQL Files failed: {sql_files_failed}")
        print(f"Migration Total rows: {migration_rows:,}")
        print(f"Migration Status: {migration_status}")
        print(f"Archive: {self._archive_line(result, migration_ok)}")
        print(f"Entity ID: {entity_id}")
        print(f"Migration LoadID: {current_load_id}")
        print(f"Migration SessionID: {current_session_id}")
        print(f"Staging LoadID: {staging_load_id}")

        if staging_rows > 0 and migration_rows == 0:
            print('WARNING: Staging data was processed but no migration rows were created!')
            print('This indicates a migration failure despite successful SQL execution.')

        if archive_attempted and not archive_success:
            print('WARNING: the staging tables were NOT archived. They are truncated '
                  'for the next customer, so re-run this customer or copy them out now.')
            customer_logger.error(
                f"Archive failed: {result.get('archive_error') or 'no detail reported'}"
            )

        if migration_stats:
            customer_logger.info('Migration table breakdown:')
            for table_name, metrics in migration_stats.items():
                if not table_name.startswith('_'):
                    rows = metrics.get('rows_inserted', 0)
                    customer_logger.info(f"  {table_name}: {rows:,} rows")

        print('=' * 60)
        return overall_status

    def _archive_line(self, result: Dict[str, Any], migration_ok: bool) -> str:
        """One line describing what the archive step did, for the summary."""
        if not result.get('archive_attempted', False):
            return 'not run' if migration_ok else 'skipped (migration did not succeed)'

        database = result.get('archive_database') or 'the archive database'
        if not result.get('archive_success', False):
            return f"FAILED - {result.get('archive_error') or 'no detail reported'}"

        tables = result.get('archive_tables', {})
        copied = sum(1 for t in tables.values() if t.get('success') and not t.get('skipped'))
        rows = result.get('archive_rows_copied', 0)
        return f'{copied} table(s), {rows:,} row(s) -> {database}'
