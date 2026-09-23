"""Approval gates for the migration, usable interactively or unattended.

The pipeline had two bare `input()` calls, so a run could not proceed without a
human at the keyboard. At the volumes this migration now targets a load takes
hours, which makes unattended execution a requirement rather than a convenience.

Interactive behaviour is unchanged when no flags are passed: the same prompts,
the same y/n/q semantics.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Optional

# Gate names. Each corresponds to one approval point in the workflow.
GATE_STAGING = 'staging'
GATE_SQL = 'sql'
ALL_GATES = (GATE_STAGING, GATE_SQL)

# --auto-approve choices.
APPROVE_NONE = 'none'
APPROVE_STAGING = 'staging'
APPROVE_ALL = 'all'
APPROVE_CHOICES = (APPROVE_NONE, APPROVE_STAGING, APPROVE_ALL)


class ApprovalPolicy:
    """Decides whether an approval gate proceeds.

    non_interactive suppresses all prompting. auto_approve says which gates are
    pre-approved: 'none' (default), 'staging' (the staging gate only), or 'all'.
    """

    def __init__(self, non_interactive: bool = False,
                 auto_approve: str = APPROVE_NONE,
                 logger: Optional[logging.Logger] = None,
                 stream: Any = None):
        if auto_approve not in APPROVE_CHOICES:
            raise ValueError(
                f'auto_approve must be one of {APPROVE_CHOICES}, got {auto_approve!r}'
            )
        self.non_interactive = bool(non_interactive)
        self.auto_approve = auto_approve
        self.logger = logger or logging.getLogger(__name__)
        self._stream = stream

    # -- policy ---------------------------------------------------------

    def is_auto_approved(self, gate: str) -> bool:
        if self.auto_approve == APPROVE_ALL:
            return True
        if self.auto_approve == APPROVE_STAGING:
            return gate == GATE_STAGING
        return False

    @property
    def approves_everything(self) -> bool:
        return self.auto_approve == APPROVE_ALL

    def describe(self) -> str:
        mode = 'non-interactive' if self.non_interactive else 'interactive'
        return f'{mode}, auto-approve={self.auto_approve}'

    # -- the gate -------------------------------------------------------

    def confirm(self, prompt: str, gate: str) -> bool:
        """Return True to proceed. Raises KeyboardInterrupt if the user quits.

        Declining returns False; the caller decides what skipping means.
        """
        if self.is_auto_approved(gate):
            self.logger.info(f'[auto-approved: {gate}] {prompt}')
            return True

        if self.non_interactive:
            # Never prompt. Not approved means declined, said plainly so an
            # unattended run that does nothing is not mistaken for success.
            self.logger.warning(
                f'[declined: {gate}] {prompt} — running non-interactively and '
                f'this gate is not covered by --auto-approve={self.auto_approve}'
            )
            return False

        try:
            answer = input(f'{prompt} (y/n/q): ').lower().strip()
        except (EOFError, OSError):
            # No console: a bare input() here used to abort mid-run with an
            # EOFError traceback.
            self.logger.error(
                f'[declined: {gate}] {prompt} — no console available to read a '
                f'response. Pass --non-interactive with --auto-approve to run '
                f'unattended.'
            )
            return False

        if answer == 'q':
            raise KeyboardInterrupt('User requested quit')
        return answer == 'y'


def stdin_is_interactive() -> bool:
    """True if there is a console to prompt on."""
    try:
        return bool(sys.stdin) and sys.stdin.isatty()
    except Exception:
        return False


def resolve_policy(non_interactive: bool, auto_approve: str,
                   logger: Optional[logging.Logger] = None) -> ApprovalPolicy:
    """Build a policy, and reject combinations that cannot do useful work.

    Two footguns are refused up front rather than discovered per customer:
      - non-interactive with nothing auto-approved would decline every gate and
        migrate nothing, while still exiting successfully.
      - no console and no flags would hit EOFError on the first prompt.
    """
    log = logger or logging.getLogger(__name__)

    if non_interactive and auto_approve == APPROVE_NONE:
        raise SystemExit(
            'Refusing to run: --non-interactive with --auto-approve=none would '
            'decline every approval gate and migrate nothing. Pass '
            '--auto-approve=staging or --auto-approve=all.'
        )

    if not non_interactive and not stdin_is_interactive():
        if auto_approve == APPROVE_ALL:
            log.warning(
                'No console detected; proceeding because --auto-approve=all '
                'covers every gate.'
            )
            non_interactive = True
        else:
            raise SystemExit(
                'Refusing to run: no console is available to answer the approval '
                'prompts, and --auto-approve=' + auto_approve + ' does not cover '
                'every gate. Pass --non-interactive --auto-approve=all to run '
                'unattended.'
            )

    policy = ApprovalPolicy(non_interactive=non_interactive,
                            auto_approve=auto_approve, logger=log)
    log.info(f'Approval policy: {policy.describe()}')
    return policy
