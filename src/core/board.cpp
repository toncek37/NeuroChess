#include "neurochess/core/board.h"
#include "neurochess/core/move.h"
#include "neurochess/core/zobrist.h"

#include <bit>
#include <charconv>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace neurochess::core {
namespace {

Piece piece_from_fen_char(char c) {
    switch (c) {
        case 'P': return Piece::WhitePawn;
        case 'N': return Piece::WhiteKnight;
        case 'B': return Piece::WhiteBishop;
        case 'R': return Piece::WhiteRook;
        case 'Q': return Piece::WhiteQueen;
        case 'K': return Piece::WhiteKing;
        case 'p': return Piece::BlackPawn;
        case 'n': return Piece::BlackKnight;
        case 'b': return Piece::BlackBishop;
        case 'r': return Piece::BlackRook;
        case 'q': return Piece::BlackQueen;
        case 'k': return Piece::BlackKing;
        default: throw std::invalid_argument("Invalid FEN piece character");
    }
}

char fen_char_from_piece(Piece piece) {
    constexpr char chars[] = "PNBRQKpnbrqk";
    const int index = piece_index(piece);
    if (index < 0 || index >= 12) {
        throw std::logic_error("Cannot serialize empty piece");
    }
    return chars[index];
}

std::uint16_t parse_u16(std::string_view text, const char* field_name, bool allow_zero) {
    if (text.empty()) {
        throw std::invalid_argument(std::string("Empty FEN ") + field_name);
    }

    unsigned int value = 0;
    const char* first = text.data();
    const char* last = text.data() + text.size();
    const auto result = std::from_chars(first, last, value);
    if (result.ec != std::errc{} || result.ptr != last || value > 65535u || (!allow_zero && value == 0u)) {
        throw std::invalid_argument(std::string("Invalid FEN ") + field_name);
    }
    return static_cast<std::uint16_t>(value);
}

} // namespace

Color opposite(Color color) noexcept {
    return color == Color::White ? Color::Black : Color::White;
}

Color piece_color(Piece piece) noexcept {
    return piece_index(piece) < 6 ? Color::White : Color::Black;
}

PieceType piece_type(Piece piece) noexcept {
    const int index = piece_index(piece);
    if (index < 0 || index >= 12) {
        return PieceType::None;
    }
    return static_cast<PieceType>(index % 6);
}

Piece make_piece(Color color, PieceType type) noexcept {
    if (type == PieceType::None) {
        return Piece::None;
    }
    return static_cast<Piece>(color_index(color) * 6 + static_cast<int>(type));
}

std::string square_name(int square) {
    if (square < 0 || square >= 64) {
        throw std::out_of_range("Square index must be in [0, 63]");
    }
    std::string result(2, ' ');
    result[0] = static_cast<char>('a' + square % 8);
    result[1] = static_cast<char>('1' + square / 8);
    return result;
}

std::optional<int> parse_square(std::string_view name) noexcept {
    if (name.size() != 2 || name[0] < 'a' || name[0] > 'h' || name[1] < '1' || name[1] > '8') {
        return std::nullopt;
    }
    return square_index(name[0] - 'a', name[1] - '1');
}

Board::Board(EmptyTag) noexcept {
    clear();
}

Board::Board() : Board(EmptyTag{}) {
    *this = from_fen(StartFen);
}

void Board::clear() noexcept {
    pieces_.fill(0);
    occupancy_.fill(0);
    occupancy_all_ = 0;
    side_to_move_ = Color::White;
    castling_rights_ = 0;
    en_passant_square_.reset();
    halfmove_clock_ = 0;
    fullmove_number_ = 1;
    zobrist_key_ = Zobrist::compute(*this);
}

void Board::put_piece(Piece piece, int square) {
    if (piece == Piece::None || square < 0 || square >= 64) {
        throw std::invalid_argument("Invalid piece placement");
    }
    pieces_[piece_index(piece)] |= square_bit(square);
}

