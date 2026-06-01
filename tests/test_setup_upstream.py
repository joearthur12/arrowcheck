from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

import arrowcheck.cli as cli
import arrowcheck.setup_upstream as upstream_setup

runner = CliRunner()


def run_git(args: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )
    return completed.stdout.strip()


def create_source_repo(tmp_path: Path) -> tuple[Path, str, str]:
    source_repo = tmp_path / "source_repo"
    source_repo.mkdir()

    run_git(["init"], cwd=source_repo)
    run_git(["config", "user.name", "ArrowCheck Tests"], cwd=source_repo)
    run_git(["config", "user.email", "tests@example.com"], cwd=source_repo)

    (source_repo / "README.md").write_text("first commit\n", encoding="utf-8")
    run_git(["add", "README.md"], cwd=source_repo)
    run_git(["commit", "-m", "first"], cwd=source_repo)
    first_sha = run_git(["rev-parse", "HEAD"], cwd=source_repo)

    (source_repo / "README.md").write_text("second commit\n", encoding="utf-8")
    run_git(["add", "README.md"], cwd=source_repo)
    run_git(["commit", "-m", "second"], cwd=source_repo)
    second_sha = run_git(["rev-parse", "HEAD"], cwd=source_repo)

    return source_repo, first_sha, second_sha


def clone_local_repo(source_repo: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", str(source_repo), str(destination)],
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )


def git_subcommand(args: list[str]) -> str:
    if args[1] == "-c":
        return args[3]
    return args[1]


