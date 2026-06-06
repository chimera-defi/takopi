from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from takopi.config import ConfigError
from takopi.model import CompletedEvent, ResumeToken, StartedEvent
from takopi.runners.delegate import (
    DelegateRunner,
    build_delegate_runner,
    delegate_backend,
)
from takopi.utils.paths import reset_run_base_dir, set_run_base_dir


def test_delegate_backend_builds_runner(tmp_path: Path) -> None:
    backend = delegate_backend(
        engine="devin_delegate",
        cli_cmd="devin-delegate",
        title="devin-delegate",
        include_workspace=True,
    )

    runner = backend.build_runner({"extra_args": ["--quiet"]}, tmp_path)

    assert backend.id == "devin_delegate"
    assert backend.cli_cmd == "devin-delegate"
    assert isinstance(runner, DelegateRunner)
    assert runner.engine == "devin_delegate"
    assert runner.cli_cmd == "devin-delegate"
    assert runner.extra_args == ("--quiet",)
    assert runner.include_workspace is True


def test_build_delegate_runner_rejects_invalid_extra_args(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="delegate extra_args"):
        build_delegate_runner(
            {"extra_args": ["--ok", 1]},
            tmp_path,
            engine="kd",
            cli_cmd="kimi-delegate",
            title="kimi-delegate",
        )


def test_delegate_runner_resume_helpers() -> None:
    runner = DelegateRunner(
        engine="devin_delegate",
        cli_cmd="devin-delegate",
        task_flag="--task",
        title="devin-delegate",
    )

    token = ResumeToken(engine="devin_delegate", value="abc")
    assert runner.format_resume(token) == "`devin_delegate session abc`"
    assert runner.extract_resume("anything") is None
    assert runner.is_resume_line("anything") is False

    with pytest.raises(RuntimeError):
        runner.format_resume(ResumeToken(engine="codex", value="abc"))


@pytest.mark.anyio
async def test_delegate_runner_invokes_cli_with_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_run_process(cmd, *, cwd, env, check):  # noqa: ANN001
        calls.append({"cmd": cmd, "cwd": cwd, "env": env, "check": check})
        return SimpleNamespace(returncode=0, stdout=b"done\n", stderr=b"")

    monkeypatch.setattr("takopi.runners.delegate.anyio.run_process", fake_run_process)
    token = set_run_base_dir(tmp_path)
    try:
        runner = DelegateRunner(
            engine="devin_delegate",
            cli_cmd="devin-delegate",
            task_flag="--task",
            title="devin-delegate",
            include_workspace=True,
            extra_args=("--mode", "review"),
        )
        events = [event async for event in runner.run_impl("hello", None)]
    finally:
        reset_run_base_dir(token)

    assert isinstance(events[0], StartedEvent)
    completed = events[-1]
    assert isinstance(completed, CompletedEvent)
    assert completed.ok is True
    assert completed.answer == "done"
    assert calls == [
        {
            "cmd": [
                "devin-delegate",
                "--mode",
                "review",
                "--task",
                "hello",
                "--workspace",
                str(tmp_path),
            ],
            "cwd": tmp_path,
            "env": calls[0]["env"],
            "check": False,
        }
    ]
    env = cast(dict[str, str], calls[0]["env"])
    assert isinstance(env, dict)
    assert env["NO_COLOR"] == "1"
    assert env["CI"] == "1"


@pytest.mark.anyio
async def test_delegate_runner_reports_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_process(cmd, *, cwd, env, check):  # noqa: ANN001
        return SimpleNamespace(returncode=2, stdout=b"out", stderr=b"err")

    monkeypatch.setattr("takopi.runners.delegate.anyio.run_process", fake_run_process)
    runner = DelegateRunner(
        engine="kd",
        cli_cmd="kimi-delegate",
        task_flag="--task",
        title="kimi-delegate",
    )

    events = [event async for event in runner.run_impl("hello", None)]

    completed = events[-1]
    assert isinstance(completed, CompletedEvent)
    assert completed.ok is False
    assert completed.answer == "out\n\nerr"
    assert completed.error == "kimi-delegate failed (rc=2)."
