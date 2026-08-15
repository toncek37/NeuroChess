# NeuroChess

NeuroChess is an experimental chess-engine project whose long-term goal is to test whether a neural model can allocate classical search effort more efficiently than a conventional search alone.

The intended final engine combines:

- a fast C++ chess core,
- iterative-deepening negamax / alpha-beta search,
- a neural policy + WDL evaluator trained in PyTorch,
- neural move ordering,
- policy-guided selective search,
- uncertainty-guided search allocation,
- tacticality-guided search allocation,
- optional tactical verification of neural candidate moves,
- reproducible Elo and compute-efficiency benchmarks.

## Current status

**Prompt 12 / head-to-head regression testing.**

The project now contains a 64-bit bitboard-based chess position representation with all 12 colored piece sets, side to move, castling rights, en-passant state, halfmove/fullmove counters, aggregate occupancy bitboards, strict six-field FEN parsing, and canonical FEN serialization. The core now also supports compact moves, pseudo-legal and legal move generation, attack/check detection, reversible in-place make/unmake, and Perft correctness testing. The core now also maintains an incremental 64-bit Zobrist position key, and the search layer contains a depth-preferred transposition table. The first modular classical static evaluator is now connected to a complete iterative-deepening negamax/alpha-beta search with quiescence, transposition-table cutoffs, move ordering, principal variation extraction, mate/draw handling, and depth/time/node limits.

The executable exposes the classical engine through a full basic UCI frontend. The Python tournament layer now includes an adaptive Stockfish Elo ladder that concentrates games around the estimated 50% score region and reports a Stockfish-equivalent rating with an approximate confidence interval.

## Architecture

```text
NeuroChess/
├── include/neurochess/
│   ├── core/       chess-state and move primitives
│   ├── search/     classical and neural-guided search
│   ├── nn/         C++ neural inference abstraction
│   └── uci/        UCI protocol frontend
├── src/
│   ├── core/
│   ├── search/
│   ├── nn/
│   └── uci/
├── tests/          correctness/unit tests
├── benchmarks/     Elo, node-efficiency and regression testing
├── python/
│   ├── data/       dataset generation / teacher labelling
│   └── training/   PyTorch model training
├── configs/        reproducible experiment configs
└── models/         local model checkpoints / exports
```

The intended dependency direction is:

```text
UCI ──> Search ──> Core
          │
          └──────> Neural inference

Python training ──exported model──> Neural inference

Benchmark runner ──UCI──> NeuroChess / reference engines
```

The chess core stays independent of PyTorch and any particular inference runtime. This keeps search testing possible without a neural model and allows the inference backend to change later without rewriting the engine.

## Technology choices

- **C++20** — engine, board representation, move generation and search.
- **CMake 3.20+** — portable build system.
- **Python + PyTorch** — dataset processing and neural training.
- **UCI** — engine interoperability and automated strength testing.
- **Inference backend** — intentionally undecided until the neural model exists; likely ONNX Runtime or another backend selected from measured latency rather than assumed in advance.

## Build

