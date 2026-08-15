# NeuroChess UCI match runner

The Prompt 10 runner launches two arbitrary UCI executables, alternates colors, assigns paired opening positions, manages Fischer clocks or fixed move time, validates moves with `python-chess`, detects normal chess termination, and stores both PGN and machine-readable JSON.

Install the Python-side dependencies first:

```bash
python -m pip install -r python/requirements.txt
```

Example: 40 NeuroChess vs Stockfish games with paired openings and four games in parallel:

```bash
PYTHONPATH=python python -m match_runner \
  --engine-a ./build/neurochess \
  --name-a NeuroChess \
  --engine-b /path/to/stockfish \
  --name-b Stockfish \
  --games 40 \
  --concurrency 4 \
  --base-ms 10000 \
  --increment-ms 100 \
  --openings configs/openings-example.txt \
  --output-dir match-results
```

Engine options can be supplied repeatedly:

```bash
--option-a "Hash=64" --option-a "Null Move Pruning=true"
```

A fixed per-move control is also supported:

```bash
--movetime-ms 250
```

Opening text files contain one position per line:

```text
startpos | Initial position
rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2 | Open Game
```

The schedule deliberately assigns each selected opening to a two-game color-swapped pair. With a fixed `--seed`, opening selection/order is reproducible.

For each completed match the runner creates:

- a `.pgn` file containing every game,
- a `.json` file containing engine commands/options, time control, seed, W/D/L, score percentage, termination reasons, move list and per-move elapsed times.

Timeouts, engine crashes, malformed `bestmove` responses and illegal moves are treated as forfeits rather than hanging the tournament.

## Adaptive Stockfish Elo ladder (Prompt 11)

The ladder runner uses Stockfish's advertised `UCI_LimitStrength` and `UCI_Elo` options. It first probes a coarse set of configured Elo rungs, then adds games only around the apparent 50% score region. Every match remains color-paired and reproducible through its seed.

Example:

```bash
PYTHONPATH=python python -m match_runner.ladder_cli \
  --engine ./build/neurochess \
  --stockfish /path/to/stockfish \
  --levels 1400,1600,1800,2000,2200,2400,2600,2800,3000,3190 \
  --probe-games 8 \
  --refine-games 32 \
  --movetime-ms 100 \
  --concurrency 4
```

The aggregate JSON report contains the estimated Stockfish-equivalent Elo, an approximate confidence interval, total games, per-rung W/D/L and score, plus paths to the underlying PGN and match JSON files.

## Head-to-head regression testing (Prompt 12)

Save a known executable and optional model as a baseline with SHA-256 metadata:

```bash
PYTHONPATH=python python -m match_runner.regression_cli snapshot \
  --engine ./build/neurochess \
  --destination baselines/v0.12 \
  --label v0.12
```

Then compare a current build in sequential color-paired batches:

```bash
PYTHONPATH=python python -m match_runner.regression_cli run \
  --current ./build/neurochess \
  --baseline baselines/v0.12/neurochess \
  --batch-games 20 --min-games 40 --max-games 400 \
  --movetime-ms 100 --openings configs/openings-example.txt
```

The runner reports W/D/L, score, Elo difference and confidence bounds. Early `better`/`worse` decisions use a conservative Bonferroni alpha-spending confidence level across all planned looks, so repeated inspection does not silently reuse an ordinary 95% threshold. If no directional result is established, the final run can be labelled `equivalent` only when its final interval lies fully inside `--equivalence-margin`; otherwise it remains `inconclusive`.
