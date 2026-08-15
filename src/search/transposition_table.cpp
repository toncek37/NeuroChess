#include "neurochess/search/transposition_table.h"

#include <algorithm>
#include <limits>

namespace neurochess::search {
namespace {

std::size_t floor_power_of_two(std::size_t value) noexcept {
    if (value == 0) return 1;
    std::size_t power = 1;
    while (power <= value / 2) power <<= 1;
    return power;
}

} // namespace

TranspositionTable::TranspositionTable(std::size_t megabytes) {
    resize(megabytes);
}

void TranspositionTable::resize(std::size_t megabytes) {
    constexpr std::size_t bytes_per_mb = 1024u * 1024u;
    const std::size_t requested_bytes = std::max<std::size_t>(1, megabytes) * bytes_per_mb;
    const std::size_t requested_entries = std::max<std::size_t>(1, requested_bytes / sizeof(TranspositionEntry));
    const std::size_t count = floor_power_of_two(requested_entries);
    entries_.assign(count, TranspositionEntry{});
    mask_ = count - 1;
}

void TranspositionTable::clear() noexcept {
    std::fill(entries_.begin(), entries_.end(), TranspositionEntry{});
}

std::size_t TranspositionTable::index_for(neurochess::core::Zobrist::Key key) const noexcept {
    return static_cast<std::size_t>(key) & mask_;
}

std::optional<TranspositionEntry> TranspositionTable::probe(neurochess::core::Zobrist::Key key) const noexcept {
    if (entries_.empty()) return std::nullopt;
    const auto& entry = entries_[index_for(key)];
    if (!entry.occupied || entry.key != key) return std::nullopt;
    return entry;
}

void TranspositionTable::store(neurochess::core::Zobrist::Key key,
                               int depth,
                               int score,
                               BoundType bound,
                               neurochess::core::Move best_move) noexcept {
    if (entries_.empty()) return;
    auto& entry = entries_[index_for(key)];

    // Prefer the same position, an empty slot, or a result searched at least as
    // deeply as the colliding entry. A more sophisticated aging policy belongs
    // to the search-optimization phase.
    if (!entry.occupied || entry.key == key || depth >= entry.depth) {
        entry.key = key;
        entry.depth = static_cast<std::int16_t>(std::clamp(depth,
            static_cast<int>(std::numeric_limits<std::int16_t>::min()),
            static_cast<int>(std::numeric_limits<std::int16_t>::max())));
        entry.score = static_cast<std::int32_t>(score);
        entry.bound = bound;
        entry.best_move = best_move;
        entry.occupied = true;
    }
}

} // namespace neurochess::search
