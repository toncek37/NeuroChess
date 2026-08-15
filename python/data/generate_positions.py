from __future__ import annotations

import argparse
import itertools
import random
from pathlib import Path

from .position_generator import (
    deduplicate,
    generate_self_play_positions,
    iter_pgn_positions,
    perturb_position,
    write_jsonl,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate NeuroChess training positions.")
    parser.add_argument("--pgn", action="append", default=[], help="Input PGN; may be repeated.")
    parser.add_argument("--output", required=True, type=Path, help="Output JSONL dataset.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--positions-per-game", type=int, default=4)
    parser.add_argument("--min-ply", type=int, default=12)
    parser.add_argument("--max-ply", type=int, default=160)
    parser.add_argument("--self-play-games", type=int, default=0)
    parser.add_argument(
        "--perturbations-per-position",
        type=int,
        default=0,
        help="Add this many legal random continuations for every sampled base position.",
    )
    parser.add_argument("--perturb-min-plies", type=int, default=1)
    parser.add_argument("--perturb-max-plies", type=int, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.pgn and args.self_play_games <= 0:
        raise SystemExit("Provide at least one --pgn or set --self-play-games > 0.")
    if args.positions_per_game <= 0:
        raise SystemExit("--positions-per-game must be positive.")
    if args.perturbations_per_position < 0:
        raise SystemExit("--perturbations-per-position cannot be negative.")
    if not (0 <= args.min_ply <= args.max_ply):
        raise SystemExit("Require 0 <= --min-ply <= --max-ply.")
    if not (1 <= args.perturb_min_plies <= args.perturb_max_plies):
        raise SystemExit("Invalid perturbation ply range.")

    pgn_paths = [Path(value) for value in args.pgn]
    missing = [str(path) for path in pgn_paths if not path.is_file()]
    if missing:
        raise SystemExit("Missing PGN file(s): " + ", ".join(missing))

    streams = []
    if pgn_paths:
        streams.append(
            iter_pgn_positions(
                pgn_paths,
                seed=args.seed,
                positions_per_game=args.positions_per_game,
                min_ply=args.min_ply,
                max_ply=args.max_ply,
            )
        )
    if args.self_play_games:
        streams.append(
            generate_self_play_positions(
                args.self_play_games,
                seed=args.seed + 1,
                positions_per_game=args.positions_per_game,
                min_ply=args.min_ply,
                max_ply=args.max_ply,
            )
        )

    rng = random.Random(args.seed + 2)

    def with_perturbations():
        for record in itertools.chain.from_iterable(streams):
            yield record
            for _ in range(args.perturbations_per_position):
                variant = perturb_position(
                    record, rng, args.perturb_min_plies, args.perturb_max_plies
                )
                if variant is not None:
                    yield variant

    count = write_jsonl(deduplicate(with_perturbations()), args.output)
    print(f"Wrote {count} unique positions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
