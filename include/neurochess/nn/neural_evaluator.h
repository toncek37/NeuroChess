#pragma once

#include "neurochess/core/board.h"
#include "neurochess/core/move.h"

#include <array>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace neurochess::nn {

struct NeuralOutput {
    std::vector<float> policy_logits; // 5 * 64 * 64 = 20480
    std::array<float, 3> wdl_logits{}; // win, draw, loss from side-to-move POV
};

class NeuralEvaluator {
public:
    virtual ~NeuralEvaluator() = default;

    virtual bool load_model(const std::string& path) = 0;
    virtual bool is_ready() const noexcept = 0;
    virtual NeuralOutput evaluate(const core::Board& board) = 0;
    virtual std::string backend_name() const = 0;
};

class NullNeuralEvaluator final : public NeuralEvaluator {
public:
    bool load_model(const std::string& path) override;
    bool is_ready() const noexcept override;
    NeuralOutput evaluate(const core::Board& board) override;
    std::string backend_name() const override { return "none"; }
};

// Returns an ONNX Runtime backed evaluator when NeuroChess was built with
// NEUROCHESS_ENABLE_ONNX=ON. Otherwise this returns the null evaluator, keeping
// the classical engine fully buildable without any neural runtime dependency.
std::shared_ptr<NeuralEvaluator> make_neural_evaluator();

[[nodiscard]] std::array<float, 26 * 8 * 8> encode_board(const core::Board& board) noexcept;
[[nodiscard]] int move_to_policy_index(core::Move move) noexcept;
[[nodiscard]] float policy_logit_for_move(const NeuralOutput& output, core::Move move) noexcept;
[[nodiscard]] int wdl_to_centipawns(const NeuralOutput& output) noexcept;

} // namespace neurochess::nn
