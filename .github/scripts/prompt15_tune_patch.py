from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:100]!r}")
    p.write_text(text.replace(old, new), encoding="utf-8")

# Policy is intentionally shallow by default: root + first replies. Running a CNN
# on every alpha-beta node would overwhelm the 100 ms/move benchmark budget.
replace(
    "src/search/searcher.cpp",
    "if (config_.neural_policy && neural_ready()) {",
    "if (config_.neural_policy && ply <= config_.neural_policy_max_ply && neural_ready()) {",
)

# Keep pruning/static heuristics classical. Neural value is used at search leaves
# (max-ply and quiescence stand-pat), avoiding an inference at every internal node.
replace(
    "src/search/searcher.cpp",
    "const int static_eval = in_check ? -Infinity : static_evaluate(board);",
    "const int static_eval = in_check ? -Infinity : evaluator_.evaluate(board);",
)

# UCI controls for policy inference depth.
replace(
    "src/uci/uci_loop.cpp",
    'write_line("option name Neural Policy type check default false");\n        write_line("option name Neural Value type check default false");',
    'write_line("option name Neural Policy type check default false");\n        write_line("option name Neural Policy Max Ply type spin default 2 min 0 max 16");\n        write_line("option name Neural Value type check default false");',
)
replace(
    "src/uci/uci_loop.cpp",
    'else if (name == "neural policy") update_bool(config_.neural_policy);\n        else if (name == "neural value") update_bool(config_.neural_value);',
    'else if (name == "neural policy") update_bool(config_.neural_policy);\n        else if (name == "neural policy max ply") {\n            if (const auto parsed = parse_int(value)) config_.neural_policy_max_ply = std::clamp(*parsed, 0, 16);\n        } else if (name == "neural value") update_bool(config_.neural_value);',
)

# Keep standard UCI info tokens standard; report neural inference count separately.
replace(
    "src/uci/uci_loop.cpp",
    '''        line << " nodes " << result.stats.nodes
             << " nps " << result.stats.nps
             << " string neural_evals=" << result.stats.neural_evaluations
             << " time " << result.stats.elapsed.count();''',
    '''        line << " nodes " << result.stats.nodes
             << " nps " << result.stats.nps
             << " time " << result.stats.elapsed.count();''',
)
replace(
    "src/uci/uci_loop.cpp",
    '''        write_line(line.str());
    }

    void stop_search''',
    '''        write_line(line.str());
        if (result.stats.neural_evaluations > 0) {
            write_line("info string neural_evals " + std::to_string(result.stats.neural_evaluations));
        }
    }

    void stop_search''',
)

# Close all subprocess pipes after a UCI engine exits. This removes ResourceWarnings
# observed by CI and matters when running many parallel games.
replace(
    "python/match_runner/uci_engine.py",
    '''        finally:
            self.process = None

    def close(self) -> None:''',
    '''        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            self.process = None

    def close(self) -> None:''',
)

# trigger
