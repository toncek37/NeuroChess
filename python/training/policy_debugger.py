from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import chess
import numpy as np

from .encoding import encode_board, move_to_index


PIECE_VALUE = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20_000,
}


@dataclass
class RankingMetrics:
    samples: int
    top1_percent: float
    top3_percent: float
    top5_percent: float
    mean_rank: float
    median_rank: float
    mrr: float


@dataclass
class PolicyDebugReport:
    model: str
    dataset: str
    neural: RankingMetrics
    classical_static: RankingMetrics
    white_to_move: RankingMetrics
    black_to_move: RankingMetrics
    neural_mean_teacher_mass_top1: float
    neural_mean_teacher_mass_top3: float
    neural_mean_teacher_mass_top5: float
    recommendation: str
    note: str


def _metrics(ranks: list[int]) -> RankingMetrics:
    if not ranks:
        return RankingMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    values = np.asarray(ranks, dtype=np.float64)
    return RankingMetrics(
        samples=len(ranks),
        top1_percent=float(np.mean(values <= 1) * 100.0),
        top3_percent=float(np.mean(values <= 3) * 100.0),
        top5_percent=float(np.mean(values <= 5) * 100.0),
        mean_rank=float(np.mean(values)),
        median_rank=float(np.median(values)),
        mrr=float(np.mean(1.0 / values)),
    )


def _capture_victim(board: chess.Board, move: chess.Move) -> int:
    if board.is_en_passant(move):
        return chess.PAWN
    piece = board.piece_at(move.to_square)
    return piece.piece_type if piece else 0


def _classical_static_score(board: chess.Board, move: chess.Move) -> int:
    score = 0
    if move.promotion:
        score += 900_000 + PIECE_VALUE.get(move.promotion, 0)
    if board.is_capture(move):
        victim_type = _capture_victim(board, move)
        attacker = board.piece_at(move.from_square)
        attacker_type = attacker.piece_type if attacker else 0
        score += 1_000_000 + 10 * PIECE_VALUE.get(victim_type, 0) - PIECE_VALUE.get(attacker_type, 0)
    return score


def _rank_of(move: chess.Move, ordered: list[chess.Move]) -> int:
    try:
        return ordered.index(move) + 1
    except ValueError:
        return len(ordered) + 1


def _teacher_mass_topk(ordered: list[chess.Move], teacher_probs: dict[chess.Move, float], k: int) -> float:
    return float(sum(teacher_probs.get(move, 0.0) for move in ordered[:k]))


def _recommend(neural: RankingMetrics, baseline: RankingMetrics) -> str:
    top3_gain = neural.top3_percent - baseline.top3_percent
    mrr_gain = neural.mrr - baseline.mrr
    if neural.top1_percent < 15.0 or neural.top3_percent < 35.0:
        return "Policy head is weak at reproducing the teacher move. Improve policy training/data before relying on it for root ordering."
    if top3_gain < -3.0 or mrr_gain < -0.03:
        return "Neural policy ranks teacher moves worse than the static classical baseline. Keep root policy guidance disabled for strength play."
    if top3_gain > 5.0 and mrr_gain > 0.03:
        return "Neural policy clearly improves teacher-move ordering over the static classical baseline. Root policy guidance is justified; Elo-test it with the one-inference design."
    return "Policy is useful but its ordering advantage over the static classical baseline is small. The near-equal Elo result is consistent with these diagnostics."


