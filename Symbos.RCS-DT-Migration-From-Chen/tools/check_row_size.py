

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TOOLS_DIR)

from db_manager import DatabaseHelper  # noqa: E402
from env_target import resolve_environment  # noqa: E402

# A row must fit one 8 KB page less the page header.
ROW_LIMIT = 8060


ROW_OVERFLOW_POINTER = 24
LOB_ROOT = 16

# Fixed-length types always occupy their full width, whether or not the column
# is null; only the null bitmap records that it was null.
FIXED_TYPE_BYTES = {
    'bit': 1, 'tinyint': 1, 'smallint': 2, 'int': 4, 'bigint': 8,
    'real': 4, 'float': 8, 'smallmoney': 4, 'money': 8,
    'date': 3, 'smalldatetime': 4, 'datetime': 8, 'time': 5,
    'datetime2': 8, 'datetimeoffset': 10, 'uniqueidentifier': 16,
}
LENGTH_TYPE_BYTES_PER_CHAR = {
    'char': 1, 'varchar': 1, 'binary': 1, 'varbinary': 1,
    'nchar': 2, 'nvarchar': 2,
}

DEFAULT_SCHEMA_DIR = os.path.join(REPO_ROOT, 'SQL', 'Schemas')
DEFAULT_VARIABLES_DIR = os.path.join(REPO_ROOT, 'variables')

# The loader picks up '*RC_*.csv' (process_staging.get_staging_files), so a file
# whose name does not carry the table name is not extract data for it - the
# field dictionaries alongside the extracts are wider than any real row and are
# never read.
CSV_PATH_TEMPLATE_FALLBACK = '//{server}/{share}/Debtrak/'

# A dictionary column can hold a whole field list on one line.
csv.field_size_limit(50 * 1024 * 1024)

_CREATE_TABLE_RE = re.compile(
    r'CREATE\s+TABLE\s+(?P<name>(?:\[[^\]]+\]|[\w]+)'
    r'(?:\s*\.\s*(?:\[[^\]]+\]|[\w]+))*)\s*\(', re.IGNORECASE)
_COLUMN_RE = re.compile(
    r'^\[?(?P<name>[^\]\s,]+)\]?\s+\[?(?P<type>\w+)\]?\s*'
    r'(?:\(\s*(?P<args>[^)]*)\s*\))?', re.IGNORECASE)
_NOT_A_COLUMN = ('--', ')', 'go', 'constraint', 'index', 'primary', 'unique',
                 'foreign', 'check', 'with', 'on ')


def decimal_bytes(precision: int) -> int:
    """Storage for decimal/numeric at a given precision."""
    if precision <= 9:
        return 5
    if precision <= 19:
        return 9
    if precision <= 28:
        return 13
    return 17


class Column:
    """One column, classified by how it occupies a row."""

    __slots__ = ('name', 'kind', 'size')

    def __init__(self, name: str, kind: str, size: int):
        self.name = name
        # 'fixed'  - always occupies self.size bytes
        # 'sized'  - variable, declared width self.size bytes, off-row costs 24
        # 'lob'    - varchar/nvarchar(max), off-row costs 16
        self.kind = kind
        self.size = size


