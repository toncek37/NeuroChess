# Training data pipeline

Prompt 13 establishes the first neural-data pipeline in two explicit stages: position generation and strong-teacher labelling.

## 1. Generate positions

Sources can be mixed in one deterministic JSONL dataset:

- **Public PGN**: sample non-terminal positions from real games.
- **Exploratory self-play**: reproducible random-legal self-play. This broadens legal-state coverage; it is not presented as strong chess.
- **Controlled perturbations**: short random legal continuations from sampled positions, retaining `parent_fen` provenance.

Every base record contains FEN, source, game id, ply, optional result and perturbation metadata. A SHA-256 key of the FEN is emitted and duplicate FENs are removed.

```bash
PYTHONPATH=python python -m data.generate_positions \
  --pgn data/public-games.pgn \
  --output datasets/positions.jsonl \
  --seed 42 --positions-per-game 4 \
  --self-play-games 100 \
  --perturbations-per-position 1
```

For public PGN corpora, keep downloaded data outside Git unless redistribution is explicitly permitted. Record corpus URL/version/licence alongside experiment metadata.

## 2. Teacher labels

Use a strong UCI engine, typically Stockfish, to create targets. The label is always expressed from the **side-to-move** perspective.

Each labelled record adds:

- `value_cp`: best teacher score in centipawn-like units; mate is mapped to a large finite value,
- `wdl`: normalized win/draw/loss target,
- `policy`: MultiPV candidate moves with score and normalized soft target probability,
- `teacher`: engine name, executable SHA-256, search budget, MultiPV and applied UCI options.

Exactly one teacher budget is selected: `--depth`, `--nodes`, or `--movetime-ms`.

```bash
PYTHONPATH=python python -m data.label_positions \
  --input datasets/positions.jsonl \
  --output datasets/labelled.jsonl \
  --engine C:/tools/stockfish/stockfish-windows-x86-64-avx2.exe \
  --depth 14 --multipv 8 --threads 1 --hash-mb 256
```

For large datasets, a fixed node budget is often preferable for reproducibility across positions:

```bash
PYTHONPATH=python python -m data.label_positions \
  --input datasets/positions.jsonl \
  --output datasets/labelled.jsonl \
  --engine /path/to/stockfish \
  --nodes 50000 --multipv 8
```

`python-chess` converts the teacher's score into the Stockfish WDL model when available. The pipeline retains exact engine/search metadata so later experiments can distinguish model changes from teacher-data changes.

## Tests

```bash
PYTHONPATH=python python -m unittest \
  python.tests.test_position_generator \
  python.tests.test_teacher_labeler
```
