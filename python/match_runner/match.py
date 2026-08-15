from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import threading
from typing import Any

from .uci_engine import EngineSpec, UciEngine, UciError, UciTimeout

try:
    import chess
    import chess.pgn
except ImportError:  # Keep config/tools importable before optional runner dependency is installed.
    chess = None


@dataclass(frozen=True)
class TimeControl:
    base_ms: int = 10_000
    increment_ms: int = 100
    move_time_ms: int | None = None
    movestogo: int | None = None

    def validate(self) -> None:
        if self.move_time_ms is not None:
            if self.move_time_ms <= 0:
                raise ValueError("move_time_ms must be positive")
            return
        if self.base_ms <= 0 or self.increment_ms < 0:
            raise ValueError("Invalid Fischer time control")

    def label(self) -> str:
        if self.move_time_ms is not None:
            return f"movetime {self.move_time_ms}ms"
        return f"{self.base_ms / 1000:g}+{self.increment_ms / 1000:g}"


@dataclass(frozen=True)
class Opening:
    fen: str | None = None
    name: str = "startpos"


@dataclass
class MatchConfig:
    engine_a: EngineSpec
    engine_b: EngineSpec
    games: int = 20
    concurrency: int = 1
    time_control: TimeControl = field(default_factory=TimeControl)
    openings: list[Opening] = field(default_factory=lambda: [Opening()])
    randomize_openings: bool = True
    seed: int = 1
    max_plies: int = 600
    output_dir: str = "match-results"
    event: str = "NeuroChess UCI Match"

    def validate(self) -> None:
        self.time_control.validate()
        if self.games <= 0:
            raise ValueError("games must be positive")
        if self.concurrency <= 0:
            raise ValueError("concurrency must be positive")
        if self.max_plies <= 0:
            raise ValueError("max_plies must be positive")
        if not self.openings:
            raise ValueError("At least one opening is required")


@dataclass
class GameResult:
    game_index: int
    white: str
    black: str
    result: str
    termination: str
    opening: str
    moves: list[str]
    move_times_ms: list[float]
    pgn: str
    engine_a_score: float


@dataclass
class MatchSummary:
    engine_a: str
    engine_b: str
    games: int
    wins: int
    draws: int
    losses: int
    score: float
    score_percent: float
    elapsed_seconds: float
    results_json: str
    pgn_file: str


def require_chess() -> None:
    if chess is None:
        raise RuntimeError(
            "The match runner requires python-chess. Install Python dependencies with "
            "'python -m pip install -r python/requirements.txt'."
        )


def load_fen_openings(path: str | Path) -> list[Opening]:
    openings: list[Opening] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            fen, name = (part.strip() for part in line.split("|", 1))
        else:
            fen, name = line, f"opening-{len(openings) + 1}"
        openings.append(Opening(None if fen.lower() == "startpos" else fen, name))
    if not openings:
        raise ValueError(f"No openings found in {path}")
    return openings


def _opening_schedule(config: MatchConfig) -> list[Opening]:
    rng = random.Random(config.seed)
    pool = list(config.openings)
    if config.randomize_openings:
        rng.shuffle(pool)
    # Pair consecutive games to the same opening so color-swapped comparisons are fair.
    schedule: list[Opening] = []
    pair = 0
    while len(schedule) < config.games:
        opening = pool[pair % len(pool)]
        schedule.extend([opening, opening])
        pair += 1
    return schedule[: config.games]


def _go_command(tc: TimeControl, white_ms: float, black_ms: float) -> str:
    if tc.move_time_ms is not None:
        return f"go movetime {tc.move_time_ms}"
    cmd = (
        f"go wtime {max(1, int(white_ms))} btime {max(1, int(black_ms))} "
        f"winc {tc.increment_ms} binc {tc.increment_ms}"
    )
    if tc.movestogo:
        cmd += f" movestogo {tc.movestogo}"
    return cmd


def _move_timeout_seconds(tc: TimeControl, own_remaining_ms: float) -> float:
    if tc.move_time_ms is not None:
        return max(2.0, tc.move_time_ms / 1000.0 * 4.0 + 1.0)
    # A hung engine must not block a whole tournament. Give it its remaining clock plus a modest protocol margin.
    return max(2.0, own_remaining_ms / 1000.0 + 2.0)


