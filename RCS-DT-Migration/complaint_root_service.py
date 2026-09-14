from typing import Any, Dict, List, Tuple

import pandas as pd

import text_normalization

# CMP_Issue_1/2/3 are three independent occurrences of the same value domain in one
# staging table, the same shape as Payment_Method appearing across RC_PAYMENTS/RC_DEAL/
# RC_ARRANGEMENT in bank_transaction_method_service. Each is rewritten in place to the
# canonical tblComplaintRoot label, feeding 78.tblComplaint.sql / tblComplaintIssue.
#
# Table and column names are hardcoded identifiers, never user input, so interpolating
# them into SQL is safe and matches the rest of the repo.
SOURCE_TABLE = 'RC_COMPLAINT_EXTRACT'
SOURCE_COLUMNS: Tuple[str, ...] = ('CMP_Issue_1', 'CMP_Issue_2', 'CMP_Issue_3')

LOOKUP_TABLE = 'tblComplaintRoot'
LOOKUP_ID_COLUMN = 'ComplaintRootId'
LOOKUP_LABEL_COLUMN = 'RootCause'


class ComplaintRootService:
    """Encapsulates CMP_Issue_1/2/3 mapping, normalization, and validation logic.

    tblComplaintRoot's existing rows are an unrelated AFCA case-taxonomy seeded for a
    different client, so - like ComplainantService - there is no built-in catch-all to
    fall back to until a real tblComplaintRoot row exists for the fallback label.
    """

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    def load_complaint_root_mapping_frame(
        self,
        root_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        rows: List[Dict[str, str]] = []
        seen_codes = set()
        duplicate_codes = 0

        for label, codes in root_mapping.items():
            if not isinstance(codes, list):
                continue

            target_label = str(label).strip()
            normalized_target = text_normalization.normalize_lookup_key(target_label)

            for code in codes:
                if code is None:
                    continue

                normalized_code = text_normalization.normalize_lookup_key(code)
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
                        'source_key': text_normalization.match_key(normalized_code),
                        'target_label': target_label,
                        'normalized_target': normalized_target,
                        'target_key': text_normalization.match_key(normalized_target),
                    }
                )

        return pd.DataFrame(rows), duplicate_codes

    def read_lookup_frame(self) -> pd.DataFrame:
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=[LOOKUP_ID_COLUMN, LOOKUP_LABEL_COLUMN])

        lookup_frame = db_helper.execute_query(
            f"""
            SELECT {LOOKUP_ID_COLUMN},
                   CAST({LOOKUP_LABEL_COLUMN} AS NVARCHAR(4000)) AS {LOOKUP_LABEL_COLUMN}
            FROM {LOOKUP_TABLE}
            WHERE {LOOKUP_LABEL_COLUMN} IS NOT NULL
            """
        )
        if lookup_frame.empty or LOOKUP_LABEL_COLUMN not in lookup_frame.columns:
            return pd.DataFrame(columns=[LOOKUP_ID_COLUMN, LOOKUP_LABEL_COLUMN])

        lookup_frame[LOOKUP_LABEL_COLUMN] = (
            lookup_frame[LOOKUP_LABEL_COLUMN].astype(str).str.strip()
        )
        return lookup_frame[lookup_frame[LOOKUP_LABEL_COLUMN] != ''].copy()

    def source_table_exists(self) -> bool:
        """Not every customer has complaints, unlike RC_ACCOUNT_EXTRACT which always exists."""
        db_helper = self.db_helper
        if not db_helper:
            return False

        present = db_helper.execute_query(
            f"SELECT 1 AS found WHERE OBJECT_ID('{SOURCE_TABLE}') IS NOT NULL"
        )
        return not present.empty

    def read_source_issues(self) -> pd.DataFrame:
        """Distinct non-null, non-blank CMP_Issue_1/2/3 values, tagged by column."""
        db_helper = self.db_helper
        if not db_helper or not self.source_table_exists():
            return pd.DataFrame(columns=['source_column', 'raw_issue'])

        frames: List[pd.DataFrame] = []
        for column in SOURCE_COLUMNS:
            frame = db_helper.execute_query(
                f"""
                SELECT DISTINCT CAST({column} AS NVARCHAR(4000)) AS raw_issue
                FROM {SOURCE_TABLE}
                WHERE {column} IS NOT NULL
                  AND LTRIM(RTRIM({column})) <> ''
                """
            )
            if frame.empty or 'raw_issue' not in frame.columns:
                continue

            frame = frame.dropna(subset=['raw_issue'])
            frame['raw_issue'] = frame['raw_issue'].astype(str).str.strip()
            frame = frame[frame['raw_issue'] != ''].copy()
            if frame.empty:
                continue

            frame['source_column'] = column
            frames.append(frame[['source_column', 'raw_issue']])

        if not frames:
            return pd.DataFrame(columns=['source_column', 'raw_issue'])

        return pd.concat(frames, ignore_index=True)

    def build_complaint_root_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, List[str]]:
        """Returns (resolved values, distinct raw issue values with no tblComplaintRoot match)."""
        empty_columns = ['source_column', 'raw_issue', 'complaint_root_id']
        db_helper = self.db_helper
        if not db_helper:
            return pd.DataFrame(columns=empty_columns), []

        source_issues = self.read_source_issues()
        if source_issues.empty:
            return pd.DataFrame(columns=empty_columns), []

        lookup_frame = self.read_lookup_frame()
        if lookup_frame.empty:
            return (
                pd.DataFrame(columns=empty_columns),
                sorted(source_issues['raw_issue'].drop_duplicates().tolist()),
            )

        source_issues['normalized_issue'] = text_normalization.normalize_lookup_series(
            source_issues['raw_issue']
        )
        source_issues['issue_key'] = text_normalization.match_key_series(
            source_issues['normalized_issue']
        )

        lookup_frame['normalized_lookup'] = text_normalization.normalize_lookup_series(
            lookup_frame[LOOKUP_LABEL_COLUMN]
        )
        lookup_frame['issue_key'] = text_normalization.match_key_series(
            lookup_frame['normalized_lookup']
        )
        lookup_frame = lookup_frame.drop_duplicates(subset=['issue_key'], keep='first')

        resolved_frame = source_issues.merge(
            lookup_frame[['issue_key', LOOKUP_ID_COLUMN]].rename(
                columns={LOOKUP_ID_COLUMN: 'direct_root_id'}
            ),
            on='issue_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            mapping_frame[['source_key', 'target_key']] if not mapping_frame.empty
            else pd.DataFrame(columns=['source_key', 'target_key']),
            left_on='issue_key',
            right_on='source_key',
            how='left',
        )
        resolved_frame = resolved_frame.merge(
            lookup_frame[['issue_key', LOOKUP_ID_COLUMN]].rename(
                columns={'issue_key': 'target_key', LOOKUP_ID_COLUMN: 'mapped_root_id'}
            ),
            on='target_key',
            how='left',
        )

        resolved_frame['resolved_root_id'] = resolved_frame['mapped_root_id']
        resolved_frame.loc[
            resolved_frame['direct_root_id'].notna(),
            'resolved_root_id',
        ] = resolved_frame['direct_root_id']

        invalid_issues = sorted(
            resolved_frame.loc[
                resolved_frame['resolved_root_id'].isna(),
                'raw_issue',
            ]
            .drop_duplicates()
            .tolist()
        )

        resolution_frame = resolved_frame.loc[
            resolved_frame['resolved_root_id'].notna(),
            ['source_column', 'raw_issue', 'resolved_root_id'],
        ].drop_duplicates(ignore_index=True)
        resolution_frame = resolution_frame.rename(
            columns={'resolved_root_id': 'complaint_root_id'}
        )
        resolution_frame['complaint_root_id'] = resolution_frame['complaint_root_id'].astype(int)

        return resolution_frame, invalid_issues

    def bulk_update_complaint_roots(self, resolution_frame: pd.DataFrame) -> Dict[str, int]:
        db_helper = self.db_helper
        if not db_helper or not db_helper.pyodbc_connection or resolution_frame.empty:
            return {}

        rows_updated: Dict[str, int] = {}
        cursor = db_helper.pyodbc_connection.cursor()

        try:
            cursor.execute(
                "IF OBJECT_ID('tempdb..#ComplaintRootResolution') IS NOT NULL "
                'DROP TABLE #ComplaintRootResolution'
            )
            cursor.execute(
                """
                CREATE TABLE #ComplaintRootResolution (
                    source_column NVARCHAR(128) NOT NULL,
                    raw_issue NVARCHAR(4000) NOT NULL,
                    complaint_root_id INT NOT NULL
                )
                """
            )
            cursor.executemany(
                'INSERT INTO #ComplaintRootResolution '
                '(source_column, raw_issue, complaint_root_id) VALUES (?, ?, ?)',
                list(
                    resolution_frame[
                        ['source_column', 'raw_issue', 'complaint_root_id']
                    ].itertuples(index=False, name=None)
                ),
            )

            for column in resolution_frame['source_column'].drop_duplicates().tolist():
                cursor.execute(
                    f"""
                    UPDATE rc
                    SET rc.{column} = t.{LOOKUP_LABEL_COLUMN}
                    FROM {SOURCE_TABLE} AS rc
                    INNER JOIN #ComplaintRootResolution AS rr
                        ON CAST(rc.{column} AS NVARCHAR(4000)) = rr.raw_issue
                        AND rr.source_column = '{column}'
                    INNER JOIN {LOOKUP_TABLE} AS t
                        ON t.{LOOKUP_ID_COLUMN} = rr.complaint_root_id
                    WHERE rc.{column} <> t.{LOOKUP_LABEL_COLUMN}
                    """
                )
                cursor.execute('SELECT @@ROWCOUNT')
                row = cursor.fetchone()
                rows_updated[column] = int(row[0]) if row and row[0] is not None else 0

            cursor.execute('DROP TABLE #ComplaintRootResolution')

            db_helper.pyodbc_connection.commit()
            return rows_updated

        except Exception:
            db_helper.pyodbc_connection.rollback()
            raise
        finally:
            cursor.close()

    def get_invalid_complaint_roots_from_db(self) -> List[str]:
        """Post-update re-check: staging values with no tblComplaintRoot match."""
        db_helper = self.db_helper
        if not db_helper:
            return []

        source_issues = self.read_source_issues()
        if source_issues.empty:
            return []

        lookup_frame = self.read_lookup_frame()
        source_issues['issue_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(source_issues['raw_issue'])
        )

        if lookup_frame.empty:
            lookup_keys = set()
        else:
            lookup_keys = set(
                text_normalization.match_key_series(
                    text_normalization.normalize_lookup_series(
                        lookup_frame[LOOKUP_LABEL_COLUMN]
                    )
                )
                .dropna()
                .tolist()
            )

        invalid = source_issues[~source_issues['issue_key'].isin(lookup_keys)]
        return sorted(invalid['raw_issue'].drop_duplicates().tolist())
