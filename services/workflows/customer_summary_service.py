from typing import Any, Dict


class CustomerSummaryService:
    """Encapsulates customer completion summary rendering and status derivation."""

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
        if staging_rows > 0 and migration_rows == 0 and sql_migration_completed:
            migration_status = 'MIGRATION FAILED - NO ROWS MIGRATED'
            overall_status = 'FAILED'
        elif staging_rows == 0 and sql_migration_completed:
            migration_status = 'SUCCESS - NO DATA TO MIGRATE'
            overall_status = 'SUCCESS'
        elif staging_rows > 0 and migration_rows > 0 and sql_migration_completed:
            migration_status = 'SUCCESS'
            overall_status = 'SUCCESS'
        else:
            migration_status = 'FAILED'
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
        print(f"Entity ID: {entity_id}")
        print(f"Migration LoadID: {current_load_id}")
        print(f"Migration SessionID: {current_session_id}")
        print(f"Staging LoadID: {staging_load_id}")

        if staging_rows > 0 and migration_rows == 0:
            print('WARNING: Staging data was processed but no migration rows were created!')
            print('This indicates a migration failure despite successful SQL execution.')

        if migration_stats:
            customer_logger.info('Migration table breakdown:')
            for table_name, metrics in migration_stats.items():
                if not table_name.startswith('_'):
                    rows = metrics.get('rows_inserted', 0)
                    customer_logger.info(f"  {table_name}: {rows:,} rows")

        print('=' * 60)
        return overall_status
