#pragma once

#include "neurochess/core/board.h"
#include "neurochess/core/move.h"

#include <cstdint>
#include <vector>

namespace neurochess::core {

class MoveGenerator {
public:
    // Pseudo-legal means movement/occupancy rules are respected, while king
    // safety is not. Castling rights and empty transit squares are checked here;
    // attacked transit squares are checked by legal().
    [[nodiscard]] static std::vector<Move> pseudo_legal(const Board& board);

    // Generates only moves legal under king-safety rules, including the special
    // rule that castling may not start in, pass through, or finish in check.
    [[nodiscard]] static std::vector<Move> legal(Board& board);
};

[[nodiscard]] std::uint64_t perft(Board& board, int depth);

} // namespace neurochess::core
