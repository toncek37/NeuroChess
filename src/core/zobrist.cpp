#include "neurochess/core/zobrist.h"

#include <bit>

namespace neurochess::core {
namespace {

std::uint64_t splitmix64(std::uint64_t& state) noexcept {
    std::uint64_t z = (state += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

} // namespace

const Zobrist::Keys& Zobrist::keys() noexcept {
    static const Keys generated = [] {
        Keys result;
        // Fixed seed: hashes are deterministic across runs, platforms and builds.
        std::uint64_t state = 0x4E6575726F436865ULL; // "NeuroChe"
        for (auto& piece_keys : result.pieces) {
            for (auto& key : piece_keys) key = splitmix64(state);
        }
        result.side = splitmix64(state);
        for (auto& key : result.castling) key = splitmix64(state);
        for (auto& key : result.en_passant) key = splitmix64(state);
        return result;
    }();
    return generated;
}

Zobrist::Key Zobrist::piece(Piece piece_value, int square) noexcept {
    if (piece_value == Piece::None || square < 0 || square >= 64) return 0;
    return keys().pieces[static_cast<std::size_t>(piece_index(piece_value))][static_cast<std::size_t>(square)];
}

Zobrist::Key Zobrist::side_to_move() noexcept {
    return keys().side;
}

Zobrist::Key Zobrist::castling(std::uint8_t rights) noexcept {
    return keys().castling[static_cast<std::size_t>(rights & 0x0Fu)];
}

Zobrist::Key Zobrist::en_passant(int square) noexcept {
    if (square < 0 || square >= 64) return 0;
    return keys().en_passant[static_cast<std::size_t>(square)];
}

Zobrist::Key Zobrist::compute(const Board& board) noexcept {
    Key key = 0;
    for (int piece_idx = 0; piece_idx < 12; ++piece_idx) {
        Bitboard bb = board.pieces(static_cast<Piece>(piece_idx));
        while (bb) {
            const int square = static_cast<int>(std::countr_zero(bb));
            key ^= piece(static_cast<Piece>(piece_idx), square);
            bb &= bb - 1;
        }
    }

    if (board.side_to_move() == Color::Black) key ^= side_to_move();
    key ^= castling(board.castling_rights());
    if (board.en_passant_square().has_value()) key ^= en_passant(*board.en_passant_square());
    return key;
}

} // namespace neurochess::core
