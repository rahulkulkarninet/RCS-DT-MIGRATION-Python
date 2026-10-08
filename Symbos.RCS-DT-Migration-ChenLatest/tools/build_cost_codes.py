

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import db_manager as dbm  # noqa: E402
import text_normalization as tn  # noqa: E402
from cost_service import (  # noqa: E402
    CHARGE_COLUMN_PREFIX,
    CODE_PATTERN,
    CostService,
)
from env_target import resolve_environment  # noqa: E402  - tools/, alongside this script

CODES_FILE = os.path.join(REPO_ROOT, 'variables', 'cost_codes.json')
DESCRIPTIONS_KEY = 'code_descriptions'


def read_mapping_table(helper) -> Dict[str, Dict[str, object]]:
    """code -> {description, destination_id} from CSRC_CostTypeMapping."""
    frame = helper.execute_query("""
        SELECT CostTypeCode, CostType, CostTypeIDDestination
        FROM CSRC_CostTypeMapping WITH (NOLOCK)
        WHERE CostTypeCode IS NOT NULL
        ORDER BY CostTypeCode
    """)
    catalogued: Dict[str, Dict[str, object]] = {}
    for row in frame.itertuples(index=False):
        code = str(row.CostTypeCode).strip()
        if not code or not CODE_PATTERN.match(code):
            continue
        catalogued[code] = {
            'description': str(row.CostType or '').strip(),
            'destination_id': (int(row.CostTypeIDDestination)
                               if row.CostTypeIDDestination is not None else None),
        }
    return catalogued


def label_by_id(helper) -> Dict[int, str]:
    frame = helper.execute_query("""
        SELECT CostTypeID, CostType FROM tblCostType WITH (NOLOCK)
        WHERE CostType IS NOT NULL
    """)
    return {int(r.CostTypeID): str(r.CostType).strip()
            for r in frame.itertuples(index=False)}


def json_assignments(config: dict) -> Dict[str, str]:
    """code -> the tblCostType label the JSON assigns it."""
    assigned: Dict[str, str] = {}
    for label, codes in (config.get('cost_types') or {}).items():
        if isinstance(codes, list):
            for code in codes:
                if code:
                    assigned[str(code).strip()] = str(label).strip()
    return assigned


def report(helper, config: dict, write: bool) -> int:
    catalogued = read_mapping_table(helper)
    labels = label_by_id(helper)
    assigned = json_assignments(config)
    excluded = {str(c).strip() for c in (config.get('not_costs') or {})}

    service = CostService(helper)
    charge_columns = service.read_source_charge_columns()
    extract_codes = [c[len(CHARGE_COLUMN_PREFIX):] for c in charge_columns]
    charged = service.read_charged_codes()

    print(f'CSRC_CostTypeMapping codes : {len(catalogued)}')
    print(f'RC_COSTS_EXTRACT Chg_ cols : {len(extract_codes)}')
    print(f'cost_codes.json assigned   : {len(assigned)} '
          f'(+{len(excluded)} excluded as not costs)')
    print(f'tblCostType labels         : {len(labels)}')
    print()

    # 1. Catalogued but not decided - a code someone listed that the migration
    #    would ignore. This is the COL shape, and the reason to run this.
    undecided = [c for c in catalogued
                 if c not in assigned and c not in excluded]
    # 2. In the extract with no mapping row and no JSON entry - the same gap, from
    #    the other direction. COL itself lands here: it has a column and a charge
    #    but was never catalogued.
    uncatalogued = [c for c in extract_codes
                    if c not in catalogued and c not in assigned
                    and c not in excluded]
    # 3. Catalogued with no column - dead entries, or a renamed extract.
    no_column = [c for c in catalogued if c not in extract_codes]
    # 4. Decided differently from the table. Expected wherever a human
    #    re-categorised a code, and the review list for that work.
    overridden = []
    for code, label in sorted(assigned.items()):
        entry = catalogued.get(code)
        if not entry:
            continue
        table_label = labels.get(entry['destination_id'])
        if table_label and tn.match_key(table_label) != tn.match_key(label):
            overridden.append((code, entry['description'], table_label, label))

    def money(code: str) -> str:
        if code not in charged:
            return ''
        rows, total = charged[code]
        return f'   *** CHARGED: {rows} row(s), {total}'

    print(f'--- catalogued but not decided in cost_codes.json ({len(undecided)}) ---')
    for code in sorted(undecided):
        print(f'  {code:<6} {catalogued[code]["description"]:<34}{money(code)}')
    if not undecided:
        print('  none')

    print(f'\n--- extract columns neither catalogued nor decided ({len(uncatalogued)}) ---')
    print('  (a charge here migrates nowhere - this is what COL was)')
    for code in sorted(uncatalogued):
        print(f'  {code:<6}{money(code)}')
    if not uncatalogued:
        print('  none')

    print(f'\n--- catalogued with no Chg_ column on the extract ({len(no_column)}) ---')
    for code in sorted(no_column):
        print(f'  {code:<6} {catalogued[code]["description"]}')
    if not no_column:
        print('  none')

    print(f'\n--- decided against the table\'s destination ({len(overridden)}) ---')
    print('  (the re-categorisation review list; the table says MERCANTILE for all 56)')
    for code, description, table_label, json_label in overridden:
        print(f'  {code:<6} {description:<34} {table_label} -> {json_label}')
    if not overridden:
        print('  none')

    charged_undecided = [c for c in (undecided + uncatalogued) if c in charged]
    print()
    if charged_undecided:
        print(f'{len(charged_undecided)} code(s) carry a charge with nowhere to go: '
              f'{", ".join(sorted(charged_undecided))}')
        print('The migration will stop the customer on these rather than drop them.')
    else:
        print('Every charged code in staging has somewhere to go.')

    if not write:
        missing_descriptions = [c for c in sorted(set(assigned) | excluded)
                                if c in catalogued
                                and config.get(DESCRIPTIONS_KEY, {}).get(c)
                                != catalogued[c]['description']]
        pending = len(undecided) + len(missing_descriptions)
        if pending:
            print(f'\n--write would add {len(undecided)} code(s) and refresh '
                  f'{len(missing_descriptions)} description(s).')
        else:
            print('\ncost_codes.json is up to date with the table; --write '
                  'would change nothing.')
        return 1 if charged_undecided else 0

    return apply_write(config, catalogued, labels, assigned, undecided,
                       charged_undecided)


