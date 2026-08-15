#include "neurochess/nn/neural_evaluator.h"

namespace neurochess::nn {

bool NullNeuralEvaluator::load_model(const std::string&) {
    return false;
}

bool NullNeuralEvaluator::is_ready() const noexcept {
    return false;
}

} // namespace neurochess::nn
