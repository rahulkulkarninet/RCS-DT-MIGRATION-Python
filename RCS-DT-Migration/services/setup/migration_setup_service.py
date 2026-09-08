from datetime import datetime
from typing import Any, Dict, Optional


class MigrationSetupService:
    """Encapsulates migration setup/session/load lifecycle operations."""

    def load_entity_mapping(self, processor: Any) -> Dict[str, int]:
        try:
            if not processor.config_parser.db_helper:
                processor.logger.error('Database connection not available')
                return {}

            query = """
            SELECT
                Entity as Client_Description,
                EntityCode as Client_Code,
                EntityID as Entity_ID
            FROM tblentity
            WHERE Parent_EntityID IS NOT NULL
            ORDER BY EntityCode
            """

            result = processor.config_parser.db_helper.execute_query(query)

            if not result.empty:
                for _, row in result.iterrows():
                    entity_code = row['Client_Code']
                    entity_id = row['Entity_ID']
                    processor.entity_mapping[entity_code] = entity_id

                processor.logger.info(f"Loaded {len(processor.entity_mapping)} entity mappings")
            else:
                processor.logger.warning('No entity mappings found in tblEntity')

        except Exception as e:
            processor.logger.error(f'Error loading entity mapping: {e}')
            processor.entity_mapping = {}

        return processor.entity_mapping

    def reuse_migration_load_record(self, processor: Any, load_id: int,
                                    entity_id: int) -> Optional[str]:
        """Adopt an existing tblLoad row for a resumed run.
        """
        try:
            cursor = processor.pyodbc_conn.cursor()
            cursor.execute(
                'SELECT LoadID, EntityID FROM tblLoad WHERE LoadID = ?', int(load_id)
            )
            row = cursor.fetchone()
            cursor.close()

            if not row:
                processor.logger.error(
                    f'Cannot resume LoadID {load_id}: no such row in tblLoad'
                )
                return None

            found_entity = int(row[1]) if row[1] is not None else None
            if found_entity is not None and int(entity_id) != found_entity:
                processor.logger.error(
                    f'Refusing to resume LoadID {load_id}: it belongs to EntityID '
                    f'{found_entity}, but this customer maps to EntityID {entity_id}'
                )
                return None

            processor.logger.info(
                f'Resuming existing LoadID {load_id} for EntityID {entity_id}'
            )
            return str(int(row[0]))

        except Exception as e:
            processor.logger.error(f'Error adopting LoadID {load_id} for resume: {e}')
            try:
                cursor.close()
            except Exception:
                pass
            return None

    def create_migration_load_record(self, processor: Any, entity_id: int) -> str:
        try:
            insert_sql = f"""
            INSERT INTO tblLoad (LoadDescription, LoadTypeID, CreateID, CreateTS, EntityID)
            VALUES ('Migration Account Load', 0, 1, GETDATE(), {entity_id})
            """
            get_id_sql = 'SELECT SCOPE_IDENTITY() as LoadID'

            cursor = processor.pyodbc_conn.cursor()
            cursor.execute(insert_sql)
            cursor.execute(get_id_sql)
            result = cursor.fetchone()

            if result and result[0]:
                load_id = str(int(result[0]))
                processor.pyodbc_conn.commit()
                cursor.close()
                processor.logger.info(f'SUCCESS: Created new load record with LoadID: {load_id} for EntityID: {entity_id}')
                return load_id

            processor.logger.error('Failed to get LoadID after insert')
            processor.pyodbc_conn.rollback()
            cursor.close()
            return None

        except Exception as e:
            processor.logger.error(f'Error creating migration load record for EntityID {entity_id}: {e}')
            try:
                processor.pyodbc_conn.rollback()
            except Exception:
                pass
            try:
                cursor.close()
            except Exception:
                pass
            return None

    def rollback_load_record(self, processor: Any, load_id: str) -> bool:
        """Delete the tblLoad row, but only if it has no migrated rows behind it.
        """
        if not load_id:
            return True

        try:
            cursor = processor.pyodbc_conn.cursor()

            cursor.execute(
                'SELECT COUNT_BIG(*) FROM dbo.tblAccount WHERE LoadID = ?', (load_id,)
            )
            row = cursor.fetchone()
            migrated_accounts = int(row[0]) if row and row[0] is not None else 0

            if migrated_accounts:
                cursor.close()
                processor.logger.error(
                    f'NOT deleting LoadID {load_id}: {migrated_accounts} migrated '
                    f'account(s) already committed under it. Deleting the load row '
                    f'would leave them orphaned.'
                )
                processor.logger.error(
                    f'  Resume it:   Run_Migration.py <env> --resume-load-id {load_id}'
                )
                processor.logger.error(
                    f'  Discard it:  python tools/discard_load.py '
                    f'--load-id {load_id} --execute'
                )
                return False

            delete_sql = 'DELETE FROM tblLoad WHERE LoadID = ?'
            cursor.execute(delete_sql, (load_id,))
            rows_affected = cursor.rowcount

            if rows_affected > 0:
                processor.pyodbc_conn.commit()
                processor.logger.info(f'Successfully deleted LoadID {load_id} from tblLoad')
                cursor.close()
                return True

            processor.logger.warning(f'No rows affected when trying to delete LoadID {load_id}')
            cursor.close()
            return False

        except Exception as e:
            processor.logger.error(f'Error deleting LoadID {load_id}: {e}')
            try:
                processor.pyodbc_conn.rollback()
            except Exception:
                pass
            try:
                cursor.close()
            except Exception:
                pass
            return False

    def create_migration_session(self, processor: Any) -> int:
        try:
            insert_sql = """
            INSERT INTO tblSession
                ( ContactID ,
                  UserName ,
                  LoginTime ,
                  StatusID
                )
                SELECT  1 ,
                        'admin' ,
                        GETDATE() ,
                        1
            """
            get_id_sql = 'SELECT SCOPE_IDENTITY() as SessionID'

            cursor = processor.pyodbc_conn.cursor()
            cursor.execute(insert_sql)
            cursor.execute(get_id_sql)
            result = cursor.fetchone()

            if result and result[0]:
                session_id = int(result[0])
                processor.pyodbc_conn.commit()
                cursor.close()
                processor.logger.info(f'SUCCESS: Created migration session with SessionID: {session_id}')
                return session_id

            processor.logger.error('Failed to get SessionID after insert')
            processor.pyodbc_conn.rollback()
            cursor.close()
            return None

        except Exception as e:
            processor.logger.error(f'Error creating migration session: {e}')
            try:
                processor.pyodbc_conn.rollback()
            except Exception:
                pass
            try:
                cursor.close()
            except Exception:
                pass
            return None

    def close_migration_session(self, processor: Any, session_id: int) -> bool:
        if not session_id:
            return True

        try:
            update_sql = """
            UPDATE tblSession
            SET LogoutTime = GETDATE(),
                StatusID = 0
            WHERE SessionID = ?
            """

            cursor = processor.pyodbc_conn.cursor()
            cursor.execute(update_sql, (session_id,))
            rows_affected = cursor.rowcount

            if rows_affected > 0:
                processor.pyodbc_conn.commit()
                processor.logger.info(f'Successfully closed SessionID {session_id}')
                cursor.close()
                return True

            processor.logger.warning(f'No rows affected when trying to close SessionID {session_id}')
            cursor.close()
            return False

        except Exception as e:
            processor.logger.error(f'Error closing SessionID {session_id}: {e}')
            try:
                processor.pyodbc_conn.rollback()
            except Exception:
                pass
            try:
                cursor.close()
            except Exception:
                pass
            return False

    def setup_customer_migration(self, processor: Any, customer_code: str, db: str) -> Dict[str, Any]:
        current_user = processor.user
        staging_load_id = processor.generate_staging_load_id(customer_code, db)

        setup_result = {
            'customer_code': customer_code,
            'db': db,
            'staging_load_id': staging_load_id,
            'entity_id': None,
            'load_id': None,
            'session_id': None,
            'user': current_user,
            'setup_success': False,
            'error': None,
        }

        processor.processing_stats = []
        processor._migration_processing_stats = []
        # Anchor for the DT_Load_Total row written at the end of the SQL workflow. Taken
        # here rather than at the first staging table so the total covers entity
        # resolution, session/load creation and the staging truncate as well.
        processor.load_start_time = datetime.now()

        try:
            if not processor.set_entity_id_from_customer_code(customer_code):
                setup_result['error'] = f'[{db}] Customer {customer_code} not found in entity mapping'
                return setup_result

            setup_result['staging_load_id'] = staging_load_id
            processor.staging_load_id = staging_load_id
            setup_result['user'] = processor.user
            setup_result['entity_id'] = processor.entity_id

            session_id = self.create_migration_session(processor)
            if not session_id:
                setup_result['error'] = 'Failed to create migration session'
                return setup_result

            setup_result['session_id'] = session_id
            processor.current_session_id = session_id

            resume_load_id = getattr(processor, 'resume_load_id', None)
            if resume_load_id:
                load_id = self.reuse_migration_load_record(
                    processor, resume_load_id, processor.entity_id
                )
            else:
                load_id = self.create_migration_load_record(processor, processor.entity_id)
            if not load_id:
                self.close_migration_session(processor, session_id)
                setup_result['error'] = 'Failed to create migration load record'
                return setup_result

            setup_result['load_id'] = load_id
            processor.current_load_id = load_id

            if 'constant_variables' not in processor.config_parser.variables:
                processor.config_parser.variables['constant_variables'] = {}

            processor.config_parser.variables['constant_variables']['LoadID'] = int(load_id)
            processor.config_parser.variables['constant_variables']['CurrentSessionID'] = session_id
            processor.config_parser.variables['constant_variables']['StagingLoadID'] = processor.staging_load_id

            setup_result['setup_success'] = True
            processor.logger.info(
                f"Migration setup complete for [{db}] {customer_code}: LoadID={load_id}, SessionID={session_id}, "
                f"EntityID={processor.entity_id}, StagingLoadID={processor.staging_load_id}, User={processor.user}"
            )

        except Exception as e:
            setup_result['error'] = f'Unexpected error during setup: {e}'
            processor.logger.error(f'Error setting up migration for {customer_code}: {e}')

        return setup_result

    def cleanup_customer_migration(
        self,
        processor: Any,
        load_id: str = None,
        session_id: int = None,
        rollback: bool = False,
    ) -> bool:
        success = True

        load_id = load_id or processor.current_load_id
        session_id = session_id or processor.current_session_id

        try:
            if session_id:
                if not self.close_migration_session(processor, session_id):
                    success = False
                    processor.logger.warning(f'Failed to close SessionID {session_id}')

            if load_id and rollback:
                if not self.rollback_load_record(processor, load_id):
                    success = False
                    processor.logger.warning(f'Failed to rollback LoadID {load_id}')
            elif load_id:
                processor.logger.info(f'Keeping LoadID {load_id} (successful migration)')

            processor.current_load_id = None
            processor.current_session_id = None

            return success

        except Exception as e:
            processor.logger.error(f'Error during migration cleanup: {e}')
            return False
