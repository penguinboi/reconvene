# ABOUTME: Builds the argv that hands a chosen session back to Claude Code to resume.
# ABOUTME: open_terminal_and_resume opens a new Terminal.app or iTerm2 window (no execvp —
# ABOUTME: the caller is a web server that must keep running to serve other requests).
import os
import shlex
import subprocess
from datetime import datetime

from .journal import verbose_age


def resume_prompt(updated_at: str, now: datetime | None = None) -> str:
    return (
        f"Resuming session from {updated_at[:19]}.\n\n"
        f"IMPORTANT: This session has been inactive for {verbose_age(updated_at, now)}. "
        "Before proceeding: check git status, look around to understand what changed, "
        "and be careful not to overwrite any work in progress."
    )


def resume_command(session_id: str, updated_at: str, extra_args: str = "",
                    now: datetime | None = None) -> list[str]:
    cmd = ["claude", "--resume", session_id]
    if extra_args:
        cmd.extend(shlex.split(extra_args))
    cmd.append(resume_prompt(updated_at, now))
    return cmd


def _applescript_escape(s: str) -> str:
    # Escape a string for embedding inside an AppleScript double-quoted literal. shlex.quote
    # makes the shell command shell-safe, but that string still lands inside `do script "..."`,
    # so a literal `"` or `\` from a project path would break out of the AppleScript string
    # (a command-injection vector); raw newlines/tabs are outright illegal in the literal and
    # would make osascript fail to compile.
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _terminal_script(shell_command: str) -> str:
    return (
        'tell application "Terminal"\n'
        "  activate\n"
        f'  do script "{_applescript_escape(shell_command)}"\n'
        "end tell"
    )


def _iterm2_script(shell_command: str) -> str:
    return (
        'tell application "iTerm2"\n'
        "  activate\n"
        "  set newWindow to (create window with default profile)\n"
        "  tell current session of newWindow\n"
        f'    write text "{_applescript_escape(shell_command)}"\n'
        "  end tell\n"
        "end tell"
    )


def open_terminal_and_resume(session_id: str, cwd: str, updated_at: str, config=None,
                              runner=subprocess.run, now: datetime | None = None,
                              path_exists=os.path.isdir) -> None:
    if not path_exists(cwd):
        # `cd <cwd> && claude` would silently no-op if the directory is gone (osascript still
        # exits 0), so the caller would falsely believe the session resumed. Fail loudly instead.
        raise FileNotFoundError(f"project directory no longer exists: {cwd}")
    terminal_app = config.terminal_app if config else "Terminal"
    extra_args = config.claude_extra_args if config else ""
    argv = resume_command(session_id, updated_at, extra_args, now)
    command = " ".join(shlex.quote(part) for part in argv)
    shell_command = f"cd {shlex.quote(cwd)} && {command}"
    script = _iterm2_script(shell_command) if terminal_app == "iTerm2" else _terminal_script(shell_command)
    runner(["osascript", "-e", script], check=True)