def _play_game(config: MatchConfig, game_index: int, opening: Opening) -> GameResult:
    require_chess()
    assert chess is not None

    a_is_white = game_index % 2 == 0
    white_spec = config.engine_a if a_is_white else config.engine_b
    black_spec = config.engine_b if a_is_white else config.engine_a

    board = chess.Board(opening.fen) if opening.fen else chess.Board()
    initial_fen = opening.fen
    game = chess.pgn.Game()
    game.headers["Event"] = config.event
    game.headers["Date"] = datetime.now(timezone.utc).strftime("%Y.%m.%d")
    game.headers["Round"] = str(game_index + 1)
    game.headers["White"] = white_spec.name
    game.headers["Black"] = black_spec.name
    game.headers["TimeControl"] = config.time_control.label()
    game.headers["Opening"] = opening.name
    if opening.fen:
        game.setup(board.copy())
    node = game

    moves_uci: list[str] = []
    move_times_ms: list[float] = []
    clocks = {chess.WHITE: float(config.time_control.base_ms), chess.BLACK: float(config.time_control.base_ms)}
    termination = ""
    result = "*"

    white = UciEngine(white_spec)
    black = UciEngine(black_spec)
    engines = {chess.WHITE: white, chess.BLACK: black}

    try:
        white.start()
        black.start()
        white.new_game()
        black.new_game()

        for _ply in range(config.max_plies):
            outcome = board.outcome(claim_draw=True)
            if outcome is not None:
                result = outcome.result()
                termination = outcome.termination.name.lower().replace("_", " ")
                break

            side = board.turn
            engine = engines[side]
            engine.set_position(initial_fen, moves_uci)
            go = _go_command(config.time_control, clocks[chess.WHITE], clocks[chess.BLACK])
            timeout = _move_timeout_seconds(config.time_control, clocks[side])

            try:
                bestmove, _info, elapsed = engine.bestmove(go, timeout)
            except UciTimeout:
                result = "0-1" if side == chess.WHITE else "1-0"
                termination = "time forfeit"
                break
            except UciError:
                result = "0-1" if side == chess.WHITE else "1-0"
                termination = "engine failure"
                break

            elapsed_ms = elapsed * 1000.0
            if config.time_control.move_time_ms is None:
                clocks[side] -= elapsed_ms
                if clocks[side] < 0:
                    result = "0-1" if side == chess.WHITE else "1-0"
                    termination = "time forfeit"
                    break

            try:
                move = chess.Move.from_uci(bestmove)
            except ValueError:
                result = "0-1" if side == chess.WHITE else "1-0"
                termination = f"invalid bestmove {bestmove}"
                break
            if move not in board.legal_moves:
                result = "0-1" if side == chess.WHITE else "1-0"
                termination = f"illegal move {bestmove}"
                break

            node = node.add_variation(move)
            board.push(move)
            moves_uci.append(bestmove)
            move_times_ms.append(elapsed_ms)
            if config.time_control.move_time_ms is None:
                clocks[side] += config.time_control.increment_ms
        else:
            result = "1/2-1/2"
            termination = "max plies adjudication"

        if result == "*":
            outcome = board.outcome(claim_draw=True)
            if outcome is not None:
                result = outcome.result()
                termination = outcome.termination.name.lower().replace("_", " ")
            else:
                result = "1/2-1/2"
                termination = "runner adjudication"
    finally:
        white.close()
        black.close()

    game.headers["Result"] = result
    game.headers["Termination"] = termination
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    pgn = game.accept(exporter)

    if result == "1/2-1/2":
        score_a = 0.5
    elif (result == "1-0" and a_is_white) or (result == "0-1" and not a_is_white):
        score_a = 1.0
    else:
        score_a = 0.0

    return GameResult(
        game_index=game_index,
        white=white_spec.name,
        black=black_spec.name,
        result=result,
        termination=termination,
        opening=opening.name,
        moves=moves_uci,
        move_times_ms=move_times_ms,
        pgn=pgn,
        engine_a_score=score_a,
    )


def run_match(config: MatchConfig) -> MatchSummary:
    require_chess()
    config.validate()
    import time

    started = time.perf_counter()
    schedule = _opening_schedule(config)
    results: list[GameResult] = []
    print_lock = threading.Lock()

    def report(result: GameResult) -> None:
        with print_lock:
            print(
                f"[{result.game_index + 1:>4}/{config.games}] {result.white} - {result.black} "
                f"{result.result} ({result.termination})"
            )

    with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
        futures = {
            pool.submit(_play_game, config, index, opening): index
            for index, opening in enumerate(schedule)
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            report(result)

    results.sort(key=lambda r: r.game_index)
    wins = sum(r.engine_a_score == 1.0 for r in results)
    draws = sum(r.engine_a_score == 0.5 for r in results)
    losses = sum(r.engine_a_score == 0.0 for r in results)
    score = wins + 0.5 * draws
    elapsed = time.perf_counter() - started

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"match-{stamp}-{config.seed}"
    pgn_path = output_dir / f"{stem}.pgn"
    json_path = output_dir / f"{stem}.json"

    pgn_path.write_text("\n\n".join(r.pgn for r in results) + "\n", encoding="utf-8")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "engine_a": {"name": config.engine_a.name, "command": list(config.engine_a.command), "options": config.engine_a.options},
        "engine_b": {"name": config.engine_b.name, "command": list(config.engine_b.command), "options": config.engine_b.options},
        "time_control": asdict(config.time_control),
        "games": config.games,
        "concurrency": config.concurrency,
        "seed": config.seed,
        "summary": {
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "score": score,
            "score_percent": 100.0 * score / config.games,
            "elapsed_seconds": elapsed,
        },
        "game_results": [
            {k: v for k, v in asdict(r).items() if k != "pgn"}
            for r in results
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return MatchSummary(
        engine_a=config.engine_a.name,
        engine_b=config.engine_b.name,
        games=config.games,
        wins=wins,
        draws=draws,
        losses=losses,
        score=score,
        score_percent=100.0 * score / config.games,
        elapsed_seconds=elapsed,
        results_json=str(json_path),
        pgn_file=str(pgn_path),
    )
