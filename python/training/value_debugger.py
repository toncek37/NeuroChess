from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import chess
import numpy as np

from .encoding import encode_board

CP_CLIP = 1500.0


@dataclass
class ValueMetrics:
    samples: int
    pearson_cp: float
    pearson_wdl_score: float
    mae_cp_clipped: float
    sign_agreement_percent: float
    teacher_mean_cp_clipped: float
    model_mean_cp: float
    wdl_brier: float
    saturated_percent: float
    white_to_move_sign_agreement: float
    black_to_move_sign_agreement: float


@dataclass
class SanityRow:
    name: str
    fen: str
    expected_sign: int
    win: float
    draw: float
    loss: float
    model_cp: int
    passed: bool
    in_distribution: bool


@dataclass
class ValueDebugReport:
    model: str
    dataset: str
    metrics: ValueMetrics
    sanity: list[SanityRow]
    orientation_passed: bool
    recommendation: str


def softmax3(logits: np.ndarray) -> np.ndarray:
    logits = np.asarray(logits, dtype=np.float64).reshape(3)
    shifted = logits - np.max(logits)
    exp = np.exp(shifted)
    return exp / max(float(exp.sum()), 1e-30)


def wdl_to_centipawns_from_probs(probs: np.ndarray) -> int:
    # Must match src/nn/neural_evaluator.cpp exactly.
    score = float(np.clip(probs[0] - probs[2], -0.999, 0.999))
    return int(400.0 * math.log10((1.0 + score) / (1.0 - score)))


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 2 or float(np.std(a)) < 1e-12 or float(np.std(b)) < 1e-12:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _sign_agreement(teacher: np.ndarray, model: np.ndarray, mask: np.ndarray) -> float:
    selected = mask & (np.abs(teacher) > 25.0)
    if not np.any(selected):
        return 0.0
    return float(np.mean(np.sign(teacher[selected]) == np.sign(model[selected])) * 100.0)


def _recommend(metrics: ValueMetrics, orientation_passed: bool) -> str:
    # In-distribution teacher agreement is authoritative. Synthetic sanity positions
    # are useful warnings, but some (especially terminal/minimal-material boards) are
    # deliberately absent from the training distribution.
    if metrics.pearson_wdl_score < 0.0 or metrics.pearson_cp < 0.0:
        return "Model value is anti-correlated with the teacher. Keep neural value disabled and retrain/check targets."
    if min(metrics.white_to_move_sign_agreement, metrics.black_to_move_sign_agreement) < 70.0:
        return "Side-to-move generalization is asymmetric on labelled data. Keep neural value disabled and improve dataset balance/training."
    if metrics.pearson_wdl_score < 0.50 or metrics.sign_agreement_percent < 80.0:
        return "Value direction is still too weak for search integration. Train on more balanced positions before Elo testing."
    if metrics.wdl_brier > 0.10 or metrics.mae_cp_clipped > 350.0 or metrics.saturated_percent > 35.0:
        return "Value direction is useful but calibration is poor. If benchmarking, use only a very small blend (5%); more data/training is recommended first."
    suffix = " Synthetic OOD sanity warnings remain." if not orientation_passed else ""
    return "Value head looks usable on held-out teacher-labelled positions. Benchmark 5% blend first, then 10% if stable." + suffix


SANITY_POSITIONS = (
    # These are intentionally simple extrapolation checks. The generator samples
    # non-terminal Stockfish-play positions, so they are warnings rather than gates.
    ("White queen advantage, White to move", "7k/8/8/8/8/8/4Q3/4K3 w - - 0 1", 1, False),
    ("White queen advantage, Black to move", "7k/8/8/8/8/8/4Q3/4K3 b - - 0 1", -1, False),
    ("Black queen advantage, White to move", "4k3/4q3/8/8/8/8/8/7K w - - 0 1", -1, False),
    ("Black queen advantage, Black to move", "4k3/4q3/8/8/8/8/8/7K b - - 0 1", 1, False),
    ("Bare kings, White to move", "7k/8/8/8/8/8/8/K7 w - - 0 1", 0, False),
    ("Bare kings, Black to move", "7k/8/8/8/8/8/8/K7 b - - 0 1", 0, False),
)


