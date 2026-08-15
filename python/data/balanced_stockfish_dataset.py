from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import chess

from .teacher_labeler import Teacher, TeacherConfig, labels_from_analysis


def bucket(cp: int) -> str:
    if cp <= -150:
        return "losing"
    if cp >= 150:
        return "winning"
    return "equal"


def side_name(turn: chess.Color) -> str:
    return "white" if turn == chess.WHITE else "black"


def main() -> int:
    p = argparse.ArgumentParser(description="Generate a side-balanced Stockfish self-play NeuroChess dataset.")
    p.add_argument("--engine", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--positions", type=int, default=10000)
    p.add_argument("--depth", type=int, default=12)
    p.add_argument("--multipv", type=int, default=8)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--min-ply", type=int, default=8)
    p.add_argument("--max-ply", type=int, default=140)
    p.add_argument("--sample-every", type=int, default=2)
    p.add_argument("--random-top", type=int, default=3, help="Choose among this many top teacher moves during self-play.")
    args = p.parse_args()
    if args.positions < 6:
        raise SystemExit("--positions must be at least 6")
    if args.random_top < 1:
        raise SystemExit("--random-top must be positive")
    if args.sample_every < 1:
        raise SystemExit("--sample-every must be positive")

    rng = random.Random(args.seed)
    groups = [(side, outcome) for side in ("white", "black") for outcome in ("losing", "equal", "winning")]
    base = args.positions // len(groups)
    quotas = {group: base for group in groups}
    for group in groups[: args.positions - base * len(groups)]:
        quotas[group] += 1
    kept = {group: 0 for group in groups}
    total = 0
    game_no = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    config = TeacherConfig(engine_path=args.engine, depth=args.depth, multipv=args.multipv, hash_mb=256, threads=1)

    with Teacher(config) as teacher, args.output.open("w", encoding="utf-8") as out:
        while total < args.positions:
            game_no += 1
            board = chess.Board()
            while not board.is_game_over(claim_draw=True) and board.ply() < args.max_ply and total < args.positions:
                infos = teacher.analyse(board)
                labels = labels_from_analysis(board, infos)
                cp = int(labels["value_cp"])
                group = (side_name(board.turn), bucket(cp))

                # Do not use board.ply() % sample_every here: with sample_every=2
                # that permanently selects only one side to move. Random thinning keeps
                # the requested sampling rate without introducing a colour/parity bias.
                sample_this_position = args.sample_every == 1 or rng.randrange(args.sample_every) == 0
                if board.ply() >= args.min_ply and sample_this_position and kept[group] < quotas[group]:
                    record = {
                        "fen": board.fen(),
                        "source": "stockfish-selfplay-side-balanced",
                        "game_id": f"sf-selfplay:{game_no}",
                        "ply": board.ply(),
                        "side_to_move": group[0],
                        "value_bucket": group[1],
                        "teacher": {
                            "name": teacher.engine_name,
                            "depth": args.depth,
                            "multipv": args.multipv,
                            "options": teacher.engine_options,
                        },
                        **labels,
                    }
                    out.write(json.dumps(record, sort_keys=True) + "\n")
                    kept[group] += 1
                    total += 1
                    if total % 100 == 0 or total == args.positions:
                        status = " | ".join(
                            f"{side[0].upper()}{outcome[0]} {kept[(side, outcome)]}/{quotas[(side, outcome)]}"
                            for side, outcome in groups
                        )
                        print(f"kept {total}/{args.positions} | {status}", flush=True)

                policy = labels["policy"]
                if not policy:
                    break
                candidates = policy[: min(args.random_top, len(policy))]
                weights = [max(1e-6, float(item["probability"])) for item in candidates]
                move_uci = rng.choices([str(item["move"]) for item in candidates], weights=weights, k=1)[0]
                move = chess.Move.from_uci(move_uci)
                if move not in board.legal_moves:
                    break
                board.push(move)

            if game_no % 10 == 0:
                print(f"generated {game_no} Stockfish-guided games", flush=True)

    print("Final side/bucket distribution:")
    for side in ("white", "black"):
        print(
            f"  {side} to move: "
            + ", ".join(f"{outcome}={kept[(side, outcome)]}" for outcome in ("losing", "equal", "winning")),
            flush=True,
        )
    print(f"DONE: wrote {total} side-balanced labelled positions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
