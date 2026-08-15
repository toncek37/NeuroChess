from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Subset

from .dataset import LabelledPositionDataset, collate_labelled
from .model import NeuroChessNet


@dataclass
class TrainConfig:
    dataset: str
    output_dir: str = "models/prompt14"
    epochs: int = 10
    batch_size: int = 64
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    validation_fraction: float = 0.1
    seed: int = 42
    channels: int = 64
    blocks: int = 4
    policy_weight: float = 1.0
    wdl_weight: float = 1.0
    workers: int = 0
    device: str = "auto"


def _device(name: str) -> torch.device:
    if name != "auto":
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _split_indices(size: int, validation_fraction: float, seed: int) -> tuple[list[int], list[int]]:
    if size < 2:
        raise ValueError("Training requires at least two labelled positions")
    if not 0.0 < validation_fraction < 0.5:
        raise ValueError("validation_fraction must be between 0 and 0.5")
    indices = list(range(size))
    random.Random(seed).shuffle(indices)
    val_count = max(1, int(round(size * validation_fraction)))
    val_count = min(val_count, size - 1)
    return indices[val_count:], indices[:val_count]


def policy_loss(logits: torch.Tensor, indices: torch.Tensor, probabilities: torch.Tensor) -> torch.Tensor:
    log_probs = F.log_softmax(logits, dim=1)
    safe_indices = indices.clamp_min(0)
    selected = log_probs.gather(1, safe_indices)
    mask = indices.ge(0)
    return -(selected * probabilities * mask).sum(dim=1).mean()


def wdl_loss(logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    return -(F.log_softmax(logits, dim=1) * target).sum(dim=1).mean()


def _run_epoch(model, loader, device, optimizer=None, policy_weight=1.0, wdl_weight=1.0):
    training = optimizer is not None
    model.train(training)
    totals = {"loss": 0.0, "policy_loss": 0.0, "wdl_loss": 0.0, "policy_top1": 0.0, "samples": 0}

    for boards, wdls, policy_indices, policy_probs in loader:
        boards = boards.to(device)
        wdls = wdls.to(device)
        policy_indices = policy_indices.to(device)
        policy_probs = policy_probs.to(device)

        with torch.set_grad_enabled(training):
            policy_logits, wdl_logits = model(boards)
            p_loss = policy_loss(policy_logits, policy_indices, policy_probs)
            v_loss = wdl_loss(wdl_logits, wdls)
            loss = policy_weight * p_loss + wdl_weight * v_loss
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                optimizer.step()

        batch = boards.shape[0]
        teacher_best = policy_indices[:, 0]
        predicted = policy_logits.argmax(dim=1)
        correct = predicted.eq(teacher_best).sum().item()
        totals["samples"] += batch
        totals["loss"] += loss.item() * batch
        totals["policy_loss"] += p_loss.item() * batch
        totals["wdl_loss"] += v_loss.item() * batch
        totals["policy_top1"] += correct

    samples = max(1, totals.pop("samples"))
    return {key: value / samples for key, value in totals.items()}


def train(config: TrainConfig) -> Path:
    _seed_everything(config.seed)
    device = _device(config.device)
    dataset = LabelledPositionDataset(config.dataset)
    train_indices, val_indices = _split_indices(len(dataset), config.validation_fraction, config.seed)
    train_loader = DataLoader(
        Subset(dataset, train_indices), batch_size=config.batch_size, shuffle=True,
        num_workers=config.workers, collate_fn=collate_labelled,
    )
    val_loader = DataLoader(
        Subset(dataset, val_indices), batch_size=config.batch_size, shuffle=False,
        num_workers=config.workers, collate_fn=collate_labelled,
    )

    model = NeuroChessNet(config.channels, config.blocks).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    output = Path(config.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    history: list[dict[str, object]] = []
    best_val = float("inf")
    best_path = output / "best.pt"

    print(f"Device: {device}")
    print(f"Dataset: {len(dataset)} positions ({len(train_indices)} train / {len(val_indices)} validation)")
    for epoch in range(1, config.epochs + 1):
        train_metrics = _run_epoch(model, train_loader, device, optimizer, config.policy_weight, config.wdl_weight)
        with torch.no_grad():
            val_metrics = _run_epoch(model, val_loader, device, None, config.policy_weight, config.wdl_weight)
        entry = {"epoch": epoch, "train": train_metrics, "validation": val_metrics}
        history.append(entry)
        print(
            f"Epoch {epoch:3d}/{config.epochs}: "
            f"train {train_metrics['loss']:.4f} | val {val_metrics['loss']:.4f} | "
            f"policy top1 {100.0 * val_metrics['policy_top1']:.1f}%"
        )
        checkpoint = {
            "schema_version": 1,
            "config": asdict(config),
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "epoch": epoch,
            "metrics": entry,
        }
        torch.save(checkpoint, output / "last.pt")
        if val_metrics["loss"] < best_val:
            best_val = val_metrics["loss"]
            torch.save(checkpoint, best_path)

    (output / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    (output / "config.json").write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    print(f"Best checkpoint: {best_path}")
    return best_path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train the first NeuroChess policy/WDL network")
    p.add_argument("--dataset", required=True)
    p.add_argument("--output-dir", default="models/prompt14")
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--learning-rate", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--validation-fraction", type=float, default=0.1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--channels", type=int, default=64)
    p.add_argument("--blocks", type=int, default=4)
    p.add_argument("--policy-weight", type=float, default=1.0)
    p.add_argument("--wdl-weight", type=float, default=1.0)
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--device", default="auto")
    return p


def main() -> int:
    args = parser().parse_args()
    train(TrainConfig(**vars(args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
