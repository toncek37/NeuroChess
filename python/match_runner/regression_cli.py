from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .match import TimeControl, load_fen_openings
from .regression import RegressionConfig, run_regression, snapshot_baseline
from .uci_engine import EngineSpec


def _parse_option(text: str) -> tuple[str, str]:
    if "=" not in text:
        raise argparse.ArgumentTypeError("Engine option must be NAME=VALUE")
    name, value = text.split("=", 1)
    return name.strip(), value.strip()


def _engine(name: str, command: str, options: list[tuple[str, str]]) -> EngineSpec:
    return EngineSpec.from_command(name, command, options=dict(options))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NeuroChess head-to-head regression testing")
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="Save an executable/model as a reproducible baseline")
    snap.add_argument("--engine", required=True)
    snap.add_argument("--destination", required=True)
    snap.add_argument("--model")
    snap.add_argument("--label")

    run = sub.add_parser("run", help="Sequential head-to-head current vs baseline test")
    run.add_argument("--current", required=True)
    run.add_argument("--baseline", required=True)
    run.add_argument("--name-current", default="NeuroChess-current")
    run.add_argument("--name-baseline", default="NeuroChess-baseline")
    run.add_argument("--option-current", action="append", default=[], type=_parse_option)
    run.add_argument("--option-baseline", action="append", default=[], type=_parse_option)
    run.add_argument("--batch-games", type=int, default=20)
    run.add_argument("--min-games", type=int, default=40)
    run.add_argument("--max-games", type=int, default=400)
    run.add_argument("--concurrency", type=int, default=1)
    tc = run.add_mutually_exclusive_group()
    tc.add_argument("--movetime-ms", type=int, default=100)
    tc.add_argument("--base-ms", type=int)
    run.add_argument("--increment-ms", type=int, default=0)
    run.add_argument("--openings")
    run.add_argument("--seed", type=int, default=1)
    run.add_argument("--output-dir", default="regression-results")
    run.add_argument("--confidence", type=float, default=0.95)
    run.add_argument("--elo-margin", type=float, default=0.0,
                     help="Require CI to clear +/- this Elo before early better/worse decision")
    run.add_argument("--equivalence-margin", type=float, default=5.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "snapshot":
        metadata = snapshot_baseline(args.engine, args.destination, model=args.model, label=args.label)
        print(f"baseline metadata: {metadata}")
        return 0

    if args.base_ms is not None:
        tc = TimeControl(base_ms=args.base_ms, increment_ms=args.increment_ms, move_time_ms=None)
    else:
        tc = TimeControl(move_time_ms=args.movetime_ms)
    openings = load_fen_openings(args.openings) if args.openings else None
    cfg = RegressionConfig(
        current=_engine(args.name_current, args.current, args.option_current),
        baseline=_engine(args.name_baseline, args.baseline, args.option_baseline),
        batch_games=args.batch_games,
        min_games=args.min_games,
        max_games=args.max_games,
        concurrency=args.concurrency,
        time_control=tc,
        seed=args.seed,
        output_dir=args.output_dir,
        confidence=args.confidence,
        elo_margin=args.elo_margin,
        equivalence_margin=args.equivalence_margin,
    )
    if openings is not None:
        cfg.openings = openings
    result = run_regression(cfg)
    print(f"decision: {result.decision}")
    print(f"W/D/L: {result.wins}/{result.draws}/{result.losses} ({result.score_percent:.2f}%)")
    print(f"Elo difference: {result.elo_difference:+.1f} "
          f"[{result.confidence_lower:+.1f}, {result.confidence_upper:+.1f}]")
    print(f"games: {result.games}")
    print(f"report: {result.report_json}")
    return 0 if result.decision != "worse" else 2


if __name__ == "__main__":
    raise SystemExit(main())
