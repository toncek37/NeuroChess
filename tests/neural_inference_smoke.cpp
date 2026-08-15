#include "neurochess/core/board.h"
#include "neurochess/nn/neural_evaluator.h"

#include <iostream>
#include <string>

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: neural_inference_smoke <model.onnx>\n";
        return 2;
    }

    auto evaluator = neurochess::nn::make_neural_evaluator();
    if (!evaluator || !evaluator->load_model(argv[1]) || !evaluator->is_ready()) {
        std::cerr << "failed to load ONNX model\n";
        return 3;
    }

    neurochess::core::Board board;
    const auto output = evaluator->evaluate(board);
    if (output.policy_logits.size() != 5u * 64u * 64u) {
        std::cerr << "wrong policy size: " << output.policy_logits.size() << "\n";
        return 4;
    }

    std::cout << "backend=" << evaluator->backend_name()
              << " policy=" << output.policy_logits.size()
              << " wdl=3\n";
    return 0;
}
