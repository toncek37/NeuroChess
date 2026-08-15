from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import queue
import shlex
import subprocess
import threading
import time
from typing import Iterable


class UciError(RuntimeError):
    pass


class UciTimeout(UciError):
    pass


@dataclass(frozen=True)
class EngineSpec:
    name: str
    command: tuple[str, ...]
    options: dict[str, str | int | bool] = field(default_factory=dict)
    cwd: str | None = None

    @staticmethod
    def from_command(name: str, command: str | Iterable[str], *, options: dict[str, str | int | bool] | None = None,
                     cwd: str | None = None) -> "EngineSpec":
        if isinstance(command, str):
            candidate = Path(command.strip().strip('"'))
            if candidate.is_file():
                args = (str(candidate),)
            else:
                args = tuple(shlex.split(command, posix=(os.name != "nt")))
        else:
            args = tuple(command)
        if not args:
            raise ValueError("Engine command cannot be empty")
        return EngineSpec(name=name, command=args, options=dict(options or {}), cwd=cwd)


class UciEngine:
    """Small synchronous UCI process wrapper with asynchronous stdout draining."""

    def __init__(self, spec: EngineSpec, startup_timeout: float = 10.0):
        self.spec = spec
        self.startup_timeout = startup_timeout
        self.process: subprocess.Popen[str] | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._reader: threading.Thread | None = None
        self.id_name = spec.name
        self.option_names: set[str] = set()

    def start(self) -> None:
        if self.process is not None:
            return
        self.process = subprocess.Popen(
            list(self.spec.command),
            cwd=self.spec.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        assert self.process.stdout is not None

        def drain_stdout() -> None:
            try:
                for line in self.process.stdout:
                    self._lines.put(line.rstrip("\r\n"))
            finally:
                self._lines.put(None)

        self._reader = threading.Thread(target=drain_stdout, name=f"uci-reader-{self.spec.name}", daemon=True)
        self._reader.start()

        self.send("uci")
        for line in self._read_until("uciok", self.startup_timeout):
            if line.startswith("id name "):
                self.id_name = line[8:].strip()
            elif line.startswith("option name "):
                tail = line[len("option name "):]
                name = tail.split(" type ", 1)[0].strip()
                if name:
                    self.option_names.add(name)
        for name, value in self.spec.options.items():
            self.set_option(name, value)
        self.send("isready")
        self._read_until("readyok", self.startup_timeout)

    def send(self, command: str) -> None:
        if self.process is None or self.process.stdin is None:
            raise UciError(f"Engine {self.spec.name} is not running")
        if self.process.poll() is not None:
            raise UciError(f"Engine {self.spec.name} exited with code {self.process.returncode}")
        try:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise UciError(f"Failed writing to {self.spec.name}: {exc}") from exc

    def set_option(self, name: str, value: str | int | bool) -> None:
        if isinstance(value, bool):
            text = "true" if value else "false"
        else:
            text = str(value)
        self.send(f"setoption name {name} value {text}")

    def new_game(self) -> None:
        self.send("ucinewgame")
        self.send("isready")
        self._read_until("readyok", self.startup_timeout)

    def set_position(self, initial_fen: str | None, moves_uci: list[str]) -> None:
        if initial_fen is None:
            command = "position startpos"
        else:
            command = f"position fen {initial_fen}"
        if moves_uci:
            command += " moves " + " ".join(moves_uci)
        self.send(command)

    def bestmove(self, go_command: str, timeout: float) -> tuple[str, list[str], float]:
        self.send(go_command)
        started = time.monotonic()
        info: list[str] = []
        while True:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise UciTimeout(f"Timed out waiting for bestmove from {self.spec.name}")
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise UciTimeout(f"Timed out waiting for bestmove from {self.spec.name}") from exc
            if line is None:
                raise UciError(f"Engine {self.spec.name} closed stdout")
            if line.startswith("info "):
                info.append(line)
            elif line.startswith("bestmove "):
                parts = line.split()
                if len(parts) < 2:
                    raise UciError(f"Malformed bestmove from {self.spec.name}: {line!r}")
                return parts[1], info, time.monotonic() - started

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.send("stop")

    def quit(self) -> None:
        process = self.process
        if process is None:
            return
        try:
            if process.poll() is None:
                try:
                    self.send("quit")
                except UciError:
                    pass
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=1.0)
        finally:
            self.process = None

    def close(self) -> None:
        """Idempotent compatibility alias used by tournament code."""
        self.quit()

    def _read_until(self, expected: str, timeout: float) -> list[str]:
        deadline = time.monotonic() + timeout
        lines: list[str] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise UciTimeout(f"Timed out waiting for {expected!r} from {self.spec.name}")
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise UciTimeout(f"Timed out waiting for {expected!r} from {self.spec.name}") from exc
            if line is None:
                raise UciError(f"Engine {self.spec.name} closed stdout while waiting for {expected!r}")
            if line == expected:
                return lines
            lines.append(line)

    def __enter__(self) -> "UciEngine":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
