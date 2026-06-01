from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

CHRIMP_REPOSITORY_URL = "https://github.com/schwallergroup/ChRIMP.git"
CHRIMP_PINNED_SHA = "56dd595af0ce2ab8d594d2201c9906cc48489089"
DEFAULT_UPSTREAM_RELATIVE_PATH = Path("upstream") / "ChRIMP"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class SetupResult:
    success: bool
    upstream_path: Path
    action_taken: str
    expected_sha: str
    actual_sha: str | None
    message: str


class CommandRunner(Protocol):
    def __call__(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
    ) -> CommandResult: ...


def setup_upstream(
    project_root: Path,
    *,
    upstream_dir: Path | None = None,
    repository_url: str = CHRIMP_REPOSITORY_URL,
    expected_sha: str = CHRIMP_PINNED_SHA,
    runner: CommandRunner | None = None,
) -> SetupResult:
    resolved_project_root = project_root.resolve()
    resolved_upstream_dir = resolve_upstream_dir(
        resolved_project_root,
        upstream_dir=upstream_dir,
    )
    active_runner = runner or _run_subprocess

    try:
        git_version = _run_git_command(
            ["--version"],
            runner=active_runner,
        )
    except FileNotFoundError:
        return SetupResult(
            success=False,
            upstream_path=resolved_upstream_dir,
            action_taken="git_unavailable",
            expected_sha=expected_sha,
            actual_sha=None,
            message="Git is required to prepare the pinned upstream checkout, but it is not available on PATH.",
        )

    if git_version.returncode != 0:
        return SetupResult(
            success=False,
            upstream_path=resolved_upstream_dir,
            action_taken="git_unavailable",
            expected_sha=expected_sha,
            actual_sha=None,
            message=_format_command_failure(
                "Git is required to prepare the pinned upstream checkout.",
                git_version,
            ),
        )

    if not resolved_upstream_dir.exists():
        resolved_upstream_dir.parent.mkdir(parents=True, exist_ok=True)
        clone_result = _run_git_command(
            ["clone", repository_url, str(resolved_upstream_dir)],
            runner=active_runner,
        )
        if clone_result.returncode != 0:
            return SetupResult(
                success=False,
                upstream_path=resolved_upstream_dir,
                action_taken="clone_failed",
                expected_sha=expected_sha,
                actual_sha=None,
                message=_format_command_failure(
                    "Git clone failed while preparing the pinned upstream checkout.",
                    clone_result,
                ),
            )

        checkout_result = _run_git_command(
            ["checkout", expected_sha],
            cwd=resolved_upstream_dir,
            runner=active_runner,
        )
        if checkout_result.returncode != 0:
            return SetupResult(
                success=False,
                upstream_path=resolved_upstream_dir,
                action_taken="checkout_failed",
                expected_sha=expected_sha,
                actual_sha=None,
                message=_format_command_failure(
                    "Git checkout failed while pinning the upstream checkout.",
                    checkout_result,
                ),
            )

        actual_sha = _get_head_sha(
            resolved_upstream_dir,
            runner=active_runner,
        )
        if actual_sha is None:
            return SetupResult(
                success=False,
                upstream_path=resolved_upstream_dir,
                action_taken="verification_failed",
                expected_sha=expected_sha,
                actual_sha=None,
                message="Unable to verify the pinned upstream checkout after cloning.",
            )
        if actual_sha != expected_sha:
            return SetupResult(
                success=False,
                upstream_path=resolved_upstream_dir,
                action_taken="verification_failed",
                expected_sha=expected_sha,
                actual_sha=actual_sha,
                message=(
                    "Cloned upstream checkout did not end at the pinned SHA. "
                    f"Expected {expected_sha} but found {actual_sha}."
                ),
            )

        return SetupResult(
            success=True,
            upstream_path=resolved_upstream_dir,
            action_taken="cloned_and_pinned",
            expected_sha=expected_sha,
            actual_sha=actual_sha,
            message="Cloned and verified the pinned upstream ChRIMP checkout.",
        )

    if not resolved_upstream_dir.is_dir():
        return SetupResult(
            success=False,
            upstream_path=resolved_upstream_dir,
            action_taken="not_git_repository",
            expected_sha=expected_sha,
            actual_sha=None,
            message="Existing upstream path is not a directory backed by a Git repository. Refusing to overwrite it.",
        )

    if not _is_git_repository(
        resolved_upstream_dir,
        runner=active_runner,
    ):
        return SetupResult(
            success=False,
            upstream_path=resolved_upstream_dir,
            action_taken="not_git_repository",
            expected_sha=expected_sha,
            actual_sha=None,
            message="Existing upstream directory is not a Git repository. Refusing to overwrite it.",
        )

    if _is_dirty_repository(
        resolved_upstream_dir,
        runner=active_runner,
    ):
        actual_sha = _get_head_sha(
            resolved_upstream_dir,
            runner=active_runner,
        )
        return SetupResult(
            success=False,
            upstream_path=resolved_upstream_dir,
            action_taken="dirty_checkout",
            expected_sha=expected_sha,
            actual_sha=actual_sha,
            message="Existing upstream checkout contains uncommitted changes. Inspect the upstream folder manually.",
        )

    actual_sha = _get_head_sha(
        resolved_upstream_dir,
        runner=active_runner,
    )
    if actual_sha is None:
        return SetupResult(
            success=False,
            upstream_path=resolved_upstream_dir,
            action_taken="verification_failed",
            expected_sha=expected_sha,
            actual_sha=None,
            message="Unable to determine the current upstream checkout SHA.",
        )
    if actual_sha != expected_sha:
        return SetupResult(
            success=False,
            upstream_path=resolved_upstream_dir,
            action_taken="sha_mismatch",
            expected_sha=expected_sha,
            actual_sha=actual_sha,
            message=(
                "Existing upstream checkout is at an unexpected SHA. "
                f"Expected {expected_sha} but found {actual_sha}. "
                "Inspect or remove the upstream folder manually."
            ),
        )

    return SetupResult(
        success=True,
        upstream_path=resolved_upstream_dir,
        action_taken="already_ready",
        expected_sha=expected_sha,
        actual_sha=actual_sha,
        message="Pinned upstream ChRIMP checkout is already ready.",
    )


