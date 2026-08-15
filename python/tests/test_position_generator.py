from __future__ import annotations

import io
import random
import unittest

import chess
import chess.pgn

from data.position_generator import (
    PositionRecord,
    deduplicate,
    generate_self_play_positions,
    perturb_position,
    sample_game_positions,
)


PGN = """[Event \"Prompt 13 test\"]
[Result \"1-0\"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7
6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3 Nb8 10. d4 Nbd7 1-0
"""


class PositionGeneratorTests(unittest.TestCase):
    def test_pgn_sampling_is_reproducible_and_legal(self):
        game = chess.pgn.read_game(io.StringIO(PGN))
        first = sample_game_positions(game, "g", random.Random(7), 3, 4, 40)
        second = sample_game_positions(game, "g", random.Random(7), 3, 4, 40)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)
        for record in first:
            board = chess.Board(record.fen)
            self.assertTrue(board.is_valid())
            self.assertEqual(record.source, "pgn")
            self.assertEqual(record.result, "1-0")

    def test_perturbation_keeps_legal_position_and_parent(self):
        base = PositionRecord(chess.STARTING_FEN, "pgn", "g", 0)
        variant = perturb_position(base, random.Random(3), 2, 2)
        self.assertIsNotNone(variant)
        self.assertEqual(variant.parent_fen, chess.STARTING_FEN)
        self.assertEqual(variant.perturbation_plies, 2)
        self.assertTrue(chess.Board(variant.fen).is_valid())

    def test_random_self_play_is_reproducible(self):
        a = list(generate_self_play_positions(2, seed=11, positions_per_game=2, min_ply=2, max_ply=20))
        b = list(generate_self_play_positions(2, seed=11, positions_per_game=2, min_ply=2, max_ply=20))
        self.assertEqual(a, b)
        self.assertGreater(len(a), 0)

    def test_deduplicate_uses_position_key(self):
        record = PositionRecord(chess.STARTING_FEN, "pgn", "a", 0)
        other = PositionRecord(chess.STARTING_FEN, "selfplay-random", "b", 0)
        self.assertEqual(list(deduplicate([record, other])), [record])


if __name__ == "__main__":
    unittest.main()
