"""Test every client against every environment, and show where each one works.

Four clients reach the database and they do not share authentication support:

  pyodbc / SQLAlchemy  ODBC keywords, so ActiveDirectoryServicePrincipal works
  bcp                  -G combinations, plus a DSN via -D. The DSN is the only
                       way to give bcp a service principal.
  sqlcmd               classic (ODBC) has no -D and no service-principal option;
                       go-sqlcmd has --authentication-method, so it does. The
                       binary is resolved explicitly because installing
                       go-sqlcmd does not displace the classic one on PATH.

Read-only by construction: every probe runs SELECT 1 and nothing else. Candidates
that would prompt are reported as skipped rather than run, so this never blocks.
Secrets are never printed. Environments and DSNs come from config/*.env, so a new
environment is picked up with no change here.

    python tools/test_connections.py                 # every environment
    python tools/test_connections.py --env uat testse
    python tools/test_connections.py --clients bcp sqlcmd
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import db_manager as dbm  # noqa: E402

LOGIN_TIMEOUT = 15
PROC_TIMEOUT = 90
BANNED = ('prod', 'production', 'live')
CLIENTS = ('pyodbc', 'sqlalchemy', 'bcp', 'sqlcmd')

OK, FAIL, SKIP, NA = 'OK', 'FAIL', 'SKIP', 'n/a'


def short(text: str, n: int = 200) -> str:
    return ' '.join((text or '').split())[:n]


def discover_environments() -> List[str]:
    names = sorted(os.path.basename(p)[:-4]
                   for p in glob.glob(os.path.join(REPO_ROOT, 'config', '*.env')))
    return [n for n in names if not any(b in n.lower() for b in BANNED)]


# --- ODBC -------------------------------------------------------------------

def odbc_candidates(helper) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """(name, connection string, skip_reason)."""
    cfg = helper.config
    server, database = cfg['SERVER'], cfg['DATABASE']
    cid, secret = cfg.get('CLIENT_ID', ''), cfg.get('CLIENT_SECRET', '')
    out: List[Tuple[str, Optional[str], Optional[str]]] = []

    def base(driver: str) -> str:
        return (f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
                f"Encrypt=yes;TrustServerCertificate=yes;"
                f"Connection Timeout={LOGIN_TIMEOUT};")

    for driver, tag in (('ODBC Driver 17 for SQL Server', '17'),
                        ('ODBC Driver 18 for SQL Server', '18')):
        if cid and secret:
            out.append((f'service-principal (drv {tag})',
                        base(driver) + f"UID={cid};PWD={secret};"
                                       "Authentication=ActiveDirectoryServicePrincipal;",
                        None))
        if helper.is_azure():
            out.append((f'entra-integrated (drv {tag})',
                        base(driver) + "Authentication=ActiveDirectoryIntegrated;",
                        None))
        else:
            out.append((f'trusted (drv {tag})',
                        base(driver) + "Trusted_Connection=yes;", None))
    out.append(('entra-interactive', None, 'would open a dialog'))
    return out


def try_pyodbc(conn_str: str) -> Tuple[bool, str]:
    import pyodbc
    try:
        with pyodbc.connect(conn_str, timeout=LOGIN_TIMEOUT) as cn:
            cur = cn.cursor()
            cur.execute('SELECT 1')
            cur.fetchone()
        return True, ''
    except Exception as e:                                       # noqa: BLE001
        return False, short(str(e))


def try_sqlalchemy(conn_str: str) -> Tuple[bool, str]:
    from urllib.parse import quote_plus
    from sqlalchemy import create_engine, text
    engine = None
    try:
        engine = create_engine(
            f'mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}')
        with engine.connect() as cn:
            cn.execute(text('SELECT 1')).scalar()
        return True, ''
    except Exception as e:                                       # noqa: BLE001
        return False, short(str(e))
    finally:
        if engine is not None:
            engine.dispose()


# --- CLI --------------------------------------------------------------------

def cli_candidates(helper, tool: str
                   ) -> List[Tuple[str, Optional[List[str]], Optional[str]]]:
    """(name, args, skip_reason). args None means not applicable to this tool."""
    cfg = helper.config
    server, database = cfg['SERVER'], cfg['DATABASE']
    cid, secret = cfg.get('CLIENT_ID', ''), cfg.get('CLIENT_SECRET', '')
    dsn = cfg.get('BCP_DSN', '')
    sql_login = os.getenv('BCP_USERNAME', '')
    target = ['-S', server, '-d', database]
    out: List[Tuple[str, Optional[List[str]], Optional[str]]] = []

    # bcp: a DSN is the only route for a service principal.
    if tool == 'bcp':
        if dsn and cid and secret:
            args = ['-D', '-S', dsn, '-d', database, '-U', cid, '-P', secret]
            if helper._dsn_targets_this_server(dsn):
                out.append((f'dsn-service-principal [{dsn}]', args, None))
            else:
                out.append((f'dsn-service-principal [{dsn}]', None,
                            'DSN points at another server'))
    else:
        out.append(('dsn-service-principal', None, None))

    # go-sqlcmd is the only sqlcmd with a service-principal option.
    if tool == 'sqlcmd':
        if cid and secret and helper.sqlcmd_is_go():
            os.environ['SQLCMDPASSWORD'] = secret
            out.append(('go-service-principal',
                        target + ['--authentication-method',
                                  'ActiveDirectoryServicePrincipal', '-U', cid],
                        None))
        elif cid and secret:
            out.append(('go-service-principal', None, 'go-sqlcmd not installed'))
    else:
        out.append(('go-service-principal', None, None))

    if cid and secret:
        out.append(('service-principal (-G -U -P)',
                    target + ['-G', '-U', cid, '-P', secret], None))
    if helper.is_azure():
        out.append(('entra-integrated (-G)', target + ['-G'], None))
    else:
        out.append(('trusted', target + (['-T'] if tool == 'bcp' else ['-E']), None))
    if sql_login and secret:
        out.append(('sql login', target + ['-U', sql_login, '-P', secret], None))
    return out


def try_bcp(args: List[str]) -> Tuple[bool, str]:
    work = tempfile.mkdtemp(prefix='rcsconn_')
    out_path = os.path.join(work, 'p.dat')
    try:
        r = subprocess.run(['bcp', 'SELECT 1', 'queryout', out_path, '-c',
                            '-l', str(LOGIN_TIMEOUT)] + args,
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=PROC_TIMEOUT)
        return (True, '') if r.returncode == 0 else (False, short(f'{r.stdout} {r.stderr}'))
    except Exception as e:                                       # noqa: BLE001
        return False, short(str(e))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def try_sqlcmd(args: List[str], executable: str) -> Tuple[bool, str]:
    try:
        r = subprocess.run([executable, '-Q', 'SELECT 1', '-l', str(LOGIN_TIMEOUT)]
                           + args,
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=PROC_TIMEOUT)
        return (True, '') if r.returncode == 0 else (False, short(f'{r.stdout} {r.stderr}'))
    except Exception as e:                                       # noqa: BLE001
        return False, short(str(e))


def probe_environment(env: str, clients: Tuple[str, ...]
                      ) -> Tuple[Dict[Tuple[str, str], str], Dict[str, str], dict]:
    """Returns (results keyed by (client, candidate), failure details, metadata)."""
    results: Dict[Tuple[str, str], str] = {}
    details: Dict[str, str] = {}
    try:
        helper = dbm.DatabaseHelper(env)
    except Exception as e:                                       # noqa: BLE001
        return results, {'(config)': short(str(e))}, {'error': short(str(e))}

    meta = {
        'server': helper.config.get('SERVER', ''),
        'database': helper.config.get('DATABASE', ''),
        'azure': helper.is_azure(),
        'client_id': bool(helper.config.get('CLIENT_ID')),
        'dsn': helper.config.get('BCP_DSN', ''),
        'sqlcmd': helper.sqlcmd_executable(),
        'sqlcmd_is_go': helper.sqlcmd_is_go(),
    }
    if any(b in (meta['server'] or '').lower() for b in BANNED):
        return results, {'(refused)': 'server name looks like production'}, meta

    for name, conn_str, skip in odbc_candidates(helper):
        for client, fn in (('pyodbc', try_pyodbc), ('sqlalchemy', try_sqlalchemy)):
            if client not in clients:
                continue
            if skip or conn_str is None:
                results[(client, name)] = SKIP
                continue
            ok, err = fn(conn_str)
            results[(client, name)] = OK if ok else FAIL
            if not ok:
                details[f'{env}/{client}/{name}'] = err

    for tool in ('bcp', 'sqlcmd'):
        if tool not in clients:
            continue
        if tool == 'bcp' and not helper.bcp_available():
            results[(tool, '(not installed)')] = NA
            continue
        for name, args, skip in cli_candidates(helper, tool):
            if args is None:
                results[(tool, name)] = SKIP if skip else NA
                if skip:
                    details[f'{env}/{tool}/{name}'] = skip
                continue
            ok, err = (try_bcp(args) if tool == 'bcp'
                       else try_sqlcmd(args, helper.sqlcmd_executable()))
            results[(tool, name)] = OK if ok else FAIL
            if not ok:
                details[f'{env}/{tool}/{name}'] = err
    return results, details, meta


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--env', nargs='*', default=None,
                   help='Environments to test. Default: every config/*.env.')
    p.add_argument('--clients', nargs='*', default=list(CLIENTS), choices=CLIENTS,
                   help='Clients to test. Default: all four.')
    p.add_argument('--details', action='store_true',
                   help='Print the failure message for every failed probe.')
    args = p.parse_args()

    envs = args.env or discover_environments()
    envs = [e for e in envs if not any(b in e.lower() for b in BANNED)]
    if not envs:
        print('no environments to test')
        return 2
    clients = tuple(args.clients)

    print('Read-only: every probe is SELECT 1. Nothing is read, written or created.')
    print()

    all_results: Dict[str, Dict[Tuple[str, str], str]] = {}
    all_details: Dict[str, str] = {}
    for env in envs:
        res, det, meta = probe_environment(env, clients)
        all_results[env] = res
        all_details.update(det)
        flags = []
        if meta.get('azure'):
            flags.append('azure')
        if meta.get('client_id'):
            flags.append('client id set')
        if meta.get('dsn'):
            flags.append(f"dsn={meta['dsn']}")
        if meta.get('sqlcmd_is_go'):
            flags.append('go-sqlcmd')
        print(f"{env:<8} {meta.get('server', '?'):<40} "
              f"{meta.get('database', '?'):<14} {', '.join(flags)}")
    print()

    rows = sorted({k for r in all_results.values() for k in r},
                  key=lambda k: (CLIENTS.index(k[0]) if k[0] in CLIENTS else 9, k[1]))
    w1 = max([len(c) for c, _ in rows] + [6]) + 2
    w2 = max([len(n) for _, n in rows] + [10]) + 2
    header = f'{"client":<{w1}}{"credential":<{w2}}' + ''.join(f'{e:<10}' for e in envs)
    print(header)
    print('-' * len(header))
    for client, name in rows:
        line = f'{client:<{w1}}{name:<{w2}}'
        for env in envs:
            line += f'{all_results[env].get((client, name), "-"):<10}'
        print(line)

    print()
    print('Working combinations by environment:')
    for env in envs:
        works = [f'{c}/{n}' for (c, n), r in all_results[env].items() if r == OK]
        print(f'  {env:<8} {len(works)}')
        for w in sorted(works):
            print(f'             {w}')

    print()
    print('Per client, environments where at least one credential works:')
    for client in clients:
        good = [e for e in envs
                if any(r == OK for (c, _), r in all_results[e].items() if c == client)]
        print(f'  {client:<12} {", ".join(good) if good else "none"}')

    if args.details and all_details:
        print()
        print('Failure details:')
        for key in sorted(all_details):
            print(f'  {key}')
            print(f'      {all_details[key]}')

    every = all(any(r == OK for r in all_results[e].values()) for e in envs)
    return 0 if every else 1


if __name__ == '__main__':
    raise SystemExit(main())
