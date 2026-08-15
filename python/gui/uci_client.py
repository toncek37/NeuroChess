from __future__ import annotations

import os
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass
class SearchInfo:
    depth: int = 0
    seldepth: int = 0
    score_cp: Optional[int] = None
    mate: Optional[int] = None
    nodes: int = 0
    nps: int = 0
    time_ms: int = 0
    pv: list[str] = field(default_factory=list)


def parse_info_line(line: str) -> Optional[SearchInfo]:
    if not line.startswith("info "):
        return None
    tokens = line.split()
    out = SearchInfo()
    i = 1
    while i < len(tokens):
        key = tokens[i]
        try:
            if key == "depth" and i + 1 < len(tokens):
                out.depth = int(tokens[i + 1]); i += 2
            elif key == "seldepth" and i + 1 < len(tokens):
                out.seldepth = int(tokens[i + 1]); i += 2
            elif key == "score" and i + 2 < len(tokens):
                kind, value = tokens[i + 1], int(tokens[i + 2])
                if kind == "cp": out.score_cp = value
                elif kind == "mate": out.mate = value
                i += 3
            elif key == "nodes" and i + 1 < len(tokens):
                out.nodes = int(tokens[i + 1]); i += 2
            elif key == "nps" and i + 1 < len(tokens):
                out.nps = int(tokens[i + 1]); i += 2
            elif key == "time" and i + 1 < len(tokens):
                out.time_ms = int(tokens[i + 1]); i += 2
            elif key == "pv":
                out.pv = tokens[i + 1:]
                break
            else:
                i += 1
        except (ValueError, IndexError):
            i += 1
    return out


def find_default_engine(project_root: Path) -> Optional[Path]:
    candidates = [
        project_root / "build" / "Release" / "neurochess.exe",
        project_root / "build" / "neurochess.exe",
        project_root / "build" / "neurochess",
        project_root / "build-release" / "neurochess",
        project_root / "neurochess.exe",
        project_root / "neurochess",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


class UciClient:
    def __init__(self, engine_path: Path, on_line: Optional[Callable[[str], None]] = None):
        self.engine_path = Path(engine_path)
        self.on_line = on_line
        self.proc: Optional[subprocess.Popen[str]] = None
        self._reader: Optional[threading.Thread] = None
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._closed = False

    def start(self) -> None:
        if self.proc is not None:
            return
        if not self.engine_path.is_file():
            raise FileNotFoundError(self.engine_path)
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW
        self.proc = subprocess.Popen(
            [str(self.engine_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=creationflags,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self.send("uci")

    def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        for raw in self.proc.stdout:
            line = raw.rstrip("\r\n")
            self._queue.put(line)
            if self.on_line:
                self.on_line(line)

    def send(self, command: str) -> None:
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("Engine is not running")
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try: self.send("stop")
            except Exception: pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.proc and self.proc.poll() is None:
            try: self.send("quit")
            except Exception: pass
            try: self.proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
