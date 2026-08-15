#include "neurochess/core/board.h"
#include "neurochess/core/move.h"
#include "neurochess/core/move_generator.h"

#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

using namespace neurochess::core;

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << "FAILED: " << message << '\n';
        std::exit(1);
    }
}

std::vector<std::string> uci_moves(const Board& board) {
    const auto moves = MoveGenerator::pseudo_legal(board);
    std::vector<std::string> result;
    result.reserve(moves.size());
    for (const auto move : moves) result.push_back(move.uci());
    std::sort(result.begin(), result.end());
    return result;
}

bool contains(const std::vector<std::string>& moves, const std::string& move) {
    return std::binary_search(moves.begin(), moves.end(), move);
}

} // namespace

int main() {
    {
        Board start;
        const auto moves = uci_moves(start);
        require(moves.size() == 20, "start position must have 20 pseudo-legal moves");
        require(contains(moves, "e2e4"), "start position must contain e2e4");
        require(contains(moves, "g1f3"), "start position must contain g1f3");
        require(!contains(moves, "e1g1"), "blocked castling must not be generated");
    }

    {
        const Board board = Board::from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1");
        const auto moves = uci_moves(board);
        require(contains(moves, "e1g1"), "white king-side castling must be generated");
        require(contains(moves, "e1c1"), "white queen-side castling must be generated");
    }

    {
        const Board board = Board::from_fen("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1");
        const auto moves = uci_moves(board);
        require(contains(moves, "e5d6"), "en passant capture must be generated");
    }

    {
        const Board board = Board::from_fen("1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1");
        const auto moves = uci_moves(board);
        for (const char p : std::string("qrbn")) {
            require(contains(moves, std::string("a7a8") + p), "quiet promotion variant missing");
            require(contains(moves, std::string("a7b8") + p), "capture promotion variant missing");
        }
    }

    {
        const Board board = Board::from_fen("4k3/8/8/8/3Q4/8/8/4K3 w - - 0 1");
        const auto moves = uci_moves(board);
        require(contains(moves, "d4d8"), "queen rook-like move missing");
        require(contains(moves, "d4h8"), "queen bishop-like move missing");
        require(contains(moves, "d4a1"), "queen reverse diagonal move missing");
    }

    {
        // The rook on e2 is pinned to its king by the black rook. Sideways
        // rook moves are pseudo-legal but must disappear from legal generation.
        Board board = Board::from_fen("4r1k1/8/8/8/8/8/4R3/4K3 w - - 0 1");
        auto pseudo = MoveGenerator::pseudo_legal(board);
        bool pseudo_sideways = false;
        for (const auto move : pseudo) if (move.uci() == "e2d2") pseudo_sideways = true;
        require(pseudo_sideways, "pinned rook sideways move should remain pseudo-legal");
        auto legal = MoveGenerator::legal(board);
        bool legal_sideways = false;
        for (const auto move : legal) if (move.uci() == "e2d2") legal_sideways = true;
        require(!legal_sideways, "pinned rook sideways move must be illegal");
    }

    {
        // f1 is attacked by the black rook, so white may not castle through it.
        Board board = Board::from_fen("4k3/5r2/8/8/8/8/8/4K2R w K - 0 1");
        const auto legal = MoveGenerator::legal(board);
        bool castles = false;
        for (const auto move : legal) if (move.uci() == "e1g1") castles = true;
        require(!castles, "castling through an attacked square must be illegal");
    }

    {
        Board board = Board::from_fen("4k3/8/8/3pP3/8/8/8/4K3 w - d6 7 23");
        const std::string before = board.to_fen();
        Move ep;
        bool found = false;
        for (const auto move : MoveGenerator::legal(board)) {
            if (move.uci() == "e5d6") { ep = move; found = true; break; }
        }
        require(found, "legal en passant move must be found");
        const auto undo = board.make_move(ep);
        require(board.piece_at(square_index(3, 5)) == Piece::WhitePawn, "EP pawn must land on d6");
        require(board.piece_at(square_index(3, 4)) == Piece::None, "EP captured pawn must be removed from d5");
        board.unmake_move(ep, undo);
        require(board.to_fen() == before, "en passant make/unmake must restore exact FEN");
    }

    {
        Move move(square_index(0, 6), square_index(0, 7), MoveFlag::Promotion, PieceType::Knight);
        require(move.from() == square_index(0, 6), "move from encoding mismatch");
        require(move.to() == square_index(0, 7), "move to encoding mismatch");
        require(move.is_promotion(), "promotion flag mismatch");
        require(move.promotion() == PieceType::Knight, "promotion piece encoding mismatch");
        require(move.uci() == "a7a8n", "promotion UCI formatting mismatch");
        require(sizeof(Move) == sizeof(std::uint32_t), "Move should remain 32-bit compact");
    }

    std::cout << "move generation tests passed\n";
    return 0;
}
