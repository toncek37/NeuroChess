from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .match import MatchConfig, Opening, TimeControl, load_fen_openings, run_match
from .uci_engine import EngineSpec


def _options(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise argparse.ArgumentTypeError(f"Expected NAME=VALUE, got {value!r}")
        name, option_value = value.split("=", 1)
        result[name.strip()] = option_value.strip()
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run reproducible UCI engine matches for NeuroChess")
    p.add_argument("--engine-a", required=True, help="Command for engine A")
    p.add_argument("--engine-b", required=True, help="Command for engine B")
    p.add_argument("--name-a", default="NeuroChess")
    p.add_argument("--name-b", default="Opponent")
    p.add_argument("--option-a", action="append", default=[], metavar="NAME=VALUE")
    p.add_argument("--option-b", action="append", default=[], metavar="NAME=VALUE")
    p.add_argument("--games", type=int, default=20)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--base-ms", type=int, default=10_000)
    p.add_argument("--increment-ms", type=int, default=100)
    p.add_argument("--movetime-ms", type=int)
    p.add_argument("--movestogo", type=int)
    p.add_argument("--openings", help="Text file: FEN | optional name; use 'startpos' for initial position")
    p.add_argument("--no-randomize-openings", action="store_true")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--max-plies", type=int, default=600)
    p.add_argument("--output-dir", default="match-results")
    p.add_argument("--event", default="NeuroChess UCI Match")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    openings = load_fen_openings(args.openings) if args.openings else [Opening()]
    config = MatchConfig(
        engine_a=EngineSpec.from_command(args.name_a, args.engine_a, options=_options(args.option_a)),
        engine_b=EngineSpec.from_command(args.name_b, args.engine_b, options=_options(args.option_b)),
        games=args.games,
        concurrency=args.concurrency,
        time_control=TimeControl(
            base_ms=args.base_ms,
            increment_ms=args.increment_ms,
            move_time_ms=args.movetime_ms,
            movestogo=args.movestogo,
        ),
        openings=openings,
        randomize_openings=not args.no_randomize_openings,
        seed=args.seed,
        max_plies=args.max_plies,
        output_dir=args.output_dir,
        event=args.event,
    )
    try:
        summary = run_match(config)
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print("\nMatch complete")
    print(f"{summary.engine_a} vs {summary.engine_b}: {summary.wins}-{summary.draws}-{summary.losses}")
    print(f"Score: {summary.score:.1f}/{summary.games} ({summary.score_percent:.1f}%)")
    print(f"PGN:  {summary.pgn_file}")
    print(f"JSON: {summary.results_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
