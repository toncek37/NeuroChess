# NeuroChess match runner

This package runs reproducible UCI-engine matches, Stockfish Elo ladders, and head-to-head regression tests.

## GUI Elo benchmark

Windows users can launch `run_elo_gui.bat` from the repository root. The Tkinter window lets you select the NeuroChess and Stockfish executables, choose move time, probe/refine game counts, parallel games, seed and results folder, then start/stop the adaptive Elo ladder without typing console commands.

The progress pane streams each sampled Stockfish rating and its W/D/L result. At completion the GUI shows the estimated Stockfish-equivalent Elo, 95% confidence interval and total games. Detailed JSON and PGN artifacts remain in the selected results folder.

The benchmark requires `python-chess` because the tournament layer uses it as an external referee/PGN writer. Install dependencies with `python -m pip install -r python/requirements.txt` if needed.

## CLI

The command-line tools remain available for automation and CI. For example:

```bash
PYTHONPATH=python python -m match_runner.ladder_cli \
  --engine ./build/neurochess \
  --stockfish /path/to/stockfish \
  --probe-games 8 --refine-games 24 \
  --movetime-ms 100 --concurrency 4
```

The Elo ladder validates that Stockfish advertises `UCI_LimitStrength` and `UCI_Elo`, searches adaptively over configured rating rungs, refines around the estimated 50% score region and writes a JSON report with the sampled W/D/L points and confidence interval.

Each underlying match alternates colors and stores PGN/JSON artifacts. The reported rating is a Stockfish-equivalent benchmark under the selected hardware and time control, not a FIDE rating.