def test_absent_checkout_is_cloned_and_pinned_correctly(tmp_path: Path) -> None:
    source_repo, pinned_sha, _ = create_source_repo(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    result = upstream_setup.setup_upstream(
        project_root,
        repository_url=str(source_repo),
        expected_sha=pinned_sha,
    )

    assert result.success is True
    assert result.action_taken == "cloned_and_pinned"
    assert result.actual_sha == pinned_sha
    assert result.upstream_path == project_root / "upstream" / "ChRIMP"
    assert run_git(["rev-parse", "HEAD"], cwd=result.upstream_path) == pinned_sha


def test_existing_correct_checkout_returns_success_without_modifying_it(tmp_path: Path) -> None:
    source_repo, pinned_sha, _ = create_source_repo(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    first_result = upstream_setup.setup_upstream(
        project_root,
        repository_url=str(source_repo),
        expected_sha=pinned_sha,
    )
    second_result = upstream_setup.setup_upstream(
        project_root,
        repository_url=str(source_repo),
        expected_sha=pinned_sha,
    )

    assert first_result.success is True
    assert second_result.success is True
    assert second_result.action_taken == "already_ready"
    assert second_result.actual_sha == pinned_sha
    assert run_git(["rev-parse", "HEAD"], cwd=second_result.upstream_path) == pinned_sha


def test_wrong_sha_fails_safely(tmp_path: Path) -> None:
    source_repo, pinned_sha, wrong_sha = create_source_repo(tmp_path)
    project_root = tmp_path / "project"
    upstream_dir = project_root / "upstream" / "ChRIMP"
    project_root.mkdir()
    clone_local_repo(source_repo, upstream_dir)

    result = upstream_setup.setup_upstream(
        project_root,
        repository_url=str(source_repo),
        expected_sha=pinned_sha,
    )

    assert result.success is False
    assert result.action_taken == "sha_mismatch"
    assert result.actual_sha == wrong_sha
    assert pinned_sha in result.message
    assert wrong_sha in result.message


def test_non_git_directory_fails_safely(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    upstream_dir = project_root / "upstream" / "ChRIMP"
    upstream_dir.mkdir(parents=True)
    (upstream_dir / "note.txt").write_text("not a repo\n", encoding="utf-8")

    result = upstream_setup.setup_upstream(project_root)

    assert result.success is False
    assert result.action_taken == "not_git_repository"
    assert "not a Git repository" in result.message


def test_dirty_checkout_fails_safely(tmp_path: Path) -> None:
    source_repo, pinned_sha, _ = create_source_repo(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    ready_result = upstream_setup.setup_upstream(
        project_root,
        repository_url=str(source_repo),
        expected_sha=pinned_sha,
    )
    (ready_result.upstream_path / "README.md").write_text("dirty working tree\n", encoding="utf-8")

    result = upstream_setup.setup_upstream(
        project_root,
        repository_url=str(source_repo),
        expected_sha=pinned_sha,
    )

    assert result.success is False
    assert result.action_taken == "dirty_checkout"
    assert result.actual_sha == pinned_sha
    assert "Inspect the upstream folder manually" in result.message


def test_missing_git_executable_fails_safely(tmp_path: Path) -> None:
    project_root = tmp_path / "project"

    def missing_git_runner(args: list[str], *, cwd: Path | None = None) -> upstream_setup.CommandResult:
        raise FileNotFoundError("git")

    result = upstream_setup.setup_upstream(project_root, runner=missing_git_runner)

    assert result.success is False
    assert result.action_taken == "git_unavailable"
    assert "Git is required" in result.message


def test_clone_failure_returns_clean_message(tmp_path: Path) -> None:
    project_root = tmp_path / "project"

    def failing_clone_runner(args: list[str], *, cwd: Path | None = None) -> upstream_setup.CommandResult:
        subcommand = git_subcommand(args)
        if subcommand == "--version":
            return upstream_setup.CommandResult(tuple(args), 0, "git version 2.45.0", "")
        if subcommand == "clone":
            return upstream_setup.CommandResult(tuple(args), 128, "", "simulated clone failure")
        raise AssertionError(f"unexpected git command: {args}")

    result = upstream_setup.setup_upstream(project_root, runner=failing_clone_runner)

    assert result.success is False
    assert result.action_taken == "clone_failed"
    assert "simulated clone failure" in result.message
    assert "Traceback" not in result.message


def test_checkout_failure_returns_clean_message(tmp_path: Path) -> None:
    source_repo, _, _ = create_source_repo(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()

    result = upstream_setup.setup_upstream(
        project_root,
        repository_url=str(source_repo),
        expected_sha="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    )

    assert result.success is False
    assert result.action_taken == "checkout_failed"
    assert "Git checkout failed" in result.message


def test_verified_sha_mismatch_after_checkout_fails_safely(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    expected_sha = "1111111111111111111111111111111111111111"
    actual_sha = "2222222222222222222222222222222222222222"

    def mismatched_head_runner(args: list[str], *, cwd: Path | None = None) -> upstream_setup.CommandResult:
        subcommand = git_subcommand(args)
        if subcommand == "--version":
            return upstream_setup.CommandResult(tuple(args), 0, "git version 2.45.0", "")
        if subcommand == "clone":
            return upstream_setup.CommandResult(tuple(args), 0, "", "")
        if subcommand == "checkout":
            return upstream_setup.CommandResult(tuple(args), 0, "", "")
        if subcommand == "rev-parse":
            return upstream_setup.CommandResult(tuple(args), 0, f"{actual_sha}\n", "")
        raise AssertionError(f"unexpected git command: {args}")

    result = upstream_setup.setup_upstream(
        project_root,
        expected_sha=expected_sha,
        runner=mismatched_head_runner,
    )

    assert result.success is False
    assert result.action_taken == "verification_failed"
    assert result.actual_sha == actual_sha
    assert expected_sha in result.message
    assert actual_sha in result.message


def test_command_execution_never_uses_shell_true(monkeypatch, tmp_path: Path) -> None:
    recorded_shell_values: list[bool] = []
    expected_sha = "1111111111111111111111111111111111111111"

    def fake_subprocess_run(args, **kwargs):
        recorded_shell_values.append(bool(kwargs.get("shell", False)))
        subcommand = git_subcommand(args)
        if subcommand == "--version":
            return subprocess.CompletedProcess(args, 0, stdout="git version 2.45.0\n", stderr="")
        if subcommand == "clone":
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if subcommand == "checkout":
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if subcommand == "rev-parse":
            return subprocess.CompletedProcess(args, 0, stdout=f"{expected_sha}\n", stderr="")
        raise AssertionError(f"unexpected git command: {args}")

    monkeypatch.setattr(upstream_setup.subprocess, "run", fake_subprocess_run)

    result = upstream_setup.setup_upstream(tmp_path / "project", expected_sha=expected_sha)

    assert result.success is True
    assert recorded_shell_values
    assert recorded_shell_values == [False] * len(recorded_shell_values)


def test_setup_cli_success_exits_zero(monkeypatch, tmp_path: Path) -> None:
    setup_result = upstream_setup.SetupResult(
        success=True,
        upstream_path=tmp_path / "upstream" / "ChRIMP",
        action_taken="already_ready",
        expected_sha=upstream_setup.CHRIMP_PINNED_SHA,
        actual_sha=upstream_setup.CHRIMP_PINNED_SHA,
        message="Pinned upstream ChRIMP checkout is already ready.",
    )

    monkeypatch.setattr(cli, "setup_upstream", lambda project_root, upstream_dir=None: setup_result)

    result = runner.invoke(cli.app, ["setup"])

    assert result.exit_code == 0
    assert "ArrowCheck Setup" in result.output
    assert setup_result.message in result.output


def test_setup_cli_safe_failure_exits_one(monkeypatch, tmp_path: Path) -> None:
    setup_result = upstream_setup.SetupResult(
        success=False,
        upstream_path=tmp_path / "upstream" / "ChRIMP",
        action_taken="sha_mismatch",
        expected_sha=upstream_setup.CHRIMP_PINNED_SHA,
        actual_sha="1234567890abcdef1234567890abcdef12345678",
        message="Existing upstream checkout is at an unexpected SHA.",
    )

    monkeypatch.setattr(cli, "setup_upstream", lambda project_root, upstream_dir=None: setup_result)

    result = runner.invoke(cli.app, ["setup"])

    assert result.exit_code == 1
    assert "ArrowCheck Setup" in result.output
    assert setup_result.message in result.output
