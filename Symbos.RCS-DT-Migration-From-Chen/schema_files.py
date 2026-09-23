r"""Read the SQL/Schemas files, and the set list in variables/schema_sets.json.

Two callers, deliberately sharing one implementation:

  tools/deploy_schemas.py  runs a named set against an environment - the setup
                           step that puts the staging tables there in the first
                           place.
  staging_archive.py       rebuilds one staging table at the end of a customer's
                           migration, after the loaded one has been renamed into
                           the archive schema.

The second is why this lives at the repo root rather than in tools/, which is
not a package and is not on the path of a migration run.

Batches are split on GO the way sqlcmd splits them, ignoring a GO inside a
comment or a string literal. Each Batch also carries a comment-free, string-
emptied copy of itself, so that reading what a file DROPs and CREATEs sees
statements and never prose - Migrations/001 opens with a comment saying "this
script begins with DROP TABLE", and nothing here should believe it.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMA_DIR = os.path.join(REPO_ROOT, 'SQL', 'Schemas')
DEFAULT_MANIFEST = os.path.join(REPO_ROOT, 'variables', 'schema_sets.json')

# The set holding one file per staging table. What a migration run rebuilds
# from, so a table named by table_keywords but absent from this set has no way
# to be recreated after it is archived.
STAGING_SET = 'staging'

_CREATE_TABLE_RE = re.compile(
    r'CREATE\s+TABLE\s+(?P<name>(?:\[[^\]]+\]|\w+)(?:\s*\.\s*(?:\[[^\]]+\]|\w+))*)',
    re.IGNORECASE)
_DROP_TABLE_RE = re.compile(
    r'DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?'
    r'(?P<name>(?:\[[^\]]+\]|\w+)(?:\s*\.\s*(?:\[[^\]]+\]|\w+))*)',
    re.IGNORECASE)
# sqlcmd's own batch terminator: GO alone on a line, optionally with a repeat
# count and a trailing line comment.
_GO_RE = re.compile(r'^\s*GO\s*(?:\d+\s*)?(?:--.*)?$', re.IGNORECASE)


class SchemaSetError(ValueError):
    """The set list, or a file it names, cannot be used as asked."""


# ----------------------------------------------------------------------------
# Reading the files
# ----------------------------------------------------------------------------

class Batch:
    """One GO-separated batch, and where in the file it started."""

    __slots__ = ('sql', 'line', 'code')

    def __init__(self, sql: str, line: int, code: str):
        self.sql = sql
        self.line = line
        # The same batch with every comment removed and every string literal
        # emptied. What DROP/CREATE detection reads, so that a comment saying
        # "this script begins with DROP TABLE" - Migrations/001 says exactly
        # that - is not mistaken for the statement it warns about.
        self.code = code

    @property
    def has_code(self) -> bool:
        return bool(self.code.strip())


def split_batches(script: str) -> List[Batch]:
    """Split on GO, ignoring one inside a comment or a string literal.

    Comment state carries across lines, which is what keeps a documentation
    block that quotes GO - SQL/Schemas/Migrations/004 is nothing but those -
    from being cut in half into two unparseable halves.

    A bracket or double-quoted identifier is only tracked within its own line.
    One spanning a newline would have to be a column named across two lines,
    which nothing here does, and treating it per line costs nothing if so.
    """
    batches: List[Batch] = []
    lines: List[str] = []
    code: List[str] = []
    start_line = 1
    comment_depth = 0
    in_string = False

    def flush(next_start: int) -> None:
        nonlocal lines, code, start_line
        if lines:
            batches.append(Batch('\n'.join(lines), start_line, '\n'.join(code)))
        lines = []
        code = []
        start_line = next_start

    for number, line in enumerate(script.splitlines(), start=1):
        if comment_depth == 0 and not in_string and _GO_RE.match(line):
            flush(number + 1)
            continue

        comment_depth, in_string, code_on_line = _scan_line(
            line, comment_depth, in_string)
        lines.append(line)
        code.append(code_on_line)

    flush(0)
    return batches


def _scan_line(line: str, comment_depth: int,
               in_string: bool) -> Tuple[int, bool, str]:
    """(comment depth, inside a string, the line's executable text) after it.

    The third value is the line with comments dropped and string contents
    emptied, so whatever reads it sees statements and never prose.
    """
    code: List[str] = []
    index = 0
    length = len(line)

    while index < length:
        char = line[index]

        if in_string:
            if char == "'":
                if line.startswith("''", index):
                    index += 2
                    continue
                in_string = False
                code.append("'")
            index += 1
            continue

        if comment_depth:
            # T-SQL block comments nest, so an inner /* has to be counted.
            if line.startswith('*/', index):
                comment_depth -= 1
                index += 2
            elif line.startswith('/*', index):
                comment_depth += 1
                index += 2
            else:
                index += 1
            continue

        if line.startswith('--', index):
            break
        if line.startswith('/*', index):
            comment_depth += 1
            index += 2
            # A comment between two tokens separates them; keep it that way.
            code.append(' ')
            continue

        if char == "'":
            in_string = True
            code.append("'")
            index += 1
            continue
        if char in '["':
            closer = ']' if char == '[' else '"'
            end = _skip_identifier(line, index + 1, closer)
            code.append(line[index:end])
            index = end
            continue

        code.append(char)
        index += 1

    return comment_depth, in_string, ''.join(code)


def _skip_identifier(line: str, index: int, closer: str) -> int:
    """Index just past a [bracketed] or "quoted" identifier, doubling escaped."""
    while index < len(line):
        if line[index] == closer:
            if line.startswith(closer * 2, index):
                index += 2
                continue
            return index + 1
        index += 1
    return index


def _unqualified(name: str) -> str:
    return name.split('.')[-1].strip('[]" ')


def tables_touched(code: str) -> Tuple[List[str], List[str]]:
    """(tables this code drops, tables it creates), in file order.

    Takes the comment-free text from split_batches, not the raw file. Read from
    the script rather than from the server because the plan has to be printable
    before anything runs, and because the guards these files use - IF EXISTS ...
    DROP - put the statement there whether or not the table is.
    """
    dropped, created = [], []
    for match in _DROP_TABLE_RE.finditer(code):
        name = _unqualified(match.group('name'))
        if name not in dropped:
            dropped.append(name)
    for match in _CREATE_TABLE_RE.finditer(code):
        name = _unqualified(match.group('name'))
        if name not in created:
            created.append(name)
    return dropped, created


class SchemaFile:
    """One file in the run: where it is, what it does, what it costs."""

    def __init__(self, relative_path: str, schema_dir: str):
        self.relative_path = relative_path
        self.path = os.path.join(schema_dir, relative_path)
        self.exists = os.path.isfile(self.path)
        self.batches: List[Batch] = []
        self.drops: List[str] = []
        self.creates: List[str] = []
        self.error: Optional[str] = None

        if self.exists:
            with open(self.path, encoding='utf-8-sig', errors='replace') as handle:
                script = handle.read()
            self.batches = [b for b in split_batches(script) if b.has_code]
            self.drops, self.creates = tables_touched(
                '\n'.join(batch.code for batch in self.batches))

    def creates_table(self, table_name: str) -> bool:
        return any(name.lower() == table_name.lower() for name in self.creates)


# ----------------------------------------------------------------------------
# The set list
# ----------------------------------------------------------------------------

def load_manifest(path: Optional[str] = None) -> Dict[str, Any]:
    path = path or DEFAULT_MANIFEST
    if not os.path.isfile(path):
        raise SchemaSetError(f'No schema set list at {path}')
    with open(path, encoding='utf-8') as handle:
        manifest = json.load(handle)
    if not isinstance(manifest.get('sets'), dict):
        raise SchemaSetError(f'{path} has no "sets" object')
    return manifest


def expand_set(manifest: Dict[str, Any], name: str,
               seen: Optional[Set[str]] = None) -> List[str]:
    """The files in one set, with any included set expanded ahead of them."""
    seen = seen if seen is not None else set()
    if name in seen:
        raise SchemaSetError(f'Set {name!r} includes itself')
    seen.add(name)

    definition = manifest['sets'].get(name)
    if definition is None:
        known = ', '.join(sorted(manifest['sets']))
        raise SchemaSetError(f'No set named {name!r}. Sets: {known}')

    files: List[str] = []
    for included in definition.get('include', []):
        files.extend(expand_set(manifest, included, seen))
    files.extend(definition.get('files', []))
    return files


def resolve_files(manifest: Dict[str, Any], set_names: Sequence[str],
                  explicit: Sequence[str]) -> Tuple[List[str], List[str]]:
    """(files to run, the set names they came from). --file wins over --set."""
    if explicit:
        if set_names:
            print(f'--file given, so --set {", ".join(set_names)} is ignored')
        return deduplicate(explicit), []

    names = list(set_names) or [manifest.get('default_set', STAGING_SET)]
    files: List[str] = []
    for name in names:
        files.extend(expand_set(manifest, name))
    return deduplicate(files), names


def deduplicate(files: Sequence[str]) -> List[str]:
    """First occurrence wins, so an included set keeps its position."""
    seen: Set[str] = set()
    ordered: List[str] = []
    for path in files:
        key = path.replace('\\', '/').lower()
        if key not in seen:
            seen.add(key)
            ordered.append(path)
    return ordered


# ----------------------------------------------------------------------------
# What the archive step needs
# ----------------------------------------------------------------------------

def load_staging_schema_files(
    tables: Sequence[str],
    manifest_path: Optional[str] = None,
    schema_dir: Optional[str] = None,
    set_name: str = STAGING_SET,
) -> Dict[str, SchemaFile]:
    """The schema file that rebuilds each of `tables`, keyed by table name.

    Indexed by the table each file CREATEs rather than by its filename, because
    those do not reliably agree: every other file is "<TABLE> Schema.sql" but
    RC_DRINSURANCE.sql is not, and a lookup by name would silently miss it.

    Raises SchemaSetError naming *every* problem at once, not the first. The
    archive step calls this when a run starts rather than when it archives, and
    the whole point of that is to report a broken set list while staging is
    still intact: once a table has been renamed away, a missing file means it
    cannot be rebuilt at all.
    """
    schema_dir = schema_dir or DEFAULT_SCHEMA_DIR
    manifest = load_manifest(manifest_path)
    relative_paths = deduplicate(expand_set(manifest, set_name))

    by_table: Dict[str, SchemaFile] = {}
    problems: List[str] = []

    for relative_path in relative_paths:
        schema_file = SchemaFile(relative_path, schema_dir)
        if not schema_file.exists:
            problems.append(f'{relative_path}: no such file in {schema_dir}')
            continue
        if not schema_file.batches:
            problems.append(f'{relative_path}: no executable batches')
            continue
        for created in schema_file.creates:
            by_table.setdefault(created.lower(), schema_file)

    resolved: Dict[str, SchemaFile] = {}
    for table_name in tables:
        schema_file = by_table.get(table_name.lower())
        if schema_file is None:
            problems.append(
                f'{table_name}: no file in the {set_name!r} set creates it, so '
                f'it could not be rebuilt after being archived')
            continue
        resolved[table_name] = schema_file

    if problems:
        raise SchemaSetError(
            f'{len(problems)} problem(s) with the {set_name!r} schema set:\n  '
            + '\n  '.join(problems))

    return resolved
