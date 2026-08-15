#include "neurochess/core/board.h"
#include "neurochess/search/searcher.h"

#include <iomanip>
#include <iostream>
#include <string_view>
#include <vector>

using neurochess::core::Board;
using neurochess::search::SearchConfig;
using neurochess::search::SearchLimits;
using neurochess::search::Searcher;

namespace {
struct Case { std::string_view name; std::string_view fen; };

SearchConfig baseline() {
    SearchConfig c;
    c.killer_moves = c.history_heuristic = c.null_move_pruning = false;
    c.late_move_reductions = c.aspiration_windows = false;
    c.futility_pruning = c.razoring = false;
    return c;
}

void run(std::string_view label, const SearchConfig& config, const std::vector<Case>& cases) {
    std::uint64_t nodes = 0;
    std::uint64_t ms = 0;
    std::cout << "\n" << label << "\n";
    for (const auto& c : cases) {
        Board board = Board::from_fen(c.fen);
        Searcher searcher(16, {}, config);
        SearchLimits limits; limits.max_depth = 5;
        const auto r = searcher.search(board, limits);
        nodes += r.stats.nodes;
        ms += static_cast<std::uint64_t>(r.stats.elapsed.count());
        std::cout << "  " << std::setw(12) << c.name
                  << " best=" << r.best_move.uci()
                  << " score=" << r.score
                  << " nodes=" << r.stats.nodes
                  << " ms=" << r.stats.elapsed.count()
                  << " null=" << r.stats.null_move_prunes
                  << " lmr=" << r.stats.lmr_reductions << "\n";
    }
    std::cout << "  TOTAL nodes=" << nodes << " ms=" << ms << "\n";
}
}

int main() {
    const std::vector<Case> cases = {
        {"startpos", Board::StartFen},
        {"middlegame", "r3k2r/ppp2ppp/2n1bn2/3qp3/3P4/2N1PN2/PPP2PPP/R2Q1RK1 w kq - 4 12"},
        {"tactical", "r1bq1rk1/ppp2ppp/2n5/3np3/2B5/2N2N2/PPPP1PPP/R1BQ1RK1 w - - 4 8"}
    };
    run("baseline", baseline(), cases);
    run("optimized", SearchConfig{}, cases);
    std::cout << "\nNote: this pre-match benchmark compares fixed-depth node/time cost and move/score stability.\n"
                 "Actual playing-strength/Elo measurement is added in the match-runner phase.\n";
}
