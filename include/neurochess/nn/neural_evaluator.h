#pragma once

#include <string>

namespace neurochess::nn {

// Abstract seam between the C++ engine and a future exported neural model.
// The concrete inference backend (ONNX Runtime, TensorRT, etc.) is deliberately
// postponed so the engine architecture is not coupled to one framework.
class NeuralEvaluator {
public:
    virtual ~NeuralEvaluator() = default;

    virtual bool load_model(const std::string& path) = 0;
    virtual bool is_ready() const noexcept = 0;
};

class NullNeuralEvaluator final : public NeuralEvaluator {
public:
    bool load_model(const std::string& path) override;
    bool is_ready() const noexcept override;
};

} // namespace neurochess::nn
