

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import text_normalization


OPERATOR_SOURCES: Tuple[Tuple[str, str], ...] = (
    ('RC_ACCOUNT_EXTRACT', 'Operator'),
    ('RC_PAYMENTS', 'Payment_Operator'),
    ('RC_SMS', 'Operator_Code'),
    ('RC_EMAIL_EXTRACT', 'Op_code'),
    ('RC_DOCHIST_EXTRACT', 'Operator_Code'),
    ('RC_NOTES_EXTRACT', 'Operator'),
)

LOOKUP_TABLE = 'tblContact'
LOOKUP_ID_COLUMN = 'ContactID'
LOOKUP_LABEL_COLUMN = 'UserName'


FALLBACK_VARIABLE = 'DefaultOperatorContactID'

FALLBACK_CONTACT_ID_DEFAULT = 1


_CLEAN = "LTRIM(RTRIM(REPLACE(CAST([{column}] AS NVARCHAR(4000)), NCHAR(160), ' ')))"


class OperatorContactService:
    """Encapsulates operator code mapping, normalization, and validation logic."""

    def __init__(self, db_helper: Any):
        self.db_helper = db_helper

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def load_operator_mapping_frame(
        self,
        contact_mapping: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, int]:
        """One row per configured operator code.

        Takes the whole parsed file, the way the other domains do. Keys whose value is
        not a list are skipped, which is what lets the file carry `_comment` notes
        beside the mappings.

        Returns (frame, duplicate_codes). A code listed under two usernames is counted
        as a duplicate and the first wins, matching the way the other domains treat a
        code listed twice.
        """
        rows: List[Dict[str, str]] = []
        seen_codes = set()
        duplicate_codes = 0

        for label, codes in contact_mapping.items():
            if not isinstance(codes, list):
                continue

            contact_label = str(label).strip()
            if not contact_label:
                continue

            for code in codes:
                if code is None:
                    continue

                source_code = str(code).strip()
                if not source_code:
                    continue

                code_key = text_normalization.match_key(source_code)
                if not code_key:
                    continue
                if code_key in seen_codes:
                    duplicate_codes += 1
                    continue

                seen_codes.add(code_key)
                rows.append(
                    {
                        'source_code': source_code,
                        'code_key': code_key,
                        'contact_label': contact_label,
                        'contact_key': text_normalization.match_key(
                            text_normalization.normalize_lookup_key(contact_label)
                        ),
                    }
                )

        columns = ['source_code', 'code_key', 'contact_label', 'contact_key']
        return pd.DataFrame(rows, columns=columns), duplicate_codes

    # ------------------------------------------------------------------
    # Database reads
    # ------------------------------------------------------------------

    def get_existing_sources(self) -> List[Tuple[str, str]]:
        """The (table, column) pairs this environment actually has."""
        db_helper = self.db_helper
        if not db_helper:
            return []

        existing = []
        for table, column in OPERATOR_SOURCES:
            present = db_helper.execute_query(
                f"""
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = '{table}'
                  AND COLUMN_NAME = '{column}'
                """
            )
            if not present.empty:
                existing.append((table, column))
        return existing

    def read_lookup_frame(self) -> Tuple[pd.DataFrame, List[str]]:
        """UserName -> ContactID, plus the usernames more than one contact holds.

        UserName is not unique - deactivated and re-created users leave two rows
        behind. The pick is made explicit rather than left to row order: an active
        contact (StatusID 1) wins over an inactive one, and the lowest ContactID wins
        between equals, which is the same rule the OUTER APPLY in the migration SQL
        applies. Every username that needed the tie-break is returned so the check can
        name it, because a mapping resolved by tie-break is one somebody should
        confirm.
        """
        empty = pd.DataFrame(
            columns=[LOOKUP_ID_COLUMN, LOOKUP_LABEL_COLUMN, 'lookup_key']
        )

        db_helper = self.db_helper
        if not db_helper:
            return empty, []

        lookup_frame = db_helper.execute_query(
            f"""
            SELECT {LOOKUP_ID_COLUMN},
                   CAST({LOOKUP_LABEL_COLUMN} AS NVARCHAR(4000)) AS {LOOKUP_LABEL_COLUMN},
                   ISNULL(StatusID, 0) AS StatusID
            FROM {LOOKUP_TABLE} WITH (NOLOCK)
            WHERE {LOOKUP_LABEL_COLUMN} IS NOT NULL
            ORDER BY CASE WHEN ISNULL(StatusID, 0) = 1 THEN 0 ELSE 1 END,
                     {LOOKUP_ID_COLUMN}
            """
        )
        if lookup_frame.empty or LOOKUP_LABEL_COLUMN not in lookup_frame.columns:
            return empty, []

        lookup_frame = lookup_frame.dropna(subset=[LOOKUP_LABEL_COLUMN])
        lookup_frame[LOOKUP_LABEL_COLUMN] = text_normalization.normalize_text_series(
            lookup_frame[LOOKUP_LABEL_COLUMN].astype(str)
        )
        lookup_frame = lookup_frame[lookup_frame[LOOKUP_LABEL_COLUMN] != ''].copy()
        if lookup_frame.empty:
            return empty, []

        lookup_frame['lookup_key'] = text_normalization.match_key_series(
            text_normalization.normalize_lookup_series(
                lookup_frame[LOOKUP_LABEL_COLUMN]
            )
        )

        duplicate_keys = lookup_frame.loc[
            lookup_frame.duplicated(subset=['lookup_key'], keep=False), 'lookup_key'
        ].unique()

        # The ORDER BY above is what 'first' means here, so the tie-break is the
        # query's, not pandas' arrival order.
        resolved = lookup_frame.drop_duplicates(subset=['lookup_key'], keep='first')

        ambiguous = sorted(
            resolved.loc[
                resolved['lookup_key'].isin(duplicate_keys), LOOKUP_LABEL_COLUMN
            ].tolist()
        )
        return resolved, ambiguous

    def read_source_operator_codes(self) -> Dict[str, Dict[str, int]]:
        """code -> {extract column: rows carrying it}, across every present source.

        Read from the extracts rather than assumed. This is what makes the JSON
        maintainable without CSRC_OperatorContactMapping: the codes come from the data
        the customer actually sent. Counted before the retention filter in
        01.tblaccount runs, so a code appearing only on excluded accounts is still
        listed - over-reporting is a note for a human, missing one would defeat the
        check.
        """
        db_helper = self.db_helper
        if not db_helper:
            return {}

        selects = []
        for table, column in self.get_existing_sources():
            cleaned = _CLEAN.format(column=column)
            selects.append(
                f"""
                SELECT '{table}.{column}' AS SourceColumn,
                       {cleaned} AS OperatorCode,
                       COUNT_BIG(*) AS RowCount_
                FROM {table} WITH (NOLOCK)
                WHERE {cleaned} <> ''
                GROUP BY {cleaned}
                """
            )

        if not selects:
            return {}

        frame = db_helper.execute_query('UNION ALL'.join(selects))
        if frame.empty or 'OperatorCode' not in frame.columns:
            return {}

        found: Dict[str, Dict[str, int]] = {}
        for row in frame.itertuples(index=False):
            code = str(row.OperatorCode).strip()
            if not code:
                continue
            found.setdefault(code, {})[str(row.SourceColumn)] = int(row.RowCount_)
        return found

    def describe_contact(self, contact_id: Optional[int]) -> str:
        """'197 (PRAM)' for a log line, or just the id if it names no contact.

        The fallback is configured by username and resolved to an id per environment,
        so a message that prints only the id makes the reader look it up, and one that
        prints only the username hides a lookup that silently defaulted.
        """
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

    def get_column_widths(self) -> Dict[str, Optional[int]]:
        """'table.column' -> declared character length, for the width pre-flight."""
        db_helper = self.db_helper
        if not db_helper:
            return {}

        widths: Dict[str, Optional[int]] = {}
        for table, column in self.get_existing_sources():
            frame = db_helper.execute_query(
                f"""
                SELECT CHARACTER_MAXIMUM_LENGTH
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = '{table}'
                  AND COLUMN_NAME = '{column}'
                """
            )
            if frame.empty:
                continue
            value = frame.iloc[0, 0]
            widths[f'{table}.{column}'] = (
                None if pd.isna(value) else int(value)
            )
        return widths

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def build_operator_resolution_frame(
        self,
        mapping_frame: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
        """Resolve every configured code to the canonical tblContact.UserName.

        The canonical *text* rather than the ContactID, because the rewrite writes the
        username back into the extract and the SQL resolves the ID. Returns
        (resolution_frame, problems) where problems collects, by kind:
          unresolved_contacts  JSON username absent from tblContact.UserName
          ambiguous_contacts   JSON username held by more than one contact
        Both are about the config, not the data.
        """
        empty_columns = ['source_code', 'contact_label', 'canonical_username']
        problems: Dict[str, List[str]] = {
            'unresolved_contacts': [],
            'ambiguous_contacts': [],
        }

        db_helper = self.db_helper
        if not db_helper or mapping_frame.empty:
            return pd.DataFrame(columns=empty_columns), problems

        contacts, ambiguous = self.read_lookup_frame()

        if contacts.empty:
            merge_frame = pd.DataFrame(columns=['contact_key', 'canonical_username'])
        else:
            merge_frame = contacts[['lookup_key', LOOKUP_LABEL_COLUMN]].rename(
                columns={
                    'lookup_key': 'contact_key',
                    LOOKUP_LABEL_COLUMN: 'canonical_username',
                }
            )

        resolved = mapping_frame.merge(merge_frame, on='contact_key', how='left')

        problems['unresolved_contacts'] = sorted(
            resolved.loc[resolved['canonical_username'].isna(), 'contact_label']
            .drop_duplicates()
            .tolist()
        )

        configured_keys = set(mapping_frame['contact_key'].tolist())
        problems['ambiguous_contacts'] = sorted(
            label for label in ambiguous
            if text_normalization.match_key(
                text_normalization.normalize_lookup_key(label)
            ) in configured_keys
        )

        usable = resolved[resolved['canonical_username'].notna()]
        if usable.empty:
            return pd.DataFrame(columns=empty_columns), problems

        return usable[empty_columns].drop_duplicates(ignore_index=True), problems

    def check_source_column_fits(
        self,
        resolution_frame: pd.DataFrame,
    ) -> List[str]:
        """Operator columns too narrow for the usernames the rewrite would write.

        The frequency domain's pre-flight, for the same reason: an UPDATE that will not
        fit should say so with the ALTER that fixes it, rather than failing mid-rewrite
        on a truncation error. Only the configured usernames matter - nothing else is
        written. The longest username in use on testse is 42 characters and the
        narrowest operator column is NVARCHAR(50), so this is expected to pass.
        """
        if resolution_frame.empty:
            return []

        longest = int(
            resolution_frame['canonical_username'].astype(str).str.len().max()
        )
        problems = []
        for qualified, width in self.get_column_widths().items():
            if width is None or width < 0:
                continue
            if width < longest:
                table, column = qualified.split('.', 1)
                problems.append(
                    f'{qualified} is NVARCHAR({width}) but the longest username it '
                    f'must hold is {longest} characters. Run: ALTER TABLE {table} '
                    f'ALTER COLUMN {column} NVARCHAR(100) NULL;'
                )
        return problems

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def bulk_update_operator_codes(
        self,
        resolution_frame: pd.DataFrame,
    ) -> Dict[str, int]:
        """Rewrite each configured operator code to its canonical username, in place.

        Only codes the file lists are touched. Anything else keeps the value the
        extract shipped, which is what lets a code that is already a username resolve
        on its own and everything else take the SQL's fallback contact.

        One temp table and one UPDATE per source, mirroring
        BankTransactionMethodService.bulk_update_payment_methods. All of it shares a
        transaction, so a failure part-way leaves every extract as it was.
        """
        db_helper = self.db_helper
        if not db_helper or not db_helper.pyodbc_connection or resolution_frame.empty:
            return {}

        rows_updated: Dict[str, int] = {}
        cursor = db_helper.pyodbc_connection.cursor()

        try:
            # Shared sessions can process multiple customers; clear any prior temp
            # table safely.
            cursor.execute(
                "IF OBJECT_ID('tempdb..#OperatorContactResolution') IS NOT NULL "
                'DROP TABLE #OperatorContactResolution'
            )
            cursor.execute(
                """
                CREATE TABLE #OperatorContactResolution (
                    source_code NVARCHAR(4000) NOT NULL,
                    canonical_username NVARCHAR(50) NOT NULL
                )
                """
            )
            cursor.executemany(
                'INSERT INTO #OperatorContactResolution '
                '(source_code, canonical_username) VALUES (?, ?)',
                list(
                    resolution_frame[['source_code', 'canonical_username']]
                    .astype(str)
                    .itertuples(index=False, name=None)
                ),
            )

            for table, column in self.get_existing_sources():
                cursor.execute(
                    f"""
                    UPDATE rc
                    SET rc.[{column}] = r.canonical_username
                    FROM {table} AS rc
                    INNER JOIN #OperatorContactResolution AS r
                        ON LTRIM(RTRIM(REPLACE(
                               CAST(rc.[{column}] AS NVARCHAR(4000)),
                               NCHAR(160), ' '))) = r.source_code
                    WHERE CAST(rc.[{column}] AS NVARCHAR(4000)) <> r.canonical_username
                    """
                )
                cursor.execute('SELECT @@ROWCOUNT')
                row = cursor.fetchone()
                rows_updated[f'{table}.{column}'] = (
                    int(row[0]) if row and row[0] is not None else 0
                )

            cursor.execute('DROP TABLE #OperatorContactResolution')

            db_helper.pyodbc_connection.commit()
            return rows_updated

        except Exception:
            db_helper.pyodbc_connection.rollback()
            raise
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Post-update re-check
    # ------------------------------------------------------------------

    def get_unresolved_operator_codes_from_db(self) -> List[str]:
        """Operator codes left with no tblContact.UserName match, busiest first.

        Read back after the rewrite rather than derived from the resolution frame, so
        it reflects what the migration SQL will actually find. These are not errors -
        each is attributed to ContactID 1 by the SQL's ISNULL, exactly as before this
        step existed. This is the list a human works from when the fallback is the
        wrong answer for a code.
        """
        db_helper = self.db_helper
        if not db_helper:
            return []

        source_codes = self.read_source_operator_codes()
        if not source_codes:
            return []

        contacts, _ = self.read_lookup_frame()
        username_keys = (
            set() if contacts.empty else set(contacts['lookup_key'].tolist())
        )

        unresolved = []
        for code, sources in source_codes.items():
            if text_normalization.match_key(code) in username_keys:
                continue
            where = ', '.join(
                f'{source} {count} row(s)'
                for source, count in sorted(sources.items())
            )
            unresolved.append((sum(sources.values()), f'{code} ({where})'))

        # Busiest first, not alphabetical. On testse 557 of the 564 codes the extracts
        # carry resolve to nothing, so an alphabetical list buries APP (532,345 rows)
        # among hundreds of codes with one. Volume is what decides whether the
        # fallback contact is worth replacing for a code, so it decides the order.
        unresolved.sort(key=lambda entry: (-entry[0], entry[1]))
        return [description for _, description in unresolved]
