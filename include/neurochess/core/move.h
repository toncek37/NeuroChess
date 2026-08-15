#pragma once

#include "neurochess/core/board.h"

#include <cstdint>
#include <string>

namespace neurochess::core {

enum class MoveFlag : std::uint8_t {
    Quiet = 0,
    Capture,
    DoublePawnPush,
    KingCastle,
    QueenCastle,
    EnPassant,
    Promotion,
    PromotionCapture
};

class Move {
public:
    constexpr Move() noexcept = default;
    constexpr Move(int from, int to, MoveFlag flag = MoveFlag::Quiet,
                   PieceType promotion = PieceType::None) noexcept
        : data_(static_cast<std::uint32_t>(from)
              | (static_cast<std::uint32_t>(to) << 6)
              | (static_cast<std::uint32_t>(promotion) << 12)
              | (static_cast<std::uint32_t>(flag) << 15)) {}

    [[nodiscard]] constexpr int from() const noexcept { return static_cast<int>(data_ & 0x3Fu); }
    [[nodiscard]] constexpr int to() const noexcept { return static_cast<int>((data_ >> 6) & 0x3Fu); }
    [[nodiscard]] constexpr PieceType promotion() const noexcept {
        return static_cast<PieceType>((data_ >> 12) & 0x7u);
    }
    [[nodiscard]] constexpr MoveFlag flag() const noexcept {
        return static_cast<MoveFlag>((data_ >> 15) & 0xFu);
    }

    [[nodiscard]] constexpr bool is_capture() const noexcept {
        return flag() == MoveFlag::Capture || flag() == MoveFlag::EnPassant
            || flag() == MoveFlag::PromotionCapture;
    }
    [[nodiscard]] constexpr bool is_promotion() const noexcept {
        return flag() == MoveFlag::Promotion || flag() == MoveFlag::PromotionCapture;
    }
    [[nodiscard]] constexpr bool is_castle() const noexcept {
        return flag() == MoveFlag::KingCastle || flag() == MoveFlag::QueenCastle;
    }
    [[nodiscard]] constexpr std::uint32_t raw() const noexcept { return data_; }

    [[nodiscard]] std::string uci() const;

    friend constexpr bool operator==(Move a, Move b) noexcept { return a.data_ == b.data_; }
    friend constexpr bool operator!=(Move a, Move b) noexcept { return !(a == b); }

private:
    std::uint32_t data_ = 0;
};

} // namespace neurochess::core
