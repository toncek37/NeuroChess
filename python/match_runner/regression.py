from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
from typing import Callable

from .elo_ladder import _normal_quantile
from .match import MatchConfig, MatchSummary, Opening, TimeControl, run_match
from .uci_engine import EngineSpec


@dataclass(frozen=True)
class EloDifference:
    elo: float
    lower: float
    upper: float
    confidence: float
    score_percent: float
    games: int
    standard_error_score: float


@dataclass
class RegressionConfig:
    current: EngineSpec
    baseline: EngineSpec
    batch_games: int = 20
    min_games: int = 40
    max_games: int = 400
    concurrency: int = 1
    time_control: TimeControl = field(default_factory=lambda: TimeControl(move_time_ms=100))
    openings: list[Opening] = field(default_factory=lambda: [Opening()])
    randomize_openings: bool = True
    seed: int = 1
    max_plies: int = 600
    output_dir: str = "regression-results"
    confidence: float = 0.95
    elo_margin: float = 0.0
    equivalence_margin: float = 5.0

    def validate(self) -> None:
        self.time_control.validate()
        if self.batch_games <= 0 or self.batch_games % 2:
            raise ValueError("batch_games must be a positive even number for color-paired matches")
        if self.min_games <= 0 or self.max_games < self.min_games:
            raise ValueError("Require 0 < min_games <= max_games")
        if not 0.5 < self.confidence < 1.0:
            raise ValueError("confidence must be between 0.5 and 1.0")
        if self.elo_margin < 0.0 or self.equivalence_margin < 0.0:
            raise ValueError("Elo margins cannot be negative")
        if self.concurrency <= 0:
            raise ValueError("concurrency must be positive")


@dataclass
class RegressionLook:
    look: int
    games: int
    wins: int
    draws: int
    losses: int
    elo: float
    lower: float
    upper: float
    nominal_confidence: float
    sequential_confidence: float
    decision: str
    match_json: str
    pgn_file: str


@dataclass
class RegressionResult:
    decision: str
    games: int
    wins: int
    draws: int
    losses: int
    score_percent: float
    elo_difference: float
    confidence_lower: float
    confidence_upper: float
    confidence: float
    looks: list[RegressionLook]
    report_json: str


def _score_to_elo(score: float) -> float:
    # Clamp only for numerical transformation; exact 0/1 results have unbounded Elo.
    p = min(max(score, 1e-9), 1.0 - 1e-9)
    return 400.0 * math.log10(p / (1.0 - p))


def estimate_elo_difference(wins: int, draws: int, losses: int, confidence: float = 0.95) -> EloDifference:
    games = wins + draws + losses
    if games <= 0:
        raise ValueError("Cannot estimate Elo difference without games")
    if min(wins, draws, losses) < 0:
        raise ValueError("W/D/L counts cannot be negative")

    score = (wins + 0.5 * draws) / games
    # Draw-aware empirical variance of the game score X in {0, 0.5, 1}.
    ex2 = (wins + 0.25 * draws) / games
    variance = max(0.0, ex2 - score * score)
    if games > 1:
        variance *= games / (games - 1)  # unbiased sample variance
    se_score = math.sqrt(variance / games)
    z = _normal_quantile(confidence)

    # Work in score space, then transform endpoints through the monotonic Elo logistic.
    # Jeffreys-like finite-sample clipping prevents infinite bounds on all-win/all-loss batches.
    eps = 0.5 / (games + 1.0)
    lower_score = min(max(score - z * se_score, eps), 1.0 - eps)
    upper_score = min(max(score + z * se_score, eps), 1.0 - eps)
    return EloDifference(
        elo=_score_to_elo(score),
        lower=_score_to_elo(lower_score),
        upper=_score_to_elo(upper_score),
        confidence=confidence,
        score_percent=100.0 * score,
        games=games,
        standard_error_score=se_score,
    )


def _sequential_confidence(base_confidence: float, max_looks: int) -> float:
    """Bonferroni alpha spending across planned looks.

    This is deliberately conservative, but unlike repeatedly peeking at an ordinary 95% CI,
    it keeps the family-wise false-decision probability bounded by the requested alpha.
    """
    alpha = 1.0 - base_confidence
    return 1.0 - alpha / max(1, max_looks)


def _decision_from_interval(lower: float, upper: float, elo_margin: float) -> str:
    if lower > elo_margin:
        return "better"
    if upper < -elo_margin:
        return "worse"
    return "continue"


