from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Callable, Iterable

from .match import MatchConfig, MatchSummary, Opening, TimeControl, run_match
from .uci_engine import EngineSpec, UciEngine, UciError


DEFAULT_STOCKFISH_LEVELS = (1400, 1600, 1800, 2000, 2200, 2400, 2600, 2800, 3000, 3190)


@dataclass
class LadderConfig:
    engine: EngineSpec
    stockfish: EngineSpec
    levels: tuple[int, ...] = DEFAULT_STOCKFISH_LEVELS
    probe_games: int = 8
    refine_games: int = 24
    concurrency: int = 1
    time_control: TimeControl = field(default_factory=lambda: TimeControl(move_time_ms=100))
    openings: list[Opening] = field(default_factory=lambda: [Opening()])
    randomize_openings: bool = True
    seed: int = 1
    max_plies: int = 600
    output_dir: str = "elo-ladder-results"
    score_band: float = 0.08
    confidence: float = 0.95
    validate_stockfish: bool = True

    def validate(self) -> None:
        if len(self.levels) < 2:
            raise ValueError("At least two Stockfish Elo levels are required")
        if tuple(sorted(set(self.levels))) != self.levels:
            raise ValueError("levels must be strictly increasing and unique")
        if self.probe_games < 2 or self.refine_games < 2:
            raise ValueError("probe_games and refine_games must be at least 2")
        if self.probe_games % 2 or self.refine_games % 2:
            raise ValueError("probe_games and refine_games must be even for color-paired matches")
        if self.concurrency <= 0:
            raise ValueError("concurrency must be positive")
        if not 0.0 < self.score_band < 0.5:
            raise ValueError("score_band must be between 0 and 0.5")
        if not 0.5 < self.confidence < 1.0:
            raise ValueError("confidence must be between 0.5 and 1.0")
        self.time_control.validate()


@dataclass
class LadderPoint:
    stockfish_elo: int
    games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    score: float = 0.0
    score_percent: float = 0.0
    match_json: list[str] = field(default_factory=list)
    pgn_files: list[str] = field(default_factory=list)

    def add(self, summary: MatchSummary) -> None:
        self.games += summary.games
        self.wins += summary.wins
        self.draws += summary.draws
        self.losses += summary.losses
        self.score += summary.score
        self.score_percent = 100.0 * self.score / self.games
        self.match_json.append(summary.results_json)
        self.pgn_files.append(summary.pgn_file)


@dataclass
class EloEstimate:
    elo: float
    lower: float
    upper: float
    confidence: float
    standard_error: float
    games: int


@dataclass
class LadderResult:
    estimated_elo: float
    confidence_lower: float
    confidence_upper: float
    confidence: float
    total_games: int
    points: list[LadderPoint]
    report_json: str


def _normal_quantile(confidence: float) -> float:
    # Acklam inverse-normal approximation. No scipy dependency needed.
    p = 0.5 + confidence / 2.0
    if not 0.0 < p < 1.0:
        raise ValueError("confidence produces invalid quantile")
    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00)
    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0-p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
    q = p - 0.5
    r = q*q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1.0)


def _expected_score(player_elo: float, opponent_elo: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (opponent_elo - player_elo) / 400.0))


def estimate_elo(points: Iterable[LadderPoint], confidence: float = 0.95) -> EloEstimate:
    used = [p for p in points if p.games > 0]
    games = sum(p.games for p in used)
    if games == 0:
        raise ValueError("Cannot estimate Elo without games")

    actual_score = sum(p.score for p in used)

    # Solve sum(expected scores) == observed total score. The function is monotonic.
    lo = min(p.stockfish_elo for p in used) - 1600.0
    hi = max(p.stockfish_elo for p in used) + 1600.0
    for _ in range(100):
        mid = (lo + hi) * 0.5
        expected = sum(p.games * _expected_score(mid, p.stockfish_elo) for p in used)
        if expected < actual_score:
            lo = mid
        else:
            hi = mid
    elo = (lo + hi) * 0.5

    # Fisher-information approximation for the logistic Elo model. Draws contribute
    # half a point to the observed score; this gives a useful match-strength CI but
    # intentionally does not claim to be a FIDE rating confidence interval.
    k = math.log(10.0) / 400.0
    information = 0.0
    for p in used:
        expected = _expected_score(elo, p.stockfish_elo)
        information += p.games * (k * k) * expected * (1.0 - expected)
    standard_error = 1.0 / math.sqrt(max(information, 1e-18))
    z = _normal_quantile(confidence)
    return EloEstimate(
        elo=elo,
        lower=elo - z * standard_error,
        upper=elo + z * standard_error,
        confidence=confidence,
        standard_error=standard_error,
        games=games,
    )


