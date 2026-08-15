#pragma once

#include "neurochess/core/move.h"
#include "neurochess/core/zobrist.h"

#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>

namespace neurochess::search {

enum class BoundType : std::uint8_t {
    Exact = 0,
    Lower,
    Upper
};

struct TranspositionEntry {
    neurochess::core::Zobrist::Key key = 0;
    std::int32_t score = 0;
    std::int16_t depth = -1;
    BoundType bound = BoundType::Exact;
    neurochess::core::Move best_move{};
    bool occupied = false;
};

class TranspositionTable {
public:
    explicit TranspositionTable(std::size_t megabytes = 16);

    void resize(std::size_t megabytes);
    void clear() noexcept;

    [[nodiscard]] std::optional<TranspositionEntry> probe(neurochess::core::Zobrist::Key key) const noexcept;
    void store(neurochess::core::Zobrist::Key key,
               int depth,
               int score,
               BoundType bound,
               neurochess::core::Move best_move) noexcept;

    [[nodiscard]] std::size_t capacity() const noexcept { return entries_.size(); }
    [[nodiscard]] std::size_t bytes() const noexcept { return entries_.size() * sizeof(TranspositionEntry); }

private:
    std::vector<TranspositionEntry> entries_;
    std::size_t mask_ = 0;

    [[nodiscard]] std::size_t index_for(neurochess::core::Zobrist::Key key) const noexcept;
};

} // namespace neurochess::search