def snapshot_baseline(executable: str | Path, destination: str | Path, *, model: str | Path | None = None,
                      label: str | None = None) -> Path:
    """Copy an executable and optional model into an immutable-ish baseline directory with hashes."""
    source = Path(executable).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    exe_dest = dest / source.name
    shutil.copy2(source, exe_dest)

    def digest(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    payload = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "label": label or dest.name,
        "executable": {"file": exe_dest.name, "sha256": digest(exe_dest)},
        "model": None,
    }
    if model is not None:
        model_source = Path(model).resolve()
        if not model_source.is_file():
            raise FileNotFoundError(model_source)
        model_dest = dest / model_source.name
        shutil.copy2(model_source, model_dest)
        payload["model"] = {"file": model_dest.name, "sha256": digest(model_dest)}

    metadata = dest / "baseline.json"
    metadata.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return metadata


def run_regression(
    config: RegressionConfig,
    *,
    match_runner: Callable[[MatchConfig], MatchSummary] = run_match,
) -> RegressionResult:
    config.validate()
    root = Path(config.output_dir)
    root.mkdir(parents=True, exist_ok=True)

    wins = draws = losses = 0
    looks: list[RegressionLook] = []
    max_looks = math.ceil(config.max_games / config.batch_games)
    seq_conf = _sequential_confidence(config.confidence, max_looks)
    decision = "inconclusive"
    batch_index = 0

    while wins + draws + losses < config.max_games:
        played = wins + draws + losses
        games = min(config.batch_games, config.max_games - played)
        # Preserve color pairs if max_games is odd/misaligned.
        if games % 2:
            games -= 1
        if games <= 0:
            break
        batch_index += 1
        batch_dir = root / f"batch-{batch_index:03d}"
        summary = match_runner(MatchConfig(
            engine_a=config.current,
            engine_b=config.baseline,
            games=games,
            concurrency=config.concurrency,
            time_control=config.time_control,
            openings=config.openings,
            randomize_openings=config.randomize_openings,
            seed=config.seed + batch_index * 7919,
            max_plies=config.max_plies,
            output_dir=str(batch_dir),
            event=f"NeuroChess regression: {config.current.name} vs {config.baseline.name}",
        ))
        wins += summary.wins
        draws += summary.draws
        losses += summary.losses
        total = wins + draws + losses
        estimate = estimate_elo_difference(wins, draws, losses, seq_conf)

        look_decision = "continue"
        if total >= config.min_games:
            look_decision = _decision_from_interval(estimate.lower, estimate.upper, config.elo_margin)
        looks.append(RegressionLook(
            look=batch_index,
            games=total,
            wins=wins,
            draws=draws,
            losses=losses,
            elo=estimate.elo,
            lower=estimate.lower,
            upper=estimate.upper,
            nominal_confidence=config.confidence,
            sequential_confidence=seq_conf,
            decision=look_decision,
            match_json=summary.results_json,
            pgn_file=summary.pgn_file,
        ))
        if look_decision in ("better", "worse"):
            decision = look_decision
            break

    final = estimate_elo_difference(wins, draws, losses, config.confidence)
    if decision == "inconclusive":
        # Equivalence is only claimed after the planned maximum sample and only if the
        # ordinary final CI lies completely inside a user-defined practical Elo band.
        if wins + draws + losses >= config.max_games and \
                final.lower > -config.equivalence_margin and final.upper < config.equivalence_margin:
            decision = "equivalent"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = root / f"regression-{stamp}-{config.seed}.json"
    payload = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "current": {"name": config.current.name, "command": list(config.current.command), "options": config.current.options},
        "baseline": {"name": config.baseline.name, "command": list(config.baseline.command), "options": config.baseline.options},
        "time_control": asdict(config.time_control),
        "settings": {
            "batch_games": config.batch_games,
            "min_games": config.min_games,
            "max_games": config.max_games,
            "confidence": config.confidence,
            "sequential_confidence": seq_conf,
            "elo_margin": config.elo_margin,
            "equivalence_margin": config.equivalence_margin,
            "seed": config.seed,
        },
        "result": {
            "decision": decision,
            "games": final.games,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "score_percent": final.score_percent,
            "elo_difference": final.elo,
            "confidence_lower": final.lower,
            "confidence_upper": final.upper,
        },
        "looks": [asdict(look) for look in looks],
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return RegressionResult(
        decision=decision,
        games=final.games,
        wins=wins,
        draws=draws,
        losses=losses,
        score_percent=final.score_percent,
        elo_difference=final.elo,
        confidence_lower=final.lower,
        confidence_upper=final.upper,
        confidence=config.confidence,
        looks=looks,
        report_json=str(report_path),
    )