class TableShape:
    """A staging table's row arithmetic, read from its schema file."""

    def __init__(self, table_name: str, path: str, columns: List[Column]):
        self.table_name = table_name
        self.path = path
        self.columns = columns

    @property
    def fixed_bytes(self) -> int:
        return sum(c.size for c in self.columns if c.kind == 'fixed')

    @property
    def variable_columns(self) -> List[Column]:
        return [c for c in self.columns if c.kind != 'fixed']

    @property
    def null_bitmap_bytes(self) -> int:
        """2 bytes of count plus one bit per column, whatever its type."""
        return 2 + (len(self.columns) + 7) // 8

    @property
    def offset_array_bytes(self) -> int:
        """Worst case: 2 bytes per variable column, plus a 2-byte count.

        A row is charged only up to its last populated variable column, so a
        sparse row pays less than this.
        """
        variable = len(self.variable_columns)
        return 2 + 2 * variable if variable else 0

    @property
    def structural_floor(self) -> int:
        """Bytes every row owes before any variable-length value is stored."""
        return (4                        # row header
                + self.null_bitmap_bytes
                + self.fixed_bytes
                + self.offset_array_bytes)

    @property
    def variable_budget(self) -> int:
        return ROW_LIMIT - self.structural_floor

    @property
    def declared_total(self) -> int:
        """What SQL Server adds up to decide whether to warn.

        A max column has no declared width; it is counted at its off-row cost,
        which is what makes the comparison against 8060 meaningful.
        """
        return self.structural_floor + sum(
            c.size if c.kind == 'sized' else LOB_ROOT
            for c in self.variable_columns)

    @property
    def warns(self) -> bool:
        """Whether creating this table draws the 8060-byte warning."""
        return self.declared_total > ROW_LIMIT

    @property
    def max_populated_variable(self) -> int:
        """Variable columns that can hold data before a row cannot be stored.

        Every one of them pushed out of the row still leaves a pointer behind,
        and those pointers are what eventually will not fit. Assumes the
        cheapest mix - the max columns first, at 16 bytes each.
        """
        budget = self.variable_budget
        if budget <= 0:
            return 0
        count = 0
        for column in sorted(self.variable_columns,
                             key=lambda c: LOB_ROOT if c.kind == 'lob'
                             else ROW_OVERFLOW_POINTER):
            cost = LOB_ROOT if column.kind == 'lob' else ROW_OVERFLOW_POINTER
            if budget < cost:
                break
            budget -= cost
            count += 1
        return count

    @property
    def worst_case_row(self) -> int:
        """Smallest a row with every column populated could be made."""
        return self.structural_floor + sum(
            LOB_ROOT if c.kind == 'lob' else ROW_OVERFLOW_POINTER
            for c in self.variable_columns)


def parse_schema_file(path: str) -> Optional[TableShape]:
    """The table one SQL/Schemas file creates, or None if it creates none."""
    with open(path, encoding='utf-8-sig', errors='replace') as handle:
        text = handle.read()

    match = _CREATE_TABLE_RE.search(text)
    if not match:
        return None

    table_name = match.group('name').split('.')[-1].strip('[] ')
    columns: List[Column] = []

    for raw in text[match.end():].splitlines():
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith(_NOT_A_COLUMN):
            # The column list is over once the closing paren is reached; a
            # constraint or inline INDEX line is not a column.
            if lowered.startswith(')'):
                break
            continue

        item = _COLUMN_RE.match(line.rstrip(','))
        if not item:
            continue
        name = item.group('name')
        type_name = item.group('type').lower()
        args = (item.group('args') or '').strip()

        if type_name in ('decimal', 'numeric'):
            precision = int(args.split(',')[0]) if args else 18
            columns.append(Column(name, 'fixed', decimal_bytes(precision)))
        elif type_name in FIXED_TYPE_BYTES:
            columns.append(Column(name, 'fixed', FIXED_TYPE_BYTES[type_name]))
        elif type_name in LENGTH_TYPE_BYTES_PER_CHAR:
            per_char = LENGTH_TYPE_BYTES_PER_CHAR[type_name]
            if args.lower() == 'max':
                columns.append(Column(name, 'lob', per_char))
            else:
                # No length at all means (1) in T-SQL.
                length = int(args) if args.isdigit() else 1
                columns.append(Column(name, 'sized', length * per_char))
        else:
            # text/ntext/image/xml/sql_variant and anything else: charge it the
            # most a variable column can cost, so an unrecognised type cannot
            # make the answer look better than it is.
            columns.append(Column(name, 'sized', ROW_OVERFLOW_POINTER))

    return TableShape(table_name, path, columns)


def upper_bound_bytes(values: List[str], shape: TableShape) -> int:
    """An upper bound on the row SQL Server would have to store for these values.

    Pessimistic on purpose, in three ways, so that a row this says fits really
    does fit:

      - the full structural floor, including an offset array covering every
        variable column rather than only those up to the last populated one;
      - every fixed-length column at full width, even where the row is null;
      - min(actual bytes, 24) for EVERY non-empty field, including the fixed
        ones already paid for above, and at the sized-column pointer cost even
        for max columns, which are cheaper.

    It needs no column mapping, which matters: several extracts carry headers
    that do not match "column mapping/", and matching on those would score a
    row as empty and understate it.
    """
    total = shape.structural_floor
    for value in values:
        if value and value.strip():
            total += min(len(value) * 2, ROW_OVERFLOW_POINTER)
    return total


