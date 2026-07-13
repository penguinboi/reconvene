# ABOUTME: Builds the argv that hands a chosen session back to Claude Code to resume.
# ABOUTME: open_terminal_and_resume opens a new macOS Terminal window (no execvp — the
# ABOUTME: caller is a web server that must keep running to serve other requests).
import shlex
import subprocess


def resume_command(session_id: str) -> list[str]:
    return ["claude", "--resume", session_id]


def open_terminal_and_resume(session_id: str, cwd: str, runner=subprocess.run) -> None:
    command = " ".join(resume_command(session_id))
    script = (
        'tell application "Terminal"\n'
        "  activate\n"
        f'  do script "cd {shlex.quote(cwd)} && {command}"\n'
        "end tell"
    )
    runner(["osascript", "-e", script], check=True)
