from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:80]!r}")
    p.write_text(text.replace(old, new), encoding="utf-8")

# searcher.cpp: initialize backend + methods
replace("src/search/searcher.cpp",
'''    : evaluator_(evaluation_config), tt_(tt_megabytes), config_(search_config) {}\n''',
'''    : evaluator_(evaluation_config), neural_(nn::make_neural_evaluator()), tt_(tt_megabytes), config_(search_config) {}\n\nbool Searcher::load_neural_model(const std::string& path) {\n    return neural_ && neural_->load_model(path);\n}\n\nbool Searcher::neural_ready() const noexcept {\n    return neural_ && neural_->is_ready();\n}\n\nstd::string Searcher::neural_backend() const {\n    return neural_ ? neural_->backend_name() : "none";\n}\n\nint Searcher::static_evaluate(core::Board& board) {\n    const int classical = evaluator_.evaluate(board);\n    if (!config_.neural_value || !neural_ready()) return classical;\n    try {\n        ++stats_.neural_evaluations;\n        const int neural_cp = nn::wdl_to_centipawns(neural_->evaluate(board));\n        const int blend = std::clamp(config_.neural_value_blend_percent, 0, 100);\n        return (classical * (100 - blend) + neural_cp * blend) / 100;\n    } catch (...) {\n        return classical;\n    }\n}\n\nvoid Searcher::order_moves(core::Board& board, std::vector<core::Move>& moves, core::Move tt_move, int ply) {\n    nn::NeuralOutput neural_output;\n    bool have_policy = false;\n    if (config_.neural_policy && neural_ready()) {\n        try {\n            neural_output = neural_->evaluate(board);\n            ++stats_.neural_evaluations;\n            have_policy = true;\n        } catch (...) {}\n    }\n    std::stable_sort(moves.begin(), moves.end(), [&](core::Move a, core::Move b) {\n        auto score = [&](core::Move move) {\n            long long value = move_order_score(board, move, tt_move, ply);\n            if (have_policy) {\n                const float logit = nn::policy_logit_for_move(neural_output, move);\n                if (std::isfinite(logit)) value += static_cast<long long>(config_.neural_policy_scale * logit);\n            }\n            return value;\n        };\n        return score(a) > score(b);\n    });\n}\n''')

# Replace classical static/leaf eval paths.
text = Path("src/search/searcher.cpp").read_text(encoding="utf-8")
text = text.replace("return evaluator_.evaluate(board);", "return static_evaluate(board);")
text = text.replace("const int static_eval = in_check ? -Infinity : evaluator_.evaluate(board);", "const int static_eval = in_check ? -Infinity : static_evaluate(board);")
text = text.replace("const int stand_pat = evaluator_.evaluate(board);", "const int stand_pat = static_evaluate(board);")
# Replace three move sorting blocks with order_moves.
old_root = '''    std::stable_sort(moves.begin(), moves.end(), [&](core::Move a, core::Move b) {\n        return move_order_score(board, a, tt_move, 0) > move_order_score(board, b, tt_move, 0);\n    });'''
old_mid = '''    std::stable_sort(moves.begin(), moves.end(), [&](core::Move a, core::Move b) {\n        return move_order_score(board, a, tt_move, ply) > move_order_score(board, b, tt_move, ply);\n    });'''
old_q = '''    std::stable_sort(moves.begin(), moves.end(), [&](core::Move a, core::Move b) {\n        return move_order_score(board, a, core::Move{}, ply) > move_order_score(board, b, core::Move{}, ply);\n    });'''
for old, new in [(old_root, "    order_moves(board, moves, tt_move, 0);"), (old_mid, "    order_moves(board, moves, tt_move, ply);"), (old_q, "    order_moves(board, moves, core::Move{}, ply);")]:
    if old not in text:
        raise SystemExit("move ordering pattern missing")
    text = text.replace(old, new, 1)
Path("src/search/searcher.cpp").write_text(text, encoding="utf-8")

