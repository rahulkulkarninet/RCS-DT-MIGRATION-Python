from typing import Any, Dict, List, Tuple

import pandas as pd

import text_normalization

# Every RCS status code the config knows, and every tblAccountStatus label, with the
# AccountStatusID it resolves to. Rebuilt by the status mapping step on each run so the
# SQL batch can resolve a status code it meets in a pipe-delimited history
# (66.tblComplaint reads RC_ACCOUNT_EXTRACT.Status_history for the status an account
# had before its complaint). Status_Key is text_normalization.match_key of the code.
MAP_TABLE = 'RC_ACCOUNT_STATUS_MAP'
_MAP_INSERT_CHUNK = 500   # 3 parameters a row, well under the 2100-parameter limit


class StatusService:
    """Encapsulates MA_Status mapping, normalization, and validation logic."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    def load_account_status_mapping_frame(self, status_mapping: Dict[str, Any]) -> Tuple[pd.DataFrame, int]:
        rows: List[Dict[str, str]] = []
        seen_codes = set()
        duplicate_codes = 0

        for label, codes in status_mapping.items():
            if not isinstance(codes, list):
                continue

            target_label = str(label).strip()
            normalized_target = self.normalize_status_lookup_key(target_label)

            for code in codes:
                if code is None:
                    continue

                normalized_code = self.normalize_status_lookup_key(code)
                if not normalized_code:
                    continue

                if normalized_code in seen_codes:
                    duplicate_codes += 1
                    continue

                seen_codes.add(normalized_code)
                rows.append(
                    {
                        'source_code': str(code).strip(),
                        'normalized_source': normalized_code,
                        'source_key': self.status_match_key(normalized_code),
                        'target_label': target_label,
                        'normalized_target': normalized_target,
                        'target_key': self.status_match_key(normalized_target),
                    }
                )

        return pd.DataFrame(rows), duplicate_codes

    def build_ma_status_resolution_frame(self, mapping_frame: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=['raw_status', 'account_status_id']), []

        rc_statuses = db_helper.execute_query(
            """
            SELECT DISTINCT CAST(MA_Status AS NVARCHAR(4000)) AS raw_status
            FROM RC_ACCOUNT_EXTRACT
            WHERE MA_Status IS NOT NULL
            """
        )
        if rc_statuses.empty:
            return pd.DataFrame(columns=['raw_status', 'account_status_id']), []

        lookup_frame = db_helper.execute_query(
            """
            SELECT AccountStatusID, CAST(AccountStatus AS NVARCHAR(4000)) AS AccountStatus
            FROM tblAccountStatus
            WHERE AccountStatus IS NOT NULL
            """
        )
        if lookup_frame.empty:
            return pd.DataFrame(columns=['raw_status', 'account_status_id']), rc_statuses['raw_status'].tolist()

        rc_statuses['raw_status'] = rc_statuses['raw_status'].astype(str).str.strip()
        rc_statuses = rc_statuses[rc_statuses['raw_status'] != ''].copy()
        rc_statuses['normalized_status'] = self.normalize_status_lookup_series(rc_statuses['raw_status'])
        rc_statuses['status_key'] = self.status_match_key_series(rc_statuses['normalized_status'])

        lookup_frame['AccountStatus'] = lookup_frame['AccountStatus'].astype(str).str.strip()
        lookup_frame = lookup_frame[lookup_frame['AccountStatus'] != ''].copy()
        lookup_frame['normalized_lookup'] = self.normalize_status_lookup_series(lookup_frame['AccountStatus'])
        lookup_frame['status_key'] = self.status_match_key_series(lookup_frame['normalized_lookup'])
        lookup_frame = lookup_frame.drop_duplicates(subset=['status_key'], keep='first')

        resolved_frame = rc_statuses.merge(
            lookup_frame[['status_key', 'AccountStatusID']].rename(
                columns={'status_key': 'status_key', 'AccountStatusID': 'direct_account_status_id'}
            ),
            on='status_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            mapping_frame[['source_key', 'target_key']],
            left_on='status_key',
            right_on='source_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            lookup_frame[['status_key', 'AccountStatusID']].rename(
                columns={'status_key': 'target_key', 'AccountStatusID': 'mapped_account_status_id'}
            ),
            on='target_key',
            how='left',
        )

        resolved_frame['resolved_account_status_id'] = resolved_frame['mapped_account_status_id']
        resolved_frame.loc[
            resolved_frame['direct_account_status_id'].notna(),
            'resolved_account_status_id',
        ] = resolved_frame['direct_account_status_id']

        invalid_statuses = sorted(
            resolved_frame.loc[
                resolved_frame['resolved_account_status_id'].isna(),
                'raw_status',
            ]
            .drop_duplicates()
            .tolist()
        )

        resolution_frame = resolved_frame.loc[
            resolved_frame['resolved_account_status_id'].notna(),
            ['raw_status', 'resolved_account_status_id'],
        ].drop_duplicates(ignore_index=True)
        resolution_frame = resolution_frame.rename(columns={'resolved_account_status_id': 'account_status_id'})
        resolution_frame['account_status_id'] = resolution_frame['account_status_id'].astype(int)

        return resolution_frame, invalid_statuses

    def bulk_update_rc_account_extract_ma_status(self, resolution_frame: pd.DataFrame) -> int:
        db_helper = self.db_helper
        if not db_helper or not db_helper.pyodbc_connection or resolution_frame.empty:
            return 0

        cursor = db_helper.pyodbc_connection.cursor()

        try:
            # Shared sessions can process multiple customers; clear any prior temp table safely.
            cursor.execute("IF OBJECT_ID('tempdb..#StatusResolution') IS NOT NULL DROP TABLE #StatusResolution")
            cursor.execute(
                """
                CREATE TABLE #StatusResolution (
                    raw_status NVARCHAR(4000) NOT NULL,
                    account_status_id INT NOT NULL
                )
                """
            )
            cursor.executemany(
                "INSERT INTO #StatusResolution (raw_status, account_status_id) VALUES (?, ?)",
                list(resolution_frame[['raw_status', 'account_status_id']].itertuples(index=False, name=None)),
            )
            cursor.execute(
                """
                UPDATE rc
                SET rc.MA_Status = t.AccountStatus
                FROM RC_ACCOUNT_EXTRACT AS rc
                INNER JOIN #StatusResolution AS sr
                    ON CAST(rc.MA_Status AS NVARCHAR(4000)) = sr.raw_status
                INNER JOIN tblAccountStatus AS t
                    ON t.AccountStatusID = sr.account_status_id
                WHERE rc.MA_Status <> t.AccountStatus
                """
            )
            cursor.execute("SELECT @@ROWCOUNT")
            row = cursor.fetchone()
            total_rows_updated = int(row[0]) if row and row[0] is not None else 0

            cursor.execute("DROP TABLE #StatusResolution")

            db_helper.pyodbc_connection.commit()
            return total_rows_updated

        except Exception:
            db_helper.pyodbc_connection.rollback()
            raise
        finally:
            cursor.close()

    def build_status_code_map_frame(self, mapping_frame: pd.DataFrame) -> pd.DataFrame:
        """Rows for RC_ACCOUNT_STATUS_MAP: (Status_Code, Status_Key, AccountStatusID).

        A code that is itself an active tblAccountStatus label resolves to that row, as
        MA_Status does; otherwise to the label account_status_codes.json maps it to.
        """
        columns = ['Status_Code', 'Status_Key', 'AccountStatusID']
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=columns)

        lookup_frame = db_helper.execute_query(
            """
            SELECT AccountStatusID, CAST(AccountStatus AS NVARCHAR(4000)) AS AccountStatus
            FROM tblAccountStatus
            WHERE AccountStatus IS NOT NULL AND StatusID = 1
            """
        )
        if lookup_frame.empty:
            return pd.DataFrame(columns=columns)

        lookup_frame['AccountStatus'] = lookup_frame['AccountStatus'].astype(str).str.strip()
        lookup_frame = lookup_frame[lookup_frame['AccountStatus'] != ''].copy()
        lookup_frame['status_key'] = self.status_match_key_series(
            self.normalize_status_lookup_series(lookup_frame['AccountStatus'])
        )
        lookup_frame = lookup_frame.drop_duplicates(subset=['status_key'], keep='first')

        rows: List[Dict[str, Any]] = []
        for label, key, ident in lookup_frame[['AccountStatus', 'status_key', 'AccountStatusID']].itertuples(index=False, name=None):
            rows.append({'Status_Code': label, 'Status_Key': key, 'AccountStatusID': int(ident)})

        if not mapping_frame.empty and 'target_key' in mapping_frame.columns:
            mapped = mapping_frame.merge(
                lookup_frame[['status_key', 'AccountStatusID']].rename(columns={'status_key': 'target_key'}),
                on='target_key',
                how='inner',
            )
            for code, key, ident in mapped[['source_code', 'source_key', 'AccountStatusID']].itertuples(index=False, name=None):
                rows.append({'Status_Code': code, 'Status_Key': key, 'AccountStatusID': int(ident)})

        frame = pd.DataFrame(rows, columns=columns)
        frame = frame[frame['Status_Key'] != '']
        # A label wins over a config code that normalises to the same key (same rule as
        # MA_Status: the direct match is preferred).
        return frame.drop_duplicates(subset=['Status_Key'], keep='first').reset_index(drop=True)

    def write_status_code_map(self, frame: pd.DataFrame) -> int:
        """Create RC_ACCOUNT_STATUS_MAP if needed, then replace its rows. Returns rows written."""
        db_helper = self.db_helper
        if not db_helper or not getattr(db_helper, 'pyodbc_connection', None):
            return 0

        connection = db_helper.pyodbc_connection
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"IF OBJECT_ID(N'dbo.{MAP_TABLE}', N'U') IS NULL "
                f"CREATE TABLE dbo.{MAP_TABLE} ("
                "Status_Code NVARCHAR(400) NOT NULL, "
                "Status_Key NVARCHAR(400) NOT NULL PRIMARY KEY, "
                "AccountStatusID INT NOT NULL)"
            )
            cursor.execute(f'TRUNCATE TABLE dbo.{MAP_TABLE}')
            written = 0
            rows = [tuple(r) for r in frame[['Status_Code', 'Status_Key', 'AccountStatusID']].itertuples(index=False, name=None)]
            for start in range(0, len(rows), _MAP_INSERT_CHUNK):
                chunk = rows[start:start + _MAP_INSERT_CHUNK]
                placeholders = ', '.join(['(?, ?, ?)'] * len(chunk))
                params = [v for row in chunk for v in (str(row[0]), str(row[1]), int(row[2]))]
                cursor.execute(
                    f'INSERT INTO dbo.{MAP_TABLE} (Status_Code, Status_Key, AccountStatusID) VALUES {placeholders}',
                    params,
                )
                written += len(chunk)
            connection.commit()
            return written
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()

    def get_invalid_ma_statuses_from_db(self) -> List[str]:
        db_helper = self.db_helper
        if not db_helper:
            return []

        rc_statuses = db_helper.execute_query(
            """
            SELECT DISTINCT CAST(MA_Status AS NVARCHAR(4000)) AS MA_Status
            FROM RC_ACCOUNT_EXTRACT
            WHERE MA_Status IS NOT NULL
            """
        )
        lookup_statuses = db_helper.execute_query(
            """
            SELECT DISTINCT CAST(AccountStatus AS NVARCHAR(4000)) AS AccountStatus
            FROM tblAccountStatus
            WHERE AccountStatus IS NOT NULL
            """
        )

        if rc_statuses.empty or 'MA_Status' not in rc_statuses.columns:
            return []

        if lookup_statuses.empty or 'AccountStatus' not in lookup_statuses.columns:
            return (
                rc_statuses['MA_Status']
                .dropna()
                .astype(str)
                .str.strip()
                .loc[lambda s: s != '']
                .drop_duplicates()
                .tolist()
            )

        rc_statuses['MA_Status'] = rc_statuses['MA_Status'].astype(str).str.strip()
        lookup_statuses['AccountStatus'] = lookup_statuses['AccountStatus'].astype(str).str.strip()

        rc_statuses['normalized'] = self.normalize_status_lookup_series(rc_statuses['MA_Status'])
        lookup_statuses['normalized'] = self.normalize_status_lookup_series(lookup_statuses['AccountStatus'])

        rc_statuses['status_key'] = self.status_match_key_series(rc_statuses['normalized'])
        lookup_statuses['status_key'] = self.status_match_key_series(lookup_statuses['normalized'])

        lookup_keys = set(lookup_statuses['status_key'].dropna().tolist())
        invalid = rc_statuses[~rc_statuses['status_key'].isin(lookup_keys)]

        return (
            invalid['MA_Status']
            .dropna()
            .astype(str)
            .str.strip()
            .loc[lambda s: s != '']
            .drop_duplicates()
            .tolist()
        )

    # Normalization now lives in text_normalization so the bank transaction method
    # mapping can share the same rules. These stay as methods for existing callers.
    def status_match_key(self, value: str) -> str:
        return text_normalization.match_key(value)

    def status_match_key_series(self, series: pd.Series) -> pd.Series:
        return text_normalization.match_key_series(series)

    def normalize_status_lookup_key(self, value: str) -> str:
        return text_normalization.normalize_lookup_key(value)

    def normalize_status_lookup_series(self, series: pd.Series) -> pd.Series:
        return text_normalization.normalize_lookup_series(series)
