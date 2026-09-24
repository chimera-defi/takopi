from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import anyio

from ..backends import EngineBackend, EngineConfig
from ..config import ConfigError
from ..logging import get_logger
from ..model import CompletedEvent, EngineId, ResumeToken, StartedEvent, TakopiEvent
from ..runner import BaseRunner
from ..utils.paths import get_run_base_dir

logger = get_logger(__name__)


@dataclass(slots=True)
class DelegateRunner(BaseRunner):
    engine: EngineId
    cli_cmd: str
    task_flag: str
    title: str
    include_workspace: bool = False
    extra_args: tuple[str, ...] = ()

    def is_resume_line(self, line: str) -> bool:
        return False

    def format_resume(self, token: ResumeToken) -> str:
        if token.engine != self.engine:
            raise RuntimeError(f"resume token is for engine {token.engine!r}")
        return f"`{self.engine} session {token.value}`"

    def extract_resume(self, text: str | None) -> ResumeToken | None:
        return None

    async def run_impl(
        self, prompt: str, resume: ResumeToken | None
    ) -> AsyncIterator[TakopiEvent]:
        token = resume or ResumeToken(engine=self.engine, value=uuid4().hex)
        cwd = get_run_base_dir() or Path.cwd()
        yield StartedEvent(
            engine=self.engine,
            resume=token,
            title=self.title,
            meta={"cwd": str(cwd), "command": self.cli_cmd},
        )

        cmd = [self.cli_cmd, *self.extra_args, self.task_flag, prompt]
        if self.include_workspace:
            cmd.extend(["--workspace", str(cwd)])
        env = dict(os.environ)
        env.setdefault("NO_COLOR", "1")
        env.setdefault("CI", "1")

        logger.info(
            "delegate.runner.start",
            engine=self.engine,
            command=self.cli_cmd,
            cwd=str(cwd),
            prompt_len=len(prompt),
            resume=token.value,
        )
        try:
            proc = await anyio.run_process(
                cmd,
                cwd=cwd,
                env=env,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            message = f"{self.cli_cmd} failed to start: {exc}"
            logger.warning(
                "delegate.runner.spawn_failed", engine=self.engine, error=str(exc)
            )
            yield CompletedEvent(
                engine=self.engine,
                ok=False,
                answer="",
                resume=token,
                error=message,
            )
            return

        stdout = proc.stdout.decode("utf-8", errors="replace").strip()
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        ok = proc.returncode == 0
        answer = stdout or stderr
        error = None if ok else f"{self.cli_cmd} failed (rc={proc.returncode})."
        if not ok and stderr and stdout:
            answer = f"{stdout}\n\n{stderr}"
        logger.info(
            "delegate.runner.completed",
            engine=self.engine,
            rc=proc.returncode,
            ok=ok,
            answer_len=len(answer),
            resume=token.value,
        )
        yield CompletedEvent(
            engine=self.engine,
            ok=ok,
            answer=answer,
            resume=token,
            error=error,
        )


def _extra_args(config: EngineConfig, config_path: Path) -> tuple[str, ...]:
    value = config.get("extra_args")
    if value is None:
        return ()
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise ConfigError(
        f"Invalid delegate extra_args in {config_path}; expected a list of strings."
    )


def build_delegate_runner(
    config: EngineConfig,
    config_path: Path,
    *,
    engine: EngineId,
    cli_cmd: str,
    title: str,
    include_workspace: bool = False,
) -> DelegateRunner:
    return DelegateRunner(
        engine=engine,
        cli_cmd=cli_cmd,
        task_flag="--task",
        title=title,
        include_workspace=include_workspace,
        extra_args=_extra_args(config, config_path),
    )


def delegate_backend(
    *,
    engine: EngineId,
    cli_cmd: str,
    title: str,
    include_workspace: bool = False,
) -> EngineBackend:
    def build_runner(config: EngineConfig, config_path: Path) -> DelegateRunner:
        return build_delegate_runner(
            config,
            config_path,
            engine=engine,
            cli_cmd=cli_cmd,
            title=title,
            include_workspace=include_workspace,
        )

    return EngineBackend(id=engine, build_runner=build_runner, cli_cmd=cli_cmd)
