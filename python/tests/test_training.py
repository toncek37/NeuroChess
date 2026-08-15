from __future__ import annotations

import unittest

import chess
import torch

from training.encoding import BOARD_CHANNELS, POLICY_SIZE, encode_board, index_to_move, move_to_index
from training.model import NeuroChessNet
from training.train import policy_loss, wdl_loss


class TrainingTests(unittest.TestCase):
    def test_move_index_roundtrip_including_promotions(self):
        moves = [
            chess.Move.from_uci("e2e4"),
            chess.Move.from_uci("e1g1"),
            chess.Move.from_uci("e7e8q"),
            chess.Move.from_uci("a2a1n"),
        ]
        for move in moves:
            index = move_to_index(move)
            self.assertGreaterEqual(index, 0)
            self.assertLess(index, POLICY_SIZE)
            self.assertEqual(index_to_move(index), move)

    def test_board_encoding_shape_and_start_position(self):
        x = encode_board(chess.Board())
        self.assertEqual(tuple(x.shape), (BOARD_CHANNELS, 8, 8))
        self.assertEqual(float(x[:12].sum()), 32.0)
        self.assertTrue(torch.all(x[12] == 1.0))  # White to move.
        self.assertTrue(torch.all(x[13:17] == 1.0))  # All castling rights.
        self.assertEqual(float(x[17:25].sum()), 0.0)

    def test_model_output_shapes(self):
        model = NeuroChessNet(channels=16, blocks=1)
        boards = torch.stack([encode_board(chess.Board()), encode_board(chess.Board())])
        policy, wdl = model(boards)
        self.assertEqual(tuple(policy.shape), (2, POLICY_SIZE))
        self.assertEqual(tuple(wdl.shape), (2, 3))

    def test_losses_are_finite_and_backpropagate(self):
        policy_logits = torch.randn(2, POLICY_SIZE, requires_grad=True)
        indices = torch.tensor([[move_to_index(chess.Move.from_uci("e2e4")), -1],
                                [move_to_index(chess.Move.from_uci("d2d4")), move_to_index(chess.Move.from_uci("g1f3"))]])
        probs = torch.tensor([[1.0, 0.0], [0.7, 0.3]])
        wdl_logits = torch.randn(2, 3, requires_grad=True)
        wdls = torch.tensor([[0.6, 0.3, 0.1], [0.2, 0.5, 0.3]])
        loss = policy_loss(policy_logits, indices, probs) + wdl_loss(wdl_logits, wdls)
        self.assertTrue(torch.isfinite(loss))
        loss.backward()
        self.assertIsNotNone(policy_logits.grad)
        self.assertIsNotNone(wdl_logits.grad)


if __name__ == "__main__":
    unittest.main()
