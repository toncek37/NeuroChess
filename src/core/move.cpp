#include "neurochess/core/move.h"

#include <stdexcept>

namespace neurochess::core {

std::string Move::uci() const {
    std::string out = square_name(from()) + square_name(to());
    if (is_promotion()) {
        char suffix = 0;
        switch (promotion()) {
            case PieceType::Knight: suffix = 'n'; break;
            case PieceType::Bishop: suffix = 'b'; break;
            case PieceType::Rook: suffix = 'r'; break;
            case PieceType::Queen: suffix = 'q'; break;
            default: throw std::logic_error("Invalid promotion piece in move");
        }
        out.push_back(suffix);
    }
    return out;
}

} // namespace neurochess::core
