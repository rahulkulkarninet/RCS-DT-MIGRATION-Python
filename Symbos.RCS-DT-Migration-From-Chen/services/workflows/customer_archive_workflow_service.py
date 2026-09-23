import logging
from typing import Any, Dict, List

from schema_files import SchemaSetError, load_staging_schema_files
from staging_archive import StagingRenamer, archive_timestamp


class CustomerArchiveWorkflowService:
    """Moves one customer's staging tables into the archive schema.

    Runs after the SQL migration, while the staging tables still hold this
    customer's extract. It renames them rather than copying them, and rebuilds
    an empty staging table in the same transaction - so unlike the copy it
    replaced, the next customer is never waiting on it and the cost does not
    grow with the size of the extract. See staging_archive.
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
            'archive_schema': '',
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
            schema_files = self.rebuild_schema_files(processor)
        except SchemaSetError as e:
            result['archive_error'] = str(e)
            customer_logger.error(
                f'Archive skipped: the staging tables could not be rebuilt after '
                f'being renamed, so none were renamed. {e}')
            return result

        try:
            archiver = StagingRenamer(
                db=processor.shared_db_helper,
                customer_code=customer_code,
                tables=tables,
                schema_files=schema_files,
                logger=customer_logger,
            )
        except ValueError as e:
            # A customer code that cannot be part of a table name. Worth its own
            # branch: it is an input problem with a nameable cause, not a
            # database failure, and no DDL has run.
            result['archive_error'] = str(e)
            customer_logger.error(f'Archive failed for [{db}]: {e}')
            return result

        result['archive_schema'] = archiver.archive_schema
        result['archive_method'] = 'rename'

        context = self.build_context(processor, customer_code, db)
        customer_logger.info(
            f'Archiving as {customer_code}_* in {archiver.archive_schema} for '
            f'LoadID {context["loadid"]}'
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
        result['archive_rows_copied'] = summary['rows_archived']
        result['archive_tables'] = summary['tables']
        result['archive_error'] = '; '.join(summary['errors'])

        self.log_summary(summary, customer_code, db, customer_logger)
        return result

    def archive_tables(self, processor: Any) -> List[str]:
        """The staging tables to archive - the same set staging truncates."""
        keywords = getattr(processor.config_parser, 'table_keywords', None) or {}
        return [name for name in keywords.values() if name]

    def rebuild_schema_files(self, processor: Any) -> Dict[str, Any]:
        """The SQL/Schemas file that rebuilds each staging table.

        process_staging reads these when the run starts, so that a missing one
        stops the run before any table has been renamed away. This prefers that
        copy and only falls back to reading them itself - which raises the same
        error - when the archive is driven from somewhere without a staging
        processor, as tools/archive_staging.py is.
        """
        staging = getattr(processor, 'staging_processor', None)
        cached = getattr(staging, 'staging_schema_files', None)
        if cached:
            return cached

        cached = getattr(processor, '_archive_schema_files', None)
        if cached is None:
            cached = load_staging_schema_files(self.archive_tables(processor))
            processor._archive_schema_files = cached
        return cached

    def build_context(self, processor: Any, customer_code: str, db: str) -> Dict[str, Any]:
        """Values for the archive catalog row this customer's archive writes.

        Keyed by lowercased name. Everything is a plain Python scalar - pyodbc
        cannot bind a numpy.int64, which is what an entity id read through
        pandas would otherwise be.
        """
        return {
            'loadid': self._as_int(processor.current_load_id),
            # One timestamp for the whole customer, so every table of one load
            # shares it rather than drifting table by table. At the column's own
            # resolution - see archive_timestamp.
            'createts': archive_timestamp(),
            'entitycode': customer_code,
            'sessionid': self._as_int(processor.current_session_id),
            'runid': getattr(processor, 'run_id', None),
            'db': db,
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
            if table_result['skipped']:
                customer_logger.info(
                    f'  {table_name}: skipped - {table_result["reason"]}')
            else:
                customer_logger.info(
                    f'  {table_name}: {table_result["rows"]:,} row(s) -> '
                    f'{summary["schema"]}.{table_result["target_table"]}')

        message = (
            f'[{db}] {customer_code} - archive to {summary["schema"]}: '
            f'{summary["tables_archived"]} table(s) renamed, '
            f'{summary["tables_skipped"]} skipped, '
            f'{summary["rows_archived"]:,} row(s)'
        )
        if summary['success']:
            customer_logger.info(f'[SUCCESS] {message}')
        else:
            customer_logger.error(f'[FAILED] {message}')
