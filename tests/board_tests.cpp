#include "neurochess/core/board.h"

#include <cassert>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace neurochess::core;

namespace {

int sq(const char* name) {
    const auto value = parse_square(name);
    assert(value.has_value());
    return *value;
}

void expect_invalid_fen(const std::string& fen) {
    bool threw = false;
    try {
        (void)Board::from_fen(fen);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    assert(threw);
}

void test_start_position() {
    const Board board;
    assert(board.to_fen() == Board::StartFen);
    assert(board.side_to_move() == Color::White);
    assert(board.castling_rights() == 0x0F);
    assert(!board.en_passant_square().has_value());
    assert(board.halfmove_clock() == 0);
    assert(board.fullmove_number() == 1);

    assert(board.piece_at(sq("a1")) == Piece::WhiteRook);
    assert(board.piece_at(sq("e1")) == Piece::WhiteKing);
    assert(board.piece_at(sq("d8")) == Piece::BlackQueen);
    assert(board.piece_at(sq("e4")) == Piece::None);

    assert(board.pieces(Piece::WhitePawn) == 0x000000000000FF00ULL);
    assert(board.pieces(Piece::BlackPawn) == 0x00FF000000000000ULL);
    assert(board.occupancy(Color::White) == 0x000000000000FFFFULL);
    assert(board.occupancy(Color::Black) == 0xFFFF000000000000ULL);
    assert(board.occupancy_all() == 0xFFFF00000000FFFFULL);
}

void test_round_trips() {
    const std::vector<std::string> fens = {
        std::string(Board::StartFen),
        "r3k2r/p1ppqpb1/bn2pnp1/2pP4/1p2P3/2N2N2/PPQBBPPP/R3K2R w KQkq - 0 1",
        "8/8/3k4/8/3Pp3/8/3K4/8 w - e3 17 42",
        "4k3/P7/8/8/8/8/7p/4K3 b - - 99 123",
        "8/8/8/8/8/8/8/K6k w - - 0 1"
    };

    for (const auto& fen : fens) {
        const Board board = Board::from_fen(fen);
        assert(board.to_fen() == fen);
    }
}

void test_state_fields() {
    const Board board = Board::from_fen(
        "r3k2r/8/8/3pP3/8/8/8/R3K2R b Kq d6 12 34");

    assert(board.side_to_move() == Color::Black);
    assert(board.has_castling_right(WhiteKingSide));
    assert(!board.has_castling_right(WhiteQueenSide));
    assert(!board.has_castling_right(BlackKingSide));
    assert(board.has_castling_right(BlackQueenSide));
    assert(board.en_passant_square().has_value());
    assert(*board.en_passant_square() == sq("d6"));
    assert(board.halfmove_clock() == 12);
    assert(board.fullmove_number() == 34);
}

void test_square_helpers() {
    assert(square_name(0) == "a1");
    assert(square_name(63) == "h8");
    assert(parse_square("a1") == 0);
    assert(parse_square("h8") == 63);
    assert(!parse_square("i1").has_value());
    assert(!parse_square("a9").has_value());
}

void test_invalid_fens() {
    expect_invalid_fen("8/8/8/8/8/8/8/8 w - - 0");
    expect_invalid_fen("8/8/8/8/8/8/8/9 w - - 0 1");
    expect_invalid_fen("8/8/8/8/8/8/8/8 x - - 0 1");
    expect_invalid_fen("8/8/8/8/8/8/8/8 w KK - 0 1");
    expect_invalid_fen("8/8/8/8/8/8/8/8 w - e4 0 1");
    expect_invalid_fen("8/8/8/8/8/8/8/8 w - - -1 1");
    expect_invalid_fen("8/8/8/8/8/8/8/8 w - - 0 0");
}

} // namespace

int main() {
    test_start_position();
    test_round_trips();
    test_state_fields();
    test_square_helpers();
    test_invalid_fens();
    std::cout << "Board/FEN tests passed\n";
    return 0;
}
