# Training-position generation

Prompt 13 establishes the unlabeled position corpus used by later teacher-labelling and neural-training prompts.

Sources can be mixed in one deterministic JSONL dataset:

- **Public PGN**: sample non-terminal positions from real games.
- **Exploratory self-play**: reproducible random-legal self-play. This is deliberately not presented as strong chess; it broadens legal-state coverage until engine-guided self-play is added.
- **Controlled perturbations**: short random legal continuations from sampled positions, retaining `parent_fen` provenance.

Every record contains FEN, source, game id, ply, optional game result and perturbation metadata. A SHA-256 key of the FEN is emitted and duplicate FENs are removed. No evaluation/policy labels are invented in this step.

Example:

```bash
PYTHONPATH=python python -m data.generate_positions \
  --pgn data/public-games.pgn \
  --output datasets/positions.jsonl \
  --seed 42 \
  --positions-per-game 4 \
  --self-play-games 100 \
  --perturbations-per-position 1
```

For a public PGN corpus, keep the downloaded source outside Git unless its licence explicitly permits redistribution. Record the corpus URL/version/licence alongside experiment metadata. The generator itself does not download third-party data, which keeps dataset provenance explicit and reproducible.

Run tests from the repository root with:

```bash
PYTHONPATH=python python -m unittest python.tests.test_position_generator
```
