#include "neurochess/uci/uci_loop.h"

#include <cassert>
#include <sstream>
#include <string>

namespace {

std::string run_uci(const std::string& commands) {
    std::istringstream input(commands);
    std::ostringstream output;
    const int code = neurochess::uci::run(input, output);
    assert(code == 0);
    return output.str();
}

void test_identification_and_options() {
    const std::string out = run_uci("uci\nisready\nquit\n");
    assert(out.find("id name NeuroChess 0.9.0") != std::string::npos);
    assert(out.find("option name Hash type spin") != std::string::npos);
    assert(out.find("option name Null Move Pruning type check") != std::string::npos);
    assert(out.find("uciok") != std::string::npos);
    assert(out.find("readyok") != std::string::npos);
}

void test_startpos_moves_and_depth_search() {
    const std::string out = run_uci(
        "position startpos moves e2e4 e7e5 g1f3\n"
        "go depth 2\n");
    assert(out.find("info depth 2") != std::string::npos);
    assert(out.find(" score ") != std::string::npos);
    assert(out.find(" nodes ") != std::string::npos);
    assert(out.find("bestmove ") != std::string::npos);
    assert(out.find("bestmove 0000") == std::string::npos);
}

void test_fen_terminal_position() {
    // Black is checkmated: no legal best move must be reported as UCI 0000.
    const std::string out = run_uci(
        "position fen 7k/6Q1/6K1/8/8/8/8/8 b - - 0 1\n"
        "go depth 2\n");
    assert(out.find("score mate 0") != std::string::npos);
    assert(out.find("bestmove 0000") != std::string::npos);
}

void test_setoption_and_node_limit() {
    const std::string out = run_uci(
        "setoption name Hash value 32\n"
        "setoption name Null Move Pruning value false\n"
        "setoption name Late Move Reductions value false\n"
        "position startpos\n"
        "go nodes 200\n");
    assert(out.find("bestmove ") != std::string::npos);
}

void test_invalid_move_is_rejected() {
    const std::string out = run_uci("position startpos moves e2e5\nquit\n");
    assert(out.find("illegal move in position command: e2e5") != std::string::npos);
}

} // namespace

int main() {
    test_identification_and_options();
    test_startpos_moves_and_depth_search();
    test_fen_terminal_position();
    test_setoption_and_node_limit();
    test_invalid_move_is_rejected();
    return 0;
}