def measure_csv(path: str, shape: TableShape) -> Dict[str, int]:
    """Widest row in one extract file, and how many rows exceed the limit."""
    worst = 0
    worst_row = 0
    over = 0
    rows = 0
    populated_max = 0

    with open(path, encoding='utf-8-sig', errors='replace', newline='') as handle:
        reader = csv.reader(handle)
        next(reader, None)                      # header
        for record in reader:
            rows += 1
            size = upper_bound_bytes(record, shape)
            populated = sum(1 for v in record if v and v.strip())
            populated_max = max(populated_max, populated)
            if size > worst:
                worst, worst_row = size, rows
            if size > ROW_LIMIT:
                over += 1

    return {'rows': rows, 'worst': worst, 'worst_row': worst_row,
            'over': over, 'populated_max': populated_max}


def resolve_csv_path(environment: Optional[str], config_dir: str,
                     variables_dir: str) -> Optional[str]:
    """Where the extracts live, resolved as the migration resolves it.

    Constructing DatabaseHelper reads config/<env>.env; it opens no connection.
    """
    if not environment:
        return None

    template = CSV_PATH_TEMPLATE_FALLBACK
    path_config = os.path.join(variables_dir, 'path_config.json')
    try:
        with open(path_config, encoding='utf-8') as handle:
            template = json.load(handle).get('csv_path_template', template)
    except (OSError, ValueError) as e:
        print(f'  ({os.path.basename(path_config)} unreadable, using the '
              f'built-in path template: {e})')

    helper = DatabaseHelper(environment=environment, config_path=config_dir)
    server = helper.config.get('NETWORK_SERVER')
    share = helper.config.get('NETWORK_SHARE')
    if not server or not share:
        return None
    return template.format(server=server, share=share)


def find_extracts(csv_path: str, table_name: str,
                  recursive: bool) -> List[str]:
    """Extract files for one table, as the loader would match them."""
    patterns = [os.path.join(csv_path, f'*{table_name}*.csv')]
    if recursive:
        patterns.append(os.path.join(csv_path, '**', f'*{table_name}*.csv'))
    found: List[str] = []
    for pattern in patterns:
        found.extend(glob.glob(pattern, recursive=recursive))
    return sorted(set(found))


