from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import chess
import chess.pgn


@dataclass(frozen=True)
class PositionRecord:
    fen: str
    source: str
    game_id: str
    ply: int
    result: str | None = None
    parent_fen: str | None = None
    perturbation_plies: int = 0

    @property
    def key(self) -> str:
        return hashlib.sha256(self.fen.encode("utf-8")).hexdigest()

    def to_json(self) -> dict[str, object]:
        data = asdict(self)
        data["key"] = self.key
        return data


def _eligible(board: chess.Board, min_ply: int, max_ply: int | None) -> bool:
    ply = board.ply()
    if ply < min_ply or (max_ply is not None and ply > max_ply):
        return False
    if board.is_game_over(claim_draw=True):
        return False
    return len(board.piece_map()) >= 4


def sample_game_positions(
    game: chess.pgn.Game,
    game_id: str,
    rng: random.Random,
    positions_per_game: int = 4,
    min_ply: int = 12,
    max_ply: int | None = 160,
) -> list[PositionRecord]:
    board = game.board()
    candidates: list[tuple[int, str]] = []
    for move in game.mainline_moves():
        board.push(move)
        if _eligible(board, min_ply, max_ply):
            candidates.append((board.ply(), board.fen()))

    if not candidates:
        return []
    count = min(positions_per_game, len(candidates))
    chosen = sorted(rng.sample(candidates, count), key=lambda item: item[0])
    result = game.headers.get("Result")
    return [
        PositionRecord(fen=fen, source="pgn", game_id=game_id, ply=ply, result=result)
        for ply, fen in chosen
    ]


def iter_pgn_positions(
    paths: Sequence[Path],
    seed: int = 0,
    positions_per_game: int = 4,
    min_ply: int = 12,
    max_ply: int | None = 160,
) -> Iterator[PositionRecord]:
    rng = random.Random(seed)
    for path in paths:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            index = 0
            while True:
                game = chess.pgn.read_game(handle)
                if game is None:
                    break
                game_id = f"{path.name}:{index}"
                yield from sample_game_positions(
                    game, game_id, rng, positions_per_game, min_ply, max_ply
                )
                index += 1


def perturb_position(
    record: PositionRecord,
    rng: random.Random,
    min_plies: int = 1,
    max_plies: int = 3,
) -> PositionRecord | None:
    board = chess.Board(record.fen)
    target = rng.randint(min_plies, max_plies)
    played = 0
    for _ in range(target):
        moves = list(board.legal_moves)
        if not moves:
            break
        board.push(rng.choice(moves))
        played += 1
        if board.is_game_over(claim_draw=True):
            break
    if played == 0 or board.is_game_over(claim_draw=True):
        return None
    return PositionRecord(
        fen=board.fen(),
        source="perturbation",
        game_id=record.game_id,
        ply=record.ply + played,
        result=record.result,
        parent_fen=record.fen,
        perturbation_plies=played,
    )


def generate_self_play_positions(
    games: int,
    seed: int = 0,
    positions_per_game: int = 4,
    min_ply: int = 12,
    max_ply: int = 160,
) -> Iterator[PositionRecord]:
    """Generate legal, reproducible exploratory self-play using random legal moves.

    This is intentionally policy-free infrastructure. A later prompt can replace the
    move selector with NeuroChess/teacher UCI play without changing the dataset format.
    """
    rng = random.Random(seed)
    for game_index in range(games):
        board = chess.Board()
        candidates: list[tuple[int, str]] = []
        while not board.is_game_over(claim_draw=True) and board.ply() < max_ply:
            board.push(rng.choice(list(board.legal_moves)))
            if _eligible(board, min_ply, max_ply):
                candidates.append((board.ply(), board.fen()))
        if not candidates:
            continue
        count = min(positions_per_game, len(candidates))
        for ply, fen in sorted(rng.sample(candidates, count)):
            yield PositionRecord(
                fen=fen,
                source="selfplay-random",
                game_id=f"selfplay:{game_index}",
                ply=ply,
                result=board.result(claim_draw=True),
            )


def deduplicate(records: Iterable[PositionRecord]) -> Iterator[PositionRecord]:
    seen: set[str] = set()
    for record in records:
        if record.key in seen:
            continue
        seen.add(record.key)
        yield record


def write_jsonl(records: Iterable[PositionRecord], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_json(), sort_keys=True) + "\n")
            count += 1
    return count
