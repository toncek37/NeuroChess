from pathlib import Path

h = Path('include/neurochess/search/searcher.h')
s = h.read_text()
s = s.replace(
'''    std::uint64_t neural_evaluations = 0;
    std::uint64_t neural_inference_us = 0;
    std::chrono::milliseconds elapsed{0};''',
'''    std::uint64_t neural_evaluations = 0;
    std::uint64_t neural_inference_us = 0;
    int root_classical_best_rank = 0;
    int root_policy_best_rank = 0;
    int root_policy_rank_gain = 0;
    std::chrono::milliseconds elapsed{0};''',
1)
s = s.replace(
'''    std::vector<std::uint64_t> search_history_;
    std::vector<core::Move> root_neural_order_;
    int selective_policy_calls_used_ = 0;
    std::atomic_bool stop_requested_{false};''',
'''    std::vector<std::uint64_t> search_history_;
    std::vector<core::Move> root_classical_order_;
    std::vector<core::Move> root_neural_order_;
    std::atomic_bool stop_requested_{false};''',
1)
s = s.replace(
'''    void order_moves(core::Board& board, std::vector<core::Move>& moves, core::Move tt_move, int ply,
                     bool allow_selective_value_policy = false);''',
'''    void order_moves(core::Board& board, std::vector<core::Move>& moves, core::Move tt_move, int ply);''',
1)
h.write_text(s)

p = Path('src/search/searcher.cpp')
s = p.read_text()
start = s.index('void Searcher::order_moves(')
end = s.index('\nvoid Searcher::set_position_history', start)
old_block = s[start:end]
new_block = '''void Searcher::order_moves(core::Board& board, std::vector<core::Move>& moves, core::Move tt_move, int ply) {
    nn::NeuralOutput neural_output;
    bool have_policy = false;
    if (config_.neural_policy && ply <= config_.neural_policy_max_ply && neural_ready()) {
        try {
            const auto neural_started = std::chrono::steady_clock::now();
            neural_output = neural_->evaluate(board);
            stats_.neural_inference_us += static_cast<std::uint64_t>(
                std::chrono::duration_cast<std::chrono::microseconds>(
                    std::chrono::steady_clock::now() - neural_started).count());
            ++stats_.neural_evaluations;
            have_policy = true;
        } catch (...) {}
    }
    std::stable_sort(moves.begin(), moves.end(), [&](core::Move a, core::Move b) {
        auto score = [&](core::Move move) {
            long long value = move_order_score(board, move, tt_move, ply);
            if (have_policy) {
                const float logit = nn::policy_logit_for_move(neural_output, move);
                if (std::isfinite(logit)) value += static_cast<long long>(config_.neural_policy_scale * logit);
            }
            return value;
        };
        return score(a) > score(b);
    });
}'''
s = s[:start] + new_block + s[end:]

s = s.replace(
'''    reset_heuristics();
    root_neural_order_.clear();
    selective_policy_calls_used_ = 0;
    start_time_ = std::chrono::steady_clock::now();''',
'''    reset_heuristics();
    root_classical_order_.clear();
    root_neural_order_.clear();
    start_time_ = std::chrono::steady_clock::now();''',
1)

# Restore all order_moves call signatures.
s = s.replace('order_moves(board, moves, tt_move, 0, false);', 'order_moves(board, moves, tt_move, 0);')
s = s.replace('order_moves(board, moves, tt_move, ply, true);', 'order_moves(board, moves, tt_move, ply);')
s = s.replace('order_moves(board, moves, core::Move{}, ply, false);', 'order_moves(board, moves, core::Move{}, ply);')

# Capture the real non-neural root ordering before root policy changes it.
needle = '''    order_moves(board, moves, tt_move, 0);

    // One neural inference on the current root position provides policy logits'''
replacement = '''    order_moves(board, moves, tt_move, 0);
    if (root_classical_order_.empty()) root_classical_order_ = moves;

    // One neural inference on the current root position provides policy logits'''
if needle not in s:
    raise SystemExit('root ordering marker not found')
s = s.replace(needle, replacement, 1)

# Remove v2 budget accounting from the root inference.
s = s.replace('''            try {
                ++selective_policy_calls_used_;
                const auto neural_started = std::chrono::steady_clock::now();''',
'''            try {
                const auto neural_started = std::chrono::steady_clock::now();''', 1)

