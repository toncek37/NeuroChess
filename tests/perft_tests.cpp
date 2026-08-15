#include "neurochess/core/board.h"
#include "neurochess/core/move_generator.h"

#include <cstdlib>
#include <iostream>
#include <string>

using namespace neurochess::core;

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) {
        std::cerr << "FAILED: " << message << '\n';
        std::exit(1);
    }
}

void expect_perft(const std::string& fen, int depth, std::uint64_t expected, const char* name) {
    Board board = Board::from_fen(fen);
    const std::string before = board.to_fen();
    const std::uint64_t actual = perft(board, depth);
    require(actual == expected,
            std::string(name) + " depth " + std::to_string(depth) +
            ": expected " + std::to_string(expected) + ", got " + std::to_string(actual));
    require(board.to_fen() == before, std::string(name) + ": perft must restore board exactly");
}

} // namespace

int main() {
    // Canonical ChessProgramming perft positions. Together these exercise
    // castling, checks/pins, en passant, promotions and unusual king mobility.
    expect_perft(std::string(Board::StartFen), 1, 20, "start");
    expect_perft(std::string(Board::StartFen), 2, 400, "start");
    expect_perft(std::string(Board::StartFen), 3, 8902, "start");
    expect_perft(std::string(Board::StartFen), 4, 197281, "start");

    const std::string kiwipete =
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1";
    expect_perft(kiwipete, 1, 48, "kiwipete");
    expect_perft(kiwipete, 2, 2039, "kiwipete");
    expect_perft(kiwipete, 3, 97862, "kiwipete");

    const std::string position3 =
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1";
    expect_perft(position3, 1, 14, "position3");
    expect_perft(position3, 2, 191, "position3");
    expect_perft(position3, 3, 2812, "position3");
    expect_perft(position3, 4, 43238, "position3");

    const std::string position4 =
        "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1";
    expect_perft(position4, 1, 6, "position4");
    expect_perft(position4, 2, 264, "position4");
    expect_perft(position4, 3, 9467, "position4");

    const std::string position5 =
        "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8";
    expect_perft(position5, 1, 44, "position5");
    expect_perft(position5, 2, 1486, "position5");
    expect_perft(position5, 3, 62379, "position5");

    const std::string position6 =
        "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10";
    expect_perft(position6, 1, 46, "position6");
    expect_perft(position6, 2, 2079, "position6");
    expect_perft(position6, 3, 89890, "position6");

    std::cout << "legal move / perft tests passed\n";
    return 0;
}
