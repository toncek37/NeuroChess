#include "neurochess/core/board.h"
#include "neurochess/core/move_generator.h"
#include "neurochess/core/zobrist.h"
#include "neurochess/search/transposition_table.h"

#include <cassert>
#include <iostream>
#include <string>

using namespace neurochess::core;
using namespace neurochess::search;

namespace {

Move find_move(Board& board, const std::string& uci) {
    for (const Move move : MoveGenerator::legal(board)) {
        if (move.uci() == uci) return move;
    }
    std::cerr << "Move not found: " << uci << '\n';
    std::abort();
}

void verify_incremental(Board& board, const std::string& uci) {
    const std::string before_fen = board.to_fen();
    const auto before_key = board.zobrist_key();
    assert(before_key == Zobrist::compute(board));

    const Move move = find_move(board, uci);
    const UndoState undo = board.make_move(move);
    assert(board.zobrist_key() == Zobrist::compute(board));
    assert(board.zobrist_key() != before_key);

    board.unmake_move(move, undo);
    assert(board.to_fen() == before_fen);
    assert(board.zobrist_key() == before_key);
    assert(board.zobrist_key() == Zobrist::compute(board));
}

} // namespace

int main() {
    Board start;
    assert(start.zobrist_key() == Zobrist::compute(start));

    // State components required by Prompt 5 must influence the key.
    const Board black_to_move = Board::from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1");
    assert(start.zobrist_key() != black_to_move.zobrist_key());

    const Board no_castling = Board::from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1");
    assert(start.zobrist_key() != no_castling.zobrist_key());

    const Board ep = Board::from_fen("8/8/8/3pP3/8/8/8/4K2k w - d6 0 1");
    const Board no_ep = Board::from_fen("8/8/8/3pP3/8/8/8/4K2k w - - 0 1");
    assert(ep.zobrist_key() != no_ep.zobrist_key());

    // Move clocks deliberately do not alter a position key.
    const Board clocks = Board::from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 17 42");
    assert(start.zobrist_key() == clocks.zobrist_key());

    // Exercise the incremental path through ordinary moves, captures,
    // castling, en-passant and promotions.
    verify_incremental(start, "e2e4");

    Board capture = Board::from_fen("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1");
    verify_incremental(capture, "e4d5");

    Board castle = Board::from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1");
    verify_incremental(castle, "e1g1");
    verify_incremental(castle, "e1c1");

    Board en_passant = Board::from_fen("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1");
    verify_incremental(en_passant, "e5d6");

    Board promotion = Board::from_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1");
    verify_incremental(promotion, "a7a8q");

    // Multi-ply chain: every intermediate key must equal a full recomputation,
    // then unwind exactly to the starting key/FEN.
    Board line;
    const std::string line_start_fen = line.to_fen();
    const auto line_start_key = line.zobrist_key();
    const Move m1 = find_move(line, "e2e4"); const UndoState u1 = line.make_move(m1);
    assert(line.zobrist_key() == Zobrist::compute(line));
    const Move m2 = find_move(line, "c7c5"); const UndoState u2 = line.make_move(m2);
    assert(line.zobrist_key() == Zobrist::compute(line));
    const Move m3 = find_move(line, "g1f3"); const UndoState u3 = line.make_move(m3);
    assert(line.zobrist_key() == Zobrist::compute(line));
    line.unmake_move(m3, u3);
    line.unmake_move(m2, u2);
    line.unmake_move(m1, u1);
    assert(line.to_fen() == line_start_fen);
    assert(line.zobrist_key() == line_start_key);

    // Basic TT behaviour: exact-key probe, metadata preservation, collision
    // rejection and depth-preferred replacement.
    TranspositionTable tt(1);
    assert(tt.capacity() > 0);
    assert(!tt.probe(start.zobrist_key()).has_value());

    const Move best = find_move(start, "e2e4");
    tt.store(start.zobrist_key(), 7, 35, BoundType::Exact, best);
    const auto hit = tt.probe(start.zobrist_key());
    assert(hit.has_value());
    assert(hit->depth == 7);
    assert(hit->score == 35);
    assert(hit->bound == BoundType::Exact);
    assert(hit->best_move == best);

    // A different key at the same bucket must not false-hit. Generate one by
    // flipping a bit above the table index mask (capacity is power-of-two).
    const auto colliding_key = start.zobrist_key() ^ static_cast<Zobrist::Key>(tt.capacity());
    assert(!tt.probe(colliding_key).has_value());

    // Shallower colliding entries are not allowed to evict a deeper one.
    tt.store(colliding_key, 3, -10, BoundType::Upper, Move{});
    assert(tt.probe(start.zobrist_key()).has_value());
    assert(!tt.probe(colliding_key).has_value());

    // A deeper colliding result may replace it.
    tt.store(colliding_key, 9, 80, BoundType::Lower, Move{});
    assert(!tt.probe(start.zobrist_key()).has_value());
    const auto replacement = tt.probe(colliding_key);
    assert(replacement.has_value());
    assert(replacement->depth == 9);
    assert(replacement->bound == BoundType::Lower);

    tt.clear();
    assert(!tt.probe(colliding_key).has_value());

    std::cout << "Zobrist and transposition-table tests passed\n";
    return 0;
}
