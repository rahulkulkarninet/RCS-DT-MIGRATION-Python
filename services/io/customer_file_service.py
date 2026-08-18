import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class CustomerFileService:
    """Handles customer file grouping, validation, and post-processing moves."""

    def extract_customer_code_from_filename(self, processor: Any, filename: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            parts = Path(filename).stem.split('_')
            if len(parts) >= 2:
                db = parts[0]
                customer_code = parts[1]
                return db, customer_code

            processor.logger.warning(f"Cannot extract db/customer code from filename: {filename}")
            return None, None
        except Exception as e:
            processor.logger.error(f"Error extracting db/customer code from {filename}: {e}")
            return None, None

    def group_files_by_customer(self, processor: Any) -> Dict[str, Dict[str, Any]]:
        staging_files = processor.staging_processor.get_staging_files()
        customer_groups: Dict[str, Dict[str, Any]] = defaultdict(lambda: {'db': None, 'files': []})
        unknown_customers: List[str] = []

        for file_path in staging_files:
            filename = os.path.basename(file_path)
            db, customer_code = self.extract_customer_code_from_filename(processor, filename)

            if customer_code:
                customer_groups[customer_code]['db'] = db
                customer_groups[customer_code]['files'].append(file_path)
            else:
                unknown_customers.append(filename)

        if unknown_customers:
            processor.logger.warning(f"Files with unknown customer codes: {unknown_customers}")

        processor.logger.info(f"Found files for {len(customer_groups)} customers")
        for customer_code, info in customer_groups.items():
            processor.logger.info(f"  [{info['db']}] {customer_code}: {len(info['files'])} files")

        return dict(customer_groups)

    def validate_customers_against_entity_mapping(
        self,
        processor: Any,
        customer_groups: Dict[str, Dict[str, Any]],
    ) -> Dict[str, bool]:
        validation_results: Dict[str, bool] = {}

        for customer_code, info in customer_groups.items():
            db = info.get('db')
            is_valid = customer_code in processor.entity_mapping
            validation_results[customer_code] = is_valid

            if is_valid:
                entity_id = processor.entity_mapping[customer_code]
                processor.logger.info(f"[SUCCESS] [{db}] Customer {customer_code} validated (Entity ID: {entity_id})")
            else:
                processor.logger.error(f"[{db}] Customer {customer_code} NOT FOUND in entity mapping")

        return validation_results

    def validate_customer_files(
        self,
        processor: Any,
        customer_code: str,
        db: str,
        files: List[str],
    ) -> Dict[str, Any]:
        validation_result: Dict[str, Any] = {
            'valid_files': [],
            'invalid_files': [],
            'valid_tables': [],
            'invalid_tables': [],
            'total_expected_rows': 0,
        }

        for file_path in files:
            try:
                _, table_name, _ = processor.staging_processor.match_file(file_path)

                if table_name:
                    validation_result['valid_files'].append(file_path)
                    if table_name not in validation_result['valid_tables']:
                        validation_result['valid_tables'].append(table_name)

                    try:
                        row_count = sum(1 for _ in open(file_path)) - 1
                        validation_result['total_expected_rows'] += row_count
                    except Exception:
                        pass
                else:
                    validation_result['invalid_files'].append(file_path)

            except Exception as e:
                validation_result['invalid_files'].append(file_path)
                processor.logger.warning(f"File validation failed for {file_path}: {e}")

        return validation_result

    def move_files_to_customer_folder(
        self,
        processor: Any,
        files: List[str],
        success: bool,
        rows_processed: int = 0,
        customer_paths: Dict[str, Path] = None,
        error_message: str = '',
    ) -> None:
        if not customer_paths:
            processor.logger.error('Customer paths not provided for file movement')
            return

        for file_path in files:
            try:
                source = Path(file_path)

                if success and rows_processed > 0:
                    destination = customer_paths['processed'] / source.name
                    shutil.move(str(source), str(destination))
                    processor.logger.info(f"Moved {source.name} to {customer_paths['processed']}")
                elif rows_processed == 0:
                    destination = customer_paths['no_data'] / source.name
                    shutil.move(str(source), str(destination))
                    processor.logger.warning(f"Moved no-data file {source.name} to {customer_paths['no_data']}")
                else:
                    destination = customer_paths['errors'] / source.name
                    shutil.move(str(source), str(destination))
                    processor.logger.error(f"Moved error file {source.name} to {customer_paths['errors']}")

            except Exception as e:
                processor.logger.error(f"Failed to move {file_path}: {e}")