def resolve_upstream_dir(
    project_root: Path,
    *,
    upstream_dir: Path | None = None,
) -> Path:
    resolved_project_root = project_root.resolve()
    if upstream_dir is None:
        return resolved_project_root / DEFAULT_UPSTREAM_RELATIVE_PATH
    if upstream_dir.is_absolute():
        return upstream_dir.resolve()
    return (resolved_project_root / upstream_dir).resolve()


def _is_git_repository(
    upstream_dir: Path,
    *,
    runner: CommandRunner,
) -> bool:
    result = _run_git_command(
        ["rev-parse", "--is-inside-work-tree"],
        cwd=upstream_dir,
        runner=runner,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _is_dirty_repository(
    upstream_dir: Path,
    *,
    runner: CommandRunner,
) -> bool:
    result = _run_git_command(
        ["status", "--porcelain"],
        cwd=upstream_dir,
        runner=runner,
    )
    return result.returncode == 0 and result.stdout.strip() != ""


def _get_head_sha(
    upstream_dir: Path,
    *,
    runner: CommandRunner,
) -> str | None:
    result = _run_git_command(
        ["rev-parse", "HEAD"],
        cwd=upstream_dir,
        runner=runner,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _run_git_command(
    git_args: list[str],
    *,
    runner: CommandRunner,
    cwd: Path | None = None,
) -> CommandResult:
    command = ["git"]
    if cwd is not None:
        command.extend(["-c", f"safe.directory={cwd.resolve().as_posix()}"])
    command.extend(git_args)
    return runner(command, cwd=cwd)


def _run_subprocess(
    args: list[str],
    *,
    cwd: Path | None = None,
) -> CommandResult:
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    return CommandResult(
        args=tuple(args),
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def _format_command_failure(prefix: str, command_result: CommandResult) -> str:
    details = command_result.stderr or command_result.stdout or "No additional Git output was captured."
    return f"{prefix} {details}"
