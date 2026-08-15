"""Automated UCI match runner for NeuroChess experiments."""

from .uci_engine import EngineSpec, UciEngine, UciError, UciTimeout
from .match import MatchConfig, TimeControl, MatchSummary, run_match
from .regression import RegressionConfig, RegressionResult, estimate_elo_difference, run_regression, snapshot_baseline

__all__ = [
    "EngineSpec",
    "UciEngine",
    "UciError",
    "UciTimeout",
    "MatchConfig",
    "TimeControl",
    "MatchSummary",
    "run_match",
    "RegressionConfig",
    "RegressionResult",
    "estimate_elo_difference",
    "run_regression",
    "snapshot_baseline",
]
