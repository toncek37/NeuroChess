#include "neurochess/uci/uci_loop.h"

#include "neurochess/core/board.h"
#include "neurochess/core/engine_info.h"
#include "neurochess/core/move_generator.h"
#include "neurochess/search/searcher.h"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <istream>
#include <memory>
#include <mutex>
#include <optional>
#include <ostream>
#include <sstream>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

namespace neurochess::uci {
namespace {

using neurochess::core::Board;
using neurochess::core::Color;
using neurochess::core::Move;
using neurochess::core::MoveGenerator;
using neurochess::search::SearchConfig;
using neurochess::search::SearchLimits;
using neurochess::search::SearchResult;
using neurochess::search::Searcher;

std::string lower_copy(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

bool parse_bool(std::string_view text, bool fallback) {
    std::string value(text);
    value = lower_copy(value);
    if (value == "true" || value == "1" || value == "on" || value == "yes") return true;
    if (value == "false" || value == "0" || value == "off" || value == "no") return false;
    return fallback;
}

std::optional<int> parse_int(std::string_view text) {
    if (text.empty()) return std::nullopt;
    const std::string storage(text);
    char* end = nullptr;
    const long value = std::strtol(storage.c_str(), &end, 10);
    if (!end || *end != '\0') return std::nullopt;
    return static_cast<int>(value);
}

std::optional<std::uint64_t> parse_u64(std::string_view text) {
    if (text.empty()) return std::nullopt;
    const std::string storage(text);
    char* end = nullptr;
    const unsigned long long value = std::strtoull(storage.c_str(), &end, 10);
    if (!end || *end != '\0') return std::nullopt;
    return static_cast<std::uint64_t>(value);
}

int mate_distance_from_score(int score) {
    const int plies = Searcher::MateScore - std::abs(score);
    const int moves = (plies + 1) / 2;
    return score >= 0 ? moves : -moves;
}

class UciSession {
public:
    explicit UciSession(std::ostream& out)
        : out_(out), searcher_(std::make_unique<Searcher>(hash_megabytes_, neurochess::search::EvaluationConfig{}, config_)) {}

    ~UciSession() { stop_search(true); }

    void command(const std::string& line) {
        std::istringstream input(line);
        std::string token;
        if (!(input >> token)) return;

        if (token == "uci") {
            identify();
        } else if (token == "isready") {
            write_line("readyok");
        } else if (token == "ucinewgame") {
            stop_search(true);
            board_ = Board{};
            position_history_.clear();
            searcher_->clear_position_history();
            searcher_->clear_tt();
        } else if (token == "position") {
            stop_search(true);
            set_position(input);
        } else if (token == "go") {
            start_search(input);
        } else if (token == "stop") {
            stop_search(true);
        } else if (token == "setoption") {
            stop_search(true);
            set_option(input);
        } else if (token == "quit") {
            stop_search(true);
            quit_ = true;
        } else if (token == "help") {
            write_line("info string NeuroChess supports UCI: uci, isready, ucinewgame, position, go, stop, setoption, quit");
        } else if (token == "debug") {
            // UCI permits this command. Debug output is intentionally not yet verbose.
        } else if (token == "nc_fen") {
            write_line("info string nc_fen " + board_.to_fen());
        } else if (token == "nc_legalmoves") {
            const auto moves = MoveGenerator::legal(board_);
            std::string line_out = "info string nc_legalmoves";
            for (const Move move : moves) line_out += " " + move.uci();
            write_line(line_out);
        } else if (token == "nc_incheck") {
            write_line(std::string("info string nc_incheck ") +
                       (board_.in_check(board_.side_to_move()) ? "1" : "0"));
        } else {
            write_line("info string unknown command: " + line);
        }
    }

    [[nodiscard]] bool quit_requested() const noexcept { return quit_; }

    void finish_input() {
        if (search_thread_.joinable()) search_thread_.join();
    }

private:
    std::ostream& out_;
    std::mutex output_mutex_;
    Board board_{};
    std::vector<std::uint64_t> position_history_;
    SearchConfig config_{};
    std::size_t hash_megabytes_ = 16;
    std::string neural_model_;
    std::unique_ptr<Searcher> searcher_;
    std::thread search_thread_;
    bool quit_ = false;

    void write_line(const std::string& text) {
        std::lock_guard<std::mutex> lock(output_mutex_);
        out_ << text << '\n';
        out_.flush();
    }

    void identify() {
        write_line("id name " + std::string(neurochess::core::EngineInfo::name()) + " "
                   + std::string(neurochess::core::EngineInfo::version()));
        write_line("id author " + std::string(neurochess::core::EngineInfo::author()));
        write_line("option name Hash type spin default 16 min 1 max 4096");
        write_line("option name Clear Hash type button");
        write_line("option name Killer Moves type check default true");
        write_line("option name History Heuristic type check default true");
        write_line("option name Null Move Pruning type check default true");
        write_line("option name Late Move Reductions type check default true");
        write_line("option name Aspiration Windows type check default true");
        write_line("option name Futility Pruning type check default true");
        write_line("option name Razoring type check default true");
        write_line("option name Neural Model type string default <empty>");
        write_line("option name Neural Policy type check default false");
        write_line("option name Neural Policy Max Ply type spin default 2 min 0 max 16");
        write_line("option name Neural Value type check default false");
        write_line("option name Neural Value Blend type spin default 50 min 0 max 100");
        write_line("uciok");
    }

    void set_position(std::istringstream& input) {
        std::string token;
        if (!(input >> token)) return;

        Board next;
        if (token == "startpos") {
            next = Board{};
        } else if (token == "fen") {
            std::vector<std::string> fields;
            for (int i = 0; i < 6 && input >> token; ++i) fields.push_back(token);
            if (fields.size() != 6) {
                write_line("info string invalid position fen: expected 6 FEN fields");
                return;
            }
            std::ostringstream fen;
            for (std::size_t i = 0; i < fields.size(); ++i) {
                if (i) fen << ' ';
                fen << fields[i];
            }
            try {
                next = Board::from_fen(fen.str());
            } catch (const std::exception& ex) {
                write_line(std::string("info string invalid FEN: ") + ex.what());
                return;
            }
        } else {
            write_line("info string invalid position command");
            return;
        }

        position_history_.clear();
        if (input >> token) {
            if (token != "moves") {
                write_line("info string expected 'moves' after position");
                return;
            }
            while (input >> token) {
                auto legal_moves = MoveGenerator::legal(next);
                const auto it = std::find_if(legal_moves.begin(), legal_moves.end(), [&](Move move) {
                    return move.uci() == token;
                });
                if (it == legal_moves.end()) {
                    write_line("info string illegal move in position command: " + token);
                    return;
                }
                position_history_.push_back(next.zobrist_key());
                (void)next.make_move(*it);
            }
        }

        board_ = next;
        searcher_->set_position_history(position_history_);
    }

    void set_option(std::istringstream& input) {
        std::string token;
        if (!(input >> token) || token != "name") return;

        std::vector<std::string> name_parts;
        std::vector<std::string> value_parts;
        bool reading_value = false;
        while (input >> token) {
            if (token == "value" && !reading_value) {
                reading_value = true;
                continue;
            }
            (reading_value ? value_parts : name_parts).push_back(token);
        }

        auto join = [](const std::vector<std::string>& parts) {
            std::string result;
            for (std::size_t i = 0; i < parts.size(); ++i) {
                if (i) result += ' ';
                result += parts[i];
            }
            return result;
        };

        const std::string name = lower_copy(join(name_parts));
        const std::string value = join(value_parts);

        if (name == "clear hash") {
            searcher_->clear_tt();
            return;
        }
        if (name == "hash") {
            const auto parsed = parse_int(value);
            if (!parsed) return;
            hash_megabytes_ = static_cast<std::size_t>(std::clamp(*parsed, 1, 4096));
            searcher_ = std::make_unique<Searcher>(hash_megabytes_, neurochess::search::EvaluationConfig{}, config_);
            searcher_->set_position_history(position_history_);
            if (!neural_model_.empty()) (void)searcher_->load_neural_model(neural_model_);
            return;
        }

        auto update_bool = [&](bool& field) { field = parse_bool(value, field); };
        if (name == "killer moves") update_bool(config_.killer_moves);
        else if (name == "history heuristic") update_bool(config_.history_heuristic);
        else if (name == "null move pruning") update_bool(config_.null_move_pruning);
        else if (name == "late move reductions") update_bool(config_.late_move_reductions);
        else if (name == "aspiration windows") update_bool(config_.aspiration_windows);
        else if (name == "futility pruning") update_bool(config_.futility_pruning);
        else if (name == "razoring") update_bool(config_.razoring);
        else if (name == "neural policy") update_bool(config_.neural_policy);
        else if (name == "neural policy max ply") {
            if (const auto parsed = parse_int(value)) config_.neural_policy_max_ply = std::clamp(*parsed, 0, 16);
        } else if (name == "neural value") update_bool(config_.neural_value);
        else if (name == "neural value blend") {
            if (const auto parsed = parse_int(value)) config_.neural_value_blend_percent = std::clamp(*parsed, 0, 100);
        } else if (name == "neural model") {
            neural_model_ = value;
            const bool ok = !neural_model_.empty() && searcher_->load_neural_model(neural_model_);
            write_line(std::string("info string neural model ") + (ok ? "loaded via " + searcher_->neural_backend() : "not loaded"));
            return;
        } else {
            write_line("info string unknown option: " + join(name_parts));
            return;
        }
        searcher_->set_config(config_);
    }

    static std::chrono::milliseconds choose_clock_budget(const Board& board,
                                                          int wtime, int btime,
                                                          int winc, int binc,
                                                          int moves_to_go) {
        const bool white = board.side_to_move() == Color::White;
        const int remaining = std::max(0, white ? wtime : btime);
        const int increment = std::max(0, white ? winc : binc);
        if (remaining <= 0) return std::chrono::milliseconds{1};

        const int divisor = moves_to_go > 0 ? std::max(1, moves_to_go) : 30;
        long long budget = remaining / divisor + (increment * 4LL) / 5LL;
        const long long reserve = std::max(10LL, remaining / 20LL);
        budget = std::min(budget, std::max(1LL, static_cast<long long>(remaining) - reserve));
        budget = std::max(1LL, budget);
        return std::chrono::milliseconds{budget};
    }

    void start_search(std::istringstream& input) {
        stop_search(true);

        SearchLimits limits{};
        int wtime = -1;
        int btime = -1;
        int winc = 0;
        int binc = 0;
        int moves_to_go = 0;
        bool infinite = false;

        std::string token;
        while (input >> token) {
            if (token == "depth") {
                if (input >> token) if (const auto v = parse_int(token)) limits.max_depth = std::max(1, *v);
            } else if (token == "movetime") {
                if (input >> token) if (const auto v = parse_int(token)) limits.max_time = std::chrono::milliseconds{std::max(1, *v)};
            } else if (token == "nodes") {
                if (input >> token) if (const auto v = parse_u64(token)) limits.max_nodes = std::max<std::uint64_t>(1, *v);
            } else if (token == "wtime") {
                if (input >> token) if (const auto v = parse_int(token)) wtime = *v;
            } else if (token == "btime") {
                if (input >> token) if (const auto v = parse_int(token)) btime = *v;
            } else if (token == "winc") {
                if (input >> token) if (const auto v = parse_int(token)) winc = *v;
            } else if (token == "binc") {
                if (input >> token) if (const auto v = parse_int(token)) binc = *v;
            } else if (token == "movestogo") {
                if (input >> token) if (const auto v = parse_int(token)) moves_to_go = *v;
            } else if (token == "infinite") {
                infinite = true;
            }
        }

        if (limits.max_time.count() <= 0 && (wtime >= 0 || btime >= 0)) {
            limits.max_time = choose_clock_budget(board_, wtime, btime, winc, binc, moves_to_go);
        }
        if (infinite && limits.max_depth <= 0 && limits.max_nodes == 0 && limits.max_time.count() <= 0) {
            limits.max_depth = Searcher::MaxPly - 1;
        }

        // Search owns a private board copy. The protocol thread remains free to
        // process stop/quit and to preserve the GUI's current position.
        Board search_board = board_;
        searcher_->set_position_history(position_history_);
        Searcher* active_searcher = searcher_.get();

        search_thread_ = std::thread([this, active_searcher, board = std::move(search_board), limits]() mutable {
            const SearchResult result = active_searcher->search(board, limits);
            emit_info(result);
            const std::string best = result.best_move.raw() != 0 ? result.best_move.uci() : "0000";
            write_line("bestmove " + best);
        });
    }

    void emit_info(const SearchResult& result) {
        std::ostringstream line;
        line << "info depth " << result.stats.depth
             << " seldepth " << result.stats.selective_depth;
        if (std::abs(result.score) >= Searcher::MateThreshold) {
            line << " score mate " << mate_distance_from_score(result.score);
        } else {
            line << " score cp " << result.score;
        }
        line << " nodes " << result.stats.nodes
             << " nps " << result.stats.nps
             << " time " << result.stats.elapsed.count();
        if (!result.principal_variation.empty()) {
            line << " pv";
            for (const Move move : result.principal_variation) line << ' ' << move.uci();
        }
        write_line(line.str());
        if (result.stats.neural_evaluations > 0) {
            write_line("info string neural_evals " + std::to_string(result.stats.neural_evaluations));
        }
    }

    void stop_search(bool request_stop) {
        if (!search_thread_.joinable()) return;
        if (request_stop) searcher_->request_stop();
        search_thread_.join();
    }
};

} // namespace

int run(std::istream& in, std::ostream& out) {
    UciSession session(out);
    std::string command;
    while (std::getline(in, command)) {
        session.command(command);
        if (session.quit_requested()) break;
    }
    session.finish_input();
    return 0;
}

} // namespace neurochess::uci
