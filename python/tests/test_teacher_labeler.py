from __future__ import annotations

import math
import unittest

import chess
import chess.engine

from data.teacher_labeler import TeacherConfig, labels_from_analysis


class TeacherLabelerTests(unittest.TestCase):
    def test_limit_requires_exactly_one_budget(self):
        with self.assertRaises(ValueError):
            TeacherConfig("engine", depth=None, nodes=None, movetime_ms=None).limit()
        with self.assertRaises(ValueError):
            TeacherConfig("engine", depth=10, nodes=1000, movetime_ms=None).limit()

    def test_policy_is_normalized_and_best_move_has_largest_probability(self):
        board = chess.Board()
        infos = [
            {"score": chess.engine.PovScore(chess.engine.Cp(80), chess.WHITE), "pv": [chess.Move.from_uci("e2e4")]},
            {"score": chess.engine.PovScore(chess.engine.Cp(20), chess.WHITE), "pv": [chess.Move.from_uci("d2d4")]},
            {"score": chess.engine.PovScore(chess.engine.Cp(-40), chess.WHITE), "pv": [chess.Move.from_uci("g1f3")]},
        ]
        labels = labels_from_analysis(board, infos)
        policy = labels["policy"]
        self.assertEqual(policy[0]["move"], "e2e4")
        total = sum(item["probability"] for item in policy)
        self.assertTrue(math.isclose(total, 1.0, rel_tol=1e-9))
        self.assertGreater(policy[0]["probability"], policy[1]["probability"])
        self.assertGreater(policy[1]["probability"], policy[2]["probability"])
        self.assertEqual(labels["value_cp"], 80)

    def test_score_is_from_side_to_move_perspective(self):
        board = chess.Board()
        board.turn = chess.BLACK
        infos = [
            {"score": chess.engine.PovScore(chess.engine.Cp(100), chess.WHITE), "pv": [chess.Move.from_uci("e7e5")]}
        ]
        labels = labels_from_analysis(board, infos)
        self.assertEqual(labels["value_cp"], -100)
        self.assertGreater(labels["wdl"]["loss"], labels["wdl"]["win"])

    def test_missing_pv_is_rejected(self):
        with self.assertRaises(ValueError):
            labels_from_analysis(chess.Board(), [{"score": chess.engine.PovScore(chess.engine.Cp(0), chess.WHITE)}])


if __name__ == "__main__":
    unittest.main()
