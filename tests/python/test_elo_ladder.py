from __future__ import annotations
from pathlib import Path
import math, sys, tempfile, unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from match_runner.elo_ladder import LadderConfig,LadderPoint,estimate_elo,run_elo_ladder,validate_stockfish_strength_options
from match_runner.match import MatchSummary, TimeControl
from match_runner.uci_engine import EngineSpec

class EloLadderTests(unittest.TestCase):
    def test_estimate_centered_on_even_match(self):
        p=LadderPoint(2200,games=100,wins=30,draws=40,losses=30,score=50,score_percent=50)
        e=estimate_elo([p])
        self.assertAlmostEqual(e.elo,2200,places=5)
        self.assertLess(e.lower,2200); self.assertGreater(e.upper,2200)

    def test_estimate_above_opponent_for_positive_score(self):
        p=LadderPoint(2000,games=100,wins=55,draws=20,losses=25,score=65,score_percent=65)
        e=estimate_elo([p])
        self.assertGreater(e.elo,2100)

    def test_stockfish_option_validation_with_fake_engine(self):
        fake=ROOT/'tests/python/fake_uci_engine.py'
        validate_stockfish_strength_options(EngineSpec.from_command('fake',[sys.executable,str(fake)]))

    def test_adaptive_ladder_concentrates_near_strength(self):
        calls=[]
        def fake_match(cfg):
            elo=int(cfg.engine_b.options['UCI_Elo']); calls.append((elo,cfg.games))
            # deterministic synthetic 2300-strength engine
            p=1/(1+10**((elo-2300)/400))
            score=round(p*cfg.games*2)/2
            wins=int(score); rem=score-wins
            draws=1 if rem else 0
            losses=cfg.games-wins-draws
            return MatchSummary(cfg.engine_a.name,cfg.engine_b.name,cfg.games,wins,draws,losses,score,100*score/cfg.games,0.01,'x.json','x.pgn')
        with tempfile.TemporaryDirectory() as tmp:
            cfg=LadderConfig(
                EngineSpec.from_command('A',['a']),EngineSpec.from_command('SF',['sf']),
                levels=(1600,1800,2000,2200,2400,2600,2800),probe_games=8,refine_games=24,
                time_control=TimeControl(move_time_ms=10),output_dir=tmp,validate_stockfish=False)
            result=run_elo_ladder(cfg,match_runner=fake_match)
            self.assertLess(len({x[0] for x in calls}),len(cfg.levels))
            self.assertTrue(2200 <= result.estimated_elo <= 2400)
            self.assertGreaterEqual(result.total_games,48)
            self.assertTrue(Path(result.report_json).exists())
if __name__=='__main__': unittest.main()
