#include "neurochess/search/searcher.h"

#include "neurochess/core/move_generator.h"

#include <algorithm>
#include <bit>
#include <cmath>

namespace neurochess::search {
namespace {

using namespace neurochess::core;

constexpr int piece_value(PieceType type) noexcept {
    switch (type) {
        case PieceType::Pawn:   return 100;
        case PieceType::Knight: return 320;
        case PieceType::Bishop: return 330;
        case PieceType::Rook:   return 500;
        case PieceType::Queen:  return 900;
        case PieceType::King:   return 20'000;
        case PieceType::None:   return 0;
    }
    return 0;
}

bool contains_move(const std::vector<Move>& moves, Move move) {
    return std::find(moves.begin(), moves.end(), move) != moves.end();
}

bool is_quiet(Move move) noexcept {
    return !move.is_capture() && !move.is_promotion();
}

} // namespace

Searcher::Searcher(std::size_t tt_megabytes,
                   EvaluationConfig evaluation_config,
                   SearchConfig search_config)
    : evaluator_(evaluation_config), neural_(nn::make_neural_evaluator()), tt_(tt_megabytes), config_(search_config) {}

bool Searcher::load_neural_model(const std::string& path) {
    return neural_ && neural_->load_model(path);
}

bool Searcher::neural_ready() const noexcept {
    return neural_ && neural_->is_ready();
}

std::string Searcher::neural_backend() const {
    return neural_ ? neural_->backend_name() : "none";
}

int Searcher::static_evaluate(core::Board& board) {
    const int classical = evaluator_.evaluate(board);
    if (!config_.neural_value || !neural_ready()) return classical;
    try {
        ++stats_.neural_evaluations;
        const int neural_cp = nn::wdl_to_centipawns(neural_->evaluate(board));
        const int blend = std::clamp(config_.neural_value_blend_percent, 0, 100);
        return (classical * (100 - blend) + neural_cp * blend) / 100;
    } catch (...) {
        return classical;
    }
}

void Searcher::order_moves(core::Board& board, std::vector<core::Move>& moves, core::Move tt_move, int ply) {
    nn::NeuralOutput neural_output;
    bool have_policy = false;
    if (config_.neural_policy && ply <= config_.neural_policy_max_ply && neural_ready()) {
        try {
            neural_output = neural_->evaluate(board);
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
}

void Searcher::set_position_history(std::vector<std::uint64_t> hashes) {
    prior_history_ = std::move(hashes);
}

void Searcher::clear_position_history() noexcept {
    prior_history_.clear();
}

void Searcher::reset_heuristics() noexcept {
    killers_ = {};
    history_ = {};
}

SearchResult Searcher::search(core::Board& board, SearchLimits limits) {
    stop_requested_.store(false, std::memory_order_relaxed);
    aborted_ = false;
    limits_ = limits;
    if (limits_.max_depth <= 0 && limits_.max_nodes == 0 && limits_.max_time.count() <= 0) {
        limits_.max_depth = 6;
    }

    stats_ = {};
    reset_heuristics();
    start_time_ = std::chrono::steady_clock::now();
    search_history_ = prior_history_;
    search_history_.push_back(board.zobrist_key());

    SearchResult best{};
    const auto initial_legal_moves = core::MoveGenerator::legal(board);
    if (initial_legal_moves.empty()) {
        best.score = board.in_check(board.side_to_move()) ? -MateScore : 0;
        best.completed = true;
    } else if (board.halfmove_clock() >= 100 || is_repetition(board.zobrist_key())
               || is_insufficient_material(board)) {
        best.best_move = initial_legal_moves.front();
        best.score = 0;
        best.completed = true;
    }

    const bool root_terminal = best.completed;
    const int maximum_depth = limits_.max_depth > 0 ? std::min(limits_.max_depth, MaxPly - 1)
                                                    : MaxPly - 1;
    int previous_score = 0;

    for (int depth = 1; depth <= maximum_depth && !root_terminal; ++depth) {
        int alpha = -Infinity;
        int beta = Infinity;
        if (config_.aspiration_windows && depth >= 3) {
            const int window = std::max(1, config_.aspiration_window_cp);
            alpha = std::max(-Infinity, previous_score - window);
            beta = std::min(Infinity, previous_score + window);
        }

        core::Move iteration_best_move{};
        int iteration_score = search_root(board, depth, alpha, beta, iteration_best_move);
        if (aborted_) break;

        if (config_.aspiration_windows && depth >= 3
            && (iteration_score <= alpha || iteration_score >= beta)) {
            ++stats_.aspiration_researches;
            iteration_score = search_root(board, depth, -Infinity, Infinity, iteration_best_move);
            if (aborted_) break;
        }

        best.best_move = iteration_best_move;
        best.score = iteration_score;
        best.completed = true;
        previous_score = iteration_score;
        stats_.depth = depth;
        best.principal_variation = extract_pv(board, depth);

        if (std::abs(best.score) >= MateThreshold) break;
        if (limits_.max_depth <= 0 && should_stop()) break;
    }

    const auto now = std::chrono::steady_clock::now();
    stats_.elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - start_time_);
    const auto elapsed_us = std::chrono::duration_cast<std::chrono::microseconds>(now - start_time_).count();
    stats_.nps = elapsed_us > 0
        ? static_cast<std::uint64_t>((stats_.nodes * 1'000'000ULL) / static_cast<std::uint64_t>(elapsed_us))
        : stats_.nodes;
    best.stats = stats_;
    return best;
}

int Searcher::search_root(core::Board& board, int depth, int alpha, int beta, core::Move& best_move) {
    auto moves = core::MoveGenerator::legal(board);
    if (moves.empty()) return board.in_check(board.side_to_move()) ? -MateScore : 0;

    core::Move tt_move{};
    if (const auto entry = tt_.probe(board.zobrist_key())) tt_move = entry->best_move;
    order_moves(board, moves, tt_move, 0);

    const int alpha_original = alpha;
    int best_score = -Infinity;
    for (const core::Move move : moves) {
        if (should_stop()) {
            aborted_ = true;
            return 0;
        }
        const core::UndoState undo = board.make_move(move);
        search_history_.push_back(board.zobrist_key());
        const int score = -negamax(board, depth - 1, 1, -beta, -alpha);
        search_history_.pop_back();
        board.unmake_move(move, undo);
        if (aborted_) return 0;

        if (score > best_score) {
            best_score = score;
            best_move = move;
        }
        alpha = std::max(alpha, score);
        if (alpha >= beta) break;
    }

    BoundType bound = BoundType::Exact;
    if (best_score <= alpha_original) bound = BoundType::Upper;
    else if (best_score >= beta) bound = BoundType::Lower;
    tt_.store(board.zobrist_key(), depth, score_to_tt(best_score, 0), bound, best_move);
    return best_score;
}

int Searcher::negamax(core::Board& board, int depth, int ply, int alpha, int beta, bool allow_null) {
    if (ply >= MaxPly - 1) return static_evaluate(board);
    ++stats_.nodes;
    stats_.selective_depth = std::max(stats_.selective_depth, ply);
    if (should_stop()) {
        aborted_ = true;
        return 0;
    }

    if (board.halfmove_clock() >= 100 || is_repetition(board.zobrist_key())
        || is_insufficient_material(board)) {
        return 0;
    }

    const int alpha_original = alpha;
    core::Move tt_move{};
    if (const auto entry = tt_.probe(board.zobrist_key())) {
        ++stats_.tt_hits;
        tt_move = entry->best_move;
        if (entry->depth >= depth) {
            const int tt_score = score_from_tt(entry->score, ply);
            if (entry->bound == BoundType::Exact) return tt_score;
            if (entry->bound == BoundType::Lower && tt_score >= beta) return tt_score;
            if (entry->bound == BoundType::Upper && tt_score <= alpha) return tt_score;
        }
    }

    if (depth <= 0) return quiescence(board, ply, alpha, beta);

    const bool in_check = board.in_check(board.side_to_move());
    const int static_eval = in_check ? -Infinity : evaluator_.evaluate(board);

    if (config_.razoring && !in_check && depth <= 2
        && static_eval + config_.razor_margin_cp * depth <= alpha) {
        const int qscore = quiescence(board, ply, alpha, beta);
        if (aborted_) return 0;
        if (qscore <= alpha) {
            ++stats_.razor_prunes;
            return qscore;
        }
    }

    if (config_.null_move_pruning && allow_null && !in_check
        && depth >= config_.null_move_min_depth
        && beta < MateThreshold
        && has_non_pawn_material(board, board.side_to_move())) {
        const core::UndoState undo = board.make_null_move();
        const int reduction = std::max(1, config_.null_move_reduction + depth / 6);
        const int null_depth = std::max(0, depth - 1 - reduction);
        const int score = -negamax(board, null_depth, ply + 1, -beta, -beta + 1, false);
        board.unmake_null_move(undo);
        if (aborted_) return 0;
        if (score >= beta) {
            ++stats_.null_move_prunes;
            return score;
        }
    }

    auto moves = core::MoveGenerator::legal(board);
    if (moves.empty()) return in_check ? (-MateScore + ply) : 0;

    order_moves(board, moves, tt_move, ply);

    int best_score = -Infinity;
    core::Move best_move{};
    bool searched_any = false;
    int move_index = 0;
    const core::Color us = board.side_to_move();

    for (const core::Move move : moves) {
        const bool quiet = is_quiet(move);

        if (config_.futility_pruning && !in_check && depth == 1 && quiet
            && move_index > 0 && static_eval + config_.futility_margin_cp <= alpha) {
            ++stats_.futility_prunes;
            ++move_index;
            continue;
        }

        const core::UndoState undo = board.make_move(move);
        search_history_.push_back(board.zobrist_key());

        int score = 0;
        const bool can_reduce = config_.late_move_reductions && quiet && !in_check
            && depth >= config_.lmr_min_depth && move_index >= config_.lmr_move_threshold;
        if (can_reduce) {
            int reduction = 1;
            if (depth >= 6 && move_index >= 8) reduction = 2;
            const int reduced_depth = std::max(0, depth - 1 - reduction);
            ++stats_.lmr_reductions;
            score = -negamax(board, reduced_depth, ply + 1, -beta, -alpha);
            if (!aborted_ && score > alpha) {
                score = -negamax(board, depth - 1, ply + 1, -beta, -alpha);
            }
        } else {
            score = -negamax(board, depth - 1, ply + 1, -beta, -alpha);
        }

        search_history_.pop_back();
        board.unmake_move(move, undo);
        if (aborted_) return 0;
        searched_any = true;

        if (score > best_score) {
            best_score = score;
            best_move = move;
        }
        alpha = std::max(alpha, score);
        if (alpha >= beta) {
            ++stats_.beta_cutoffs;
            if (quiet) record_quiet_cutoff(us, move, ply, depth);
            break;
        }
        ++move_index;
    }

    if (!searched_any) return static_eval;

    BoundType bound = BoundType::Exact;
    if (best_score <= alpha_original) bound = BoundType::Upper;
    else if (best_score >= beta) bound = BoundType::Lower;
    tt_.store(board.zobrist_key(), depth, score_to_tt(best_score, ply), bound, best_move);
    return best_score;
}

int Searcher::quiescence(core::Board& board, int ply, int alpha, int beta) {
    if (ply >= MaxPly - 1) return static_evaluate(board);
    ++stats_.nodes;
    ++stats_.qnodes;
    stats_.selective_depth = std::max(stats_.selective_depth, ply);
    if (should_stop()) {
        aborted_ = true;
        return 0;
    }

    if (board.halfmove_clock() >= 100 || is_repetition(board.zobrist_key())
        || is_insufficient_material(board)) return 0;

    const bool in_check = board.in_check(board.side_to_move());
    if (!in_check) {
        const int stand_pat = static_evaluate(board);
        if (stand_pat >= beta) return stand_pat;
        alpha = std::max(alpha, stand_pat);
    }

    auto moves = core::MoveGenerator::legal(board);
    if (moves.empty()) return in_check ? -MateScore + ply : 0;

    if (!in_check) {
        std::erase_if(moves, [](core::Move move) {
            return !move.is_capture() && !move.is_promotion();
        });
        if (moves.empty()) return alpha;
    }

    order_moves(board, moves, core::Move{}, ply);

    for (const core::Move move : moves) {
        const core::UndoState undo = board.make_move(move);
        search_history_.push_back(board.zobrist_key());
        const int score = -quiescence(board, ply + 1, -beta, -alpha);
        search_history_.pop_back();
        board.unmake_move(move, undo);
        if (aborted_) return 0;
        if (score >= beta) return score;
        alpha = std::max(alpha, score);
    }
    return alpha;
}

bool Searcher::should_stop() {
    if (stop_requested_.load(std::memory_order_relaxed)) return true;
    if (limits_.max_nodes > 0 && stats_.nodes >= limits_.max_nodes) return true;
    if (limits_.max_time.count() > 0
        && std::chrono::steady_clock::now() - start_time_ >= limits_.max_time) return true;
    return false;
}

bool Searcher::is_repetition(std::uint64_t key) const noexcept {
    int occurrences = 0;
    for (const auto historic_key : search_history_) {
        if (historic_key == key && ++occurrences >= 3) return true;
    }
    return false;
}

bool Searcher::is_insufficient_material(const core::Board& board) noexcept {
    if (board.pieces(core::Piece::WhitePawn) || board.pieces(core::Piece::BlackPawn)
        || board.pieces(core::Piece::WhiteRook) || board.pieces(core::Piece::BlackRook)
        || board.pieces(core::Piece::WhiteQueen) || board.pieces(core::Piece::BlackQueen)) return false;

    const int white_knights = std::popcount(board.pieces(core::Piece::WhiteKnight));
    const int black_knights = std::popcount(board.pieces(core::Piece::BlackKnight));
    const int white_bishops = std::popcount(board.pieces(core::Piece::WhiteBishop));
    const int black_bishops = std::popcount(board.pieces(core::Piece::BlackBishop));
    const int minors = white_knights + black_knights + white_bishops + black_bishops;
    if (minors <= 1) return true;
    if (minors == 2 && white_bishops == 1 && black_bishops == 1
        && white_knights == 0 && black_knights == 0) {
        const int wb = std::countr_zero(board.pieces(core::Piece::WhiteBishop));
        const int bb = std::countr_zero(board.pieces(core::Piece::BlackBishop));
        return ((((wb % 8) + (wb / 8)) & 1) == (((bb % 8) + (bb / 8)) & 1));
    }
    return false;
}

bool Searcher::has_non_pawn_material(const core::Board& board, core::Color color) noexcept {
    return board.pieces(core::make_piece(color, core::PieceType::Knight))
        || board.pieces(core::make_piece(color, core::PieceType::Bishop))
        || board.pieces(core::make_piece(color, core::PieceType::Rook))
        || board.pieces(core::make_piece(color, core::PieceType::Queen));
}

int Searcher::score_to_tt(int score, int ply) noexcept {
    if (score >= MateThreshold) return score + ply;
    if (score <= -MateThreshold) return score - ply;
    return score;
}

int Searcher::score_from_tt(int score, int ply) noexcept {
    if (score >= MateThreshold) return score - ply;
    if (score <= -MateThreshold) return score + ply;
    return score;
}

int Searcher::move_order_score(const core::Board& board, core::Move move,
                               core::Move tt_move, int ply) const noexcept {
    if (move == tt_move && tt_move.raw() != 0) return 2'000'000;

    int score = 0;
    if (move.is_promotion()) score += 900'000 + piece_value(move.promotion());
    if (move.is_capture()) {
        core::Piece victim = board.piece_at(move.to());
        if (move.flag() == core::MoveFlag::EnPassant) {
            victim = core::make_piece(core::opposite(board.side_to_move()), core::PieceType::Pawn);
        }
        const core::Piece attacker = board.piece_at(move.from());
        score += 1'000'000 + 10 * piece_value(core::piece_type(victim)) - piece_value(core::piece_type(attacker));
        return score;
    }

    if (config_.killer_moves && ply >= 0 && ply < MaxPly) {
        if (move == killers_[ply][0] && move.raw() != 0) score += 800'000;
        else if (move == killers_[ply][1] && move.raw() != 0) score += 700'000;
    }
    if (config_.history_heuristic) {
        score += history_[core::color_index(board.side_to_move())][move.from()][move.to()];
    }
    return score;
}

void Searcher::record_quiet_cutoff(core::Color side, core::Move move, int ply, int depth) noexcept {
    if (config_.killer_moves && ply >= 0 && ply < MaxPly && move != killers_[ply][0]) {
        killers_[ply][1] = killers_[ply][0];
        killers_[ply][0] = move;
    }
    if (config_.history_heuristic) {
        int& value = history_[core::color_index(side)][move.from()][move.to()];
        const int bonus = depth * depth;
        value = std::min(200'000, value + bonus);
    }
}

std::vector<core::Move> Searcher::extract_pv(const core::Board& root, int max_length) const {
    core::Board board = root;
    std::vector<core::Move> pv;
    pv.reserve(static_cast<std::size_t>(std::max(0, max_length)));

    for (int ply = 0; ply < max_length; ++ply) {
        const auto entry = tt_.probe(board.zobrist_key());
        if (!entry || entry->best_move.raw() == 0) break;
        const auto legal = core::MoveGenerator::legal(board);
        if (!contains_move(legal, entry->best_move)) break;
        pv.push_back(entry->best_move);
        [[maybe_unused]] const core::UndoState undo = board.make_move(entry->best_move);
    }
    return pv;
}

} // namespace neurochess::search
