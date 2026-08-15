#include "neurochess/core/board.h"
#include "neurochess/search/searcher.h"

#include <cassert>
#include <iostream>
#include <string>

using neurochess::core::Board;
using neurochess::search::SearchConfig;
using neurochess::search::SearchLimits;
using neurochess::search::Searcher;

namespace {

SearchConfig baseline_config() {
    SearchConfig c;
    c.killer_moves = false;
    c.history_heuristic = false;
    c.null_move_pruning = false;
    c.late_move_reductions = false;
    c.aspiration_windows = false;
    c.futility_pruning = false;
    c.razoring = false;
    return c;
}

void test_null_move_roundtrip() {
    Board board = Board::from_fen("r3k2r/ppp2ppp/2n5/3qp3/8/2N2N2/PPP2PPP/R2Q1RK1 w kq - 4 12");
    const std::string before = board.to_fen();
    const auto key = board.zobrist_key();
    const auto side = board.side_to_move();
    const auto undo = board.make_null_move();
    assert(board.side_to_move() != side);
    assert(board.zobrist_key() != key);
    board.unmake_null_move(undo);
    assert(board.to_fen() == before);
    assert(board.zobrist_key() == key);
}

void test_baseline_and_optimized_reach_requested_depth() {
    Board baseline_board;
    Board optimized_board;
    const std::string before = baseline_board.to_fen();
    SearchLimits limits;
    limits.max_depth = 4;

    Searcher baseline(8, {}, baseline_config());
    const auto base = baseline.search(baseline_board, limits);
    assert(base.completed);
    assert(base.stats.depth == 4);
    assert(base.best_move.raw() != 0);
    assert(baseline_board.to_fen() == before);

    Searcher optimized(8);
    const auto fast = optimized.search(optimized_board, limits);
    assert(fast.completed);
    assert(fast.stats.depth == 4);
    assert(fast.best_move.raw() != 0);
    assert(optimized_board.to_fen() == before);
    assert(fast.stats.lmr_reductions > 0);
}

void test_every_optimization_can_be_enabled_independently() {
    const std::string fen = "r3k2r/ppp2ppp/2n1bn2/3qp3/3P4/2N1PN2/PPP2PPP/R2Q1RK1 w kq - 4 12";
    SearchLimits limits;
    limits.max_depth = 4;

    for (int feature = 0; feature < 7; ++feature) {
        SearchConfig c = baseline_config();
        switch (feature) {
            case 0: c.killer_moves = true; break;
            case 1: c.history_heuristic = true; break;
            case 2: c.null_move_pruning = true; break;
            case 3: c.late_move_reductions = true; break;
            case 4: c.aspiration_windows = true; break;
            case 5: c.futility_pruning = true; break;
            case 6: c.razoring = true; break;
        }
        Board board = Board::from_fen(fen);
        const std::string before = board.to_fen();
        Searcher searcher(4, {}, c);
        const auto result = searcher.search(board, limits);
        assert(result.completed);
        assert(result.stats.depth == 4);
        assert(result.best_move.raw() != 0);
        assert(board.to_fen() == before);
    }
}

void test_null_move_is_used_in_middlegame() {
    Board board = Board::from_fen("r2q1rk1/ppp2ppp/2n1bn2/3pp3/3P4/2P1PN2/PP3PPP/R1BQ1RK1 w - - 2 10");
    SearchConfig c = baseline_config();
    c.null_move_pruning = true;
    SearchLimits limits;
    limits.max_depth = 5;
    Searcher searcher(8, {}, c);
    const auto result = searcher.search(board, limits);
    assert(result.completed);
    assert(result.stats.null_move_prunes > 0);
}

} // namespace

int main() {
    test_null_move_roundtrip();
    test_baseline_and_optimized_reach_requested_depth();
    test_every_optimization_can_be_enabled_independently();
    test_null_move_is_used_in_middlegame();
    std::cout << "search optimization tests passed\n";
    return 0;
}
