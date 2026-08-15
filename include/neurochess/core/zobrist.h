#pragma once

#include "neurochess/core/board.h"

#include <array>
#include <cstdint>

namespace neurochess::core {

class Zobrist {
public:
    using Key = std::uint64_t;

    [[nodiscard]] static Key piece(Piece piece, int square) noexcept;
    [[nodiscard]] static Key side_to_move() noexcept;
    [[nodiscard]] static Key castling(std::uint8_t rights) noexcept;
    [[nodiscard]] static Key en_passant(int square) noexcept;
    [[nodiscard]] static Key compute(const Board& board) noexcept;

private:
    struct Keys {
        std::array<std::array<Key, 64>, 12> pieces{};
        Key side{};
        std::array<Key, 16> castling{};
        std::array<Key, 64> en_passant{};
    };

    [[nodiscard]] static const Keys& keys() noexcept;
};

} // namespace neurochess::core