void Board::rebuild_occupancy() noexcept {
    occupancy_.fill(0);
    for (int i = 0; i < 6; ++i) {
        occupancy_[0] |= pieces_[i];
        occupancy_[1] |= pieces_[i + 6];
    }
    occupancy_all_ = occupancy_[0] | occupancy_[1];
}

Bitboard Board::pieces(Piece piece) const noexcept {
    if (piece == Piece::None) {
        return 0;
    }
    return pieces_[piece_index(piece)];
}

Piece Board::piece_at(int square) const noexcept {
    if (square < 0 || square >= 64) {
        return Piece::None;
    }
    const Bitboard mask = square_bit(square);
    for (int i = 0; i < 12; ++i) {
        if ((pieces_[i] & mask) != 0) {
            return static_cast<Piece>(i);
        }
    }
    return Piece::None;
}

Board Board::from_fen(std::string_view fen) {
    std::istringstream stream{std::string(fen)};
    std::vector<std::string> fields;
    std::string field;
    while (stream >> field) {
        fields.push_back(field);
    }
    if (fields.size() != 6) {
        throw std::invalid_argument("FEN must contain exactly six fields");
    }

    Board board(EmptyTag{});

    int rank = 7;
    int file = 0;
    int rank_count = 1;
    for (const char c : fields[0]) {
        if (c == '/') {
            if (file != 8 || rank <= 0) {
                throw std::invalid_argument("Invalid FEN board layout");
            }
            --rank;
            file = 0;
            ++rank_count;
            continue;
        }

        if (c >= '1' && c <= '8') {
            file += c - '0';
            if (file > 8) {
                throw std::invalid_argument("Invalid FEN board rank width");
            }
            continue;
        }

        if (file >= 8) {
            throw std::invalid_argument("Too many squares in FEN rank");
        }
        board.put_piece(piece_from_fen_char(c), square_index(file, rank));
        ++file;
    }
    if (rank != 0 || file != 8 || rank_count != 8) {
        throw std::invalid_argument("FEN board layout must contain eight complete ranks");
    }

    if (fields[1] == "w") {
        board.side_to_move_ = Color::White;
    } else if (fields[1] == "b") {
        board.side_to_move_ = Color::Black;
    } else {
        throw std::invalid_argument("Invalid FEN side-to-move field");
    }

    if (fields[2] != "-") {
        for (char c : fields[2]) {
            std::uint8_t right = 0;
            switch (c) {
                case 'K': right = WhiteKingSide; break;
                case 'Q': right = WhiteQueenSide; break;
                case 'k': right = BlackKingSide; break;
                case 'q': right = BlackQueenSide; break;
                default: throw std::invalid_argument("Invalid FEN castling rights");
            }
            if ((board.castling_rights_ & right) != 0) {
                throw std::invalid_argument("Duplicate FEN castling right");
            }
            board.castling_rights_ |= right;
        }
    }

    if (fields[3] != "-") {
        board.en_passant_square_ = parse_square(fields[3]);
        if (!board.en_passant_square_.has_value()) {
            throw std::invalid_argument("Invalid FEN en-passant square");
        }
        const int ep_rank = *board.en_passant_square_ / 8;
        if (ep_rank != 2 && ep_rank != 5) {
            throw std::invalid_argument("FEN en-passant square must be on rank 3 or 6");
        }
    }

    board.halfmove_clock_ = parse_u16(fields[4], "halfmove clock", true);
    board.fullmove_number_ = parse_u16(fields[5], "fullmove number", false);
    board.rebuild_occupancy();
    board.zobrist_key_ = Zobrist::compute(board);

    return board;
}

