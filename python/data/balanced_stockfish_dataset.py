from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import chess
import chess.engine

from .teacher_labeler import Teacher, TeacherConfig, labels_from_analysis


def bucket(cp: int) -> str:
    if cp <= -150:
        return "losing"
    if cp >= 150:
        return "winning"
    return "equal"


def main() -> int:
    p = argparse.ArgumentParser(description="Generate a balanced Stockfish self-play NeuroChess dataset.")
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
    if args.positions < 3:
        raise SystemExit("--positions must be at least 3")
    if args.random_top < 1:
        raise SystemExit("--random-top must be positive")

    rng = random.Random(args.seed)
    quotas = {
        "losing": args.positions // 3,
        "equal": args.positions // 3,
        "winning": args.positions - 2 * (args.positions // 3),
    }
    kept = {k: 0 for k in quotas}
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
                group = bucket(cp)
                if board.ply() >= args.min_ply and board.ply() % args.sample_every == 0 and kept[group] < quotas[group]:
                    record = {
                        "fen": board.fen(),
                        "source": "stockfish-selfplay-balanced",
                        "game_id": f"sf-selfplay:{game_no}",
                        "ply": board.ply(),
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
                        print(f"kept {total}/{args.positions} positions | losing {kept['losing']}/{quotas['losing']} | equal {kept['equal']}/{quotas['equal']} | winning {kept['winning']}/{quotas['winning']}", flush=True)

                policy = labels["policy"]
                if not policy:
                    break
                candidates = policy[: min(args.random_top, len(policy))]
                # Weighted random choice keeps play strong while producing varied, non-identical games.
                weights = [max(1e-6, float(item["probability"])) for item in candidates]
                move_uci = rng.choices([str(item["move"]) for item in candidates], weights=weights, k=1)[0]
                move = chess.Move.from_uci(move_uci)
                if move not in board.legal_moves:
                    break
                board.push(move)

            if game_no % 10 == 0:
                print(f"generated {game_no} Stockfish-guided games", flush=True)

    print(f"DONE: wrote {total} balanced labelled positions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