def run_policy_debug(
    model_path: str | Path,
    dataset_path: str | Path,
    *,
    max_samples: int = 2000,
    progress: Callable[[str], None] | None = None,
) -> PolicyDebugReport:
    emit = progress or (lambda _msg: None)
    model_path = Path(model_path)
    dataset_path = Path(dataset_path)
    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    if not dataset_path.is_file():
        raise FileNotFoundError(dataset_path)

    import onnxruntime as ort

    emit(f"Loading ONNX model: {model_path}")
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_names = [o.name for o in session.get_outputs()]
    if "policy_logits" not in output_names:
        raise RuntimeError(f"ONNX model has no policy_logits output: {output_names}")

    neural_ranks: list[int] = []
    classical_ranks: list[int] = []
    white_ranks: list[int] = []
    black_ranks: list[int] = []
    mass1: list[float] = []
    mass3: list[float] = []
    mass5: list[float] = []

    emit(f"Validating up to {max_samples} labelled positions...")
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if len(neural_ranks) >= max_samples:
                break
            if not line.strip():
                continue
            record = json.loads(line)
            if "fen" not in record or "policy" not in record:
                continue
            candidates = record["policy"]
            if not candidates:
                continue

            board = chess.Board(str(record["fen"]))
            legal = list(board.legal_moves)
            if not legal:
                continue

            teacher_probs: dict[chess.Move, float] = {}
            for candidate in candidates:
                try:
                    move = chess.Move.from_uci(str(candidate["move"]))
                    probability = float(candidate["probability"])
                except (KeyError, TypeError, ValueError):
                    continue
                if move in legal and probability > 0.0:
                    teacher_probs[move] = teacher_probs.get(move, 0.0) + probability
            if not teacher_probs:
                continue
            total = sum(teacher_probs.values())
            teacher_probs = {move: p / total for move, p in teacher_probs.items()}
            teacher_move = max(teacher_probs.items(), key=lambda item: item[1])[0]

            tensor = encode_board(board).numpy().astype(np.float32, copy=False)[None, ...]
            logits = np.asarray(session.run(["policy_logits"], {input_name: tensor})[0][0], dtype=np.float64)
            neural_order = sorted(legal, key=lambda move: float(logits[move_to_index(move)]), reverse=True)

            # Cold-root static C++ ordering baseline. TT/killer/history need live search
            # state and cannot be reconstructed from an isolated labelled FEN.
            indexed_legal = list(enumerate(legal))
            indexed_legal.sort(key=lambda item: (-_classical_static_score(board, item[1]), item[0]))
            classical_order = [move for _, move in indexed_legal]

            nrank = _rank_of(teacher_move, neural_order)
            crank = _rank_of(teacher_move, classical_order)
            neural_ranks.append(nrank)
            classical_ranks.append(crank)
            (white_ranks if board.turn == chess.WHITE else black_ranks).append(nrank)
            mass1.append(_teacher_mass_topk(neural_order, teacher_probs, 1))
            mass3.append(_teacher_mass_topk(neural_order, teacher_probs, 3))
            mass5.append(_teacher_mass_topk(neural_order, teacher_probs, 5))

            if len(neural_ranks) % 250 == 0:
                emit(f"  analysed {len(neural_ranks)} positions")

    if not neural_ranks:
        raise RuntimeError("Dataset contains no usable labelled positions with FEN/policy targets.")

    neural = _metrics(neural_ranks)
    classical = _metrics(classical_ranks)
    white = _metrics(white_ranks)
    black = _metrics(black_ranks)
    recommendation = _recommend(neural, classical)
    note = (
        "classical_static reproduces promotion/capture MVV-LVA ordering only. "
        "TT, killer and history ordering require live search state and are intentionally excluded."
    )

    emit(f"Neural policy: top1 {neural.top1_percent:.1f}% | top3 {neural.top3_percent:.1f}% | top5 {neural.top5_percent:.1f}%")
    emit(f"  mean rank {neural.mean_rank:.2f} | median {neural.median_rank:.1f} | MRR {neural.mrr:.3f}")
    emit(f"  White: top1 {white.top1_percent:.1f}% | top3 {white.top3_percent:.1f}% | MRR {white.mrr:.3f}")
    emit(f"  Black: top1 {black.top1_percent:.1f}% | top3 {black.top3_percent:.1f}% | MRR {black.mrr:.3f}")
    emit(f"Static classical baseline: top1 {classical.top1_percent:.1f}% | top3 {classical.top3_percent:.1f}% | top5 {classical.top5_percent:.1f}% | MRR {classical.mrr:.3f}")
    emit(f"Teacher probability mass captured by neural top1/top3/top5: {np.mean(mass1)*100:.1f}% / {np.mean(mass3)*100:.1f}% / {np.mean(mass5)*100:.1f}%")
    emit(f"Recommendation: {recommendation}")

    return PolicyDebugReport(
        model=str(model_path),
        dataset=str(dataset_path),
        neural=neural,
        classical_static=classical,
        white_to_move=white,
        black_to_move=black,
        neural_mean_teacher_mass_top1=float(np.mean(mass1) * 100.0),
        neural_mean_teacher_mass_top3=float(np.mean(mass3) * 100.0),
        neural_mean_teacher_mass_top5=float(np.mean(mass5) * 100.0),
        recommendation=recommendation,
        note=note,
    )


def save_report(report: PolicyDebugReport, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
