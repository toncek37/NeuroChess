#pragma once

#include <string_view>

namespace neurochess::core {

struct EngineInfo {
    static constexpr std::string_view name() noexcept { return "NeuroChess"; }
    static constexpr std::string_view version() noexcept { return "0.12.5"; }
    static constexpr std::string_view author() noexcept { return "NeuroChess project"; }
};

} // namespace neurochess::core
