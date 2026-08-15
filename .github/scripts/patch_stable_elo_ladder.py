from pathlib import Path

p = Path('python/match_runner/elo_ladder.py')
text = p.read_text(encoding='utf-8')
old = '''    low_idx = 0
    high_idx = len(config.levels) - 1
    visited: set[int] = set()
    target_idx: int | None = None
    while low_idx <= high_idx:
        idx = (low_idx + high_idx) // 2
        level = config.levels[idx]
        if level not in visited:
            point = sample(level, config.probe_games)
            visited.add(level)
        else:
            point = points[level]
        p = point.score / point.games
        if abs(p - 0.5) <= config.score_band:
            target_idx = idx
            emit(f"Target band reached near Stockfish Elo {level}.")
            break
        if p > 0.5:
            low_idx = idx + 1
        else:
            high_idx = idx - 1

    if target_idx is None:
        target_idx = min(max(low_idx, 0), len(config.levels) - 1)
'''
new = '''    # A binary search is a poor fit for tiny match samples: a noisy 5/8 at
    # one level can otherwise jump several hundred Elo in one step. Start near
    # the middle of the ladder and walk only one level (normally 200 Elo) at a
    # time. Scores close enough to 50% are confirmed with extra games before
    # deciding which direction to move.
    idx = len(config.levels) // 2
    target_idx: int | None = None
    previous_direction = 0
    visited_indices: set[int] = set()
    confirmation_games = max(config.probe_games * 2, min(config.refine_games, 16))

    while 0 <= idx < len(config.levels):
        level = config.levels[idx]
        point = points[level]
        if point.games < config.probe_games:
            sample(level, config.probe_games - point.games)
            point = points[level]

        score_fraction = point.score / point.games

        # With only a handful of games, do not make a direction decision from
        # a moderately imbalanced score. Top up the same level first.
        if 0.25 < score_fraction < 0.75 and point.games < confirmation_games:
            emit(
                f"SF {level} probe is noisy ({100.0 * score_fraction:.1f}%); "
                f"confirming at the same level before moving."
            )
            sample(level, confirmation_games - point.games)
            point = points[level]
            score_fraction = point.score / point.games

        if abs(score_fraction - 0.5) <= config.score_band:
            target_idx = idx
            emit(f"Target band reached near Stockfish Elo {level}.")
            break

        direction = 1 if score_fraction > 0.5 else -1
        next_idx = idx + direction

        # If the direction changes after adjacent levels, the crossover lies
        # between them. Refine around the current point instead of oscillating.
        if previous_direction and direction != previous_direction:
            target_idx = idx
            emit(f"Strength crossover bracketed near Stockfish Elo {level}.")
            break

        visited_indices.add(idx)
        if next_idx < 0 or next_idx >= len(config.levels) or next_idx in visited_indices:
            target_idx = idx
            break

        emit(
            f"Moving one ladder step {'up' if direction > 0 else 'down'} "
            f"to Stockfish Elo {config.levels[next_idx]}."
        )
        previous_direction = direction
        idx = next_idx

    if target_idx is None:
        target_idx = min(max(idx, 0), len(config.levels) - 1)
'''
if old not in text:
    raise SystemExit('target block not found')
p.write_text(text.replace(old, new), encoding='utf-8')