# UCI: advertise and configure model/policy/value.
replace("src/uci/uci_loop.cpp",
'''        write_line("option name Razoring type check default true");\n        write_line("uciok");''',
'''        write_line("option name Razoring type check default true");\n        write_line("option name Neural Model type string default <empty>");\n        write_line("option name Neural Policy type check default false");\n        write_line("option name Neural Value type check default false");\n        write_line("option name Neural Value Blend type spin default 50 min 0 max 100");\n        write_line("uciok");''')
replace("src/uci/uci_loop.cpp",
'''    std::size_t hash_megabytes_ = 16;\n    std::unique_ptr<Searcher> searcher_;''',
'''    std::size_t hash_megabytes_ = 16;\n    std::string neural_model_;\n    std::unique_ptr<Searcher> searcher_;''')
replace("src/uci/uci_loop.cpp",
'''            searcher_ = std::make_unique<Searcher>(hash_megabytes_, neurochess::search::EvaluationConfig{}, config_);\n            searcher_->set_position_history(position_history_);\n            return;''',
'''            searcher_ = std::make_unique<Searcher>(hash_megabytes_, neurochess::search::EvaluationConfig{}, config_);\n            searcher_->set_position_history(position_history_);\n            if (!neural_model_.empty()) (void)searcher_->load_neural_model(neural_model_);\n            return;''')
replace("src/uci/uci_loop.cpp",
'''        else if (name == "razoring") update_bool(config_.razoring);\n        else {''',
'''        else if (name == "razoring") update_bool(config_.razoring);\n        else if (name == "neural policy") update_bool(config_.neural_policy);\n        else if (name == "neural value") update_bool(config_.neural_value);\n        else if (name == "neural value blend") {\n            if (const auto parsed = parse_int(value)) config_.neural_value_blend_percent = std::clamp(*parsed, 0, 100);\n        } else if (name == "neural model") {\n            neural_model_ = value;\n            const bool ok = !neural_model_.empty() && searcher_->load_neural_model(neural_model_);\n            write_line(std::string("info string neural model ") + (ok ? "loaded via " + searcher_->neural_backend() : "not loaded"));\n            return;\n        } else {''')

# Emit neural inference count in UCI info.
replace("src/uci/uci_loop.cpp",
'''        line << " nodes " << result.stats.nodes\n             << " nps " << result.stats.nps''',
'''        line << " nodes " << result.stats.nodes\n             << " nps " << result.stats.nps\n             << " string neural_evals=" << result.stats.neural_evaluations''')

# CMake optional ONNX Runtime integration.
replace("CMakeLists.txt",
'''option(NEUROCHESS_BUILD_BENCHMARKS "Build NeuroChess benchmark tools" ON)\n''',
'''option(NEUROCHESS_BUILD_BENCHMARKS "Build NeuroChess benchmark tools" ON)\noption(NEUROCHESS_ENABLE_ONNX "Enable ONNX Runtime neural inference" OFF)\nset(ONNXRUNTIME_ROOT "" CACHE PATH "Path to extracted ONNX Runtime package")\n''')
replace("CMakeLists.txt",
'''target_include_directories(neurochess_engine\n    PUBLIC\n        ${PROJECT_SOURCE_DIR}/include\n)\n''',
'''target_include_directories(neurochess_engine\n    PUBLIC\n        ${PROJECT_SOURCE_DIR}/include\n)\n\nif(NEUROCHESS_ENABLE_ONNX)\n    if(NOT ONNXRUNTIME_ROOT)\n        message(FATAL_ERROR "NEUROCHESS_ENABLE_ONNX=ON requires -DONNXRUNTIME_ROOT=<onnxruntime package>")\n    endif()\n    target_compile_definitions(neurochess_engine PRIVATE NEUROCHESS_ENABLE_ONNX=1)\n    target_include_directories(neurochess_engine PRIVATE ${ONNXRUNTIME_ROOT}/include)\n    find_library(ONNXRUNTIME_LIBRARY onnxruntime PATHS ${ONNXRUNTIME_ROOT}/lib REQUIRED NO_DEFAULT_PATH)\n    target_link_libraries(neurochess_engine PRIVATE ${ONNXRUNTIME_LIBRARY})\nendif()\n''')

# Bump engine version for branch testing.
replace("CMakeLists.txt", "project(NeuroChess VERSION 0.12.6 LANGUAGES CXX)", "project(NeuroChess VERSION 0.15.0 LANGUAGES CXX)")

# trigger retry
