import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Marks the handlers this service attaches to the root logger so they can be
# found and detached again without touching the handlers Run_Migration set up.
_CAPTURE_FLAG = '_dt_customer_capture'


class CustomerIOService:
    """Handles customer-specific filesystem and logger setup/cleanup."""

    def create_customer_directories(
        self,
        customer_code: str,
        db: str,
        base_path: str,
        entity_id: int,
        load_id: int,
        session_id: int,
    ) -> Dict[str, Path]:
        base = Path(base_path)

        current_date = datetime.now().strftime('%Y-%m-%d')
        date_path = base / current_date

        if entity_id and load_id and session_id:
            customer_folder_name = f"{db}_{customer_code}-{entity_id}-{load_id}-{session_id}"
        else:
            customer_folder_name = f"{db}_{customer_code}"

        customer_path = date_path / customer_folder_name

        paths = {
            'date_root': date_path,
            'customer_root': customer_path,
            'processed': customer_path / 'Processed',
            'no_data': customer_path / 'No_Data',
            'errors': customer_path / 'Errors',
            'reports': customer_path / 'Reports',
            'executed_queries': customer_path / 'Executed Queries',
        }

        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)

        return paths

    def setup_customer_logger(
        self,
        customer_code: str,
        db: str,
        customer_paths: Dict[str, Path],
        entity_id: int,
        load_id: int,
        session_id: int,
    ) -> logging.Logger:
        current_date = datetime.now().strftime('%Y-%m-%d')
        logger_name = f"customer_{current_date}_{db}_{customer_code}_{load_id}_{session_id}"

        customer_logger = logging.getLogger(logger_name)
        customer_logger.handlers.clear()
        customer_logger.setLevel(logging.INFO)

        stem = f"{db}_{customer_code}_{entity_id}_{load_id}_{session_id}"
        customer_root = customer_paths['customer_root']
        log_path = customer_root / f"processing_log_{stem}.log"
        error_log_path = customer_paths.get('errors', customer_root) / f"error_log_{stem}.log"

        # The processing log carries the logger name so a line's origin
        # (DT_query_processor, process_staging, ...) is visible at a glance.
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        )
        console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(file_formatter)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)

        # Errors-only companion, pinned in the Errors folder with source line
        # numbers. delay=True keeps the file from being created for clean runs.
        error_handler = logging.FileHandler(
            error_log_path, mode='w', encoding='utf-8', delay=True
        )
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s.%(funcName)s:%(lineno)d - %(message)s'
        ))

        customer_logger.addHandler(file_handler)
        customer_logger.addHandler(console_handler)
        customer_logger.addHandler(error_handler)
        customer_logger.propagate = False

        # Most detail (SQL failures, rollbacks, connection errors, tracebacks) is
        # emitted on module loggers that propagate to root, so it previously only
        # reached the terminal. Attaching the customer's file handlers to root
        # mirrors that same detail into this customer's log for the duration of
        # the run. customer_logger.propagate is False, so nothing double-logs.
        self._attach_capture_handlers([file_handler, error_handler])

        customer_logger.info(f"=== PROCESSING LOG FOR CUSTOMER [{db}] {customer_code} ===")
        customer_logger.info(f"Processing Date: {current_date}")
        customer_logger.info(f"DB: {db}")
        customer_logger.info(f"Entity ID: {entity_id}")
        customer_logger.info(f"Migration LoadID: {load_id}")
        customer_logger.info(f"Migration SessionID: {session_id}")
        customer_logger.info(f"Log file: {log_path}")
        customer_logger.info(f"Error log: {error_log_path} (written only if errors occur)")
        customer_logger.info('=' * 60)

        return customer_logger

    def _attach_capture_handlers(self, handlers: List[logging.Handler]) -> None:
        """Mirror root-logger output into this customer's log files."""
        root_logger = logging.getLogger()

        # A previous customer that failed before cleanup could have left handlers
        # behind; drop any stragglers so logs never cross-contaminate.
        for stale in [h for h in root_logger.handlers if getattr(h, _CAPTURE_FLAG, False)]:
            root_logger.removeHandler(stale)

        for handler in handlers:
            setattr(handler, _CAPTURE_FLAG, True)
            root_logger.addHandler(handler)

        # basicConfig pins root at INFO; without this, records from module loggers
        # are dropped before any handler sees them.
        if root_logger.level > logging.INFO:
            root_logger.setLevel(logging.INFO)

    def cleanup_customer_logger(self, processor: Any, customer_logger: logging.Logger) -> None:
        if not customer_logger:
            return

        try:
            logger_name = customer_logger.name
            handlers_count = len(customer_logger.handlers)

            # Detach from root first. If this is skipped, the handlers stay live
            # and the next customer's output appends to this customer's log.
            root_logger = logging.getLogger()
            for handler in list(root_logger.handlers):
                if getattr(handler, _CAPTURE_FLAG, False):
                    root_logger.removeHandler(handler)

            for handler in customer_logger.handlers[:]:
                try:
                    handler.close()
                    customer_logger.removeHandler(handler)
                except Exception as handler_error:
                    processor.logger.warning(f"Error closing handler: {handler_error}")

            customer_logger.setLevel(logging.NOTSET)
            customer_logger.propagate = True
            processor.logger.debug(
                f"Successfully cleaned up customer logger '{logger_name}' ({handlers_count} handlers)"
            )
        except Exception as e:
            processor.logger.error(f"Error cleaning up customer logger: {e}")
