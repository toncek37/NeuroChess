# Prompt 14 — first policy/WDL network

This prompt turns Prompt 13 labelled JSONL into tensors and trains the first NeuroChess neural model.

## Input representation

Each position becomes a `26 x 8 x 8` float tensor:

- 12 piece planes (white and black separately),
- side to move,
- four castling-right planes,
- eight en-passant-file planes,
- normalized halfmove clock.

## Policy representation

Every UCI move maps to one of 20,480 classes:

`promotion_bucket * 4096 + from_square * 64 + to_square`

The five promotion buckets are none, queen, rook, bishop and knight. The policy head is implemented as a compact `1x1` convolution producing 320 channels over 64 source squares rather than a huge fully connected layer.

## Value target

The value head outputs three logits for win/draw/loss from the side-to-move perspective. Targets come directly from Prompt 13 teacher labels.

## Model

Baseline defaults:

- 64 trunk channels,
- 4 residual blocks,
- policy head: 20,480 move logits,
- WDL head: 3 logits.

The model is intentionally small enough for fast iteration. Architecture size is configurable so later experiments can compare Elo gain versus inference cost.

## Training GUI

On Windows run:

```bat
run_training_gui.bat
```

The launcher installs `torch`, `numpy` and `python-chess` automatically if needed. Select a labelled JSONL dataset, choose the output directory and training settings, then click **Start training**.

The output directory contains:

- `best.pt` — lowest validation-loss checkpoint,
- `last.pt` — most recent checkpoint,
- `history.json` — per-epoch metrics,
- `config.json` — exact training configuration.

Policy top-1 in the GUI measures agreement with the teacher's highest-ranked move. This is a useful supervised metric but not a substitute for Elo; the trained model still needs to be integrated into C++ search and benchmarked against the classical baseline.
