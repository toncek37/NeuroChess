#pragma once

#include "neurochess/core/board.h"

namespace neurochess::search {

struct EvaluationConfig {
    bool material = true;
    bool piece_square = true;
    bool mobility = true;
    bool pawn_structure = true;
    bool king_safety = true;
    bool bishop_pair = true;
    bool passed_pawns = true;
};

struct EvaluationBreakdown {
    int material = 0;
    int piece_square = 0;
    int mobility = 0;
    int pawn_structure = 0;
    int king_safety = 0;
    int bishop_pair = 0;
    int passed_pawns = 0;

    [[nodiscard]] int total_white_pov() const noexcept {
        return material + piece_square + mobility + pawn_structure
             + king_safety + bishop_pair + passed_pawns;
    }
};

class ClassicalEvaluator {
public:
    explicit ClassicalEvaluator(EvaluationConfig config = {}) noexcept : config_(config) {}

    // Positive means good for the side to move; intended directly for negamax.
    [[nodiscard]] int evaluate(const core::Board& board) const noexcept;

    // Component scores are always from White's point of view. This is useful
    // for diagnostics and later ablation/benchmark tooling.
    [[nodiscard]] EvaluationBreakdown breakdown(const core::Board& board) const noexcept;

    [[nodiscard]] const EvaluationConfig& config() const noexcept { return config_; }

private:
    EvaluationConfig config_;
};

} // namespace neurochess::search