def apply_write(config: dict, catalogued: dict, labels: dict,
                assigned: Dict[str, str], undecided: List[str],
                charged_undecided: List[str]) -> int:
    cost_types = config.setdefault('cost_types', {})

    added: List[str] = []
    unplaceable: List[str] = []
    for code in sorted(undecided):
        destination_id = catalogued[code]['destination_id']
        label = labels.get(destination_id) if destination_id is not None else None
        if not label:
            # No destination to reproduce, so there is nothing to generate that
            # would not be a guess. Left undecided, which the migration reports.
            unplaceable.append(code)
            continue
        cost_types.setdefault(label, []).append(code)
        added.append(f'{code} -> {label}')

    # Descriptions for every code the JSON mentions, so the codes left for
    # business sign-off are reviewable without opening the database.
    descriptions = {}
    for code in sorted(set(json_assignments(config)) |
                       {str(c).strip() for c in (config.get('not_costs') or {})}):
        entry = catalogued.get(code)
        if entry and entry['description']:
            descriptions[code] = entry['description']
    if descriptions:
        config[DESCRIPTIONS_KEY] = descriptions

    with open(CODES_FILE, 'w', encoding='utf-8') as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)
        handle.write('\n')

    print(f'\nWrote {CODES_FILE}')
    print(f'  codes added   : {len(added)}')
    for line in added:
        print(f'    {line}')
    print(f'  descriptions  : {len(descriptions)}')
    if unplaceable:
        print(f'  left undecided (no usable destination in the table): '
              f'{", ".join(unplaceable)}')
    return 1 if charged_undecided else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('environment', nargs='?', default=None,
                        help='Environment name, e.g. uat, testse, dev')
    parser.add_argument('--config', dest='config_path', default=None, metavar='PATH',
                        help='Environment file, or the directory holding <env>.env')
    parser.add_argument('--write', action='store_true',
                        help='Add newly catalogued codes and refresh descriptions. '
                             'Never changes a cost type or master cost already '
                             'recorded in the file.')
    args = parser.parse_args()

    environment, config_dir = resolve_environment(args)

    if not os.path.isfile(CODES_FILE):
        print(f'No {CODES_FILE}', file=sys.stderr)
        return 2
    with open(CODES_FILE, 'r', encoding='utf-8') as handle:
        config = json.load(handle)

    helper = dbm.DatabaseHelper(environment, config_path=config_dir)
    try:
        helper.connect_sqlalchemy()
        return report(helper, config, args.write)
    finally:
        helper.close_connections()


if __name__ == '__main__':
    raise SystemExit(main())
