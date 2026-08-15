#include "neurochess/core/move_generator.h"

#include <array>
#include <bit>

namespace neurochess::core {
namespace {

constexpr bool on_board(int file, int rank) noexcept {
    return file >= 0 && file < 8 && rank >= 0 && rank < 8;
}

void add_promotions(std::vector<Move>& moves, int from, int to, bool capture) {
    constexpr std::array<PieceType, 4> promotion_pieces{
        PieceType::Queen, PieceType::Rook, PieceType::Bishop, PieceType::Knight
    };
    const auto flag = capture ? MoveFlag::PromotionCapture : MoveFlag::Promotion;
    for (PieceType type : promotion_pieces) {
        moves.emplace_back(from, to, flag, type);
    }
}

void add_step_moves(const Board& board, std::vector<Move>& moves, int from,
                    const int (*offsets)[2], std::size_t count, Color us) {
    const int from_file = from % 8;
    const int from_rank = from / 8;
    const Bitboard friendly = board.occupancy(us);
    const Bitboard enemy = board.occupancy(opposite(us));

    for (std::size_t i = 0; i < count; ++i) {
        const int file = from_file + offsets[i][0];
        const int rank = from_rank + offsets[i][1];
        if (!on_board(file, rank)) continue;
        const int to = square_index(file, rank);
        const Bitboard bit = square_bit(to);
        if (friendly & bit) continue;
        moves.emplace_back(from, to, (enemy & bit) ? MoveFlag::Capture : MoveFlag::Quiet);
    }
}

void add_slider_moves(const Board& board, std::vector<Move>& moves, int from,
                      const int (*directions)[2], std::size_t count, Color us) {
    const int from_file = from % 8;
    const int from_rank = from / 8;
    const Bitboard friendly = board.occupancy(us);
    const Bitboard enemy = board.occupancy(opposite(us));

    for (std::size_t i = 0; i < count; ++i) {
        int file = from_file + directions[i][0];
        int rank = from_rank + directions[i][1];
        while (on_board(file, rank)) {
            const int to = square_index(file, rank);
            const Bitboard bit = square_bit(to);
            if (friendly & bit) break;
            if (enemy & bit) {
                moves.emplace_back(from, to, MoveFlag::Capture);
                break;
            }
            moves.emplace_back(from, to, MoveFlag::Quiet);
            file += directions[i][0];
            rank += directions[i][1];
        }
    }
}

void generate_pawns(const Board& board, std::vector<Move>& moves, Color us) {
    const Piece pawn_piece = make_piece(us, PieceType::Pawn);
    Bitboard pawns = board.pieces(pawn_piece);
    const int direction = us == Color::White ? 1 : -1;
    const int start_rank = us == Color::White ? 1 : 6;
    const int promotion_rank = us == Color::White ? 7 : 0;
    const Bitboard enemy = board.occupancy(opposite(us));
    const Bitboard occupied = board.occupancy_all();

    while (pawns) {
        const int from = std::countr_zero(pawns);
        pawns &= pawns - 1;
        const int file = from % 8;
        const int rank = from / 8;
        const int one_rank = rank + direction;

        if (on_board(file, one_rank)) {
            const int one = square_index(file, one_rank);
            if ((occupied & square_bit(one)) == 0) {
                if (one_rank == promotion_rank) add_promotions(moves, from, one, false);
                else moves.emplace_back(from, one, MoveFlag::Quiet);

                const int two_rank = rank + 2 * direction;
                if (rank == start_rank && on_board(file, two_rank)) {
                    const int two = square_index(file, two_rank);
                    if ((occupied & square_bit(two)) == 0) {
                        moves.emplace_back(from, two, MoveFlag::DoublePawnPush);
                    }
                }
            }
        }

        for (int df : {-1, 1}) {
            const int target_file = file + df;
            const int target_rank = rank + direction;
            if (!on_board(target_file, target_rank)) continue;
            const int to = square_index(target_file, target_rank);
            if (enemy & square_bit(to)) {
                if (target_rank == promotion_rank) add_promotions(moves, from, to, true);
                else moves.emplace_back(from, to, MoveFlag::Capture);
            } else if (board.en_passant_square() && *board.en_passant_square() == to) {
                // FEN validity only guarantees a target square. Ensure there is
                // actually an opposing pawn adjacent before emitting EP.
                const int captured_square = square_index(target_file, rank);
                if (board.piece_at(captured_square) == make_piece(opposite(us), PieceType::Pawn)) {
                    moves.emplace_back(from, to, MoveFlag::EnPassant);
                }
            }
        }
    }
}

void generate_castling(const Board& board, std::vector<Move>& moves, Color us) {
    const Bitboard occupied = board.occupancy_all();
    if (us == Color::White && board.piece_at(square_index(4, 0)) == Piece::WhiteKing) {
        if (board.has_castling_right(WhiteKingSide)
            && board.piece_at(square_index(7, 0)) == Piece::WhiteRook
            && !(occupied & (square_bit(square_index(5, 0)) | square_bit(square_index(6, 0))))) {
            moves.emplace_back(square_index(4, 0), square_index(6, 0), MoveFlag::KingCastle);
        }
        if (board.has_castling_right(WhiteQueenSide)
            && board.piece_at(square_index(0, 0)) == Piece::WhiteRook
            && !(occupied & (square_bit(square_index(1, 0)) | square_bit(square_index(2, 0)) | square_bit(square_index(3, 0))))) {
            moves.emplace_back(square_index(4, 0), square_index(2, 0), MoveFlag::QueenCastle);
        }
    } else if (us == Color::Black && board.piece_at(square_index(4, 7)) == Piece::BlackKing) {
        if (board.has_castling_right(BlackKingSide)
            && board.piece_at(square_index(7, 7)) == Piece::BlackRook
            && !(occupied & (square_bit(square_index(5, 7)) | square_bit(square_index(6, 7))))) {
            moves.emplace_back(square_index(4, 7), square_index(6, 7), MoveFlag::KingCastle);
        }
        if (board.has_castling_right(BlackQueenSide)
            && board.piece_at(square_index(0, 7)) == Piece::BlackRook
            && !(occupied & (square_bit(square_index(1, 7)) | square_bit(square_index(2, 7)) | square_bit(square_index(3, 7))))) {
            moves.emplace_back(square_index(4, 7), square_index(2, 7), MoveFlag::QueenCastle);
        }
    }
}

} // namespace

std::vector<Move> MoveGenerator::pseudo_legal(const Board& board) {
    std::vector<Move> moves;
    moves.reserve(64);
    const Color us = board.side_to_move();

    generate_pawns(board, moves, us);

    constexpr int knight_offsets[8][2] = {
        {1,2},{2,1},{2,-1},{1,-2},{-1,-2},{-2,-1},{-2,1},{-1,2}
    };
    constexpr int king_offsets[8][2] = {
        {1,0},{1,1},{0,1},{-1,1},{-1,0},{-1,-1},{0,-1},{1,-1}
    };
    constexpr int bishop_dirs[4][2] = {{1,1},{1,-1},{-1,1},{-1,-1}};
    constexpr int rook_dirs[4][2] = {{1,0},{-1,0},{0,1},{0,-1}};
    constexpr int queen_dirs[8][2] = {
        {1,1},{1,-1},{-1,1},{-1,-1},{1,0},{-1,0},{0,1},{0,-1}
    };

    auto for_each_piece = [&](PieceType type, auto&& fn) {
        Bitboard bb = board.pieces(make_piece(us, type));
        while (bb) {
            const int from = std::countr_zero(bb);
            bb &= bb - 1;
            fn(from);
        }
    };

    for_each_piece(PieceType::Knight, [&](int from) {
        add_step_moves(board, moves, from, knight_offsets, 8, us);
    });
    for_each_piece(PieceType::Bishop, [&](int from) {
        add_slider_moves(board, moves, from, bishop_dirs, 4, us);
    });
    for_each_piece(PieceType::Rook, [&](int from) {
        add_slider_moves(board, moves, from, rook_dirs, 4, us);
    });
    for_each_piece(PieceType::Queen, [&](int from) {
        add_slider_moves(board, moves, from, queen_dirs, 8, us);
    });
    for_each_piece(PieceType::King, [&](int from) {
        add_step_moves(board, moves, from, king_offsets, 8, us);
    });

    generate_castling(board, moves, us);
    return moves;
}


std::vector<Move> MoveGenerator::legal(Board& board) {
    const Color us = board.side_to_move();
    const Color them = opposite(us);
    const auto pseudo = pseudo_legal(board);
    std::vector<Move> result;
    result.reserve(pseudo.size());

    const bool started_in_check = board.in_check(us);

    for (const Move move : pseudo) {
        // Castling has an extra condition that cannot be detected solely by
        // testing the final board: the king may not castle out of or through check.
        if (move.is_castle()) {
            if (started_in_check) continue;
            const int transit = move.flag() == MoveFlag::KingCastle
                ? move.from() + 1
                : move.from() - 1;
            if (board.is_square_attacked(transit, them)) continue;
        }

        const UndoState undo = board.make_move(move);
        const bool leaves_king_in_check = board.in_check(us);
        board.unmake_move(move, undo);
        if (!leaves_king_in_check) result.push_back(move);
    }
    return result;
}

std::uint64_t perft(Board& board, int depth) {
    if (depth < 0) return 0;
    if (depth == 0) return 1;

    const auto moves = MoveGenerator::legal(board);
    if (depth == 1) return static_cast<std::uint64_t>(moves.size());

    std::uint64_t nodes = 0;
    for (const Move move : moves) {
        const UndoState undo = board.make_move(move);
        nodes += perft(board, depth - 1);
        board.unmake_move(move, undo);
    }
    return nodes;
}

} // namespace neurochess::core
