#!/usr/bin/env python3
"""
model.py -- PyTorch MLP for CV2X-IDS multiclass classification.
Mirrors the sklearn MLP from the classification workstream:
  15 -> 128 -> ReLU -> 64 -> ReLU -> 32 -> ReLU -> 12
"""

import numpy as np
import torch
import torch.nn as nn

from config import HIDDEN_LAYERS, N_CLASSES, N_FEATURES


class CV2XMLP(nn.Module):
    def __init__(
        self,
        input_dim=N_FEATURES,
        hidden_layers=None,
        n_classes=N_CLASSES,
    ):
        super().__init__()
        if hidden_layers is None:
            hidden_layers = HIDDEN_LAYERS

        layers = []
        prev_dim = input_dim
        for h in hidden_layers:
            layers.append(nn.Linear(prev_dim, h))
            layers.append(nn.ReLU())
            prev_dim = h
        layers.append(nn.Linear(prev_dim, n_classes))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


def get_n_params(model):
    return sum(p.numel() for p in model.parameters())


def get_model_size_bytes(model):
    return get_n_params(model) * 4  # float32


def get_weights(model):
    return [p.detach().cpu().numpy().copy() for p in model.parameters()]


def set_weights(model, weights):
    with torch.no_grad():
        for p, w in zip(model.parameters(), weights):
            p.copy_(torch.from_numpy(w))
