#include "neurochess/core/engine_info.h"
#include "neurochess/nn/neural_evaluator.h"
#include "neurochess/search/searcher.h"
#include "neurochess/uci/uci_loop.h"

#include <cassert>
#include <sstream>
#include <string>

int main() {
    using neurochess::core::EngineInfo;

    assert(EngineInfo::name() == "NeuroChess");
    assert(!EngineInfo::version().empty());

    neurochess::nn::NullNeuralEvaluator neural;
    assert(!neural.is_ready());
    assert(!neural.load_model("missing-model"));

    neurochess::search::Searcher searcher;
    assert(searcher.available());

    std::istringstream input("uci\nisready\nquit\n");
    std::ostringstream output;
    const int code = neurochess::uci::run(input, output);
    assert(code == 0);

    const std::string text = output.str();
    assert(text.find("uciok") != std::string::npos);
    assert(text.find("readyok") != std::string::npos);

    return 0;
}