def report_shape(shape: TableShape) -> None:
    print(f'{shape.table_name}  ({len(shape.columns)} columns, '
          f'{len(shape.variable_columns)} variable)')
    if not shape.warns:
        print(f'  declared row size {shape.declared_total:,} B of {ROW_LIMIT:,}'
              f' - no warning on create')
        return

    print(f'  declared row size {shape.declared_total:,} B exceeds '
          f'{ROW_LIMIT:,} - CREATE TABLE warns')
    print(f'  structural floor  {shape.structural_floor:,} B '
          f'(row header 4, null bitmap {shape.null_bitmap_bytes}, '
          f'fixed columns {shape.fixed_bytes:,}, '
          f'offset array {shape.offset_array_bytes:,})')
    print(f'  left for data     {shape.variable_budget:,} B')
    if shape.worst_case_row > ROW_LIMIT:
        print(f'  a row can hold    {shape.max_populated_variable} of '
              f'{len(shape.variable_columns)} variable columns before it '
              f'cannot be stored')
    else:
        print(f'  every row fits    worst case with all '
              f'{len(shape.variable_columns)} columns populated is '
              f'{shape.worst_case_row:,} B')


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('environment', nargs='?', default=None,
                        help='Environment name, e.g. dev, uat, testse. Used '
                             'only to locate the extracts')
    parser.add_argument('--config', dest='config_path', default=None,
                        metavar='PATH',
                        help='Environment file, or the directory holding '
                             '<env>.env')
    parser.add_argument('--variables', dest='variables_path', default=None,
                        metavar='DIR',
                        help=f'Folder holding path_config.json. Default: '
                             f'{DEFAULT_VARIABLES_DIR}')
    parser.add_argument('--schemas', dest='schema_dir',
                        default=DEFAULT_SCHEMA_DIR, metavar='DIR',
                        help=f'Folder holding the schema files. Default: '
                             f'{DEFAULT_SCHEMA_DIR}')
    parser.add_argument('--table', action='append', dest='tables', default=None,
                        help='Check only this table (repeatable). Default: '
                             'every schema file')
    parser.add_argument('--csv-path', dest='csv_path', default=None,
                        metavar='PATH',
                        help='Folder holding the extract CSVs, instead of the '
                             "environment's network share")
    parser.add_argument('--recursive', action='store_true',
                        help='Also measure extracts in subfolders. The loader '
                             'reads only the top folder')
    parser.add_argument('--no-data', action='store_true',
                        help='Report the schema arithmetic only; read no CSVs')
    args = parser.parse_args()

    environment: Optional[str] = None
    config_dir = os.path.join(REPO_ROOT, 'config')
    if args.environment or args.config_path:
        environment, config_dir = resolve_environment(args)
    variables_dir = os.path.abspath(args.variables_path or DEFAULT_VARIABLES_DIR)

    schema_files = sorted(glob.glob(os.path.join(args.schema_dir, '*.sql')))
    if not schema_files:
        print(f'No schema files in {args.schema_dir}')
        return 1

    wanted = {name.lower() for name in (args.tables or [])}
    shapes: List[TableShape] = []
    for path in schema_files:
        shape = parse_schema_file(path)
        if shape is None:
            continue
        if wanted and shape.table_name.lower() not in wanted:
            continue
        shapes.append(shape)

    if not shapes:
        print(f'No matching table found in {args.schema_dir}')
        return 1

    csv_path = None
    if not args.no_data:
        csv_path = args.csv_path or resolve_csv_path(environment, config_dir,
                                                     variables_dir)

    at_risk = [s for s in shapes if s.warns]
    print(f'{len(shapes)} table(s) from {args.schema_dir}; '
          f'{len(at_risk)} declare more than {ROW_LIMIT:,} bytes per row')
    if csv_path:
        print(f'extracts: {csv_path}'
              f'{" (including subfolders)" if args.recursive else ""}')
    print()

    failures: List[str] = []
    unmeasured: List[str] = []

    for shape in shapes:
        report_shape(shape)

        if not shape.warns or not csv_path:
            print()
            continue

        files = find_extracts(csv_path, shape.table_name, args.recursive)
        if not files:
            print(f'  no extract found matching *{shape.table_name}*.csv')
            unmeasured.append(shape.table_name)
            print()
            continue

        total_rows = 0
        total_over = 0
        worst = 0
        worst_where = ''
        populated_max = 0
        for path in files:
            try:
                result = measure_csv(path, shape)
            except OSError as e:
                print(f'  unreadable: {os.path.basename(path)}: {e}')
                continue
            total_rows += result['rows']
            total_over += result['over']
            populated_max = max(populated_max, result['populated_max'])
            if result['worst'] > worst:
                worst = result['worst']
                worst_where = f'{os.path.basename(path)} row {result["worst_row"]}'
            if result['over']:
                print(f'  OVER LIMIT: {result["over"]:,} of {result["rows"]:,} '
                      f'rows in {os.path.basename(path)}, '
                      f'worst {result["worst"]:,} B')

        print(f'  measured          {len(files)} file(s), {total_rows:,} rows')
        if total_rows:
            print(f'  widest row        {worst:,} B '
                  f'({worst * 100 // ROW_LIMIT}% of {ROW_LIMIT:,}), '
                  f'{ROW_LIMIT - worst:,} B spare - {worst_where}')
            print(f'  most populated    {populated_max} field(s) in one row')
        if total_over:
            failures.append(f'{shape.table_name}: {total_over:,} row(s) over '
                            f'the limit')
        print()

    print('-' * 70)
    if failures:
        for failure in failures:
            print(f'FAIL  {failure}')
        print('These rows are rejected with Msg 511 and will fail the load.')
        return 1

    if at_risk and csv_path:
        measured = [s.table_name for s in at_risk
                    if s.table_name not in unmeasured]
        if measured:
            print(f'PASS  every measured row fits, for {", ".join(measured)}. '
                  f'The create-time warning is about the declared widths, not '
                  f'this data.')
    if unmeasured:
        print(f'      not measured, no extract on this path: '
              f'{", ".join(unmeasured)}')
    if at_risk and not csv_path:
        print('      no extract path resolved, so no data was measured. Name '
              'an environment, or pass --csv-path.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
