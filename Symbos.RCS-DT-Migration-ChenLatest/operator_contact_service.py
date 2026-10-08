

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# The one extract this service maps. Operator is read, never written, so staging and
# its archive keep the code the customer sent; the resolved contact goes in
# Operator_ContactID, a derived column of the staging schema, which 01.tblaccount takes
# as AccountManager_ContactID. The other operator columns (RC_SMS, RC_EMAIL_EXTRACT,
# RC_DOCHIST_EXTRACT, RC_NOTES_EXTRACT) are not mapped: their SQL keeps its own
# UserName lookup and falls back to {{DefaultOperatorContactID}}.
SOURCE_TABLE = 'RC_ACCOUNT_EXTRACT'
SOURCE_COLUMN = 'Operator'
TARGET_COLUMN = 'Operator_ContactID'
SCHEMA_FILE = 'RC_ACCOUNT_EXTRACT Schema.sql'

LOOKUP_TABLE = 'tblContact'
LOOKUP_ID_COLUMN = 'ContactID'
LOOKUP_LABEL_COLUMN = 'UserName'
LOOKUP_REF_COLUMN = 'Z_REF'

# Users are set up with an email UserName and their legacy operator code in Z_REF, so
# the default contact is named by Z_REF too. The same contact is what
# {{DefaultOperatorContactID}} resolves to in migration_variables.json, which is the
# fallback every other operator lookup in the SQL uses.
DEFAULT_OPERATOR_Z_REF = 'TEMS'

FALLBACK_VARIABLE = 'DefaultOperatorContactID'

FALLBACK_CONTACT_ID_DEFAULT = 1


_CLEAN = "LTRIM(RTRIM(REPLACE(CAST({column} AS NVARCHAR(4000)), NCHAR(160), ' ')))"

# Active contact first, lowest ContactID between equals - the tie-break the OUTER
# APPLY in the migration SQL uses for UserName, applied to Z_REF as well.
_PICK_ORDER = (
    f'CASE WHEN ISNULL(C.StatusID, 0) = 1 THEN 0 ELSE 1 END, C.{LOOKUP_ID_COLUMN}'
)


