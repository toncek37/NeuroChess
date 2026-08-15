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
    k = math.log(10.0) / 400.0
    information = 0.0
    for p in used:
        expected = _expected_score(elo, p.stockfish_elo)
        information += p.games * (k * k) * expected * (1.0 - expected)
    standard_error = 1.0 / math.sqrt(max(information, 1e-18))
    z = _normal_quantile(confidence)
    return EloEstimate(elo, elo - z * standard_error, elo + z * standard_error,
                       confidence, standard_error, games)


def validate_stockfish_strength_options(stockfish: EngineSpec) -> None:
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
    progress: Callable[[str], None] | None = None,
) -> LadderResult:
    config.validate()
    emit = progress or (lambda _message: None)
    emit("Validating Stockfish UCI strength controls...")
    if config.validate_stockfish:
        validate_stockfish_strength_options(config.stockfish)
    emit("Stockfish validation OK.")

    root = Path(config.output_dir)
    root.mkdir(parents=True, exist_ok=True)
    points = {level: LadderPoint(level) for level in config.levels}
    run_counter = 0

    def sample(level: int, games: int) -> LadderPoint:
        nonlocal run_counter
        run_counter += 1
        emit(f"Playing {games} games vs Stockfish Elo {level}...")
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
        point = points[level]
        emit(
            f"SF {level}: {point.wins}-{point.draws}-{point.losses}, "
            f"score {point.score_percent:.1f}% ({point.games} games)."
        )
        return point

    # A binary search is a poor fit for tiny match samples: a noisy 5/8 at
    # one level can otherwise jump several hundred Elo in one step. Start near
    # the middle of the ladder and walk only one level (normally 200 Elo) at a
    # time. Scores close enough to 50% are confirmed with extra games before
    # deciding which direction to move.
    idx = len(config.levels) // 2
    target_idx: int | None = None
    previous_direction = 0
    visited_indices: set[int] = set()
    confirmation_games = max(config.probe_games * 2, min(config.refine_games, 16))

    while 0 <= idx < len(config.levels):
        level = config.levels[idx]
        point = points[level]
        if point.games < config.probe_games:
            sample(level, config.probe_games - point.games)
            point = points[level]

        score_fraction = point.score / point.games

        # With only a handful of games, do not make a direction decision from
        # a moderately imbalanced score. Top up the same level first.
        if 0.25 < score_fraction < 0.75 and point.games < confirmation_games:
            emit(
                f"SF {level} probe is noisy ({100.0 * score_fraction:.1f}%); "
                f"confirming at the same level before moving."
            )
            sample(level, confirmation_games - point.games)
            point = points[level]
            score_fraction = point.score / point.games

        if abs(score_fraction - 0.5) <= config.score_band:
            target_idx = idx
            emit(f"Target band reached near Stockfish Elo {level}.")
            break

        direction = 1 if score_fraction > 0.5 else -1
        next_idx = idx + direction

        # If the direction changes after adjacent levels, the crossover lies
        # between them. Refine around the current point instead of oscillating.
        if previous_direction and direction != previous_direction:
            target_idx = idx
            emit(f"Strength crossover bracketed near Stockfish Elo {level}.")
            break

        visited_indices.add(idx)
        if next_idx < 0 or next_idx >= len(config.levels) or next_idx in visited_indices:
            target_idx = idx
            break

        emit(
            f"Moving one ladder step {'up' if direction > 0 else 'down'} "
            f"to Stockfish Elo {config.levels[next_idx]}."
        )
        previous_direction = direction
        idx = next_idx

    if target_idx is None:
        target_idx = min(max(idx, 0), len(config.levels) - 1)

    refine_indices = sorted({i for i in (target_idx - 1, target_idx, target_idx + 1)
                             if 0 <= i < len(config.levels)})
    emit("Refining around the estimated strength region...")
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
    emit(
        f"Estimated Elo {estimate.elo:.0f}; {config.confidence*100:.0f}% CI "
        f"{estimate.lower:.0f}..{estimate.upper:.0f}; {estimate.games} games."
    )

    return LadderResult(
        estimated_elo=estimate.elo,
        confidence_lower=estimate.lower,
        confidence_upper=estimate.upper,
        confidence=config.confidence,
        total_games=estimate.games,
        points=used_points,
        report_json=str(report_path),
    )