def validate_stockfish_strength_options(stockfish: EngineSpec) -> None:
    """Fail early when the reference engine does not advertise the needed UCI options."""
    with UciEngine(stockfish) as engine:
        normalized = {name.lower() for name in engine.option_names}
        missing = [name for name in ("UCI_LimitStrength", "UCI_Elo") if name.lower() not in normalized]
        if missing:
            raise UciError(
                f"Reference engine '{engine.id_name}' does not advertise required options: {', '.join(missing)}"
            )


def _stockfish_at_elo(base: EngineSpec, elo: int) -> EngineSpec:
    options = dict(base.options)
    options["UCI_LimitStrength"] = True
    options["UCI_Elo"] = elo
    return EngineSpec(name=f"{base.name} {elo}", command=base.command, options=options, cwd=base.cwd)


def run_elo_ladder(
    config: LadderConfig,
    *,
    match_runner: Callable[[MatchConfig], MatchSummary] = run_match,
) -> LadderResult:
    config.validate()
    if config.validate_stockfish:
        validate_stockfish_strength_options(config.stockfish)

    root = Path(config.output_dir)
    root.mkdir(parents=True, exist_ok=True)
    points = {level: LadderPoint(level) for level in config.levels}
    run_counter = 0

    def sample(level: int, games: int) -> LadderPoint:
        nonlocal run_counter
        run_counter += 1
        per_run_dir = root / f"sf-{level}" / f"run-{run_counter:03d}"
        match = MatchConfig(
            engine_a=config.engine,
            engine_b=_stockfish_at_elo(config.stockfish, level),
            games=games,
            concurrency=config.concurrency,
            time_control=config.time_control,
            openings=config.openings,
            randomize_openings=config.randomize_openings,
            seed=config.seed + run_counter * 1009 + level,
            max_plies=config.max_plies,
            output_dir=str(per_run_dir),
            event=f"NeuroChess Elo ladder vs Stockfish {level}",
        )
        summary = match_runner(match)
        points[level].add(summary)
        return points[level]

    # Coarse binary search over configured rungs. Each comparison asks whether the
    # engine is clearly above/below the rung or already within the 50% target band.
    low_idx = 0
    high_idx = len(config.levels) - 1
    visited: set[int] = set()
    target_idx: int | None = None
    while low_idx <= high_idx:
        idx = (low_idx + high_idx) // 2
        level = config.levels[idx]
        if level not in visited:
            point = sample(level, config.probe_games)
            visited.add(level)
        else:
            point = points[level]
        p = point.score / point.games
        if abs(p - 0.5) <= config.score_band:
            target_idx = idx
            break
        if p > 0.5:
            low_idx = idx + 1
        else:
            high_idx = idx - 1

    if target_idx is None:
        # Bracket is between high_idx (engine scored >50%) and low_idx (<50%).
        target_idx = min(max(low_idx, 0), len(config.levels) - 1)

    # Refine the closest rung plus its immediate neighbours. This concentrates games
    # where they contribute most to the rating estimate without wasting a full match
    # at every ladder level.
    refine_indices = sorted({i for i in (target_idx - 1, target_idx, target_idx + 1) if 0 <= i < len(config.levels)})
    for idx in refine_indices:
        level = config.levels[idx]
        already = points[level].games
        if already < config.refine_games:
            sample(level, config.refine_games - already)

    used_points = [points[level] for level in config.levels if points[level].games]
    estimate = estimate_elo(used_points, config.confidence)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = root / f"elo-ladder-{stamp}-{config.seed}.json"
    payload = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "engine": {"name": config.engine.name, "command": list(config.engine.command), "options": config.engine.options},
        "stockfish": {"name": config.stockfish.name, "command": list(config.stockfish.command), "base_options": config.stockfish.options},
        "levels": list(config.levels),
        "probe_games": config.probe_games,
        "refine_games": config.refine_games,
        "time_control": asdict(config.time_control),
        "confidence": config.confidence,
        "estimate": asdict(estimate),
        "points": [asdict(point) for point in used_points],
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return LadderResult(
        estimated_elo=estimate.elo,
        confidence_lower=estimate.lower,
        confidence_upper=estimate.upper,
        confidence=config.confidence,
        total_games=estimate.games,
        points=used_points,
        report_json=str(report_path),
    )
