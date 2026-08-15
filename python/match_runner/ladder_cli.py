from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .elo_ladder import DEFAULT_STOCKFISH_LEVELS, LadderConfig, run_elo_ladder
from .match import Opening, TimeControl, load_fen_openings
from .uci_engine import EngineSpec, UciError


def _options(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise argparse.ArgumentTypeError(f"Expected NAME=VALUE, got {value!r}")
        name, option_value = value.split("=", 1)
        result[name.strip()] = option_value.strip()
    return result


def _levels(text: str) -> tuple[int, ...]:
    try:
        values = tuple(int(part.strip()) for part in text.split(",") if part.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("levels must be comma-separated integers") from exc
    if not values:
        raise argparse.ArgumentTypeError("at least one level is required")
    return values


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Estimate NeuroChess strength against Stockfish UCI_Elo")
    p.add_argument("--engine", required=True, help="NeuroChess (or other tested engine) command")
    p.add_argument("--stockfish", required=True, help="Stockfish command")
    p.add_argument("--engine-name", default="NeuroChess")
    p.add_argument("--stockfish-name", default="Stockfish")
    p.add_argument("--engine-option", action="append", default=[], metavar="NAME=VALUE")
    p.add_argument("--stockfish-option", action="append", default=[], metavar="NAME=VALUE")
    p.add_argument("--levels", type=_levels, default=DEFAULT_STOCKFISH_LEVELS)
    p.add_argument("--probe-games", type=int, default=8)
    p.add_argument("--refine-games", type=int, default=24)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--movetime-ms", type=int, default=100)
    p.add_argument("--base-ms", type=int, default=10_000)
    p.add_argument("--increment-ms", type=int, default=100)
    p.add_argument("--openings")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--max-plies", type=int, default=600)
    p.add_argument("--score-band", type=float, default=0.08)
    p.add_argument("--confidence", type=float, default=0.95)
    p.add_argument("--output-dir", default="elo-ladder-results")
    p.add_argument("--no-randomize-openings", action="store_true")
    p.add_argument("--skip-stockfish-validation", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    openings = load_fen_openings(args.openings) if args.openings else [Opening()]
    tc = TimeControl(
        base_ms=args.base_ms,
        increment_ms=args.increment_ms,
        move_time_ms=args.movetime_ms if args.movetime_ms > 0 else None,
    )
    config = LadderConfig(
        engine=EngineSpec.from_command(args.engine_name, args.engine, options=_options(args.engine_option)),
        stockfish=EngineSpec.from_command(args.stockfish_name, args.stockfish, options=_options(args.stockfish_option)),
        levels=args.levels,
        probe_games=args.probe_games,
        refine_games=args.refine_games,
        concurrency=args.concurrency,
        time_control=tc,
        openings=openings,
        randomize_openings=not args.no_randomize_openings,
        seed=args.seed,
        max_plies=args.max_plies,
        output_dir=args.output_dir,
        score_band=args.score_band,
        confidence=args.confidence,
        validate_stockfish=not args.skip_stockfish_validation,
    )
    try:
        result = run_elo_ladder(config)
    except (RuntimeError, ValueError, UciError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    pct = result.confidence * 100.0
    print("\nElo ladder complete")
    for point in result.points:
        print(
            f"SF {point.stockfish_elo:4d}: {point.wins}-{point.draws}-{point.losses} "
            f"({point.score_percent:5.1f}%, {point.games} games)"
        )
    print(
        f"Estimated Stockfish-equivalent Elo: {result.estimated_elo:.0f} "
        f"({pct:.0f}% CI {result.confidence_lower:.0f}..{result.confidence_upper:.0f})"
    )
    print(f"Games: {result.total_games}")
    print(f"JSON:  {result.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
