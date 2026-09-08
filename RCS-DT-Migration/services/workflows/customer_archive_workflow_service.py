import logging
from typing import Any, Dict, List

from staging_archive import StagingArchiver, archive_timestamp


class CustomerArchiveWorkflowService:
    """Copies one customer's staging tables into the migration_data archive.

    Runs after the SQL migration, while the staging tables still hold this
    customer's extract - the next customer's truncate is what it is racing.
    """

    def archive_staging_tables_step(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        customer_logger: logging.Logger,
    ) -> Dict[str, Any]:
        customer_logger.info('Final step: Archiving staging tables...')

        result: Dict[str, Any] = {
            'archive_attempted': True,
            'archive_success': False,
            'archive_database': '',
            'archive_method': '',
            'archive_rows_copied': 0,
            'archive_tables': {},
            'archive_error': '',
        }

        tables = self.archive_tables(processor)
        if not tables:
            result['archive_error'] = 'no table keywords configured'
            customer_logger.error(f'Archive skipped: {result["archive_error"]}')
            return result

        try:
            target_db = processor.get_archive_db_helper()
        except Exception as e:
            result['archive_error'] = (
                f'could not reach the archive database: {type(e).__name__}: {e}')
            customer_logger.error(f'Archive failed: {result["archive_error"]}')
            return result

        archiver = StagingArchiver(
            source_db=processor.shared_db_helper,
            target_db=target_db,
            tables=tables,
            logger=customer_logger,
        )
        result['archive_database'] = archiver.archive_database
        result['archive_method'] = archiver.method

        context = self.build_context(processor, customer_code, db)
        customer_logger.info(
            f'Archiving to {archiver.archive_database} for LoadID '
            f'{context["loadid"]}, EntityCode {context["entitycode"]}'
        )

        try:
            summary = archiver.archive_all(context)
        except Exception as e:
            result['archive_error'] = f'{type(e).__name__}: {e}'
            customer_logger.error(
                f'Archive failed for [{db}] {customer_code}: {result["archive_error"]}',
                exc_info=True,
            )
            return result

        result['archive_success'] = summary['success']
        result['archive_rows_copied'] = summary['rows_copied']
        result['archive_tables'] = summary['tables']
        result['archive_error'] = '; '.join(summary['errors'])

        self.log_summary(summary, customer_code, db, customer_logger)
        return result

    def archive_tables(self, processor: Any) -> List[str]:
        """The staging tables to archive - the same set staging truncates."""
        keywords = getattr(processor.config_parser, 'table_keywords', None) or {}
        return [name for name in keywords.values() if name]

    def build_context(self, processor: Any, customer_code: str, db: str) -> Dict[str, Any]:
        """Values for the audit columns the archive tables add.

        Keyed by lowercased column name, so the archive table decides which of
        these it wants. LoadID, CreateTS and EntityCode are the three every
        archive table gets; the rest are there for a table that names one of
        them, and cost nothing when it does not.

        Everything is a plain Python scalar - pyodbc cannot bind a numpy.int64,
        which is what an entity id read through pandas would otherwise be.
        """
        return {
            'loadid': self._as_int(processor.current_load_id),
            # One timestamp for the whole customer, so every archived row of one
            # load shares it rather than drifting table by table. At the
            # column's own resolution - see archive_timestamp.
            'createts': archive_timestamp(),
            'entitycode': customer_code,
            'entityid': self._as_int(processor.entity_id),
            'customer_code': customer_code,
            'customercode': customer_code,
            'db': db,
            'staging_loadid': processor.staging_load_id,
            'stagingloadid': processor.staging_load_id,
            'sessionid': self._as_int(processor.current_session_id),
            'runid': getattr(processor, 'run_id', None),
        }

    @staticmethod
    def _as_int(value: Any) -> Any:
        """int(value), or None when there is nothing to convert."""
        if value is None or value == '':
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    def log_summary(self, summary: Dict[str, Any], customer_code: str, db: str,
                    customer_logger: logging.Logger) -> None:
        for table_name, table_result in summary['tables'].items():
            if not table_result['success']:
                customer_logger.error(
                    f'  {table_name}: archive FAILED - {table_result["error"]}')
            elif table_result['skipped']:
                customer_logger.info(
                    f'  {table_name}: skipped - {table_result["reason"]}')
            else:
                customer_logger.info(
                    f'  {table_name}: {table_result["rows_copied"]:,} row(s) archived')

        message = (
            f'[{db}] {customer_code} - archive to {summary["database"]}: '
            f'{summary["tables_copied"]} table(s) copied, '
            f'{summary["tables_skipped"]} skipped, {summary["tables_failed"]} failed, '
            f'{summary["rows_copied"]:,} row(s)'
        )
        if summary['success']:
            customer_logger.info(f'[SUCCESS] {message}')
        else:
            customer_logger.error(f'[FAILED] {message}')
