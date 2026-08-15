#pragma once

#include "neurochess/core/board.h"
#include "neurochess/core/move.h"
#include "neurochess/nn/neural_evaluator.h"
#include "neurochess/search/evaluator.h"
#include "neurochess/search/transposition_table.h"

#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace neurochess::search {

struct SearchLimits {
    int max_depth = 0;
    std::uint64_t max_nodes = 0;
    std::chrono::milliseconds max_time{0};
};

struct SearchConfig {
    bool killer_moves = true;
    bool history_heuristic = true;
    bool null_move_pruning = true;
    bool late_move_reductions = true;
    bool aspiration_windows = true;
    bool futility_pruning = true;
    bool razoring = true;
    bool neural_policy = false;
    bool neural_value = false;

    int aspiration_window_cp = 35;
    int null_move_min_depth = 3;
    int null_move_reduction = 2;
    int lmr_min_depth = 3;
    int lmr_move_threshold = 3;
    int futility_margin_cp = 120;
    int razor_margin_cp = 250;
    int neural_policy_scale = 200;
    int neural_policy_max_ply = 2;
    int neural_value_blend_percent = 50;
};

struct SearchStats {
    int depth = 0;
    int selective_depth = 0;
    std::uint64_t nodes = 0;
    std::uint64_t qnodes = 0;
    std::uint64_t tt_hits = 0;
    std::uint64_t beta_cutoffs = 0;
    std::uint64_t null_move_prunes = 0;
    std::uint64_t lmr_reductions = 0;
    std::uint64_t futility_prunes = 0;
    std::uint64_t razor_prunes = 0;
    std::uint64_t aspiration_researches = 0;
    std::uint64_t neural_evaluations = 0;
    std::uint64_t neural_inference_us = 0;
    std::chrono::milliseconds elapsed{0};
    std::uint64_t nps = 0;
};

struct SearchResult {
    core::Move best_move{};
    int score = 0;
    std::vector<core::Move> principal_variation;
    SearchStats stats{};
    bool completed = false;
};

class Searcher {
public:
    static constexpr int Infinity = 32'000;
    static constexpr int MateScore = 30'000;
    static constexpr int MateThreshold = 29'000;
    static constexpr int MaxPly = 128;

    explicit Searcher(std::size_t tt_megabytes = 16,
                      EvaluationConfig evaluation_config = {},
                      SearchConfig search_config = {});

    [[nodiscard]] SearchResult search(core::Board& board, SearchLimits limits = {});
    [[nodiscard]] constexpr bool available() const noexcept { return true; }

    void set_position_history(std::vector<std::uint64_t> hashes);
    void clear_position_history() noexcept;

    void set_config(SearchConfig config) noexcept { config_ = config; }
    [[nodiscard]] const SearchConfig& config() const noexcept { return config_; }

    bool load_neural_model(const std::string& path);
    [[nodiscard]] bool neural_ready() const noexcept;
    [[nodiscard]] std::string neural_backend() const;

    void request_stop() noexcept { stop_requested_.store(true, std::memory_order_relaxed); }
    void clear_tt() noexcept { tt_.clear(); }

    [[nodiscard]] const TranspositionTable& transposition_table() const noexcept { return tt_; }

private:
    ClassicalEvaluator evaluator_;
    std::shared_ptr<nn::NeuralEvaluator> neural_;
    TranspositionTable tt_;
    SearchConfig config_{};
    std::vector<std::uint64_t> prior_history_;
    std::vector<std::uint64_t> search_history_;
    std::vector<core::Move> root_neural_order_;
    std::atomic_bool stop_requested_{false};

    std::array<std::array<core::Move, 2>, MaxPly> killers_{};
    std::array<std::array<std::array<int, 64>, 64>, 2> history_{};

    SearchLimits limits_{};
    SearchStats stats_{};
    std::chrono::steady_clock::time_point start_time_{};
    bool aborted_ = false;

    int search_root(core::Board& board, int depth, int alpha, int beta, core::Move& best_move);
    int negamax(core::Board& board, int depth, int ply, int alpha, int beta, bool allow_null = true);
    int quiescence(core::Board& board, int ply, int alpha, int beta);
    int static_evaluate(core::Board& board);
    void order_moves(core::Board& board, std::vector<core::Move>& moves, core::Move tt_move, int ply);

    [[nodiscard]] bool should_stop();
    [[nodiscard]] bool is_repetition(std::uint64_t key) const noexcept;
    [[nodiscard]] static bool is_insufficient_material(const core::Board& board) noexcept;
    [[nodiscard]] static bool has_non_pawn_material(const core::Board& board, core::Color color) noexcept;
    [[nodiscard]] static int score_to_tt(int score, int ply) noexcept;
    [[nodiscard]] static int score_from_tt(int score, int ply) noexcept;
    [[nodiscard]] int move_order_score(const core::Board& board,
                                       core::Move move,
                                       core::Move tt_move,
                                       int ply) const noexcept;
    void record_quiet_cutoff(core::Color side, core::Move move, int ply, int depth) noexcept;
    void reset_heuristics() noexcept;
    [[nodiscard]] std::vector<core::Move> extract_pv(const core::Board& board, int max_length) const;
};

} // namespace neurochess::search
