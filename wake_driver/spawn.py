"""Build argv + the fixed prompt to spawn one headless agent turn (prompt on stdin).

Flags were verified against the installed CLIs by the agent-slack review: Codex's -a is
a TOP-LEVEL flag (codex -a never exec ...), and Claude auto-approves MCP tools via
--permission-mode dontAsk + --allowedTools (NOT acceptEdits). The real zero-prompt
round-trip is the BLOCKING Phase-0.4 live smoke, not an automated test.
"""
from __future__ import annotations

import os
import shutil
import subprocess

DRIVER_PROMPT = (
    'You hold the relay baton on thread "{thread_id}". Do EXACTLY ONE turn:\n'
    '1. Call relay_begin_turn("{thread_id}") ONCE to claim the turn and read prior_events.\n'
    "2. The relay thread is your ONLY memory; assume no prior in-session state.\n"
    "3. Do one unit of work.\n"
    '4. Call relay_submit_turn(turn_token, body, next_baton="{other}") EXACTLY once to hand '
    "the baton to the OTHER agent. NEVER set next_baton to yourself, and do NOT call "
    "relay_status or relay_halt_turn for a normal hand-off. ONLY if you are genuinely "
    'blocked and need a human, call relay_halt_turn(turn_token, body, status="needs_human", '
    "question=...) instead of submit.\n"
    "Then STOP. Do not call relay_begin_turn or relay_submit_turn more than once."
)


def _resolve_bin(name: str) -> str:
    """Resolve a CLI to its real (un-symlinked) path so bundled helpers load."""
    found = shutil.which(name)
    return os.path.realpath(found) if found else name


def claude_argv(bin_path: str, mcp_config: str, max_turns: int = 12) -> list[str]:
    """Headless Claude: auto-approve relay tools, load ONLY the relay MCP server."""
    return [
        bin_path, "-p", "--permission-mode", "dontAsk",
        "--allowedTools", "mcp__relay__*",
        "--mcp-config", mcp_config, "--strict-mcp-config",
        "--max-turns", str(max_turns),
    ]


def codex_argv(bin_path: str, clone: str, out_path: str) -> list[str]:
    """Headless Codex: -a is TOP-LEVEL (before exec); write the last message to out_path."""
    return [
        bin_path, "-a", "never", "exec", "--json", "--skip-git-repo-check",
        "-C", clone, "--sandbox", "workspace-write", "-o", out_path,
    ]


def prompt_for(thread_id: str, other: str) -> str:
    """The fixed one-turn instruction handed to the spawned agent on stdin."""
    return DRIVER_PROMPT.format(thread_id=thread_id, other=other)


def run_turn(argv: list[str], prompt: str, env: dict, cwd: str, timeout: int) -> int:
    """Spawn one headless turn with the prompt on stdin; return the exit code."""
    proc = subprocess.run(  # noqa: S603 - argv built from our own resolved binaries
        argv, input=prompt, env=env, cwd=cwd, timeout=timeout,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode
