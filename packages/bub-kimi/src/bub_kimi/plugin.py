from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from bub import hookimpl
from bub.types import State
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from bub_kimi.utils import with_bub_skills

if TYPE_CHECKING:
    from bub.builtin.agent import Agent

THREADS_FILE = ".bub-kimi-threads.json"
RESUME_LINE_PREFIX = "To resume this session:"
KIMI_CLI_PACKAGE = "kimi-cli"
KIMI_CLI_PYTHON = "3.13"

_kimi_install_checked = False


def _ensure_kimi_installed() -> None:
    """Install `kimi-cli` via `uv tool install` on first use if missing.

    bub-kimi shells out to the `kimi` binary rather than importing it, so we
    can't rely on normal Python dependency resolution. The first time we're
    about to spawn `kimi`, probe PATH and auto-install via uv if absent.
    """
    global _kimi_install_checked
    if _kimi_install_checked:
        return
    if shutil.which("kimi") is not None:
        _kimi_install_checked = True
        return

    print(
        f"bub-kimi: kimi binary not found on PATH; installing `{KIMI_CLI_PACKAGE}` "
        "via `uv tool install` (one-time setup)…",
        file=sys.stderr,
        flush=True,
    )
    try:
        subprocess.run(
            ["uv", "tool", "install", "--python", KIMI_CLI_PYTHON, KIMI_CLI_PACKAGE],
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "bub-kimi: cannot auto-install kimi-cli because `uv` is not on PATH. "
            "Install uv (https://docs.astral.sh/uv/) or run `uv tool install kimi-cli` manually."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"bub-kimi: `uv tool install {KIMI_CLI_PACKAGE}` failed with exit code "
            f"{exc.returncode}. Run it manually to see the underlying error."
        ) from exc

    if shutil.which("kimi") is None:
        raise RuntimeError(
            "bub-kimi: installed kimi-cli but the `kimi` binary is still not on PATH. "
            "Ensure uv's tool bin directory (`uv tool dir --bin`) is on PATH, then retry."
        )
    _kimi_install_checked = True


def _load_thread_id(session_id: str, state: State) -> str | None:
    workspace = workspace_from_state(state)
    threads_file = workspace / THREADS_FILE
    with contextlib.suppress(FileNotFoundError):
        with threads_file.open() as f:
            threads = json.load(f)
        return threads.get(session_id)


def _save_thread_id(session_id: str, thread_id: str, state: State) -> None:
    workspace = workspace_from_state(state)
    threads_file = workspace / THREADS_FILE
    if threads_file.exists():
        with threads_file.open() as f:
            threads = json.load(f)
    else:
        threads = {}
    threads[session_id] = thread_id
    with threads_file.open("w") as f:
        json.dump(threads, f, indent=2)


def workspace_from_state(state: State) -> Path:
    raw = state.get("_runtime_workspace")
    if isinstance(raw, str) and raw.strip():
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve()


class KimiSettings(BaseSettings):
    """Configuration for Kimi plugin."""

    model_config = SettingsConfigDict(
        env_prefix="BUB_KIMI_", env_file=".env", extra="ignore"
    )
    model_name: str | None = Field(default=None)
    api_key: str | None = Field(default=None)
    base_url: str | None = Field(default=None)


kimi_settings = KimiSettings()


def _runtime_agent_from_state(state: State) -> Agent | None:
    agent = state.get("_runtime_agent")
    if agent is None:
        return None
    return cast("Agent", agent)


async def _run_internal_command(prompt: str, session_id: str, state: State) -> str | None:
    if not prompt.strip().startswith(","):
        return None
    agent = _runtime_agent_from_state(state)
    if agent is None:
        return None
    return await agent.run(session_id=session_id, prompt=prompt, state=state)


@hookimpl
async def run_model(prompt: str, session_id: str, state: State) -> str:
    internal_command_result = await _run_internal_command(prompt, session_id, state)
    if internal_command_result is not None:
        return internal_command_result

    _ensure_kimi_installed()

    workspace = workspace_from_state(state)
    thread_id = _load_thread_id(session_id, state)
    command: list[str] = ["kimi"]
    if thread_id:
        command.extend(["-r", thread_id])
    command.append("--quiet")
    command.extend(["-p", prompt])
    env = os.environ.copy()
    if kimi_settings.api_key:
        env["KIMI_API_KEY"] = kimi_settings.api_key
    if kimi_settings.base_url:
        env["KIMI_BASE_URL"] = kimi_settings.base_url
    if kimi_settings.model_name:
        env["KIMI_MODEL_NAME"] = kimi_settings.model_name
    with with_bub_skills(workspace):
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workspace),
            env=env,
        )
        stdout, stderr = await process.communicate()

    stdout_text = stdout.decode() if stdout else ""
    stderr_text = stderr.decode() if stderr else ""

    stderr_lines: list[str] = []
    for line in stderr_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(RESUME_LINE_PREFIX):
            new_thread_id = stripped.rsplit(" ", 1)[-1]
            if new_thread_id:
                _save_thread_id(session_id, new_thread_id, state)
            continue
        stderr_lines.append(line)

    if process.returncode != 0:
        parts = [f"Kimi process exited with code {process.returncode}."]
        filtered_stderr = "\n".join(stderr_lines).strip()
        if filtered_stderr:
            parts.append(filtered_stderr)
        if stdout_text.strip():
            parts.append(stdout_text)
        return "\n\n".join(parts)

    return stdout_text
