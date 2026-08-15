#include "neurochess/nn/neural_evaluator.h"

#include <algorithm>
#include <bit>
#include <cmath>
#include <filesystem>
#include <limits>
#include <stdexcept>

#ifdef NEUROCHESS_ENABLE_ONNX
#include <onnxruntime_cxx_api.h>
#endif

namespace neurochess::nn {
namespace {

constexpr int policy_size = 5 * 64 * 64;

int promotion_bucket(core::PieceType type) noexcept {
    switch (type) {
        case core::PieceType::Queen: return 1;
        case core::PieceType::Rook: return 2;
        case core::PieceType::Bishop: return 3;
        case core::PieceType::Knight: return 4;
        default: return 0;
    }
}

#ifdef NEUROCHESS_ENABLE_ONNX
class OnnxNeuralEvaluator final : public NeuralEvaluator {
public:
    OnnxNeuralEvaluator()
        : env_(ORT_LOGGING_LEVEL_WARNING, "NeuroChess"), options_{} {
        options_.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
        options_.SetIntraOpNumThreads(1);
    }

    bool load_model(const std::string& path) override {
        try {
#ifdef _WIN32
            const std::wstring wide = std::filesystem::path(path).wstring();
            session_ = std::make_unique<Ort::Session>(env_, wide.c_str(), options_);
#else
            session_ = std::make_unique<Ort::Session>(env_, path.c_str(), options_);
#endif
            return true;
        } catch (...) {
            session_.reset();
            return false;
        }
    }

    bool is_ready() const noexcept override { return static_cast<bool>(session_); }
    std::string backend_name() const override { return "onnxruntime"; }

    NeuralOutput evaluate(const core::Board& board) override {
        if (!session_) throw std::runtime_error("ONNX model is not loaded");
        auto input = encode_board(board);
        const std::array<int64_t, 4> shape{1, 26, 8, 8};
        auto memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
        auto tensor = Ort::Value::CreateTensor<float>(memory, input.data(), input.size(), shape.data(), shape.size());
        const char* input_names[] = {"board"};
        const char* output_names[] = {"policy", "wdl_logits"};
        auto outputs = session_->Run(Ort::RunOptions{nullptr}, input_names, &tensor, 1, output_names, 2);

        NeuralOutput result;
        const auto policy_info = outputs[0].GetTensorTypeAndShapeInfo();
        const std::size_t policy_count = policy_info.GetElementCount();
        if (policy_count != static_cast<std::size_t>(policy_size)) {
            throw std::runtime_error("Unexpected ONNX policy output size");
        }
        const float* policy = outputs[0].GetTensorData<float>();
        result.policy_logits.assign(policy, policy + policy_count);

        const auto wdl_info = outputs[1].GetTensorTypeAndShapeInfo();
        if (wdl_info.GetElementCount() != 3) throw std::runtime_error("Unexpected ONNX WDL output size");
        const float* wdl = outputs[1].GetTensorData<float>();
        std::copy_n(wdl, 3, result.wdl_logits.begin());
        return result;
    }

private:
    Ort::Env env_;
    Ort::SessionOptions options_;
    std::unique_ptr<Ort::Session> session_;
};
#endif

} // namespace

bool NullNeuralEvaluator::load_model(const std::string&) { return false; }
bool NullNeuralEvaluator::is_ready() const noexcept { return false; }
NeuralOutput NullNeuralEvaluator::evaluate(const core::Board&) { return {}; }

std::shared_ptr<NeuralEvaluator> make_neural_evaluator() {
#ifdef NEUROCHESS_ENABLE_ONNX
    return std::make_shared<OnnxNeuralEvaluator>();
#else
    return std::make_shared<NullNeuralEvaluator>();
#endif
}

std::array<float, 26 * 8 * 8> encode_board(const core::Board& board) noexcept {
    std::array<float, 26 * 8 * 8> x{};
    auto plane = [&](int channel, int rank, int file) -> float& {
        return x[static_cast<std::size_t>(channel) * 64 + static_cast<std::size_t>(rank * 8 + file)];
    };
    auto fill_plane = [&](int channel, float value) {
        std::fill_n(x.begin() + static_cast<std::ptrdiff_t>(channel * 64), 64, value);
    };

    for (int square = 0; square < 64; ++square) {
        const core::Piece piece = board.piece_at(square);
        if (piece == core::Piece::None) continue;
        const int channel = core::piece_index(piece);
        plane(channel, square / 8, square % 8) = 1.0f;
    }
    if (board.side_to_move() == core::Color::White) fill_plane(12, 1.0f);
    if (board.has_castling_right(core::WhiteKingSide)) fill_plane(13, 1.0f);
    if (board.has_castling_right(core::WhiteQueenSide)) fill_plane(14, 1.0f);
    if (board.has_castling_right(core::BlackKingSide)) fill_plane(15, 1.0f);
    if (board.has_castling_right(core::BlackQueenSide)) fill_plane(16, 1.0f);
    if (const auto ep = board.en_passant_square()) fill_plane(17 + (*ep % 8), 1.0f);
    fill_plane(25, static_cast<float>(std::min<int>(board.halfmove_clock(), 100)) / 100.0f);
    return x;
}

int move_to_policy_index(core::Move move) noexcept {
    return promotion_bucket(move.promotion()) * 4096 + move.from() * 64 + move.to();
}

float policy_logit_for_move(const NeuralOutput& output, core::Move move) noexcept {
    const int index = move_to_policy_index(move);
    if (index < 0 || static_cast<std::size_t>(index) >= output.policy_logits.size()) {
        return -std::numeric_limits<float>::infinity();
    }
    return output.policy_logits[static_cast<std::size_t>(index)];
}

int wdl_to_centipawns(const NeuralOutput& output) noexcept {
    const float max_logit = *std::max_element(output.wdl_logits.begin(), output.wdl_logits.end());
    std::array<float, 3> p{};
    float sum = 0.0f;
    for (std::size_t i = 0; i < 3; ++i) {
        p[i] = std::exp(output.wdl_logits[i] - max_logit);
        sum += p[i];
    }
    if (!(sum > 0.0f)) return 0;
    for (float& value : p) value /= sum;
    const float score = std::clamp(p[0] - p[2], -0.999f, 0.999f);
    return static_cast<int>(400.0f * std::log10((1.0f + score) / (1.0f - score)));
}

} // namespace neurochess::nn
