from pathlib import Path

p = Path('src/search/searcher.cpp')
s = p.read_text()
start_marker = '    // Neural root guidance is computed once per search, then reused at every\n'
end_marker = '    const int alpha_original = alpha;\n'
start = s.index(start_marker)
end = s.index(end_marker, start)
replacement = '''    // One neural inference on the current root position provides policy logits
    // for every legal move. Cache that ordering for the whole iterative-
    // deepening search. TT remains the highest-priority root move; policy then
    // orders the remaining moves, while actual tree scores stay classical.
    if (config_.neural_value && neural_ready() && config_.neural_value_blend_percent > 0) {
        if (root_neural_order_.empty()) {
            try {
                const auto neural_started = std::chrono::steady_clock::now();
                const auto neural_output = neural_->evaluate(board);
                stats_.neural_inference_us += static_cast<std::uint64_t>(
                    std::chrono::duration_cast<std::chrono::microseconds>(
                        std::chrono::steady_clock::now() - neural_started).count());
                ++stats_.neural_evaluations;

                std::vector<std::pair<core::Move, float>> policy_ranked;
                policy_ranked.reserve(moves.size());
                for (const core::Move move : moves) {
                    float logit = nn::policy_logit_for_move(neural_output, move);
                    if (!std::isfinite(logit)) logit = -std::numeric_limits<float>::infinity();
                    policy_ranked.emplace_back(move, logit);
                }
                std::stable_sort(policy_ranked.begin(), policy_ranked.end(), [](const auto& a, const auto& b) {
                    return a.second > b.second;
                });
                root_neural_order_.reserve(policy_ranked.size());
                for (const auto& item : policy_ranked) root_neural_order_.push_back(item.first);
            } catch (...) {
                // If inference fails, normal TT/history ordering remains intact.
            }
        }

        if (!root_neural_order_.empty()) {
            std::vector<core::Move> reordered;
            reordered.reserve(moves.size());
            if (tt_move.raw() != 0 && contains_move(moves, tt_move)) reordered.push_back(tt_move);
            for (const core::Move preferred : root_neural_order_) {
                if (preferred != tt_move && contains_move(moves, preferred)) reordered.push_back(preferred);
            }
            for (const core::Move move : moves) {
                if (!contains_move(reordered, move)) reordered.push_back(move);
            }
            moves.swap(reordered);
        }
    }

'''
s = s[:start] + replacement + s[end:]
if '#include <limits>' not in s:
    s = s.replace('#include <cmath>\n', '#include <cmath>\n#include <limits>\n', 1)
p.write_text(s)
