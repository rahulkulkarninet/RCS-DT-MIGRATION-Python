"""Snapshot what the migration needs from a DebtRak database, and diff two snapshots.

Answers "is environment B set up like environment A?" - typically "what does prod
lack that testse has, so someone can add it before we migrate there". It runs the
same checks the migration runs, against the database alone (no staging data):

  mappings    every DT label a variables/*_codes.json file names must resolve in its
              lookup table, matched the way the mapping services match it
              (text_normalization.match_key: case, spacing and punctuation ignored).
              A label that misses here is a hard stop in that mapping step.
  variables   vwHost columns, lookup_variables and metafield_variables as
              ConfigParser.resolve_database_vars reads them - but raw, without its
              ISNULL/default fallback. That fallback is the dangerous case: a value
              missing on prod silently becomes the hardcoded default, which is a
              testse-era ID, and the run carries on with it.
  constants   constant_variables are hardcoded IDs. Their label on each environment
              is recorded so the diff shows an ID that means something else.
  schema      every tbl*/vw* object the Direct SQL references: does it exist, and its
              columns (type, nullability, default). A NOT NULL column with no default
              that the target has and the source lacks is the DebtRak-drift case that
              fails an INSERT.

Read-only by construction: every statement is a SELECT against catalog views or
lookup tables. Nothing is written to the database.

    python tools/env_readiness.py snapshot testse
    python tools/env_readiness.py snapshot --config C:/secure/prod.env
    python tools/env_readiness.py diff out/testse.json out/prod.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import text_normalization  # noqa: E402
from db_manager import DatabaseHelper  # noqa: E402
from tools.env_target import DEFAULT_CONFIG_DIR, DEFAULT_VARIABLES_DIR  # noqa: E402

SQL_DIR = os.path.join(REPO_ROOT, 'SQL', 'Migration queries')
DEFAULT_OUT_DIR = os.path.join(REPO_ROOT, 'tools', 'out')

# (lookup table, id column, label column), as each mapping service declares them.
LOOKUPS = {
    'tblAccountStatus': ('AccountStatusID', 'AccountStatus'),
    'tblArrangementType': ('ArrangementTypeID', 'ArrangementType'),
    'tblBankTransactionMethod': ('BankTransactionMethodID', 'BankTransactionMethod'),
    'tblClosureReason': ('ClosureReasonID', 'ClosureReason'),
    'tblCostType': ('CostTypeID', 'CostType'),
    'tblMasterCost': ('MasterCostID', 'MasterCost'),
    'tblFrequency': ('FrequencyID', 'Frequency'),
    'tblIncidentType': ('IncidentTypeID', 'IncidentType'),
    'tblRelationship': ('RelationshipID', 'Relationship'),
    'tblState': ('StateID', 'StateShort'),
    'tblAddressType': ('AddressTypeID', 'AddressType'),
    'tblEntryType': ('EntryTypeID', 'EntryType'),
    'tblContactType': ('ContactTypeID', 'ContactType'),
    'tblContactDetailType': ('ContactDetailTypeID', 'ContactDetailType'),
    'tblCountry': ('CountryID', 'Country'),
}

# Which ID prefix of a vwHost/constant variable names which lookup, so an ID can be
# shown with its label.
ID_PREFIX_LOOKUP = {
    'AccountStatusID': 'tblAccountStatus',
    'ArrangementTypeID': 'tblArrangementType',
    'RelationshipID': 'tblRelationship',
    'SecondaryRelationshipID': 'tblRelationship',
    'ContactTypeID': 'tblContactType',
    'ContactDetailTypeID': 'tblContactDetailType',
    'AddressTypeID': 'tblAddressType',
    'DefaultCountryID': 'tblCountry',
    'EntryTypeID': 'tblEntryType',
}


# What the mapping step does when a label it names is absent, per (file, role). Read
# off services/workflows/customer_*_workflow_service.py.
BLOCKS = 'blocks'
EFFECT = {
    ('cost_codes.json', 'cost_types'): (BLOCKS, 'cost step stops the customer'),
    ('cost_codes.json', 'master_costs'): (BLOCKS, 'cost step stops the customer'),
    ('cost_codes.json', 'default_master_cost'): (BLOCKS, 'cost step stops the customer'),
    ('incident_type_codes.json', 'rules'): (BLOCKS, 'incident step stops the customer'),
    ('incident_type_codes.json', 'default'): (BLOCKS, 'incident step stops the customer'),
    ('arrangement_type_codes.json', 'default'): (BLOCKS, 'arrangement step stops the customer'),
    ('closure_reason_codes.json', 'default_for_unmapped'): (BLOCKS, 'closure step stops the customer'),
    ('related_party_type_codes.json', 'default_for_unmapped'): (BLOCKS, 'related party step stops the customer'),
    ('closure_reason_codes.json', 'mapping'): ('silent', 'its codes fall to the default_for_unmapped reason'),
    ('related_party_type_codes.json', 'mapping'): ('silent', 'its codes fall to the default_for_unmapped relationship'),
    ('account_status_codes.json', 'mapping'): ('silent', 'its codes migrate as AccountStatusID_Creation (check step warns)'),
    ('frequency_codes.json', 'mapping'): ('silent', 'its codes migrate as a NULL FrequencyID (check step warns)'),
    ('bank_transaction_method_codes.json', 'mapping'): ('silent', 'its codes get no BankTransactionMethodID (check step warns)'),
    ('arrangement_type_codes.json', 'mapping'): ('silent', 'its codes get no ArrangementTypeID (check step warns)'),
    ('state_codes.json', 'mapping'): ('silent', 'those addresses keep a NULL StateID (check step warns)'),
}


def key(value: Any) -> str:
    """The comparison key every mapping service matches labels on."""
    return text_normalization.match_key(text_normalization.normalize_lookup_key(value))


def load_variables_json(variables_dir: str, name: str) -> Dict[str, Any]:
    with open(os.path.join(variables_dir, name), 'r', encoding='utf-8') as handle:
        return json.load(handle)


# --- what each mapping file requires ----------------------------------------

def required_labels(variables_dir: str) -> List[Tuple[str, str, str, str]]:
    """(mapping file, role, lookup table, label) for every label the files name.

    Mirrors how each workflow service reads its file: which keys are labels, and
    which single values (default / fallback) must resolve too.
    """
    out: List[Tuple[str, str, str, str]] = []

    def labels(file: str, table: str, mapping: Dict[str, Any], role: str = 'mapping'):
        for label, codes in mapping.items():
            if str(label).startswith('_') or not isinstance(codes, list):
                continue
            out.append((file, role, table, str(label)))

    data = load_variables_json(variables_dir, 'account_status_codes.json')
    labels('account_status_codes.json', 'tblAccountStatus', data)

    data = load_variables_json(variables_dir, 'arrangement_type_codes.json')
    labels('arrangement_type_codes.json', 'tblArrangementType', data.get('mapping', {}))
    if data.get('default'):
        out.append(('arrangement_type_codes.json', 'default', 'tblArrangementType', data['default']))

    data = load_variables_json(variables_dir, 'bank_transaction_method_codes.json')
    labels('bank_transaction_method_codes.json', 'tblBankTransactionMethod', data)

    data = load_variables_json(variables_dir, 'closure_reason_codes.json')
    labels('closure_reason_codes.json', 'tblClosureReason', data.get('mapping', {}))
    if data.get('default_for_unmapped'):
        out.append(('closure_reason_codes.json', 'default_for_unmapped', 'tblClosureReason',
                    data['default_for_unmapped']))

    data = load_variables_json(variables_dir, 'cost_codes.json')
    labels('cost_codes.json', 'tblCostType', data.get('cost_types', {}), 'cost_types')
    labels('cost_codes.json', 'tblMasterCost', data.get('master_costs', {}), 'master_costs')
    if data.get('default_master_cost'):
        out.append(('cost_codes.json', 'default_master_cost', 'tblMasterCost',
                    data['default_master_cost']))

    data = load_variables_json(variables_dir, 'frequency_codes.json')
    labels('frequency_codes.json', 'tblFrequency', data)

    data = load_variables_json(variables_dir, 'incident_type_codes.json')
    for rule in data.get('rules', []):
        out.append(('incident_type_codes.json', 'rules', 'tblIncidentType', rule['incident_type']))
    if data.get('default'):
        out.append(('incident_type_codes.json', 'default', 'tblIncidentType', data['default']))

    data = load_variables_json(variables_dir, 'related_party_type_codes.json')
    labels('related_party_type_codes.json', 'tblRelationship', data.get('mapping', {}))
    if data.get('default_for_unmapped'):
        out.append(('related_party_type_codes.json', 'default_for_unmapped', 'tblRelationship',
                    data['default_for_unmapped']))

    data = load_variables_json(variables_dir, 'state_codes.json')
    labels('state_codes.json', 'tblState', data)

    return out


def referenced_objects() -> Dict[str, List[str]]:
    """{tbl/vw object: [Direct SQL files that name it]}. RC_* staging is ours, so skipped."""
    pattern = re.compile(r'\b((?:tbl|vw)[A-Za-z0-9_]+)\b')
    found: Dict[str, set] = {}
    for path in glob.glob(os.path.join(SQL_DIR, '**', '*.sql'), recursive=True):
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            text = re.sub(r'--[^\n]*', '', handle.read())
        for name in pattern.findall(text):
            found.setdefault(name.lower(), set()).add(os.path.basename(path))
    return {name: sorted(files) for name, files in sorted(found.items())}


# --- snapshot ---------------------------------------------------------------

def q(db: DatabaseHelper, sql: str):
    return db.execute_query(sql)


def snapshot(db: DatabaseHelper, environment: str, variables_dir: str) -> Dict[str, Any]:
    ident = q(db, "SELECT @@SERVERNAME AS server_name, DB_NAME() AS db_name, "
                  "SUSER_SNAME() AS login_name").iloc[0]
    snap: Dict[str, Any] = {
        'environment': environment,
        'server': str(ident['server_name']),
        'database': str(ident['db_name']),
        'login': str(ident['login_name']),
        'taken_at': dt.datetime.now().isoformat(timespec='seconds'),
    }

    # Lookup tables, whole. Small, and the diff needs labels on both sides.
    lookups: Dict[str, Any] = {}
    for table, (id_col, label_col) in LOOKUPS.items():
        try:
            frame = q(db, f"SELECT [{id_col}] AS id, CAST([{label_col}] AS NVARCHAR(4000)) AS label "
                          f"FROM [{table}] WITH (NOLOCK) WHERE [{label_col}] IS NOT NULL")
            lookups[table] = {'rows': [[int(r.id), str(r.label).strip()]
                                       for r in frame.itertuples(index=False)]}
        except Exception as exc:  # table or column absent on this environment
            lookups[table] = {'error': str(exc).splitlines()[0][:300]}
    snap['lookups'] = lookups

    # Schema of every object the Direct SQL references.
    objects = referenced_objects()
    names = ', '.join(f"'{n}'" for n in objects)
    obj_frame = q(db, f"""
        SELECT LOWER(o.name) AS name, o.type_desc
        FROM sys.objects o
        WHERE o.schema_id = SCHEMA_ID('dbo') AND LOWER(o.name) IN ({names})""")
    col_frame = q(db, f"""
        SELECT LOWER(o.name) AS obj, c.name AS col, t.name AS type_name,
               c.max_length, c.precision, c.scale, c.is_nullable, c.is_identity,
               c.is_computed, CASE WHEN c.default_object_id <> 0 THEN 1 ELSE 0 END AS has_default
        FROM sys.columns c
        JOIN sys.objects o ON o.object_id = c.object_id
        JOIN sys.types t ON t.user_type_id = c.user_type_id
        WHERE o.schema_id = SCHEMA_ID('dbo') AND LOWER(o.name) IN ({names})""")
    schema: Dict[str, Any] = {}
    present = {r.name: r.type_desc for r in obj_frame.itertuples(index=False)}
    for name, files in objects.items():
        if name not in present:
            continue
        cols = {}
        for r in col_frame[col_frame['obj'] == name].itertuples(index=False):
            cols[r.col.lower()] = {
                'name': r.col, 'type': r.type_name, 'max_length': int(r.max_length),
                'precision': int(r.precision), 'scale': int(r.scale),
                'nullable': bool(r.is_nullable), 'identity': bool(r.is_identity),
                'computed': bool(r.is_computed), 'has_default': bool(r.has_default),
            }
        schema[name] = {'type': present[name], 'columns': cols}
    snap['referenced_objects'] = objects
    snap['schema'] = schema

    # Variables, raw - what resolve_database_vars would read before its fallback.
    config = load_variables_json(variables_dir, 'migration_variables.json')['migration_variables']
    variables: Dict[str, Any] = {}

    vw = config['vwHost']
    details = vw['query_details']
    for name, cfg in vw['variables'].items():
        try:
            frame = q(db, f"SELECT TOP 1 [{cfg['column']}] AS v FROM [{details['main_table']}] "
                          f"LEFT JOIN [{details['join_table']}] ON {details['join_condition']}")
            raw = None if frame.empty else frame.iloc[0, 0]
            variables[name] = {'category': 'vwHost', 'source': f"vwHost.{cfg['column']}",
                               'raw': None if raw is None or raw != raw else int(raw),
                               'default': cfg.get('default')}
        except Exception as exc:
            variables[name] = {'category': 'vwHost', 'source': f"vwHost.{cfg['column']}",
                               'error': str(exc).splitlines()[0][:300],
                               'default': cfg.get('default')}

    for name, cfg in config['lookup_variables']['variables'].items():
        col, value = cfg['filter_col'], str(cfg['filter_value'])
        if cfg.get('filter_normalized'):
            where = (f"LOWER(REPLACE(REPLACE(REPLACE([{col}], ' ', ''), CHAR(9), ''), '-', '')) = "
                     f"'{''.join(value.lower().split()).replace('-', '')}'")
        else:
            where = f"[{col}] = '{value}'"
        source = f"{cfg['main_table']}.{col} = '{value}'"
        try:
            frame = q(db, f"SELECT [{cfg['column']}] AS v FROM [{cfg['main_table']}] WITH (NOLOCK) "
                          f"WHERE {where}")
            vals = [int(v) for v in frame['v'].dropna().tolist()]
            variables[name] = {'category': 'lookup_variables', 'source': source,
                               'raw': vals[0] if vals else None, 'matches': len(vals),
                               'default': cfg.get('default')}
        except Exception as exc:
            variables[name] = {'category': 'lookup_variables', 'source': source,
                               'error': str(exc).splitlines()[0][:300],
                               'default': cfg.get('default')}

    meta = config['metafield_variables']['query_details']
    for name, cfg in config['metafield_variables']['variables'].items():
        source = f"{meta['main_table']}.{meta['filter_col']} = '{cfg['filter_value']}' (active)"
        try:
            frame = q(db, f"SELECT [{meta['column']}] AS v FROM [{meta['main_table']}] WITH (NOLOCK) "
                          f"WHERE [{meta['filter_col']}] = '{cfg['filter_value']}' "
                          f"AND [{meta['sec_col']}] = {meta['sec_value']}")
            vals = [int(v) for v in frame['v'].dropna().tolist()]
            variables[name] = {'category': 'metafield_variables', 'source': source,
                               'raw': vals[0] if vals else None, 'matches': len(vals),
                               'default': None}
        except Exception as exc:
            variables[name] = {'category': 'metafield_variables', 'source': source,
                               'error': str(exc).splitlines()[0][:300], 'default': None}

    for name, cfg in config['constant_variables']['variables'].items():
        variables[name] = {'category': 'constant_variables', 'source': 'hardcoded',
                           'raw': cfg.get('default'), 'default': cfg.get('default')}

    snap['variables'] = variables
    return snap


# --- diff -------------------------------------------------------------------

def label_index(snap: Dict[str, Any], table: str) -> Optional[Dict[str, Tuple[int, str]]]:
    entry = snap['lookups'].get(table, {})
    if 'rows' not in entry:
        return None
    index: Dict[str, Tuple[int, str]] = {}
    for ident, label in entry['rows']:
        index.setdefault(key(label), (ident, label))
    return index


def id_label(snap: Dict[str, Any], var_name: str, value: Any) -> str:
    if value is None:
        return ''
    for prefix, table in ID_PREFIX_LOOKUP.items():
        if var_name.startswith(prefix):
            for ident, label in snap['lookups'].get(table, {}).get('rows', []):
                if ident == value:
                    return label
            return '(no such ID)'
    return ''


def type_text(col: Dict[str, Any]) -> str:
    t = col['type']
    if t in ('varchar', 'char', 'varbinary', 'binary'):
        return f"{t}({'max' if col['max_length'] == -1 else col['max_length']})"
    if t in ('nvarchar', 'nchar'):
        return f"{t}({'max' if col['max_length'] == -1 else col['max_length'] // 2})"
    if t in ('decimal', 'numeric'):
        return f"{t}({col['precision']},{col['scale']})"
    return t


def files_naming(column: str, files: List[str]) -> List[str]:
    """Which of these migration SQL files mention the column by name (comments ignored)."""
    pattern = re.compile(r'\b' + re.escape(column) + r'\b', re.IGNORECASE)
    hits = []
    for path in glob.glob(os.path.join(SQL_DIR, '**', '*.sql'), recursive=True):
        if os.path.basename(path) not in files:
            continue
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            if pattern.search(re.sub(r'--[^\n]*', '', handle.read())):
                hits.append(os.path.basename(path))
    return sorted(set(hits))


def effective(var: Dict[str, Any]) -> Any:
    """The value the run ends up using: ConfigParser falls back to the default."""
    if 'error' in var or var.get('raw') is None:
        return var.get('default')
    return var['raw']


def diff(a: Dict[str, Any], b: Dict[str, Any], variables_dir: str) -> str:
    A, B = a['environment'], b['environment']
    asks: List[str] = []
    also_on_a: List[str] = []
    body: List[str] = []

    # 1. Mapping labels.
    body += ['## 1. Mapping file labels', '']
    rows = []
    for file, role, table, label in required_labels(variables_dir):
        ia, ib = label_index(a, table), label_index(b, table)
        in_a = ia is not None and key(label) in ia
        in_b = ib is not None and key(label) in ib
        if in_b:
            continue
        severity, effect = EFFECT.get((file, role), ('silent', 'unresolved'))
        where = f'{table} unreadable on {B}' if ib is None else f'not in {table}'
        rows.append(f"| {file} | {role} | {label} | {'yes' if in_a else '**no**'} | "
                    f"{where} | {'**blocks**' if severity == BLOCKS else 'silent'}: {effect} |")
        if in_a:
            ident, real = ia[key(label)]
            asks.append(f'{table}: add "{real}" (ID {ident} on {A}) - {file} {role}; '
                        f'without it {effect}')
        else:
            also_on_a.append(f'{table} has no "{label}" ({file} {role}) - {effect}')
    if rows:
        body += [f'| File | Role | Label | On {A} | {B} | Effect on {B} |',
                 '|---|---|---|---|---|---|', *rows, '']
    else:
        body += [f'All labels in every mapping file resolve on {B}.', '']

    # 2. Variables, compared by what the effective ID means on each side.
    body += ['## 2. Database variables and constants', '',
             'Compared by meaning: the ID each side would actually use (its own value, or the '
             'JSON default when its lookup comes back empty) and that ID\'s label there.', '']
    rows = []
    for name, va in a['variables'].items():
        vb = b['variables'].get(name, {})
        ea, eb = effective(va), effective(vb)
        la, lb = id_label(a, name, ea), id_label(b, name, eb)
        b_fell_back = 'error' in vb or vb.get('raw') is None
        a_fell_back = 'error' in va or va.get('raw') is None
        problem = ''
        if va['category'] == 'metafield_variables' and vb.get('raw') is None:
            problem = 'not found - the metafield loop for it inserts nothing'
        elif eb is None:
            problem = f"not found and no default - resolves to NULL{': ' + vb['error'] if 'error' in vb else ''}"
        elif lb == '(no such ID)':
            problem = f'ID {eb} does not exist here' + (' (default used)' if b_fell_back else '')
        elif la and lb and key(la) != key(lb):
            problem = (f'ID {eb} means "{lb}" here but {A} uses "{la}"'
                       + (' (default used)' if b_fell_back else ''))
        elif b_fell_back and not a_fell_back and not la:
            problem = f'not found - run silently uses default {eb!r}; {A} has its own value {ea!r}'
        elif vb.get('matches', 1) > 1:
            problem = f"{vb['matches']} rows match; first is used"
        if problem:
            rows.append(f"| {name} | {va['category']} | {va['source']} | "
                        f"{ea}{f' ({la})' if la else ''} | {eb}{f' ({lb})' if lb else ''} | {problem} |")
            asks.append(f'{name} [{va["source"]}]: {problem}')
    if rows:
        body += [f'| Variable | Category | Source | {A} | {B} | Problem on {B} |',
                 '|---|---|---|---|---|---|', *rows, '']
    else:
        body += [f'Every variable means the same on {B} as on {A}.', '']

    # 3. Schema.
    body += ['## 3. Tables and columns the Direct SQL uses', '']
    missing_objects, col_rows = [], []
    for name, files in a['referenced_objects'].items():
        sa, sb = a['schema'].get(name), b['schema'].get(name)
        if sa is None:
            continue  # not an object on the reference env either (alias, temp table)
        if sb is None:
            missing_objects.append(f"| {name} | {sa['type']} | {', '.join(files)} |")
            asks.append(f"Create {sa['type'].lower().replace('_', ' ')} {name} "
                        f"(used by {', '.join(files)})")
            continue
        for ck, ca in sa['columns'].items():
            cb = sb['columns'].get(ck)
            if cb is None:
                users = files_naming(ca['name'], files)
                if users:
                    col_rows.append(f"| {name} | {ca['name']} | {type_text(ca)} | missing | "
                                    f"**blocks** {', '.join(users)} |")
                    asks.append(f"Add column {name}.{ca['name']} {type_text(ca)}"
                                f"{'' if ca['nullable'] else ' NOT NULL'} (used by {', '.join(users)})")
                else:
                    col_rows.append(f"| {name} | {ca['name']} | {type_text(ca)} | missing | "
                                    f"not named by the migration SQL - harmless |")
            elif type_text(ca) != type_text(cb):
                col_rows.append(f"| {name} | {ca['name']} | {type_text(ca)} | {type_text(cb)} | "
                                f"type differs - check truncation |")
        for ck, cb in sb['columns'].items():
            if ck in sa['columns']:
                continue
            must = not (cb['nullable'] or cb['has_default'] or cb['identity'] or cb['computed'])
            col_rows.append(f"| {name} | {cb['name']} | (absent) | {type_text(cb)}"
                            f"{' NOT NULL, no default' if must else ''} | "
                            f"{'**blocks** INSERTs that omit it - migration SQL change, not a DBA ask' if must else f'extra on {B}, harmless'} |")
    if missing_objects:
        body += [f'Missing on {B}:', '', '| Object | Type | Used by |', '|---|---|---|',
                 *missing_objects, '']
    if col_rows:
        body += ['Column differences:', '', f'| Object | Column | {A} | {B} | Effect |',
                 '|---|---|---|---|---|', *col_rows, '']
    if not missing_objects and not col_rows:
        body += ['Every referenced object and column matches.', '']

    unreadable = [t for t in LOOKUPS if 'error' in b['lookups'].get(t, {})
                  and 'error' not in a['lookups'].get(t, {})]
    if unreadable:
        body += [f'## 4. Lookup tables unreadable on {B}', '',
                 *[f"- {t}: {b['lookups'][t]['error']}" for t in unreadable], '']

    head = [
        f'# Migration readiness: {B} compared with {A}', '',
        f"- {A}: {a['server']} / {a['database']}, snapshot {a['taken_at']}",
        f"- {B}: {b['server']} / {b['database']}, snapshot {b['taken_at']}", '',
        f'## To ask for on {B}', '',
        *([f'{i}. {s}' for i, s in enumerate(asks, 1)] or ['Nothing - it matches.']), '',
    ]
    if also_on_a:
        head += [f'## Gaps on {A} too (not a {B} ask - fix the mapping file or both DBs)', '',
                 *[f'- {s}' for s in also_on_a], '']
    return '\n'.join(head + body)


# --- signing in as a person -------------------------------------------------

class UserConnection:
    """Read-only connection as the operator's own Entra account.

    For reading an environment this repo holds no service principal for (prod).
    DatabaseHelper deliberately never authenticates a person, so this lives here,
    behind an explicit --server, and only offers what snapshot() calls.
    """

    def __init__(self, server: str, database: str, auth: str, user: Optional[str],
                 driver: str = 'ODBC Driver 17 for SQL Server'):
        import pyodbc
        parts = [f'DRIVER={{{driver}}}', f'SERVER={server}', f'DATABASE={database}',
                 'Encrypt=yes', 'TrustServerCertificate=no',
                 # Nothing here writes, and saying so lets a read-only replica serve it.
                 'ApplicationIntent=ReadOnly']
        attrs = {}
        if auth == 'integrated':
            parts.append('Authentication=ActiveDirectoryIntegrated')
        elif auth == 'interactive':
            # Driver 17's own sign-in window is an old embedded browser that Entra
            # refuses for MFA registration ("Update your browser"); prefer 'browser'.
            parts.append('Authentication=ActiveDirectoryInteractive')
            if user:
                parts.append(f'UID={user}')
        else:
            # Sign in through the system browser and hand the driver the token.
            import struct
            from azure.identity import InteractiveBrowserCredential
            token = InteractiveBrowserCredential(login_hint=user).get_token(
                'https://database.windows.net/.default').token.encode('utf-16-le')
            SQL_COPT_SS_ACCESS_TOKEN = 1256
            attrs[SQL_COPT_SS_ACCESS_TOKEN] = struct.pack(f'<I{len(token)}s', len(token), token)
        self.connection = pyodbc.connect(';'.join(parts) + ';', timeout=60, readonly=True,
                                         attrs_before=attrs or None)

    def execute_query(self, query: str):
        import pandas as pd
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            columns = [c[0] for c in cursor.description]
            return pd.DataFrame.from_records([tuple(r) for r in cursor.fetchall()], columns=columns)
        finally:
            cursor.close()

    def close_connections(self) -> None:
        self.connection.close()


# --- entry ------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('snapshot', help='Read one environment into a JSON snapshot')
    p.add_argument('environment', nargs='?', default=None)
    p.add_argument('--config', dest='config_path', default=None, metavar='PATH',
                   help='An <env>.env file, or the directory holding one. Keep '
                        f'credentials for other environments outside the repo. Default: {DEFAULT_CONFIG_DIR}')
    p.add_argument('--variables', default=DEFAULT_VARIABLES_DIR, metavar='DIR')
    p.add_argument('--out', default=None, metavar='FILE')
    p.add_argument('--server', default=None,
                   help='Sign in as yourself instead of an env file: the server to read. '
                        'Needs --database; the environment argument names the snapshot.')
    p.add_argument('--database', default=None)
    p.add_argument('--auth', choices=('browser', 'integrated', 'interactive'), default='browser',
                   help='With --server: browser (sign in through your default browser; '
                        'needs azure-identity, default), integrated (silent Windows sign-in) '
                        "or interactive (the ODBC driver's own sign-in window)")
    p.add_argument('--user', default=None, help='Your sign-in name, pre-filled at sign-in')

    d = sub.add_parser('diff', help='Report what B lacks compared with A')
    d.add_argument('a', help='Reference snapshot (e.g. testse.json)')
    d.add_argument('b', help='Snapshot to check (e.g. prod.json)')
    d.add_argument('--variables', default=DEFAULT_VARIABLES_DIR, metavar='DIR')
    d.add_argument('--out', default=None, metavar='FILE', help='Markdown report path')

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    if args.command == 'snapshot':
        if args.server:
            if not (args.database and args.environment):
                raise SystemExit('--server needs --database and an environment name')
            environment = args.environment
            db = UserConnection(args.server, args.database, args.auth, args.user)
        else:
            from tools.env_target import resolve_environment
            environment, config_dir = resolve_environment(args)
            db = DatabaseHelper(environment=environment, config_path=config_dir)
        try:
            snap = snapshot(db, environment, os.path.abspath(args.variables))
        finally:
            db.close_connections()
        out = args.out or os.path.join(DEFAULT_OUT_DIR, f'readiness_{environment}.json')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf-8') as handle:
            json.dump(snap, handle, indent=1, ensure_ascii=False)
        print(f"Snapshot of {snap['server']}/{snap['database']} written to {out}")
        return 0

    with open(args.a, 'r', encoding='utf-8') as handle:
        a = json.load(handle)
    with open(args.b, 'r', encoding='utf-8') as handle:
        b = json.load(handle)
    report = diff(a, b, os.path.abspath(args.variables))
    out = args.out or os.path.join(DEFAULT_OUT_DIR,
                                   f"readiness_{b['environment']}_vs_{a['environment']}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as handle:
        handle.write(report)
    print(f'Report written to {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
