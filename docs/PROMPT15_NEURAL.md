# Prompt 15 — neural inference and Elo ablation

Prompt 15 connects a trained Prompt 14 checkpoint to the C++ engine through ONNX Runtime while keeping the classical engine path intact.

## Windows workflow (no console required)

1. Pull and switch to branch `prompt-15-onnx-inference` in GitHub Desktop.
2. Run `run_neural_setup_gui.bat`.
3. Select the trained `best.pt` checkpoint. The GUI exports it to ONNX, downloads the pinned official ONNX Runtime CPU package locally, and builds `build-neural/neurochess.exe`.
4. Run `run_elo_gui.bat`.
5. Select `build-neural/neurochess.exe`, Stockfish, and the exported `.onnx` model.
6. Keep move time, game counts and seed unchanged and compare these modes:
   - Classical
   - Policy
   - Value
   - Policy + Value

For the cleanest ablation, use the same neural-enabled executable even in **Classical** mode. That isolates the effect of enabling the model from unrelated build differences.

## Search integration

- Neural policy only affects move ordering; legality and alpha-beta scoring remain classical.
- Policy inference is limited to the upper search plies by default (`Neural Policy Max Ply = 2`) so inference cost does not dominate short time controls.
- Neural value is blended with classical evaluation at leaf/quiescence evaluation points. Internal pruning heuristics retain classical static evaluation.
- `Neural Value Blend` defaults to 50% and can be benchmarked independently.
- All neural features default to OFF and the normal non-ONNX build continues to work without ONNX Runtime.

## UCI options

- `Neural Model` — path to exported ONNX model
- `Neural Policy` — enable neural move ordering
- `Neural Policy Max Ply` — maximum ply for policy inference
- `Neural Value` — enable neural value evaluation
- `Neural Value Blend` — percentage of neural value in the leaf evaluation

The engine reports the number of neural inferences through `info string neural_evals N` after a completed search.
