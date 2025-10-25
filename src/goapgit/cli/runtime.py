"""Helpers shared across CLI commands for planning and execution."""

from __future__ import annotations

import io
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from goapgit.actions import (
    apply_path_strategy,
    auto_trivial_resolve,
    create_backup_ref,
    ensure_clean_or_stash,
    rebase_continue_or_abort,
)
from goapgit.core.explain import ActionContext
from goapgit.core.models import ActionSpec, Config, GoalSpec, RepoState, StrategyRule
from goapgit.core.planner import SimplePlanner
from goapgit.git.facade import GitCommandError, GitFacade
from goapgit.git.observe import RepoObserver
from goapgit.io import StructuredLogger, load_config

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from goapgit.core.executor import ActionRunner


@dataclass(slots=True)
class WorkflowContext:
    """Container bundling CLI dependencies for planning and execution."""

    repo_path: Path
    config: Config
    logger: StructuredLogger
    action_facade: GitFacade
    observer_facade: GitFacade
    observer: RepoObserver
    planner: SimplePlanner

    def build_action_runner(
        self,
    ) -> ActionRunner:
        """Return an executor-compatible action runner."""

        def runner(action: ActionSpec) -> bool:
            result: bool | None = None
            try:
                if action.name == "Safety:CreateBackupRef":
                    create_backup_ref(self.action_facade, self.logger)
                    result = True
                elif action.name == "Safety:EnsureCleanOrStash":
                    ensure_clean_or_stash(self.action_facade, self.logger)
                    result = True
                elif action.name == "Conflict:AutoTrivialResolve":
                    auto_trivial_resolve(self.action_facade, self.logger)
                    result = True
                elif action.name == "Conflict:ApplyPathStrategy":
                    state = self.observer.observe()
                    apply_path_strategy(
                        self.action_facade,
                        self.logger,
                        state.conflicts,
                        self.config.strategy_rules,
                    )
                    result = True
                elif action.name == "Rebase:ContinueOrAbort":
                    backup_ref = action.params.get("backup_ref") if action.params else None
                    result = rebase_continue_or_abort(
                        self.action_facade,
                        self.logger,
                        backup_ref=backup_ref,
                    )
            except GitCommandError as error:
                self.logger.error(
                    "action failed",
                    action=action.name,
                    returncode=error.returncode,
                    stderr=error.stderr,
                )
                return False
            except Exception as error:  # pragma: no cover - defensive logging
                self.logger.error("unexpected action failure", action=action.name, error=str(error))
                return False

            if result is None:
                self.logger.warning("unknown action", action=action.name)
                return False
            return bool(result)

        return runner


def default_config() -> Config:
    """Return the default configuration used when no config file is provided."""
    return Config(
        goal=GoalSpec(),
        strategy_rules=[],
        enable_rerere=True,
        conflict_style="zdiff3",
        allow_force_push=False,
        dry_run=True,
        max_test_runtime_sec=600,
    )


def load_cli_config(config_path: Path | None) -> Config:
    """Load configuration from ``config_path`` or fall back to defaults."""
    if config_path is None:
        return default_config()
    return load_config(path=config_path)


def build_workflow_context(
    repo_path: Path,
    config: Config,
    *,
    json_logs: bool,
    dry_run_actions: bool,
    silence_logs: bool,
) -> WorkflowContext:
    """Assemble the context required by CLI commands."""
    stream = io.StringIO() if silence_logs else sys.stderr
    logger = StructuredLogger(name="goapgit.cli", json_mode=json_logs, stream=stream)
    observer_facade = GitFacade(repo_path=repo_path, logger=logger, dry_run=False)
    action_facade = GitFacade(repo_path=repo_path, logger=logger, dry_run=dry_run_actions)
    observer = RepoObserver(observer_facade)
    planner = SimplePlanner()
    return WorkflowContext(
        repo_path=repo_path,
        config=config,
        logger=logger,
        action_facade=action_facade,
        observer_facade=observer_facade,
        observer=observer,
        planner=planner,
    )


def build_action_specs(state: RepoState, config: Config) -> list[ActionSpec]:
    """Return the default action catalogue for the current ``state``."""
    actions: list[ActionSpec] = [
        ActionSpec(
            name="Safety:CreateBackupRef",
            cost=0.4,
            rationale="Create a recoverable snapshot before making changes.",
        ),
        ActionSpec(
            name="Safety:EnsureCleanOrStash",
            cost=0.6,
            rationale="Ensure the working tree is clean or safely stashed.",
        ),
        ActionSpec(
            name="Conflict:AutoTrivialResolve",
            cost=0.8,
            rationale="Reuse rerere knowledge to resolve trivial conflicts.",
        ),
    ]

    if config.strategy_rules:
        actions.append(
            ActionSpec(
                name="Conflict:ApplyPathStrategy",
                cost=1.2,
                rationale="Apply configured conflict resolution strategies to matching paths.",
            ),
        )

    if state.ongoing_rebase:
        actions.append(
            ActionSpec(
                name="Rebase:ContinueOrAbort",
                cost=1.5,
                rationale="Complete or abort the ongoing rebase safely.",
            ),
        )

    return actions


def build_action_contexts(config: Config) -> dict[str, ActionContext]:
    """Create explanation metadata for known actions."""
    contexts: dict[str, ActionContext] = {
        "Safety:CreateBackupRef": ActionContext(
            reason="Create a timestamped backup ref so HEAD can be restored if later steps fail.",
            alternatives=(
                "Skip the backup and rely on reflog entries for recovery.",
                "Create a lightweight branch instead of an update-ref entry.",
            ),
            cost_override=1.0,
        ),
        "Safety:EnsureCleanOrStash": ActionContext(
            reason="Guarantee a clean working tree before automated operations continue.",
            alternatives=(
                "Abort the workflow and ask the operator to clean up manually.",
                "Create a temporary worktree rather than stashing changes.",
            ),
            cost_override=0.6,
        ),
        "Conflict:AutoTrivialResolve": ActionContext(
            reason="Reuse git rerere to automatically apply previously recorded resolutions.",
            alternatives=(
                "Resolve conflicts manually to confirm each change.",
                "Run a domain specific merge driver for known file types.",
            ),
            cost_override=0.8,
        ),
    }

    if config.strategy_rules:
        contexts["Conflict:ApplyPathStrategy"] = ActionContext(
            reason="Use configured strategy rules to prefer ours/theirs on matching paths.",
            alternatives=(
                "Escalate to manual resolution in an editor.",
                "Invoke a custom merge driver tuned for the file type.",
            ),
            cost_override=1.2,
        )

    contexts.setdefault(
        "Rebase:ContinueOrAbort",
        ActionContext(
            reason="Continue the rebase if conflicts are cleared, otherwise abort to restore HEAD.",
            alternatives=(
                "Abort immediately without attempting to continue.",
                "Skip rebase continuation and return control to the operator.",
            ),
            cost_override=1.5,
        ),
    )

    return contexts


def strategy_rules_to_params(rules: Sequence[StrategyRule]) -> list[dict[str, str | None]]:
    """Convert strategy rules to serialisable dictionaries for display."""
    return [
        {
            "pattern": rule.pattern,
            "resolution": rule.resolution,
            "when": rule.when,
        }
        for rule in rules
    ]


__all__ = [
    "WorkflowContext",
    "build_action_contexts",
    "build_action_specs",
    "build_workflow_context",
    "default_config",
    "load_cli_config",
    "strategy_rules_to_params",
]