def run_value_debug(
    model_path: str | Path,
    dataset_path: str | Path,
    *,
    max_samples: int = 2000,
    progress: Callable[[str], None] | None = None,
) -> ValueDebugReport:
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
    if "wdl_logits" not in output_names:
        raise RuntimeError(f"ONNX model has no wdl_logits output: {output_names}")

    def infer(board: chess.Board) -> tuple[np.ndarray, int]:
        tensor = encode_board(board).numpy().astype(np.float32, copy=False)[None, ...]
        outputs = session.run(["wdl_logits"], {input_name: tensor})
        probs = softmax3(outputs[0][0])
        return probs, wdl_to_centipawns_from_probs(probs)

    emit("Running synthetic material sanity positions (OOD warnings, not hard gates)...")
    sanity: list[SanityRow] = []
    for name, fen, expected, in_distribution in SANITY_POSITIONS:
        board = chess.Board(fen)
        probs, cp = infer(board)
        if expected == 0:
            passed = abs(cp) <= 200
        else:
            passed = cp * expected > 25
        row = SanityRow(name, fen, expected, float(probs[0]), float(probs[1]), float(probs[2]), cp, passed, in_distribution)
        sanity.append(row)
        emit(f"  {name}: W/D/L={row.win:.3f}/{row.draw:.3f}/{row.loss:.3f}, cp={cp:+d} -> {'PASS' if passed else 'WARN'}")

    # OOD sanity positions no longer decide orientation correctness.
    orientation_passed = True

    teacher_cp: list[float] = []
    model_cp: list[float] = []
    teacher_wdl: list[list[float]] = []
    model_wdl: list[list[float]] = []
    turns_white: list[bool] = []
    emit(f"Validating up to {max_samples} labelled positions...")
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if len(teacher_cp) >= max_samples:
                break
            if not line.strip():
                continue
            record = json.loads(line)
            if "fen" not in record or "wdl" not in record:
                continue
            board = chess.Board(str(record["fen"]))
            probs, cp = infer(board)
            wdl = record["wdl"]
            t = [float(wdl["win"]), float(wdl["draw"]), float(wdl["loss"])]
            tcp = float(record.get("value_cp", 0.0))
            teacher_cp.append(tcp)
            model_cp.append(float(cp))
            teacher_wdl.append(t)
            model_wdl.append(probs.tolist())
            turns_white.append(board.turn == chess.WHITE)
            if len(teacher_cp) % 250 == 0:
                emit(f"  analysed {len(teacher_cp)} positions")

    if not teacher_cp:
        raise RuntimeError("Dataset contains no labelled positions with FEN/WDL.")

    tc_raw = np.asarray(teacher_cp, dtype=np.float64)
    tc = np.clip(tc_raw, -CP_CLIP, CP_CLIP)
    mc = np.asarray(model_cp, dtype=np.float64)
    tw = np.asarray(teacher_wdl, dtype=np.float64)
    mw = np.asarray(model_wdl, dtype=np.float64)
    white_mask = np.asarray(turns_white, dtype=bool)
    black_mask = ~white_mask
    all_mask = np.ones_like(white_mask, dtype=bool)
    teacher_score = tw[:, 0] - tw[:, 2]
    model_score = mw[:, 0] - mw[:, 2]
    confidence = np.maximum(mw[:, 0], mw[:, 2])

    metrics = ValueMetrics(
        samples=int(tc.size),
        pearson_cp=_pearson(tc, mc),
        pearson_wdl_score=_pearson(teacher_score, model_score),
        mae_cp_clipped=float(np.mean(np.abs(tc - mc))),
        sign_agreement_percent=_sign_agreement(tc, mc, all_mask),
        teacher_mean_cp_clipped=float(np.mean(tc)),
        model_mean_cp=float(np.mean(mc)),
        wdl_brier=float(np.mean(np.sum((tw - mw) ** 2, axis=1))),
        saturated_percent=float(np.mean(confidence >= 0.95) * 100.0),
        white_to_move_sign_agreement=_sign_agreement(tc, mc, white_mask),
        black_to_move_sign_agreement=_sign_agreement(tc, mc, black_mask),
    )
    orientation_passed = min(metrics.white_to_move_sign_agreement, metrics.black_to_move_sign_agreement) >= 70.0
    recommendation = _recommend(metrics, orientation_passed)
    emit(f"Pearson teacher/model clipped cp: {metrics.pearson_cp:.3f}")
    emit(f"Pearson teacher/model WDL score: {metrics.pearson_wdl_score:.3f}")
    emit(f"MAE clipped to ±{CP_CLIP:.0f} cp: {metrics.mae_cp_clipped:.1f} cp")
    emit(f"Sign agreement overall: {metrics.sign_agreement_percent:.1f}%")
    emit(f"  White to move: {metrics.white_to_move_sign_agreement:.1f}%")
    emit(f"  Black to move: {metrics.black_to_move_sign_agreement:.1f}%")
    emit(f"WDL Brier: {metrics.wdl_brier:.4f}")
    emit(f"Saturated decisive predictions: {metrics.saturated_percent:.1f}%")
    emit(f"Recommendation: {recommendation}")
    return ValueDebugReport(str(model_path), str(dataset_path), metrics, sanity, orientation_passed, recommendation)


def save_report(report: ValueDebugReport, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