std::string Board::to_fen() const {
    std::ostringstream out;

    for (int rank = 7; rank >= 0; --rank) {
        int empty = 0;
        for (int file = 0; file < 8; ++file) {
            const Piece piece = piece_at(square_index(file, rank));
            if (piece == Piece::None) {
                ++empty;
                continue;
            }
            if (empty != 0) {
                out << empty;
                empty = 0;
            }
            out << fen_char_from_piece(piece);
        }
        if (empty != 0) {
            out << empty;
        }
        if (rank != 0) {
            out << '/';
        }
    }

    out << ' ' << (side_to_move_ == Color::White ? 'w' : 'b') << ' ';
    if (castling_rights_ == 0) {
        out << '-';
    } else {
        if (has_castling_right(WhiteKingSide)) out << 'K';
        if (has_castling_right(WhiteQueenSide)) out << 'Q';
        if (has_castling_right(BlackKingSide)) out << 'k';
        if (has_castling_right(BlackQueenSide)) out << 'q';
    }

    out << ' ';
    if (en_passant_square_.has_value()) {
        out << square_name(*en_passant_square_);
    } else {
        out << '-';
    }

    out << ' ' << halfmove_clock_ << ' ' << fullmove_number_;
    return out.str();
}


void Board::remove_piece(Piece piece, int square) noexcept {
    if (piece == Piece::None || square < 0 || square >= 64) return;
    pieces_[piece_index(piece)] &= ~square_bit(square);
}

void Board::move_piece(Piece piece, int from, int to) noexcept {
    const Bitboard from_bit = square_bit(from);
    const Bitboard to_bit = square_bit(to);
    auto& bb = pieces_[piece_index(piece)];
    bb &= ~from_bit;
    bb |= to_bit;
}

int Board::king_square(Color color) const noexcept {
    const Bitboard king = pieces(make_piece(color, PieceType::King));
    return king ? static_cast<int>(std::countr_zero(king)) : -1;
}

bool Board::is_square_attacked(int square, Color by_color) const noexcept {
    if (square < 0 || square >= 64) return false;
    const int file = square % 8;
    const int rank = square / 8;

    // Pawns: invert the usual capture direction because we trace backwards
    // from the target square to possible attacking pawn origins.
    const int pawn_origin_rank = rank + (by_color == Color::White ? -1 : 1);
    if (pawn_origin_rank >= 0 && pawn_origin_rank < 8) {
        for (int df : {-1, 1}) {
            const int f = file + df;
            if (f >= 0 && f < 8
                && piece_at(square_index(f, pawn_origin_rank)) == make_piece(by_color, PieceType::Pawn)) {
                return true;
            }
        }
    }

    constexpr int knight_offsets[8][2] = {
        {1,2},{2,1},{2,-1},{1,-2},{-1,-2},{-2,-1},{-2,1},{-1,2}
    };
    for (const auto& o : knight_offsets) {
        const int f = file + o[0];
        const int r = rank + o[1];
        if (f >= 0 && f < 8 && r >= 0 && r < 8
            && piece_at(square_index(f, r)) == make_piece(by_color, PieceType::Knight)) {
            return true;
        }
    }

    constexpr int king_offsets[8][2] = {
        {1,0},{1,1},{0,1},{-1,1},{-1,0},{-1,-1},{0,-1},{1,-1}
    };
    for (const auto& o : king_offsets) {
        const int f = file + o[0];
        const int r = rank + o[1];
        if (f >= 0 && f < 8 && r >= 0 && r < 8
            && piece_at(square_index(f, r)) == make_piece(by_color, PieceType::King)) {
            return true;
        }
    }

    auto attacked_by_slider = [&](const int (*dirs)[2], int count, PieceType a, PieceType b) {
        for (int i = 0; i < count; ++i) {
            int f = file + dirs[i][0];
            int r = rank + dirs[i][1];
            while (f >= 0 && f < 8 && r >= 0 && r < 8) {
                const Piece p = piece_at(square_index(f, r));
                if (p != Piece::None) {
                    if (piece_color(p) == by_color && (piece_type(p) == a || piece_type(p) == b)) {
                        return true;
                    }
                    break;
                }
                f += dirs[i][0];
                r += dirs[i][1];
            }
        }
        return false;
    };

    constexpr int bishop_dirs[4][2] = {{1,1},{1,-1},{-1,1},{-1,-1}};
    if (attacked_by_slider(bishop_dirs, 4, PieceType::Bishop, PieceType::Queen)) return true;
    constexpr int rook_dirs[4][2] = {{1,0},{-1,0},{0,1},{0,-1}};
    return attacked_by_slider(rook_dirs, 4, PieceType::Rook, PieceType::Queen);
}

