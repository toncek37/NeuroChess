from __future__ import annotations

import argparse
from pathlib import Path

from .teacher_labeler import Teacher, TeacherConfig, label_records, read_jsonl, write_labelled_jsonl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Label NeuroChess positions with a strong UCI teacher.")
    parser.add_argument("--input", required=True, type=Path, help="Unlabelled JSONL from generate_positions.")
    parser.add_argument("--output", required=True, type=Path, help="Labelled JSONL output.")
    parser.add_argument("--engine", required=True, help="Path to teacher UCI engine (typically Stockfish).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--depth", type=int, default=14)
    group.add_argument("--nodes", type=int)
    group.add_argument("--movetime-ms", type=int)
    parser.add_argument("--multipv", type=int, default=8)
    parser.add_argument("--hash-mb", type=int, default=256)
    parser.add_argument("--threads", type=int, default=1)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.input.is_file():
        raise SystemExit(f"Input dataset does not exist: {args.input}")
    engine_path = Path(args.engine)
    if not engine_path.is_file():
        raise SystemExit(f"Teacher engine does not exist: {engine_path}")
    if args.multipv <= 0:
        raise SystemExit("--multipv must be positive.")

    depth = args.depth
    if args.nodes is not None or args.movetime_ms is not None:
        depth = None
    config = TeacherConfig(
        engine_path=str(engine_path),
        depth=depth,
        nodes=args.nodes,
        movetime_ms=args.movetime_ms,
        multipv=args.multipv,
        hash_mb=args.hash_mb,
        threads=args.threads,
    )

    with Teacher(config) as teacher:
        count = write_labelled_jsonl(label_records(read_jsonl(args.input), teacher), args.output)
    print(f"Wrote {count} teacher-labelled positions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