### Linux / macOS

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
./build/neurochess
```

### Windows (Visual Studio generator)

```powershell
cmake -S . -B build
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
.\build\Release\neurochess.exe
```

## UCI check

```text
> uci
id name NeuroChess 0.9.0
id author NeuroChess project
option name Hash type spin default 16 min 1 max 4096
option name Clear Hash type button
option name Killer Moves type check default true
option name History Heuristic type check default true
option name Null Move Pruning type check default true
option name Late Move Reductions type check default true
option name Aspiration Windows type check default true
option name Futility Pruning type check default true
option name Razoring type check default true
uciok
> isready
readyok
> position startpos moves e2e4 e7e5
> go depth 5
info depth 5 ... score cp ... nodes ... nps ... time ... pv ...
bestmove ...
```

Supported search limits include `go depth`, `go nodes`, `go movetime`, and normal `wtime/btime/winc/binc/movestogo` clock input. `go infinite` is also accepted and can be interrupted with `stop`.

## Design rule for future work

Every major optimization or neural component should be independently switchable and benchmarkable. The project is intended as an experiment, not only as a chess program, so a change is considered useful only after its effect on playing strength and computational cost can be measured.

Primary long-term metrics:

- Elo at fixed wall-clock time,
- Elo at fixed node budget,
- nodes per move at a target Elo,
- neural inference cost per move,
- head-to-head Elo change versus a retained baseline.

## Prompt 4 correctness coverage

The legal-move layer now checks king safety, pins, attacked castling transit squares, en passant discovered attacks, promotions and reversible state updates. `make_move()` mutates bitboards in place and returns a compact `UndoState`; `unmake_move()` restores the exact previous state without copying the whole board.

Perft regression tests use the canonical Chess Programming Wiki positions and currently verify:

- initial position through depth 4 (197,281 leaves),
- Kiwipete through depth 3 (97,862 leaves),
- Position 3 through depth 4 (43,238 leaves),
- Position 4 through depth 3 (9,467 leaves),
- Position 5 through depth 3 (62,379 leaves),
- Position 6 through depth 3 (89,890 leaves).

The suite also directly tests a pinned piece, castling through check, en-passant make/unmake restoration, and the earlier pseudo-legal generator.

## Prompt 5 hashing / TT coverage

The board now owns a deterministic 64-bit Zobrist key covering piece-square occupancy, side to move, castling rights, and en-passant square. `make_move()` updates the key incrementally; `unmake_move()` restores the exact previous key from `UndoState`. Halfmove/fullmove clocks are intentionally excluded because they do not define board transpositions.

The new transposition table stores:

- full 64-bit position key,
- search depth,
- score,
- bound type (`Exact`, `Lower`, `Upper`),
- best move.

It uses a power-of-two direct-mapped table and a simple depth-preferred replacement policy suitable as a baseline for Prompt 7 search integration. Tests cover ordinary moves, captures, castling, en passant, promotion, multi-ply make/unmake, state-sensitive hashing, collision rejection, replacement behavior, and full recomputation consistency. Existing Perft tests still pass unchanged.

## Prompt 6 classical evaluation

The baseline evaluator scores positions in centipawn-like integer units and returns the score from the side-to-move perspective for direct future negamax use. A diagnostic breakdown remains in White POV. Components are independently switchable through `EvaluationConfig`:

- material,
- generated piece-square terms,
- piece mobility,
- doubled/isolated pawn structure,
- local king safety and pawn shield,
- bishop pair,
- passed pawns with advancement bonus.

The terms are intentionally simple rather than heavily tuned: Prompt 6 establishes a transparent classical baseline so later neural/search changes can be measured against it. Tests cover symmetry, material dominance, side-to-move sign convention, component switches, bishop pair, passed-pawn advancement, and pawn-structure penalties.

## Prompt 7 search

The engine now has a synchronous `Searcher` implementing iterative deepening over negamax/alpha-beta. Leaf nodes enter quiescence search, which extends captures/promotions and searches all evasions when the side to move is in check. The existing transposition table is used for exact/lower/upper cutoffs and TT-best-move ordering; captures use a simple MVV-LVA-style priority and promotions are prioritized.

Search results expose:

- completed depth and selective depth,
- total nodes and quiescence nodes,
- transposition-table hits,
- elapsed time and NPS,
- centipawn/mate score,
- best move and principal variation.

Terminal handling covers checkmate, stalemate, the 50-move rule, threefold repetition when prior game hashes are supplied, and basic insufficient-material cases. Mate scores are ply-normalized when written to/read from the TT so a transposition does not change mate distance. Search can be bounded independently by depth, wall-clock time, or node count and always restores the root board after interruption.

The search regression suite checks a start-position search, mate-in-one recognition, root checkmate/stalemate, 50-move and repetition draws, a hanging-queen quiescence case, and safe node/time interruption. Existing Perft, hashing, move-generation, board, evaluator and smoke tests remain unchanged.

## Next implementation step

Prompt 13 adds training-position dataset generation from public PGN, self-play and controlled perturbations.

## v0.8 search optimizations

The classical search now exposes independent `SearchConfig` switches for killer moves, history heuristic, null-move pruning, late-move reductions (LMR), aspiration windows, futility pruning and razoring. Search statistics include counters for the selective techniques so ablation tests can verify both correctness and whether a feature actually triggers.

A fixed-depth `neurochess_search_benchmark` executable compares the clean alpha-beta baseline against the fully optimized configuration. Elo/playing-strength measurement intentionally remains separate and will be implemented with the UCI match infrastructure in the next project phase.

## v0.9 UCI frontend

The UCI layer now supports `uci`, `isready`, `ucinewgame`, `position startpos`, six-field `position fen`, appended UCI move lists, `go depth`, `go movetime`, `go nodes`, chess-clock inputs (`wtime`, `btime`, `winc`, `binc`, `movestogo`), `go infinite`, `stop`, `quit`, `setoption`, and `Clear Hash`. Search runs asynchronously on a worker thread and emits standard `info` plus `bestmove` lines.

Search heuristics from v0.8 are exposed as independent UCI check options, preserving the project's ablation-testing requirement. The Hash option rebuilds the transposition table at a requested size. Position setup validates each supplied move against the legal move generator and carries pre-root Zobrist history into search for repetition detection.

Dedicated UCI regression tests cover identification/options, startpos plus move application, FEN terminal positions, depth/node searches, option changes, and rejection of illegal position moves.


## v0.10 automated UCI match runner

`python/match_runner` is a reusable tournament harness for arbitrary UCI executables. It starts and handshakes each engine, applies requested UCI options, sends the complete game position before each move, manages Fischer clocks or fixed `movetime`, alternates engine colors, and schedules openings in color-swapped pairs. Multiple games can run concurrently.

`python-chess` acts only as the external referee/PGN layer: it validates every returned `bestmove`, detects checkmate/stalemate/rule draws, and writes standards-compliant PGN. The C++ engine remains independent of Python. Engine timeout, process failure, malformed move, and illegal move are recorded as forfeits. A maximum-ply safety adjudication prevents pathological games from running forever.

Each run writes a PGN plus JSON containing reproducibility data (engine commands/options, time control, seed, opening name), aggregate W/D/L and score percentage, per-game termination, UCI move list, and measured move times. See `python/match_runner/README.md` and `configs/openings-example.txt`.

The Python unit suite uses a fake UCI subprocess to test the real protocol wrapper without requiring Stockfish. A full live tournament additionally requires the `python-chess` dependency from `python/requirements.txt` and the opponent executable.


## v0.11 adaptive Stockfish Elo ladder

`python/match_runner/elo_ladder.py` builds an adaptive strength test on top of the v0.10 UCI match runner. It validates that the reference engine advertises `UCI_LimitStrength` and `UCI_Elo`, performs a coarse binary search across configured rating rungs, then concentrates additional color-paired games on the closest rung and its neighbours.

The final estimate combines every sampled rung with the standard logistic Elo expectation model. The report includes an approximate normal confidence interval from Fisher information, total games, per-rung W/D/L and score, and links to each underlying PGN/JSON match artifact. This rating is explicitly a **Stockfish-equivalent benchmark under the chosen time control and hardware**, not a FIDE rating.

Example:

```bash
cd python
python -m match_runner.ladder_cli \
  --engine ../build/neurochess \
  --stockfish /path/to/stockfish \
  --probe-games 8 --refine-games 32 \
  --movetime-ms 100 --concurrency 4
