#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace neurochess::core {

using Bitboard = std::uint64_t;

enum class Color : std::uint8_t { White = 0, Black = 1 };
enum class PieceType : std::uint8_t { Pawn = 0, Knight, Bishop, Rook, Queen, King, None };
enum class Piece : std::uint8_t {
    WhitePawn = 0, WhiteKnight, WhiteBishop, WhiteRook, WhiteQueen, WhiteKing,
    BlackPawn, BlackKnight, BlackBishop, BlackRook, BlackQueen, BlackKing,
    None
};

enum CastlingRight : std::uint8_t {
    WhiteKingSide  = 1u << 0,
    WhiteQueenSide = 1u << 1,
    BlackKingSide  = 1u << 2,
    BlackQueenSide = 1u << 3,
};

class Move;

struct UndoState {
    std::uint64_t zobrist_key = 0;
    Piece captured_piece = Piece::None;
    std::uint8_t castling_rights = 0;
    std::optional<int> en_passant_square{};
    std::uint16_t halfmove_clock = 0;
    std::uint16_t fullmove_number = 1;
};

constexpr int square_index(int file, int rank) noexcept { return rank * 8 + file; }
constexpr Bitboard square_bit(int square) noexcept { return Bitboard{1} << square; }
constexpr int piece_index(Piece piece) noexcept { return static_cast<int>(piece); }
constexpr int color_index(Color color) noexcept { return static_cast<int>(color); }

[[nodiscard]] Color opposite(Color color) noexcept;
[[nodiscard]] Color piece_color(Piece piece) noexcept;
[[nodiscard]] PieceType piece_type(Piece piece) noexcept;
[[nodiscard]] Piece make_piece(Color color, PieceType type) noexcept;
[[nodiscard]] std::string square_name(int square);
[[nodiscard]] std::optional<int> parse_square(std::string_view name) noexcept;

class Board {
public:
    static constexpr std::string_view StartFen =
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

    Board();

    [[nodiscard]] static Board from_fen(std::string_view fen);
    [[nodiscard]] std::string to_fen() const;

    void clear() noexcept;

    [[nodiscard]] const std::array<Bitboard, 12>& piece_bitboards() const noexcept { return pieces_; }
    [[nodiscard]] Bitboard pieces(Piece piece) const noexcept;
    [[nodiscard]] Bitboard occupancy(Color color) const noexcept { return occupancy_[color_index(color)]; }
    [[nodiscard]] Bitboard occupancy_all() const noexcept { return occupancy_all_; }
    [[nodiscard]] Piece piece_at(int square) const noexcept;

    [[nodiscard]] Color side_to_move() const noexcept { return side_to_move_; }
    [[nodiscard]] std::uint8_t castling_rights() const noexcept { return castling_rights_; }
    [[nodiscard]] std::optional<int> en_passant_square() const noexcept { return en_passant_square_; }
    [[nodiscard]] std::uint16_t halfmove_clock() const noexcept { return halfmove_clock_; }
    [[nodiscard]] std::uint16_t fullmove_number() const noexcept { return fullmove_number_; }
    [[nodiscard]] std::uint64_t zobrist_key() const noexcept { return zobrist_key_; }

    [[nodiscard]] bool has_castling_right(CastlingRight right) const noexcept {
        return (castling_rights_ & static_cast<std::uint8_t>(right)) != 0;
    }

    [[nodiscard]] int king_square(Color color) const noexcept;
    [[nodiscard]] bool is_square_attacked(int square, Color by_color) const noexcept;
    [[nodiscard]] bool in_check(Color color) const noexcept;

    // Applies a pseudo-legal move in-place and returns the small amount of state
    // needed to reverse it. No Board copy is made in the search path.
    [[nodiscard]] UndoState make_move(const Move& move);
    void unmake_move(const Move& move, const UndoState& undo) noexcept;

    // Search-only null move: flip side to move and clear en-passant without
    // changing any pieces. This is never exposed as a legal chess move.
    [[nodiscard]] UndoState make_null_move() noexcept;
    void unmake_null_move(const UndoState& undo) noexcept;

private:
    struct EmptyTag {};
    explicit Board(EmptyTag) noexcept;

    std::array<Bitboard, 12> pieces_{};
    std::array<Bitboard, 2> occupancy_{};
    Bitboard occupancy_all_ = 0;
    Color side_to_move_ = Color::White;
    std::uint8_t castling_rights_ = 0;
    std::optional<int> en_passant_square_{};
    std::uint16_t halfmove_clock_ = 0;
    std::uint16_t fullmove_number_ = 1;
    std::uint64_t zobrist_key_ = 0;

    void put_piece(Piece piece, int square);
    void remove_piece(Piece piece, int square) noexcept;
    void move_piece(Piece piece, int from, int to) noexcept;
    void rebuild_occupancy() noexcept;
    void clear_castling_right_for_rook_square(int square) noexcept;
};

} // namespace neurochess::core
