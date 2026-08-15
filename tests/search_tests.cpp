#include "neurochess/core/board.h"
#include "neurochess/core/move_generator.h"
#include "neurochess/search/searcher.h"

#include <algorithm>
#include <cassert>
#include <chrono>
#include <iostream>
#include <string>

using neurochess::core::Board;
using neurochess::search::Searcher;
using neurochess::search::SearchLimits;

namespace {

void test_start_position_searches_and_preserves_board() {
    Board board;
    const std::string before = board.to_fen();
    Searcher searcher(4);
    SearchLimits limits;
    limits.max_depth = 3;
    const auto result = searcher.search(board, limits);
    assert(result.completed);
    assert(result.best_move.raw() != 0);
    assert(result.stats.depth == 3);
    assert(result.stats.nodes > 0);
    assert(!result.principal_variation.empty());
    assert(board.to_fen() == before);
}

void test_mate_in_one() {
    // White: Kg6 Qg7, Black: Kh8. Qh7# is an immediate mate.
    Board board = Board::from_fen("7k/6Q1/6K1/8/8/8/8/8 w - - 0 1");
    Searcher searcher(4);
    SearchLimits limits;
    limits.max_depth = 3;
    const auto result = searcher.search(board, limits);
    assert(result.completed);
    assert(result.score >= Searcher::MateThreshold);

    const auto move = result.best_move.uci();
    // There may be multiple mates in one in this constructed position; verify
    // the selected move actually leaves Black checkmated rather than naming one.
    const auto undo = board.make_move(result.best_move);
    const auto replies = neurochess::core::MoveGenerator::legal(board);
    assert(replies.empty());
    assert(board.in_check(board.side_to_move()));
    board.unmake_move(result.best_move, undo);
    (void)move;
}

void test_stalemate_and_checkmate_root() {
    Searcher searcher(1);
    SearchLimits limits;
    limits.max_depth = 2;

    Board stalemate = Board::from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1");
    auto result = searcher.search(stalemate, limits);
    assert(result.completed);
    assert(result.score == 0);

    Board mate = Board::from_fen("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1");
    result = searcher.search(mate, limits);
    assert(result.completed);
    assert(result.score <= -Searcher::MateThreshold);
}

void test_fifty_move_rule() {
    Board board = Board::from_fen("8/8/8/8/8/4k3/8/R3K3 w Q - 100 60");
    Searcher searcher(1);
    SearchLimits limits;
    limits.max_depth = 2;
    const auto result = searcher.search(board, limits);
    assert(result.completed);
    assert(result.score == 0);
}

void test_threefold_history() {
    Board board;
    Searcher searcher(1);
    // Two prior occurrences plus the root occurrence are a claimable threefold.
    searcher.set_position_history({board.zobrist_key(), board.zobrist_key()});
    SearchLimits limits;
    limits.max_depth = 2;
    const auto result = searcher.search(board, limits);
    assert(result.completed);
    assert(result.score == 0);
    assert(result.stats.depth == 0);
    assert(result.best_move.raw() != 0);
}

void test_quiescence_sees_hanging_queen() {
    Board board = Board::from_fen("4k3/8/8/8/8/8/4q3/4R1K1 w - - 0 1");
    Searcher searcher(1);
    SearchLimits limits;
    limits.max_depth = 1;
    const auto result = searcher.search(board, limits);
    assert(result.completed);
    assert(result.best_move.uci() == "e1e2");
    assert(result.stats.qnodes > 0);
}

void test_node_limit_interrupts_safely() {
    Board board;
    const auto before = board.to_fen();
    Searcher searcher(1);
    SearchLimits limits;
    limits.max_nodes = 200;
    const auto result = searcher.search(board, limits);
    assert(result.stats.nodes <= 205); // stop checks happen at node entry
    assert(board.to_fen() == before);
}

void test_time_limit_interrupts_safely() {
    Board board;
    const auto legal = neurochess::core::MoveGenerator::legal(board);
    Searcher searcher(1);
    SearchLimits limits;
    limits.max_time = std::chrono::milliseconds(1);
    const auto result = searcher.search(board, limits);
    assert(result.stats.elapsed < std::chrono::milliseconds(500));
    assert(board.to_fen() == Board::StartFen);
    // Even if depth 1 cannot finish before the deadline, a playable position
    // must never produce the null/default UCI move 0000.
    assert(result.best_move.raw() != 0);
    assert(std::find(legal.begin(), legal.end(), result.best_move) != legal.end());
}

} // namespace

int main() {
    test_start_position_searches_and_preserves_board();
    test_mate_in_one();
    test_stalemate_and_checkmate_root();
    test_fifty_move_rule();
    test_threefold_history();
    test_quiescence_sees_hanging_queen();
    test_node_limit_interrupts_safely();
    test_time_limit_interrupts_safely();
    std::cout << "search tests passed\n";
    return 0;
}
