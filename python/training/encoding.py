from __future__ import annotations

import chess
import torch

BOARD_CHANNELS = 26
PROMOTION_BUCKETS = (None, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
POLICY_SIZE = 5 * 64 * 64

PIECE_CHANNEL = {
    (chess.WHITE, chess.PAWN): 0,
    (chess.WHITE, chess.KNIGHT): 1,
    (chess.WHITE, chess.BISHOP): 2,
    (chess.WHITE, chess.ROOK): 3,
    (chess.WHITE, chess.QUEEN): 4,
    (chess.WHITE, chess.KING): 5,
    (chess.BLACK, chess.PAWN): 6,
    (chess.BLACK, chess.KNIGHT): 7,
    (chess.BLACK, chess.BISHOP): 8,
    (chess.BLACK, chess.ROOK): 9,
    (chess.BLACK, chess.QUEEN): 10,
    (chess.BLACK, chess.KING): 11,
}


def encode_board(board: chess.Board) -> torch.Tensor:
    """Encode a position as 26 x 8 x 8 float32 planes.

    Planes: 12 piece planes, side-to-move, four castling-right planes,
    eight en-passant-file planes, and normalized halfmove clock.
    """
    x = torch.zeros((BOARD_CHANNELS, 8, 8), dtype=torch.float32)
    for square, piece in board.piece_map().items():
        channel = PIECE_CHANNEL[(piece.color, piece.piece_type)]
        rank = chess.square_rank(square)
        file = chess.square_file(square)
        x[channel, rank, file] = 1.0

    if board.turn == chess.WHITE:
        x[12].fill_(1.0)

    rights = (
        board.has_kingside_castling_rights(chess.WHITE),
        board.has_queenside_castling_rights(chess.WHITE),
        board.has_kingside_castling_rights(chess.BLACK),
        board.has_queenside_castling_rights(chess.BLACK),
    )
    for offset, enabled in enumerate(rights, start=13):
        if enabled:
            x[offset].fill_(1.0)

    if board.ep_square is not None:
        x[17 + chess.square_file(board.ep_square)].fill_(1.0)

    x[25].fill_(min(board.halfmove_clock, 100) / 100.0)
    return x


def move_to_index(move: chess.Move) -> int:
    try:
        promotion_bucket = PROMOTION_BUCKETS.index(move.promotion)
    except ValueError as exc:
        raise ValueError(f"Unsupported promotion piece: {move.promotion}") from exc
    return promotion_bucket * 4096 + move.from_square * 64 + move.to_square


def index_to_move(index: int) -> chess.Move:
    if not 0 <= index < POLICY_SIZE:
        raise ValueError(f"Policy index out of range: {index}")
    promotion_bucket, remainder = divmod(index, 4096)
    from_square, to_square = divmod(remainder, 64)
    return chess.Move(from_square, to_square, promotion=PROMOTION_BUCKETS[promotion_bucket])
