from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from match_runner.match import MatchSummary, TimeControl
from match_runner.regression import (
    RegressionConfig,
    estimate_elo_difference,
    run_regression,
    snapshot_baseline,
)
from match_runner.uci_engine import EngineSpec


class RegressionTests(unittest.TestCase):
    def test_even_match_is_zero_elo(self):
        estimate = estimate_elo_difference(30, 40, 30)
        self.assertAlmostEqual(estimate.elo, 0.0, places=6)
        self.assertLess(estimate.lower, 0.0)
        self.assertGreater(estimate.upper, 0.0)

    def test_positive_score_is_positive_elo(self):
        estimate = estimate_elo_difference(55, 20, 25)
        self.assertGreater(estimate.elo, 100.0)

    def test_snapshot_copies_and_hashes_engine_and_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            exe = tmp / "engine"
            model = tmp / "model.bin"
            exe.write_bytes(b"engine-v1")
            model.write_bytes(b"model-v1")
            metadata = snapshot_baseline(exe, tmp / "baseline", model=model, label="v1")
            payload = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual(payload["label"], "v1")
            self.assertEqual(len(payload["executable"]["sha256"]), 64)
            self.assertEqual(len(payload["model"]["sha256"]), 64)
            self.assertTrue((tmp / "baseline" / "engine").exists())

    def test_sequential_test_stops_on_clear_improvement(self):
        calls = []
        def fake_match(cfg):
            calls.append(cfg.games)
            # 75% score in each batch; enough to trigger a strong positive decision.
            wins = cfg.games * 3 // 4
            draws = 0
            losses = cfg.games - wins
            return MatchSummary(cfg.engine_a.name, cfg.engine_b.name, cfg.games,
                                wins, draws, losses, float(wins), 100.0*wins/cfg.games,
                                0.01, "x.json", "x.pgn")
        with tempfile.TemporaryDirectory() as tmp:
            cfg = RegressionConfig(
                current=EngineSpec.from_command("new", ["new"]),
                baseline=EngineSpec.from_command("old", ["old"]),
                batch_games=40, min_games=40, max_games=400,
                time_control=TimeControl(move_time_ms=10), output_dir=tmp)
            result = run_regression(cfg, match_runner=fake_match)
            self.assertEqual(result.decision, "better")
            self.assertLess(result.games, cfg.max_games)
            self.assertGreater(result.confidence_lower, 0.0)
            self.assertTrue(Path(result.report_json).exists())

    def test_noisy_even_match_remains_inconclusive_at_small_sample(self):
        def fake_match(cfg):
            draws = cfg.games
            return MatchSummary(cfg.engine_a.name, cfg.engine_b.name, cfg.games,
                                0, draws, 0, 0.5*draws, 50.0,
                                0.01, "x.json", "x.pgn")
        with tempfile.TemporaryDirectory() as tmp:
            cfg = RegressionConfig(
                current=EngineSpec.from_command("new", ["new"]),
                baseline=EngineSpec.from_command("old", ["old"]),
                batch_games=20, min_games=20, max_games=40,
                equivalence_margin=5.0,
                time_control=TimeControl(move_time_ms=10), output_dir=tmp)
            result = run_regression(cfg, match_runner=fake_match)
            # All draws have zero empirical variance, so at max sample this is exactly equivalent.
            self.assertEqual(result.decision, "equivalent")
            self.assertEqual(result.games, 40)


if __name__ == "__main__":
    unittest.main()
