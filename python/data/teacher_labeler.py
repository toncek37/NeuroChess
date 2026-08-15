from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

import chess
import chess.engine


@dataclass(frozen=True)
class TeacherConfig:
    engine_path: str
    depth: int | None = 14
    nodes: int | None = None
    movetime_ms: int | None = None
    multipv: int = 8
    hash_mb: int | None = 256
    threads: int | None = 1

    def limit(self) -> chess.engine.Limit:
        selected = sum(x is not None for x in (self.depth, self.nodes, self.movetime_ms))
        if selected != 1:
            raise ValueError("Exactly one of depth, nodes, or movetime_ms must be set.")
        return chess.engine.Limit(
            depth=self.depth,
            nodes=self.nodes,
            time=None if self.movetime_ms is None else self.movetime_ms / 1000.0,
        )


class Teacher:
    def __init__(self, config: TeacherConfig):
        self.config = config
        self.engine: chess.engine.SimpleEngine | None = None
        self.engine_name = "unknown"
        self.engine_options: dict[str, object] = {}

    def __enter__(self) -> "Teacher":
        self.engine = chess.engine.SimpleEngine.popen_uci(self.config.engine_path)
        self.engine_name = self.engine.id.get("name", "unknown")
        options = self.engine.options
        configure: dict[str, object] = {}
        if self.config.hash_mb is not None and "Hash" in options:
            configure["Hash"] = self.config.hash_mb
        if self.config.threads is not None and "Threads" in options:
            configure["Threads"] = self.config.threads
        if "UCI_ShowWDL" in options:
            configure["UCI_ShowWDL"] = True
        if configure:
            self.engine.configure(configure)
        self.engine_options = configure
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.engine is not None:
            self.engine.quit()
            self.engine = None

    def analyse(self, board: chess.Board) -> list[Mapping[str, object]]:
        if self.engine is None:
            raise RuntimeError("Teacher engine is not running.")
        raw = self.engine.analyse(
            board,
            self.config.limit(),
            multipv=max(1, self.config.multipv),
            info=chess.engine.INFO_SCORE | chess.engine.INFO_PV,
        )
        return raw if isinstance(raw, list) else [raw]


def _score_cp(score: chess.engine.PovScore, turn: chess.Color) -> int:
    pov = score.pov(turn)
    return pov.score(mate_score=100000) or 0


def _wdl_from_score(score: chess.engine.PovScore, turn: chess.Color) -> tuple[float, float, float]:
    pov = score.pov(turn)
    try:
        wdl = pov.wdl(model="sf", ply=30)
        total = wdl.wins + wdl.draws + wdl.losses
        if total > 0:
            return wdl.wins / total, wdl.draws / total, wdl.losses / total
    except (TypeError, AttributeError):
        pass

    cp = pov.score(mate_score=100000) or 0
    if abs(cp) >= 90000:
        return (1.0, 0.0, 0.0) if cp > 0 else (0.0, 0.0, 1.0)
    expected = 1.0 / (1.0 + math.exp(-cp / 240.0))
    draw = max(0.0, 1.0 - abs(2.0 * expected - 1.0)) * 0.35
    decisive = 1.0 - draw
    win = decisive * expected
    loss = decisive * (1.0 - expected)
    return win, draw, loss


def labels_from_analysis(board: chess.Board, infos: Sequence[Mapping[str, object]]) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    best_score: chess.engine.PovScore | None = None

    for rank, info in enumerate(infos, start=1):
        score = info.get("score")
        pv = info.get("pv")
        if not isinstance(score, chess.engine.PovScore) or not isinstance(pv, list) or not pv:
            continue
        move = pv[0]
        if not isinstance(move, chess.Move):
            continue
        if best_score is None:
            best_score = score
        candidates.append(
            {
                "move": move.uci(),
                "rank": rank,
                "score_cp": _score_cp(score, board.turn),
            }
        )

    if best_score is None or not candidates:
        raise ValueError("Teacher analysis contained no usable score/PV candidates.")

    best_cp = _score_cp(best_score, board.turn)
    logits = [-(best_cp - int(item["score_cp"])) / 120.0 for item in candidates]
    max_logit = max(logits)
    weights = [math.exp(value - max_logit) for value in logits]
    total = sum(weights)
    for item, weight in zip(candidates, weights):
        item["probability"] = weight / total

    win, draw, loss = _wdl_from_score(best_score, board.turn)
    return {
        "value_cp": best_cp,
        "wdl": {"win": win, "draw": draw, "loss": loss},
        "policy": candidates,
    }


def read_jsonl(path: Path) -> Iterator[dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no}: {exc}") from exc
            if not isinstance(record, dict) or "fen" not in record:
                raise ValueError(f"Dataset line {line_no} has no FEN.")
            yield record


def label_records(records: Iterable[dict[str, object]], teacher: Teacher) -> Iterator[dict[str, object]]:
    for record in records:
        fen = str(record["fen"])
        board = chess.Board(fen)
        infos = teacher.analyse(board)
        labelled = dict(record)
        labelled["teacher"] = {
            "name": teacher.engine_name,
            "executable_sha256": sha256_file(Path(teacher.config.engine_path)),
            "depth": teacher.config.depth,
            "nodes": teacher.config.nodes,
            "movetime_ms": teacher.config.movetime_ms,
            "multipv": teacher.config.multipv,
            "options": teacher.engine_options,
        }
        labelled.update(labels_from_analysis(board, infos))
        yield labelled


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_labelled_jsonl(records: Iterable[dict[str, object]], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            count += 1
    return count
