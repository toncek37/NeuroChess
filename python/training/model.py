from __future__ import annotations

import torch
from torch import nn

from .encoding import BOARD_CHANNELS, POLICY_SIZE


class ResidualBlock(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(channels, channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(channels, channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
        )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.relu(x + self.net(x))


class NeuroChessNet(nn.Module):
    def __init__(self, channels: int = 64, blocks: int = 4):
        super().__init__()
        self.channels = channels
        self.blocks = blocks
        self.stem = nn.Sequential(
            nn.Conv2d(BOARD_CHANNELS, channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
            nn.ReLU(inplace=True),
        )
        self.trunk = nn.Sequential(*(ResidualBlock(channels) for _ in range(blocks)))

        # 320 channels = 5 promotion buckets x 64 destination squares.
        # Spatial position encodes the source square, giving 20,480 move logits.
        self.policy_head = nn.Conv2d(channels, 320, kernel_size=1)

        self.value_head = nn.Sequential(
            nn.Conv2d(channels, 16, kernel_size=1, bias=False),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
            nn.Flatten(),
            nn.Linear(16 * 8 * 8, 128),
            nn.ReLU(inplace=True),
            nn.Linear(128, 3),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        features = self.trunk(self.stem(x))
        policy_map = self.policy_head(features)
        # Convert [B, promo*to, from_rank, from_file] to the encoding order
        # promo*4096 + from*64 + to.
        batch = policy_map.shape[0]
        policy = policy_map.view(batch, 5, 64, 64).permute(0, 1, 3, 2).reshape(batch, POLICY_SIZE)
        wdl_logits = self.value_head(features)
        return policy, wdl_logits
