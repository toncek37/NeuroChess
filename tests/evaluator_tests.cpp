#include "neurochess/core/board.h"
#include "neurochess/search/evaluator.h"

#include <cassert>
#include <iostream>

using neurochess::core::Board;
using neurochess::search::ClassicalEvaluator;
using neurochess::search::EvaluationConfig;

int main() {
    ClassicalEvaluator eval;

    // Symmetry: the initial position is deliberately evaluated as equal.
    Board start;
    assert(eval.evaluate(start) == 0);
    assert(eval.breakdown(start).total_white_pov() == 0);

    // A free queen must dominate all positional terms.
    Board white_queen = Board::from_fen("4k3/8/8/8/8/8/4Q3/4K3 w - - 0 1");
    Board black_queen = Board::from_fen("4k3/4q3/8/8/8/8/8/4K3 w - - 0 1");
    assert(eval.evaluate(white_queen) > 700);
    assert(eval.evaluate(black_queen) < -700);

    // Negamax convention: same board state, opposite side to move flips score.
    Board white_to_move = Board::from_fen("4k3/8/8/8/8/8/4Q3/4K3 w - - 0 1");
    Board black_to_move = Board::from_fen("4k3/8/8/8/8/8/4Q3/4K3 b - - 0 1");
    assert(eval.evaluate(white_to_move) == -eval.evaluate(black_to_move));

    // Bishop-pair term can be isolated and switched off.
    EvaluationConfig only_pair{};
    only_pair.material = false;
    only_pair.piece_square = false;
    only_pair.mobility = false;
    only_pair.pawn_structure = false;
    only_pair.king_safety = false;
    only_pair.passed_pawns = false;
    ClassicalEvaluator pair_eval(only_pair);
    Board bishops = Board::from_fen("4k3/8/8/8/8/8/8/2B1KB2 w - - 0 1");
    assert(pair_eval.breakdown(bishops).bishop_pair == 30);

    only_pair.bishop_pair = false;
    ClassicalEvaluator no_terms(only_pair);
    assert(no_terms.evaluate(bishops) == 0);

    // Passed-pawn term should reward advancement and be independently visible.
    EvaluationConfig only_passed{};
    only_passed.material = false;
    only_passed.piece_square = false;
    only_passed.mobility = false;
    only_passed.pawn_structure = false;
    only_passed.king_safety = false;
    only_passed.bishop_pair = false;
    ClassicalEvaluator passed_eval(only_passed);
    Board passed_low = Board::from_fen("4k3/8/8/8/8/P7/8/4K3 w - - 0 1");
    Board passed_high = Board::from_fen("4k3/8/P7/8/8/8/8/4K3 w - - 0 1");
    assert(passed_eval.evaluate(passed_high) > passed_eval.evaluate(passed_low));

    // Doubled + isolated pawns are worse than connected pawns when we isolate
    // the pawn-structure component.
    EvaluationConfig only_pawns{};
    only_pawns.material = false;
    only_pawns.piece_square = false;
    only_pawns.mobility = false;
    only_pawns.king_safety = false;
    only_pawns.bishop_pair = false;
    only_pawns.passed_pawns = false;
    ClassicalEvaluator pawn_eval(only_pawns);
    Board healthy = Board::from_fen("4k3/8/8/8/8/8/2PP4/4K3 w - - 0 1");
    Board doubled = Board::from_fen("4k3/8/8/8/8/2P5/2P5/4K3 w - - 0 1");
    assert(pawn_eval.evaluate(healthy) > pawn_eval.evaluate(doubled));

    std::cout << "Classical evaluator tests passed\n";
    return 0;
}
