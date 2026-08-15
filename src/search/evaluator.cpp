#include "neurochess/search/evaluator.h"

#include <algorithm>
#include <array>
#include <bit>
#include <cstdlib>

namespace neurochess::search {
namespace {

using namespace neurochess::core;

constexpr std::array<int, 6> PieceValue = {100, 320, 330, 500, 900, 0};

int popcount(Bitboard b) noexcept { return static_cast<int>(std::popcount(b)); }

int relative_rank(Color color, int rank) noexcept {
    return color == Color::White ? rank : 7 - rank;
}

int center_bonus(int file, int rank) noexcept {
    // Integer centralisation score: maximum near d4/e4/d5/e5.
    const int df = std::min(std::abs(file - 3), std::abs(file - 4));
    const int dr = std::min(std::abs(rank - 3), std::abs(rank - 4));
    return 6 - 2 * (df + dr);
}

int piece_square_value(PieceType type, Color color, int square) noexcept {
    const int file = square % 8;
    const int rank = square / 8;
    const int rr = relative_rank(color, rank);
    const int center = center_bonus(file, rank);

    switch (type) {
        case PieceType::Pawn:
            return rr * 7 + center / 2;
        case PieceType::Knight:
            return center * 5 - (rr == 0 ? 8 : 0);
        case PieceType::Bishop:
            return center * 3 + rr;
        case PieceType::Rook:
            return rr * 2 + (rr == 6 ? 8 : 0);
        case PieceType::Queen:
            return center - (rr > 3 ? 3 : 0);
        case PieceType::King: {
            // Baseline middlegame preference: king near a castled edge and
            // away from the centre. Endgame interpolation comes later.
            const int edge = std::min(file, 7 - file);
            return -center * 3 - edge * 2;
        }
        case PieceType::None:
            return 0;
    }
    return 0;
}

int slider_mobility(const Board& board, int square, Color color,
                    const int (*dirs)[2], int dir_count) noexcept {
    const int file = square % 8;
    const int rank = square / 8;
    int count = 0;
    for (int i = 0; i < dir_count; ++i) {
        int f = file + dirs[i][0];
        int r = rank + dirs[i][1];
        while (f >= 0 && f < 8 && r >= 0 && r < 8) {
            const Piece target = board.piece_at(square_index(f, r));
            if (target == Piece::None) {
                ++count;
            } else {
                if (piece_color(target) != color) ++count;
                break;
            }
            f += dirs[i][0];
            r += dirs[i][1];
        }
    }
    return count;
}

int mobility_for_piece(const Board& board, PieceType type, Color color, int square) noexcept {
    constexpr int knight[8][2] = {{1,2},{2,1},{2,-1},{1,-2},{-1,-2},{-2,-1},{-2,1},{-1,2}};
    constexpr int bishop[4][2] = {{1,1},{1,-1},{-1,1},{-1,-1}};
    constexpr int rook[4][2] = {{1,0},{-1,0},{0,1},{0,-1}};
    constexpr int queen[8][2] = {{1,1},{1,-1},{-1,1},{-1,-1},{1,0},{-1,0},{0,1},{0,-1}};
    constexpr int king[8][2] = {{1,0},{1,1},{0,1},{-1,1},{-1,0},{-1,-1},{0,-1},{1,-1}};

    const int file = square % 8;
    const int rank = square / 8;
    auto jump_count = [&](const int (*offsets)[2], int count) {
        int result = 0;
        for (int i = 0; i < count; ++i) {
            const int f = file + offsets[i][0];
            const int r = rank + offsets[i][1];
            if (f < 0 || f >= 8 || r < 0 || r >= 8) continue;
            const Piece target = board.piece_at(square_index(f, r));
            if (target == Piece::None || piece_color(target) != color) ++result;
        }
        return result;
    };

    switch (type) {
        case PieceType::Knight: return jump_count(knight, 8);
        case PieceType::Bishop: return slider_mobility(board, square, color, bishop, 4);
        case PieceType::Rook:   return slider_mobility(board, square, color, rook, 4);
        case PieceType::Queen:  return slider_mobility(board, square, color, queen, 8);
        case PieceType::King:   return jump_count(king, 8);
        default: return 0;
    }
}

int signed_for(Color color, int value) noexcept {
    return color == Color::White ? value : -value;
}

int pawn_structure_for(const Board& board, Color color) noexcept {
    const Bitboard pawns = board.pieces(make_piece(color, PieceType::Pawn));
    int score = 0;
    std::array<int, 8> count{};
    Bitboard tmp = pawns;
    while (tmp) {
        const int sq = static_cast<int>(std::countr_zero(tmp));
        tmp &= tmp - 1;
        ++count[sq % 8];
    }

    for (int file = 0; file < 8; ++file) {
        if (count[file] > 1) score -= 14 * (count[file] - 1); // doubled
        if (count[file] == 0) continue;
        const bool left = file > 0 && count[file - 1] > 0;
        const bool right = file < 7 && count[file + 1] > 0;
        if (!left && !right) score -= 12 * count[file]; // isolated
    }
    return score;
}

int passed_pawns_for(const Board& board, Color color) noexcept {
    const Bitboard ours = board.pieces(make_piece(color, PieceType::Pawn));
    const Bitboard theirs = board.pieces(make_piece(opposite(color), PieceType::Pawn));
    int score = 0;
    Bitboard tmp = ours;
    while (tmp) {
        const int sq = static_cast<int>(std::countr_zero(tmp));
        tmp &= tmp - 1;
        const int file = sq % 8;
        const int rank = sq / 8;
        bool blocked = false;
        for (int ef = std::max(0, file - 1); ef <= std::min(7, file + 1) && !blocked; ++ef) {
            if (color == Color::White) {
                for (int r = rank + 1; r < 8; ++r) {
                    if (theirs & square_bit(square_index(ef, r))) { blocked = true; break; }
                }
            } else {
                for (int r = rank - 1; r >= 0; --r) {
                    if (theirs & square_bit(square_index(ef, r))) { blocked = true; break; }
                }
            }
        }
        if (!blocked) {
            const int rr = relative_rank(color, rank);
            score += 12 + rr * rr * 4;
        }
    }
    return score;
}

int king_safety_for(const Board& board, Color color) noexcept {
    const int king = board.king_square(color);
    if (king < 0) return 0;
    const int file = king % 8;
    const int rank = king / 8;
    const int forward = color == Color::White ? 1 : -1;
    int score = 0;

    // Pawn shield immediately in front of the king.
    const Piece pawn = make_piece(color, PieceType::Pawn);
    const int shield_rank = rank + forward;
    if (shield_rank >= 0 && shield_rank < 8) {
        for (int f = std::max(0, file - 1); f <= std::min(7, file + 1); ++f) {
            if (board.piece_at(square_index(f, shield_rank)) == pawn) score += 10;
            else score -= 5;
        }
    }

    // Penalise enemy control in the king's local 3x3 zone.
    int attacked = 0;
    for (int df = -1; df <= 1; ++df) {
        for (int dr = -1; dr <= 1; ++dr) {
            const int f = file + df;
            const int r = rank + dr;
            if (f >= 0 && f < 8 && r >= 0 && r < 8
                && board.is_square_attacked(square_index(f, r), opposite(color))) {
                ++attacked;
            }
        }
    }
    score -= attacked * 8;
    return score;
}

} // namespace

EvaluationBreakdown ClassicalEvaluator::breakdown(const core::Board& board) const noexcept {
    EvaluationBreakdown out;

    for (Color color : {Color::White, Color::Black}) {
        for (int t = 0; t < 6; ++t) {
            const PieceType type = static_cast<PieceType>(t);
            Bitboard bb = board.pieces(make_piece(color, type));
            if (config_.material) {
                out.material += signed_for(color, popcount(bb) * PieceValue[t]);
            }
            while (bb) {
                const int sq = static_cast<int>(std::countr_zero(bb));
                bb &= bb - 1;
                if (config_.piece_square) {
                    out.piece_square += signed_for(color, piece_square_value(type, color, sq));
                }
                if (config_.mobility) {
                    constexpr std::array<int, 6> MobilityWeight = {0, 4, 4, 2, 1, 0};
                    out.mobility += signed_for(color, mobility_for_piece(board, type, color, sq) * MobilityWeight[t]);
                }
            }
        }

        if (config_.pawn_structure) {
            out.pawn_structure += signed_for(color, pawn_structure_for(board, color));
        }
        if (config_.king_safety) {
            out.king_safety += signed_for(color, king_safety_for(board, color));
        }
        if (config_.bishop_pair
            && popcount(board.pieces(make_piece(color, PieceType::Bishop))) >= 2) {
            out.bishop_pair += signed_for(color, 30);
        }
        if (config_.passed_pawns) {
            out.passed_pawns += signed_for(color, passed_pawns_for(board, color));
        }
    }

    return out;
}

int ClassicalEvaluator::evaluate(const core::Board& board) const noexcept {
    const int white_score = breakdown(board).total_white_pov();
    return board.side_to_move() == core::Color::White ? white_score : -white_score;
}

} // namespace neurochess::search
