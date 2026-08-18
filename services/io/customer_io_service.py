import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


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

        log_filename = f"processing_log_{db}_{customer_code}_{entity_id}_{load_id}_{session_id}.log"
        log_path = customer_paths['customer_root'] / log_filename

        file_handler = logging.FileHandler(log_path, mode='w')
        file_handler.setLevel(logging.INFO)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        customer_logger.addHandler(file_handler)
        customer_logger.addHandler(console_handler)
        customer_logger.propagate = False

        customer_logger.info(f"=== PROCESSING LOG FOR CUSTOMER [{db}] {customer_code} ===")
        customer_logger.info(f"Processing Date: {current_date}")
        customer_logger.info(f"DB: {db}")
        customer_logger.info(f"Entity ID: {entity_id}")
        customer_logger.info(f"Migration LoadID: {load_id}")
        customer_logger.info(f"Migration SessionID: {session_id}")
        customer_logger.info(f"Log file: {log_path}")
        customer_logger.info('=' * 60)

        return customer_logger

    def cleanup_customer_logger(self, processor: Any, customer_logger: logging.Logger) -> None:
        if not customer_logger:
            return

        try:
            logger_name = customer_logger.name
            handlers_count = len(customer_logger.handlers)

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