bool Board::in_check(Color color) const noexcept {
    const int king = king_square(color);
    return king >= 0 && is_square_attacked(king, opposite(color));
}

void Board::clear_castling_right_for_rook_square(int square) noexcept {
    switch (square) {
        case 0:  castling_rights_ &= ~static_cast<std::uint8_t>(WhiteQueenSide); break;
        case 7:  castling_rights_ &= ~static_cast<std::uint8_t>(WhiteKingSide); break;
        case 56: castling_rights_ &= ~static_cast<std::uint8_t>(BlackQueenSide); break;
        case 63: castling_rights_ &= ~static_cast<std::uint8_t>(BlackKingSide); break;
        default: break;
    }
}

UndoState Board::make_move(const Move& move) {
    UndoState undo;
    undo.zobrist_key = zobrist_key_;
    undo.castling_rights = castling_rights_;
    undo.en_passant_square = en_passant_square_;
    undo.halfmove_clock = halfmove_clock_;
    undo.fullmove_number = fullmove_number_;

    const Color us = side_to_move_;
    const Piece moving = piece_at(move.from());
    if (moving == Piece::None || piece_color(moving) != us) {
        throw std::invalid_argument("Move source does not contain side-to-move piece");
    }

    // Remove position-state components before mutating them. Piece keys are
    // updated incrementally below; clocks are intentionally not part of the key.
    zobrist_key_ ^= Zobrist::castling(castling_rights_);
    if (en_passant_square_.has_value()) {
        zobrist_key_ ^= Zobrist::en_passant(*en_passant_square_);
    }

    int captured_square = move.to();
    if (move.flag() == MoveFlag::EnPassant) {
        captured_square += (us == Color::White ? -8 : 8);
    }
    undo.captured_piece = piece_at(captured_square);

    en_passant_square_.reset();
    ++halfmove_clock_;
    if (piece_type(moving) == PieceType::Pawn || undo.captured_piece != Piece::None) {
        halfmove_clock_ = 0;
    }

    if (undo.captured_piece != Piece::None) {
        zobrist_key_ ^= Zobrist::piece(undo.captured_piece, captured_square);
        remove_piece(undo.captured_piece, captured_square);
        if (piece_type(undo.captured_piece) == PieceType::Rook) {
            clear_castling_right_for_rook_square(captured_square);
        }
    }

    zobrist_key_ ^= Zobrist::piece(moving, move.from());
    remove_piece(moving, move.from());
    Piece placed = moving;
    if (move.is_promotion()) {
        placed = make_piece(us, move.promotion());
    }
    put_piece(placed, move.to());
    zobrist_key_ ^= Zobrist::piece(placed, move.to());

    if (move.flag() == MoveFlag::KingCastle) {
        const int rook_from = us == Color::White ? 7 : 63;
        const int rook_to = us == Color::White ? 5 : 61;
        const Piece rook = make_piece(us, PieceType::Rook);
        zobrist_key_ ^= Zobrist::piece(rook, rook_from);
        zobrist_key_ ^= Zobrist::piece(rook, rook_to);
        move_piece(rook, rook_from, rook_to);
    } else if (move.flag() == MoveFlag::QueenCastle) {
        const int rook_from = us == Color::White ? 0 : 56;
        const int rook_to = us == Color::White ? 3 : 59;
        const Piece rook = make_piece(us, PieceType::Rook);
        zobrist_key_ ^= Zobrist::piece(rook, rook_from);
        zobrist_key_ ^= Zobrist::piece(rook, rook_to);
        move_piece(rook, rook_from, rook_to);
    }

    if (piece_type(moving) == PieceType::King) {
        if (us == Color::White) {
            castling_rights_ &= ~(static_cast<std::uint8_t>(WhiteKingSide) | static_cast<std::uint8_t>(WhiteQueenSide));
        } else {
            castling_rights_ &= ~(static_cast<std::uint8_t>(BlackKingSide) | static_cast<std::uint8_t>(BlackQueenSide));
        }
    } else if (piece_type(moving) == PieceType::Rook) {
        clear_castling_right_for_rook_square(move.from());
    }

    if (move.flag() == MoveFlag::DoublePawnPush) {
        en_passant_square_ = (move.from() + move.to()) / 2;
    }

    if (us == Color::Black) ++fullmove_number_;
    side_to_move_ = opposite(us);
    zobrist_key_ ^= Zobrist::side_to_move();
    zobrist_key_ ^= Zobrist::castling(castling_rights_);
    if (en_passant_square_.has_value()) {
        zobrist_key_ ^= Zobrist::en_passant(*en_passant_square_);
    }
    rebuild_occupancy();
    return undo;
}

