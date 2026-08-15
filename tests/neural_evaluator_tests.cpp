#include "neurochess/nn/neural_evaluator.h"
#include "neurochess/core/board.h"
#include "neurochess/core/move.h"

#include <cassert>
#include <cmath>
#include <iostream>

using namespace neurochess;

int main() {
    core::Board board;
    const auto encoded = nn::encode_board(board);
    static_assert(encoded.size() == 26 * 8 * 8);

    // White pawn e2 = square 12 -> channel 0, rank 1, file 4.
    assert(encoded[0 * 64 + 12] == 1.0f);
    // Black king e8 = square 60 -> channel 11.
    assert(encoded[11 * 64 + 60] == 1.0f);
    // White to move and all four castling rights in the initial position.
    assert(encoded[12 * 64] == 1.0f);
    assert(encoded[13 * 64] == 1.0f);
    assert(encoded[14 * 64] == 1.0f);
    assert(encoded[15 * 64] == 1.0f);
    assert(encoded[16 * 64] == 1.0f);

    const core::Move e2e4{12, 28, core::MoveFlag::DoublePawnPush};
    assert(nn::move_to_policy_index(e2e4) == 12 * 64 + 28);

    const core::Move promo{48, 56, core::MoveFlag::Promotion, core::PieceType::Queen};
    assert(nn::move_to_policy_index(promo) == 4096 + 48 * 64 + 56);

    // Promotion buckets must exactly match Python: None,Q,R,B,N = 0..4.
    const core::Move promo_r{48, 56, core::MoveFlag::Promotion, core::PieceType::Rook};
    const core::Move promo_b{48, 56, core::MoveFlag::Promotion, core::PieceType::Bishop};
    const core::Move promo_n{48, 56, core::MoveFlag::Promotion, core::PieceType::Knight};
    assert(nn::move_to_policy_index(promo_r) == 2 * 4096 + 48 * 64 + 56);
    assert(nn::move_to_policy_index(promo_b) == 3 * 4096 + 48 * 64 + 56);
    assert(nn::move_to_policy_index(promo_n) == 4 * 4096 + 48 * 64 + 56);

    // Castling and en-passant use the ordinary non-promotion bucket; flags must
    // not alter the neural policy index.
    const core::Move castle{4, 6, core::MoveFlag::KingCastle};
    const core::Move ep{36, 43, core::MoveFlag::EnPassant};
    assert(nn::move_to_policy_index(castle) == 4 * 64 + 6);
    assert(nn::move_to_policy_index(ep) == 36 * 64 + 43);

    nn::NeuralOutput out;
    out.policy_logits.resize(5 * 64 * 64, -1.0f);
    out.policy_logits[static_cast<std::size_t>(nn::move_to_policy_index(e2e4))] = 3.5f;
    assert(std::fabs(nn::policy_logit_for_move(out, e2e4) - 3.5f) < 1e-6f);

    out.wdl_logits = {4.0f, 0.0f, -4.0f};
    assert(nn::wdl_to_centipawns(out) > 0);
    out.wdl_logits = {-4.0f, 0.0f, 4.0f};
    assert(nn::wdl_to_centipawns(out) < 0);

    std::cout << "neural evaluator tests passed\n";
    return 0;
}
