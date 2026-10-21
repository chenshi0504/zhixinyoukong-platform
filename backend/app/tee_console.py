"""Run a command and mirror its output to the visible console and a log file."""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys


def _open_console_output():
    if os.name != "nt":
        return None
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    try:
        return open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--title", default="Backend Experiment")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("[ERROR] Missing command.", flush=True)
        return 2

    os.makedirs(os.path.dirname(args.log), exist_ok=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    console = _open_console_output()
    with open(args.log, "a", encoding="utf-8", errors="replace") as log:
        def emit(line: str = "") -> None:
            if console is not None:
                try:
                    console.write(line + "\n")
                    console.flush()
                except OSError:
                    pass
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

        emit("=" * 70)
        emit(args.title)
        emit("=" * 70)
        emit("Working directory: " + args.cwd)
        emit("Command: " + subprocess.list2cmdline(command))
        emit("")

        proc = subprocess.Popen(
            command,
            cwd=args.cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            emit(line.rstrip("\r\n"))
        proc.wait()
        emit("")
        emit("=" * 70)
        emit(f"ExitCode: {proc.returncode}")
        emit("=" * 70)
        if console is not None:
            console.close()
        return int(proc.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