void Board::unmake_move(const Move& move, const UndoState& undo) noexcept {
    const Color us = opposite(side_to_move_);
    side_to_move_ = us;
    castling_rights_ = undo.castling_rights;
    en_passant_square_ = undo.en_passant_square;
    halfmove_clock_ = undo.halfmove_clock;
    fullmove_number_ = undo.fullmove_number;

    Piece placed = piece_at(move.to());
    remove_piece(placed, move.to());
    const Piece original = move.is_promotion() ? make_piece(us, PieceType::Pawn) : placed;
    put_piece(original, move.from());

    if (move.flag() == MoveFlag::KingCastle) {
        const int rook_from = us == Color::White ? 7 : 63;
        const int rook_to = us == Color::White ? 5 : 61;
        move_piece(make_piece(us, PieceType::Rook), rook_to, rook_from);
    } else if (move.flag() == MoveFlag::QueenCastle) {
        const int rook_from = us == Color::White ? 0 : 56;
        const int rook_to = us == Color::White ? 3 : 59;
        move_piece(make_piece(us, PieceType::Rook), rook_to, rook_from);
    }

    if (undo.captured_piece != Piece::None) {
        int captured_square = move.to();
        if (move.flag() == MoveFlag::EnPassant) {
            captured_square += (us == Color::White ? -8 : 8);
        }
        put_piece(undo.captured_piece, captured_square);
    }
    rebuild_occupancy();
    zobrist_key_ = undo.zobrist_key;
}

UndoState Board::make_null_move() noexcept {
    UndoState undo;
    undo.zobrist_key = zobrist_key_;
    undo.castling_rights = castling_rights_;
    undo.en_passant_square = en_passant_square_;
    undo.halfmove_clock = halfmove_clock_;
    undo.fullmove_number = fullmove_number_;

    if (en_passant_square_.has_value()) {
        zobrist_key_ ^= Zobrist::en_passant(*en_passant_square_);
        en_passant_square_.reset();
    }
    side_to_move_ = opposite(side_to_move_);
    zobrist_key_ ^= Zobrist::side_to_move();
    return undo;
}

void Board::unmake_null_move(const UndoState& undo) noexcept {
    side_to_move_ = opposite(side_to_move_);
    castling_rights_ = undo.castling_rights;
    en_passant_square_ = undo.en_passant_square;
    halfmove_clock_ = undo.halfmove_clock;
    fullmove_number_ = undo.fullmove_number;
    zobrist_key_ = undo.zobrist_key;
}

} // namespace neurochess::core