```

## v0.12 head-to-head regression testing

`python/match_runner/regression.py` compares a current NeuroChess build against a retained baseline using color-paired batches. It reports W/D/L, score percentage, logistic Elo difference and a draw-aware confidence interval. Sequential early decisions use conservative Bonferroni alpha spending across the planned number of looks, avoiding the false-confidence problem of repeatedly peeking at an ordinary 95% interval. A run can end as `better`, `worse`, `equivalent`, or `inconclusive`.

Save a reproducible baseline executable (and later an optional neural model) with SHA-256 metadata:

```bash
PYTHONPATH=python python -m match_runner.regression_cli snapshot \
  --engine ./build/neurochess \
  --destination baselines/v0.12 \
  --label v0.12
```

Compare a new build against it:

```bash
PYTHONPATH=python python -m match_runner.regression_cli run \
  --current ./build/neurochess \
  --baseline baselines/v0.12/neurochess \
  --batch-games 20 --min-games 40 --max-games 400 \
  --movetime-ms 100 --concurrency 4 \
  --openings configs/openings-example.txt
```

`--elo-margin` can require a practical improvement before early acceptance, while `--equivalence-margin` defines the final practical-equivalence band. Every batch keeps its PGN/JSON artifacts and the aggregate report records every sequential look.

## Prompt 12.5 — local playable GUI

A lightweight Tkinter GUI is now included under `python/gui/`. It talks to the C++ engine over UCI and deliberately keeps chess-rule authority inside the C++ core. Three NeuroChess-specific diagnostic commands (`nc_fen`, `nc_legalmoves`, `nc_incheck`) expose read-only state for the GUI; normal engine interoperability remains standard UCI.

The GUI provides:

- a clickable chessboard with legal-target highlighting,
- play as White or Black,
- promotion selection,
- New Game and two-ply Undo,
- fixed depth or fixed move-time search,
- Stop Search,
- live evaluation, depth/seldepth, nodes, NPS and principal variation,
- engine executable selection and auto-detection of common build paths.

The GUI itself has **no third-party chess dependency**; it requires only Python with Tkinter. (`python-chess` remains a dependency of the tournament/match-runner tools.)

### Windows: build and play

With Python 3 and CMake/Visual Studio Build Tools installed, run:

```bat
build_and_play.bat
```

The script configures and builds the Release engine, then starts the GUI with `build\\Release\\neurochess.exe`.

Alternatively:

```powershell
cmake -S . -B build
cmake --build build --config Release
python play_gui.py --engine .\\build\\Release\\neurochess.exe
```

### Linux/macOS-style build

```bash
./build_and_play.sh
```

On Linux, Tkinter may be packaged separately by the distribution (often `python3-tk`).

### Windows build launcher

`build_and_play.bat` supports both Visual Studio multi-config builds (`build\Release\neurochess.exe`) and single-config generators such as Ninja (`build\neurochess.exe`). If configuration, compilation, or GUI startup fails, the window now remains open and displays the actual error.
