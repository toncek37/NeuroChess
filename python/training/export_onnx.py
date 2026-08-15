from __future__ import annotations

import argparse
from pathlib import Path

import torch

from .model import NeuroChessNet


def main() -> int:
    p = argparse.ArgumentParser(description="Export NeuroChess best.pt checkpoint to ONNX.")
    p.add_argument("--checkpoint", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--opset", type=int, default=18)
    args = p.parse_args()

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    config = checkpoint.get("config", {}) if isinstance(checkpoint, dict) else {}
    channels = int(config.get("channels", 64))
    blocks = int(config.get("blocks", 4))
    model = NeuroChessNet(channels=channels, blocks=blocks)
    state = checkpoint.get("model_state", checkpoint) if isinstance(checkpoint, dict) else checkpoint
    model.load_state_dict(state)
    model.eval()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros((1, 26, 8, 8), dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy,
        str(args.output),
        input_names=["board"],
        output_names=["policy", "wdl_logits"],
        opset_version=args.opset,
        do_constant_folding=True,
    )
    print(f"Exported ONNX model to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
