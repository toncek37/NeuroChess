# NeuroChess

NeuroChess is an experimental chess-engine project whose long-term goal is to test whether a neural model can allocate classical search effort more efficiently than a conventional search alone.

The intended final engine combines a fast C++ chess core, classical alpha-beta search, a neural policy + WDL evaluator, neural move ordering and selective search, and reproducible Elo/compute-efficiency benchmarks.

## Current status

**Prompt 13 / training-data generation and teacher labelling.**

The C++ engine already provides legal chess state, incremental hashing, classical evaluation/search, UCI, match running, adaptive Stockfish Elo measurement and head-to-head regression testing. A local Tkinter GUI is also available.

Prompt 13 adds the first neural-data infrastructure under `python/data/`: deterministic position sampling from public PGN, reproducible exploratory legal self-play, controlled legal perturbations, provenance metadata, FEN-based deduplication and JSONL output. Generated positions can then be labelled by a strong UCI teacher with MultiPV policy candidates plus value/WDL targets. Every labelled sample records teacher identity, executable SHA-256 and exact search budget for reproducibility.

## Architecture

```text
NeuroChess/
├── include/neurochess/   C++ core/search/NN/UCI interfaces
├── src/                  C++ implementation
├── tests/                engine correctness tests
├── benchmarks/           search and strength benchmarks
├── python/
│   ├── data/             dataset generation / teacher labelling
│   ├── match_runner/     UCI tournaments and regression tests
│   ├── gui/              local playable GUI
│   └── training/         PyTorch model training
├── configs/              reproducible experiment configs
└── models/               local checkpoints / exports
```

The chess core stays independent of PyTorch and any particular inference runtime.

## Build

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
```

Windows users can run `build_and_play.bat`; Linux/macOS-style environments can use `build_and_play.sh`.

## Prompt 13 dataset example

```bash
PYTHONPATH=python python -m data.generate_positions \
  --pgn /path/to/public-games.pgn \
  --output datasets/positions.jsonl \
  --seed 42 --positions-per-game 4 \
  --self-play-games 100 \
  --perturbations-per-position 1
```

Teacher labelling example:

```bash
PYTHONPATH=python python -m data.label_positions \
  --input datasets/positions.jsonl \
  --output datasets/labelled.jsonl \
  --engine /path/to/stockfish \
  --nodes 50000 --multipv 8
```

See `python/data/README.md` for schema and provenance guidance. Public PGN is consumed locally rather than silently downloaded or redistributed by the project.

## Design rule

Every major optimization or neural component should be independently switchable and benchmarkable. Primary long-term metrics are Elo at fixed wall-clock time, Elo at fixed node budget, nodes per move at target Elo, neural inference cost per move, and head-to-head Elo change versus a retained baseline.

## Next implementation step

Prompt 14: convert labelled JSONL positions into tensor features/targets and implement the first PyTorch policy + WDL/value network with a minimal training loop and checkpoint format.
