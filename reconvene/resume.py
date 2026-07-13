# ABOUTME: Builds the argv that hands a chosen session back to Claude Code to resume.
# ABOUTME: open_terminal_and_resume opens a new Terminal.app or iTerm2 window (no execvp —
# ABOUTME: the caller is a web server that must keep running to serve other requests).
import shlex
import subprocess


def resume_command(session_id: str, extra_args: str = "") -> list[str]:
    cmd = ["claude", "--resume", session_id]
    if extra_args:
        cmd.extend(shlex.split(extra_args))
    return cmd


def _terminal_script(cwd: str, command: str) -> str:
    return (
        'tell application "Terminal"\n'
        "  activate\n"
        f'  do script "cd {shlex.quote(cwd)} && {command}"\n'
        "end tell"
    )


def _iterm2_script(cwd: str, command: str) -> str:
    return (
        'tell application "iTerm2"\n'
        "  activate\n"
        "  set newWindow to (create window with default profile)\n"
        "  tell current session of newWindow\n"
        f'    write text "cd {shlex.quote(cwd)} && {command}"\n'
        "  end tell\n"
        "end tell"
    )


def open_terminal_and_resume(session_id: str, cwd: str, config=None, runner=subprocess.run) -> None:
    terminal_app = config.terminal_app if config else "Terminal"
    extra_args = config.claude_extra_args if config else ""
    command = " ".join(resume_command(session_id, extra_args))
    script = _iterm2_script(cwd, command) if terminal_app == "iTerm2" else _terminal_script(cwd, command)
    runner(["osascript", "-e", script], check=True)