class OperatorContactService:
    """Maps RC_ACCOUNT_EXTRACT.Operator to a tblContact user by Z_REF."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    # ------------------------------------------------------------------
    # Database reads
    # ------------------------------------------------------------------

    def resolve_default_contact(self) -> Optional[Tuple[int, str]]:
        """(ContactID, UserName) of the user whose Z_REF is DEFAULT_OPERATOR_Z_REF."""
        db_helper = self.db_helper
        if not db_helper:
            return None

        frame = db_helper.execute_query(
            f"""
            SELECT TOP 1 C.{LOOKUP_ID_COLUMN},
                   CAST(C.{LOOKUP_LABEL_COLUMN} AS NVARCHAR(4000)) AS {LOOKUP_LABEL_COLUMN}
            FROM {LOOKUP_TABLE} C WITH (NOLOCK)
            WHERE C.{LOOKUP_REF_COLUMN} = '{DEFAULT_OPERATOR_Z_REF}'
              AND C.{LOOKUP_LABEL_COLUMN} IS NOT NULL
            ORDER BY {_PICK_ORDER}
            """
        )
        if frame.empty or frame.iloc[0, 1] is None:
            return None
        return int(frame.iloc[0, 0]), str(frame.iloc[0, 1])

    def _column_exists(self, column: str) -> bool:
        db_helper = self.db_helper
        if not db_helper:
            return False

        present = db_helper.execute_query(
            f"""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{SOURCE_TABLE}'
              AND COLUMN_NAME = '{column}'
            """
        )
        return not present.empty

    def source_exists(self) -> bool:
        return self._column_exists(SOURCE_COLUMN)

    def target_column_exists(self) -> bool:
        """False in an environment whose staging schema predates Operator_ContactID."""
        return self._column_exists(TARGET_COLUMN)

    def read_account_operator_resolution(self) -> pd.DataFrame:
        """One row per operator code in the account extract, busiest first.

        Columns: OperatorCode, RowCount_, ContactID / UserName (the Z_REF match, NULL
        if none), ZRefHolders (users carrying that Z_REF - more than one means the
        tie-break picked).
        """
        empty = pd.DataFrame(
            columns=['OperatorCode', 'RowCount_', 'ContactID', 'UserName',
                     'ZRefHolders']
        )
        db_helper = self.db_helper
        if not db_helper or not self.source_exists():
            return empty

        cleaned = _CLEAN.format(column=f'RC.[{SOURCE_COLUMN}]')
        frame = db_helper.execute_query(
            f"""
            WITH Codes AS (
                SELECT ISNULL({cleaned}, '') AS OperatorCode,
                       COUNT_BIG(*) AS RowCount_
                FROM {SOURCE_TABLE} RC WITH (NOLOCK)
                GROUP BY ISNULL({cleaned}, '')
            )
            SELECT K.OperatorCode,
                   K.RowCount_,
                   Z.{LOOKUP_ID_COLUMN},
                   Z.{LOOKUP_LABEL_COLUMN},
                   ISNULL(Z.Holders, 0) AS ZRefHolders
            FROM Codes K
            OUTER APPLY ( SELECT TOP 1
                                 C.{LOOKUP_ID_COLUMN},
                                 CAST(C.{LOOKUP_LABEL_COLUMN} AS NVARCHAR(4000))
                                     AS {LOOKUP_LABEL_COLUMN},
                                 COUNT(*) OVER () AS Holders
                          FROM {LOOKUP_TABLE} C WITH (NOLOCK)
                          WHERE K.OperatorCode <> ''
                            AND C.{LOOKUP_REF_COLUMN} = K.OperatorCode
                            AND C.{LOOKUP_LABEL_COLUMN} IS NOT NULL
                          ORDER BY {_PICK_ORDER}
                        ) Z
            ORDER BY K.RowCount_ DESC, K.OperatorCode
            """
        )
        if frame.empty or 'OperatorCode' not in frame.columns:
            return empty
        return frame

    def describe_contact(self, contact_id: Optional[int]) -> str:
        """'150849 (temoului_soro@...)' for a log line, or just the id if it names no contact."""
        if contact_id is None:
            return 'unknown'

        db_helper = self.db_helper
        if not db_helper:
            return str(contact_id)

        frame = db_helper.execute_query(
            f"""
            SELECT CAST({LOOKUP_LABEL_COLUMN} AS NVARCHAR(4000)) AS {LOOKUP_LABEL_COLUMN}
            FROM {LOOKUP_TABLE} WITH (NOLOCK)
            WHERE {LOOKUP_ID_COLUMN} = {int(contact_id)}
            """
        )
        if frame.empty or frame.iloc[0, 0] is None:
            return f'{contact_id} (no such contact)'

        username = str(frame.iloc[0, 0]).strip()
        return f'{contact_id} ({username})' if username else str(contact_id)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def assign_account_operator_contacts(self, default_contact_id: int) -> int:
        """Fill RC_ACCOUNT_EXTRACT.Operator_ContactID from the Operator code.

        The user whose Z_REF is the cleaned code, else default_contact_id (blank and
        NULL included). Operator is only read, so a re-run lands on the same values.
        Only rows whose ContactID changes are written. Returns the rows updated.
        """
        db_helper = self.db_helper
        if not db_helper or not db_helper.pyodbc_connection or not self.source_exists():
            return 0

        cleaned = _CLEAN.format(column=f'RC.[{SOURCE_COLUMN}]')
        cursor = db_helper.pyodbc_connection.cursor()
        try:
            cursor.execute(
                f"""
                UPDATE RC
                SET RC.[{TARGET_COLUMN}] = T.ContactID
                FROM {SOURCE_TABLE} AS RC
                CROSS APPLY ( SELECT ISNULL({cleaned}, '') AS Code ) K
                OUTER APPLY ( SELECT TOP 1 C.{LOOKUP_ID_COLUMN}
                              FROM {LOOKUP_TABLE} C WITH (NOLOCK)
                              WHERE K.Code <> ''
                                AND C.{LOOKUP_REF_COLUMN} = K.Code
                                AND C.{LOOKUP_LABEL_COLUMN} IS NOT NULL
                              ORDER BY {_PICK_ORDER}
                            ) Z
                CROSS APPLY ( SELECT ISNULL(Z.{LOOKUP_ID_COLUMN}, CAST(? AS INT))
                                         AS ContactID ) T
                WHERE RC.[{TARGET_COLUMN}] IS NULL
                   OR RC.[{TARGET_COLUMN}] <> T.ContactID
                """,
                int(default_contact_id),
            )
            cursor.execute('SELECT @@ROWCOUNT')
            row = cursor.fetchone()
            rows_updated = int(row[0]) if row and row[0] is not None else 0
            db_helper.pyodbc_connection.commit()
            return rows_updated

        except Exception:
            db_helper.pyodbc_connection.rollback()
            raise
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @staticmethod
    def summarise_resolution(frame: pd.DataFrame) -> Dict[str, Any]:
        """Split a read_account_operator_resolution frame for the log and result.

        defaulted   codes taking the default contact, busiest first with row counts
        ambiguous   Z_REFs held by more than one user (the tie-break picked)
        matched     codes resolved by Z_REF
        """
        defaulted: List[str] = []
        ambiguous: List[str] = []
        matched = 0

        for row in frame.itertuples(index=False):
            code = str(row.OperatorCode)
            count = int(row.RowCount_)
            has_match = row.UserName is not None and not pd.isna(row.UserName)
            if has_match:
                matched += 1
                if int(row.ZRefHolders) > 1:
                    ambiguous.append(f'{code} -> {row.UserName}')
            else:
                label = code if code else '(blank)'
                defaulted.append(f'{label} ({SOURCE_TABLE}.{SOURCE_COLUMN} {count} row(s))')

        return {'defaulted': defaulted, 'ambiguous': sorted(ambiguous), 'matched': matched}

    def get_unresolved_operator_codes_from_db(self) -> List[str]:
        """Account operator codes that will take the default contact, busiest first."""
        return self.summarise_resolution(
            self.read_account_operator_resolution()
        )['defaulted']
