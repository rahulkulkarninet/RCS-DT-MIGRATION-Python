r"""Replay the treatment step rule (variables/treatment_step_codes.json) over a client's
RC_ACCOUNT_EXTRACT CSVs and compare it with the "Complete Mapping" tab of Suz's
Treatment_Migration_Validation workbook.

    python tools/validate_treatment_step_rule.py SM9641 --account-csv "C:\extracts\SMAUS_SM9641_RC_ACCOUNT_EXTRACT_*.csv" --workbook "C:\...\Treatment_Migration_Validation.xlsx"
    python tools/validate_treatment_step_rule.py CG8110 --account-csv ... --workbook ... --as-of 2026-09-23 --mismatches out.csv

Same rule as treatment_step_service.py, in pandas instead of T-SQL, so the two must agree:
  treated  : ladder offset + MA_Next_Step_No, capped at the ladder's last step
  untreated: default step, or the first age band the debt age fits
  closed   : no step
--as-of is the date debt age is measured at (the workbook's snapshot date; default today).
The workbook's DbCode is RCS Short_Debt_Code. Only accounts present in both are compared;
accounts the rule treats but the workbook omits, and vice versa, are counted separately.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import date
from typing import Optional

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(REPO_ROOT, 'variables', 'treatment_step_codes.json')


COLUMN_MAPPING = os.path.join(REPO_ROOT, 'column mapping', 'RC_ACCOUNT_EXTRACT.csv')


def staging_renames() -> dict:
    """Extract header -> staging column, from the same mapping file the loader uses
    (e.g. the second Next_Step_No header, MA_Next_Step_No, lands in Next_Step_No_1)."""
    if not os.path.exists(COLUMN_MAPPING):
        return {}
    mapping = pd.read_csv(COLUMN_MAPPING, dtype=str).fillna('')
    if mapping.shape[1] < 2:
        return {}
    a, b = mapping.columns[0], mapping.columns[1]
    # whichever column holds the staging names (it contains Next_Step_No_1) is the target
    target, source = (a, b) if (mapping[a] == 'Next_Step_No_1').any() else (b, a)
    return {src: tgt for src, tgt in zip(mapping[source], mapping[target]) if src and tgt and src != tgt}


def load_extract(pattern: str) -> pd.DataFrame:
    files = sorted(glob.glob(pattern))
    if not files:
        raise SystemExit(f'no account extract matches {pattern}')
    frames = [pd.read_csv(f, dtype=str, index_col=False, encoding_errors='replace') for f in files]
    frame = pd.concat(frames, ignore_index=True).drop_duplicates('Short_Debt_Code', keep='last')
    return frame.rename(columns=staging_renames())


def derive(extract: pd.DataFrame, config: dict, as_of: date) -> pd.DataFrame:
    cols = config.get('source_columns', {}) or {}
    c_cur = cols.get('current_treatment', 'Current_Treatment')
    c_next = cols.get('next_step', 'MA_Next_Step_No')
    c_closed = cols.get('closed_date', 'Date_Closed')
    c_age = cols.get('age_from', 'Date_Time_Entered')
    ladder = config['ladder']
    code_map = {}
    for new_code, codes in config['rcs_treatment_codes'].items():
        for code in codes:
            code_map.setdefault(str(code).strip(), new_code)
    untreated = config['untreated']
    bands = sorted(untreated.get('age_bands', []) or [], key=lambda b: int(b['max_age_days']))

    out = extract[['Short_Debt_Code', 'Full_Debt_Code', c_cur, c_next, c_closed, c_age, 'MA_Status']].copy()
    out['is_open'] = out[c_closed].isna() | (out[c_closed].astype(str).str.strip() == '')
    out['age_days'] = (pd.Timestamp(as_of) - pd.to_datetime(out[c_age], errors='coerce')).dt.days
    nxt = pd.to_numeric(out[c_next], errors='coerce')
    new_code = out[c_cur].astype(str).str.strip().map(code_map)

    def untreated_step(age: Optional[float]) -> int:
        if pd.notna(age):
            for band in bands:
                if age <= int(band['max_age_days']):
                    return int(band['step'])
        return int(untreated['default_step'])

    steps, codes = [], []
    for is_open, nc, n, age in zip(out['is_open'], new_code, nxt, out['age_days']):
        if not is_open:
            steps.append(None); codes.append(None); continue
        if pd.notna(nc) and pd.notna(n) and n >= 1:
            spec = ladder[nc]
            steps.append(min(int(spec['first_step']) - 1 + int(n), int(spec['last_step']))); codes.append(nc)
        else:
            steps.append(untreated_step(age)); codes.append('UNTREATED')
    out['rule_step'] = steps
    out['rule_code'] = codes
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('client')
    ap.add_argument('--account-csv', required=True, help='glob of the client\'s RC_ACCOUNT_EXTRACT CSV(s)')
    ap.add_argument('--workbook', required=True)
    ap.add_argument('--sheet', default='Complete Mapping')
    ap.add_argument('--as-of', default=None, help='YYYY-MM-DD the workbook was cut (debt age reference); default today')
    ap.add_argument('--config', default=CONFIG)
    ap.add_argument('--mismatches', default=None, help='write the disagreeing rows to this CSV')
    args = ap.parse_args()

    with open(args.config, 'r', encoding='utf-8') as handle:
        config = json.load(handle)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    extract = load_extract(args.account_csv)
    derived = derive(extract, config, as_of)
    sheet = pd.read_excel(args.workbook, sheet_name=args.sheet, dtype=str)
    sheet = sheet[sheet['Client Code'].astype(str).str.strip().str.upper() == args.client.upper()].copy()
    if sheet.empty:
        raise SystemExit(f'{args.sheet} has no rows for {args.client}')
    sheet['sheet_step'] = pd.to_numeric(sheet['New Treatment step'], errors='coerce')

    both = derived.merge(sheet[['DbCode', 'Current Treatment Code', 'Current Treatment Step', 'Account Status', 'sheet_step']],
                         left_on='Short_Debt_Code', right_on='DbCode', how='inner')
    open_only_rule = derived[derived['is_open'] & ~derived['Short_Debt_Code'].isin(sheet['DbCode'])]
    sheet_only = sheet[~sheet['DbCode'].isin(derived['Short_Debt_Code'])]

    agree = (both['rule_step'] == both['sheet_step'])
    print(f'{args.client}: extract {len(extract)} accounts ({int(derived["is_open"].sum())} open), workbook {len(sheet)} rows')
    print(f'  compared {len(both)}: rule == workbook {int(agree.sum())} ({agree.mean():.1%}), differ {int((~agree).sum())}')
    treated = both['rule_code'] != 'UNTREATED'
    if treated.any():
        print(f'    on a mapped treatment: {int(treated.sum())}, agree {agree[treated].mean():.1%}')
    if (~treated).any():
        print(f'    untreated open:        {int((~treated).sum())}, agree {agree[~treated].mean():.1%}')
    closed_in_sheet = both[~both['is_open']]
    print(f'  open in rule but not in workbook: {len(open_only_rule)}  |  in workbook but not in extract: {len(sheet_only)}'
          f'  |  closed in extract yet in workbook: {len(closed_in_sheet)}')
    mism = both[~agree]
    if not mism.empty:
        print('  top disagreements (rule code, extract code, extract next, rule step, workbook step, n):')
        top = (mism.groupby(['rule_code', config['source_columns'].get('current_treatment', 'Current_Treatment'),
                             config['source_columns'].get('next_step', 'MA_Next_Step_No'), 'rule_step', 'sheet_step'], dropna=False)
                   .size().sort_values(ascending=False).head(15))
        for key, n in top.items():
            print('   ', key, n)
    if args.mismatches:
        mism.to_csv(args.mismatches, index=False)
        print(f'  wrote {len(mism)} rows to {args.mismatches}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
