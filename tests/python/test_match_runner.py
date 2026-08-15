from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from match_runner.match import MatchConfig, Opening, TimeControl, _go_command, _opening_schedule, load_fen_openings
from match_runner.uci_engine import EngineSpec, UciEngine


class MatchRunnerTests(unittest.TestCase):
    def test_engine_handshake_and_bestmove(self):
        fake = ROOT / "tests" / "python" / "fake_uci_engine.py"
        spec = EngineSpec.from_command("fake", [sys.executable, str(fake)], options={"Skill": 3})
        with UciEngine(spec) as engine:
            self.assertEqual(engine.id_name, "FakeUCI 1.0")
            engine.new_game()
            engine.set_position(None, [])
            move, info, elapsed = engine.bestmove("go depth 1", timeout=2.0)
            self.assertEqual(move, "e2e4")
            self.assertTrue(any(line.startswith("info depth 1") for line in info))
            self.assertGreaterEqual(elapsed, 0.0)

    def test_color_paired_opening_schedule_is_reproducible(self):
        a = EngineSpec.from_command("a", ["a"])
        b = EngineSpec.from_command("b", ["b"])
        openings = [Opening(name="A"), Opening(name="B"), Opening(name="C")]
        cfg = MatchConfig(a, b, games=5, openings=openings, seed=42)
        one = _opening_schedule(cfg)
        two = _opening_schedule(cfg)
        self.assertEqual([x.name for x in one], [x.name for x in two])
        self.assertEqual(one[0].name, one[1].name)
        self.assertEqual(one[2].name, one[3].name)

    def test_go_commands(self):
        self.assertEqual(_go_command(TimeControl(move_time_ms=250), 1, 1), "go movetime 250")
        cmd = _go_command(TimeControl(base_ms=5000, increment_ms=50, movestogo=20), 4321.7, 3988.2)
        self.assertEqual(cmd, "go wtime 4321 btime 3988 winc 50 binc 50 movestogo 20")

    def test_opening_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "openings.txt"
            path.write_text("# comment\nstartpos | Start\n8/8/8/8/8/8/8/K6k w - - 0 1 | Kings\n", encoding="utf-8")
            openings = load_fen_openings(path)
            self.assertEqual(len(openings), 2)
            self.assertIsNone(openings[0].fen)
            self.assertEqual(openings[1].name, "Kings")


if __name__ == "__main__":
    unittest.main()
