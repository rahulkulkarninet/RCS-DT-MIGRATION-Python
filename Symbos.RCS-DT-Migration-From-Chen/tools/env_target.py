"""Where a tool's environment and table list come from.

Shared by the two archive tools so they take the same arguments and resolve them
the same way. Both default to the repo's own config/ and variables/, and both
accept --config for an environment whose credentials are kept outside the repo.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from config_parser import ConfigParser  # noqa: E402

DEFAULT_CONFIG_DIR = os.path.join(REPO_ROOT, 'config')
DEFAULT_VARIABLES_DIR = os.path.join(REPO_ROOT, 'variables')

TABLE_KEYWORDS_FILE = 'table_keywords.json'


def add_target_arguments(parser: argparse.ArgumentParser, verb: str) -> None:
    """The environment, --config, --variables and --table arguments."""
    parser.add_argument('environment', nargs='?', default=None,
                        help='Environment name, e.g. dev, v10, testse. Optional '
                             'when --config names an environment file, whose '
                             'own name is then the environment')
    parser.add_argument('--config', dest='config_path', default=None, metavar='PATH',
                        help='Environment file to use, or the directory holding '
                             f'<env>.env. Default: {DEFAULT_CONFIG_DIR}')
    parser.add_argument('--variables', dest='variables_path', default=None,
                        metavar='DIR',
                        help=f'Folder holding {TABLE_KEYWORDS_FILE}. Default: '
                             f'{DEFAULT_VARIABLES_DIR}')
    parser.add_argument('--table', action='append', dest='tables', default=None,
                        help=f'{verb} only this table (repeatable). Default: '
                             f'every table in {TABLE_KEYWORDS_FILE}')


def resolve_environment(args: argparse.Namespace) -> Tuple[str, str]:
    """(environment name, directory holding <env>.env) from the arguments.

    DatabaseHelper takes a name and a directory rather than a path, so a
    --config pointing straight at a file is split into the two. The file's own
    name is then the environment name, which is what lets the positional
    argument be left off in that form.
    """
    if not args.config_path:
        if not args.environment:
            raise SystemExit(
                'Name the environment, or point --config at an environment file')
        return args.environment, DEFAULT_CONFIG_DIR

    path = os.path.abspath(args.config_path)

    if os.path.isdir(path):
        if not args.environment:
            raise SystemExit(
                f'--config {path} is a directory, so name the environment too')
        return args.environment, path

    if not os.path.isfile(path):
        raise SystemExit(f'No environment file or directory at {path}')

    name = os.path.splitext(os.path.basename(path))[0]
    # Both given and disagreeing would load neither the named file nor an
    # obviously wrong one - DatabaseHelper would go looking for
    # <environment>.env in the same directory - so say so rather than guess.
    if args.environment and args.environment.lower() != name.lower():
        raise SystemExit(
            f'--config names environment {name!r} but the environment argument '
            f'is {args.environment!r}. Drop one of them.')
    return name, os.path.dirname(path)


def resolve_variables_dir(args: argparse.Namespace) -> str:
    return os.path.abspath(args.variables_path or DEFAULT_VARIABLES_DIR)


def resolve_tables(environment: str, variables_dir: str,
                   requested: List[str]) -> List[str]:
    """The RC_* staging tables this run covers, from table_keywords.json."""
    if requested:
        return requested

    config = ConfigParser(db_environment=environment, variables_folder=variables_dir)
    # Only the table list matters to these tools; load_configs would read four
    # more files they have no use for and warn about any that are absent.
    keywords = config.load_json(TABLE_KEYWORDS_FILE)
    return [name for name in keywords.values() if name]


def describe_target(environment: str, config_dir: str, variables_dir: str,
                    tables: List[str], requested: List[str]) -> str:
    """One line naming the env file and where the table list came from."""
    source = '--table' if requested else os.path.join(variables_dir,
                                                      TABLE_KEYWORDS_FILE)
    return (f'Environment {environment} '
            f'({os.path.join(config_dir, environment + ".env")}), '
            f'{len(tables)} table(s) from {source}')
