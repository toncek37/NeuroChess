import unittest

import chess

from training.encoding import POLICY_SIZE, index_to_move, move_to_index


class PolicyEncodingExhaustiveTests(unittest.TestCase):
    def test_all_policy_indices_round_trip(self):
        for index in range(POLICY_SIZE):
            self.assertEqual(move_to_index(index_to_move(index)), index)

    def test_special_moves_use_expected_indices(self):
        for uci in ("e1g1", "e1c1", "e5d6"):
            move = chess.Move.from_uci(uci)
            self.assertEqual(move_to_index(move), move.from_square * 64 + move.to_square)
        buckets = {chess.QUEEN: 1, chess.ROOK: 2, chess.BISHOP: 3, chess.KNIGHT: 4}
        for piece, bucket in buckets.items():
            move = chess.Move(chess.A7, chess.A8, promotion=piece)
            self.assertEqual(move_to_index(move), bucket * 4096 + chess.A7 * 64 + chess.A8)


if __name__ == "__main__":
    unittest.main()