# Add final-best-move rank diagnostics before stats are copied into SearchResult.
needle = '''    stats_.nps = elapsed_us > 0
        ? static_cast<std::uint64_t>((stats_.nodes * 1'000'000ULL) / static_cast<std::uint64_t>(elapsed_us))
        : stats_.nodes;
    best.stats = stats_;'''
replacement = '''    stats_.nps = elapsed_us > 0
        ? static_cast<std::uint64_t>((stats_.nodes * 1'000'000ULL) / static_cast<std::uint64_t>(elapsed_us))
        : stats_.nodes;

    auto rank_in = [](const std::vector<core::Move>& ordered, core::Move move) -> int {
        if (move.raw() == 0) return 0;
        const auto it = std::find(ordered.begin(), ordered.end(), move);
        return it == ordered.end() ? 0 : static_cast<int>(std::distance(ordered.begin(), it)) + 1;
    };
    stats_.root_classical_best_rank = rank_in(root_classical_order_, best.best_move);
    stats_.root_policy_best_rank = rank_in(root_neural_order_, best.best_move);
    if (stats_.root_classical_best_rank > 0 && stats_.root_policy_best_rank > 0) {
        stats_.root_policy_rank_gain = stats_.root_classical_best_rank - stats_.root_policy_best_rank;
    }
    best.stats = stats_;'''
if needle not in s:
    raise SystemExit('stats marker not found')
s = s.replace(needle, replacement, 1)
p.write_text(s)

u = Path('src/uci/uci_loop.cpp')
s = u.read_text()
needle = '''                    << " neural_us=" << result.stats.neural_inference_us
                    << " neural_ms=" << neural_ms
                    << " neural_share_pct=" << neural_share;'''
replacement = '''                    << " neural_us=" << result.stats.neural_inference_us
                    << " neural_ms=" << neural_ms
                    << " neural_share_pct=" << neural_share
                    << " root_classical_rank=" << result.stats.root_classical_best_rank
                    << " root_policy_rank=" << result.stats.root_policy_best_rank
                    << " root_rank_gain=" << result.stats.root_policy_rank_gain;'''
if needle not in s:
    raise SystemExit('uci profile marker not found')
s = s.replace(needle, replacement, 1)
u.write_text(s)

m = Path('python/match_runner/match.py')
s = m.read_text()
needle = '''                print(
                    "       nc_profile avg: "
                    f"moves={len(profiles)} depth={avg('depth'):.2f} seldepth={avg('seldepth'):.2f} "
                    f"nodes={avg('nodes'):.0f} nps={avg('nps'):.0f} "
                    f"neural_calls={avg('neural_calls'):.1f} neural_ms={avg('neural_ms'):.1f} "
                    f"neural_share={avg('neural_share_pct'):.1f}% avg_call_us={avg('avg_neural_us'):.0f}"
                )'''
replacement = '''                print(
                    "       nc_profile avg: "
                    f"moves={len(profiles)} depth={avg('depth'):.2f} seldepth={avg('seldepth'):.2f} "
                    f"nodes={avg('nodes'):.0f} nps={avg('nps'):.0f} "
                    f"neural_calls={avg('neural_calls'):.1f} neural_ms={avg('neural_ms'):.1f} "
                    f"neural_share={avg('neural_share_pct'):.1f}% avg_call_us={avg('avg_neural_us'):.0f}"
                )
                ranked = [p for p in profiles if p.get('root_classical_rank', 0) > 0 and p.get('root_policy_rank', 0) > 0]
                if ranked:
                    improved = sum(p['root_rank_gain'] > 0 for p in ranked)
                    same = sum(p['root_rank_gain'] == 0 for p in ranked)
                    worsened = sum(p['root_rank_gain'] < 0 for p in ranked)
                    print(
                        "       root_policy: "
                        f"classical_rank={sum(p['root_classical_rank'] for p in ranked)/len(ranked):.2f} "
                        f"policy_rank={sum(p['root_policy_rank'] for p in ranked)/len(ranked):.2f} "
                        f"gain={sum(p['root_rank_gain'] for p in ranked)/len(ranked):+.2f} "
                        f"improved={100.0*improved/len(ranked):.1f}% "
                        f"same={100.0*same/len(ranked):.1f}% worsened={100.0*worsened/len(ranked):.1f}%"
                    )'''
if needle not in s:
    raise SystemExit('match profile print marker not found')
s = s.replace(needle, replacement, 1)
m.write_text(s)
