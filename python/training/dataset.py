from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import chess
import torch
from torch.utils.data import Dataset

from .encoding import encode_board, move_to_index


class LabelledPositionDataset(Dataset):
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.records: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict) or "fen" not in record or "wdl" not in record or "policy" not in record:
                    raise ValueError(f"Invalid labelled dataset record on line {line_no}")
                self.records.append(record)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int):
        record = self.records[index]
        board = chess.Board(record["fen"])
        board_tensor = encode_board(board)
        wdl = record["wdl"]
        wdl_tensor = torch.tensor(
            [float(wdl["win"]), float(wdl["draw"]), float(wdl["loss"])],
            dtype=torch.float32,
        )

        indices: list[int] = []
        probabilities: list[float] = []
        for candidate in record["policy"]:
            move = chess.Move.from_uci(candidate["move"])
            indices.append(move_to_index(move))
            probabilities.append(float(candidate["probability"]))
        if not indices:
            raise ValueError(f"Record {index} has empty policy target")

        probs = torch.tensor(probabilities, dtype=torch.float32)
        probs /= probs.sum().clamp_min(1e-12)
        return board_tensor, wdl_tensor, torch.tensor(indices, dtype=torch.long), probs


def collate_labelled(batch):
    boards, wdls, index_lists, prob_lists = zip(*batch)
    max_candidates = max(len(x) for x in index_lists)
    policy_indices = torch.full((len(batch), max_candidates), -1, dtype=torch.long)
    policy_probs = torch.zeros((len(batch), max_candidates), dtype=torch.float32)
    for row, (indices, probs) in enumerate(zip(index_lists, prob_lists)):
        policy_indices[row, : len(indices)] = indices
        policy_probs[row, : len(probs)] = probs
    return torch.stack(boards), torch.stack(wdls), policy_indices, policy_probs
