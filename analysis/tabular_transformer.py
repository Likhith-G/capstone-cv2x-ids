#!/usr/bin/env python3
"""
A transformer over the window features, as a fifth learner family.

The four families in model_independence.py fail in different ways, and a
transformer fails in a fifth: every feature becomes a token, attention lets any
feature condition on any other, and a classification token reads the result.
If a position lie left a signal in some interaction of the 50 features that the
trees, the network and the linear model all missed, attention is the family
most likely to find it.

The architecture is the team's tabular transformer, moved from the network
intrusion data it was first built on to this corpus without changing its
design: a learned weight, bias and position per feature, a CLS token, GELU
encoder layers and a LayerNorm head. Its training recipe is kept too:
square-root balanced class weights, label smoothing 0.05, AdamW with cosine
annealing, and early stopping on validation macro F1. Only batch size, learning
rate and the epoch budget change, for compute (see __init__).

Two things change because this corpus is grouped by transmitter. The early
stopping split is drawn by station inside the training fold, so the model never
selects its epoch on a station it is scored on; and scaling is fitted inside
fit(), on the training fold only. The window features are not sequences, so
this is the comparable run. A transformer over raw message sequences changes
what the detector may see and is a different experiment.
"""
import numpy as np
import torch
import torch.nn as nn
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_class_weight


class _Net(nn.Module):
    def __init__(self, n_features, n_classes, d=64, heads=4, layers=3,
                 dropout=0.15):
        super().__init__()
        self.w = nn.Parameter(torch.randn(1, n_features, d) * 0.02)
        self.b = nn.Parameter(torch.zeros(1, n_features, d))
        self.pos = nn.Parameter(torch.randn(1, n_features, d) * 0.02)
        self.cls = nn.Parameter(torch.randn(1, 1, d) * 0.02)
        layer = nn.TransformerEncoderLayer(d_model=d, nhead=heads,
                                           dim_feedforward=4 * d,
                                           dropout=dropout, batch_first=True,
                                           activation="gelu")
        self.encoder = nn.TransformerEncoder(layer, num_layers=layers)
        self.head = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, d), nn.GELU(),
                                  nn.Dropout(dropout), nn.Linear(d, n_classes))

    def forward(self, x):
        tokens = x.unsqueeze(-1) * self.w + self.b + self.pos
        x = torch.cat([self.cls.expand(x.shape[0], -1, -1), tokens], dim=1)
        return self.head(self.encoder(x)[:, 0])


class TabularTransformer(BaseEstimator, ClassifierMixin):
    """sklearn interface so it runs on model_independence.py's folds unchanged.

    `groups` passed to fit() keep the early stopping split station-disjoint.
    Without them the split falls back to rows, which is only safe on data with
    one row per station.
    """

    # The team's recipe used batches of 128, a learning rate of 5e-4, up to 30
    # epochs and patience 6. On 150,000 rows that is about three minutes an
    # epoch on the development laptop, hours for three folds, so batches are
    # 1024 with the learning rate doubled, at most 20 epochs and patience 4.
    # Architecture, loss, class weights, smoothing and schedule are unchanged.
    def __init__(self, d=64, heads=4, layers=3, dropout=0.15, lr=1e-3,
                 weight_decay=1e-4, smoothing=0.05, batch=1024, max_epochs=20,
                 patience=4, val_frac=0.1, seed=0, device=None):
        self.d, self.heads, self.layers, self.dropout = d, heads, layers, dropout
        self.lr, self.weight_decay, self.smoothing = lr, weight_decay, smoothing
        self.batch, self.max_epochs, self.patience = batch, max_epochs, patience
        self.val_frac, self.seed, self.device = val_frac, seed, device

    def _dev(self):
        if self.device:
            return torch.device(self.device)
        return torch.device("mps" if torch.backends.mps.is_available() else "cpu")

    def _predict_codes(self, net, X, dev):
        net.eval()
        out = []
        with torch.no_grad():
            for i in range(0, len(X), 4096):
                xb = torch.tensor(X[i:i + 4096], dtype=torch.float32, device=dev)
                out.append(net(xb).argmax(1).cpu().numpy())
        return np.concatenate(out)

    def fit(self, X, y, groups=None):
        torch.manual_seed(self.seed)
        rng = np.random.RandomState(self.seed)
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)
        self.classes_ = np.unique(y)
        codes = np.searchsorted(self.classes_, y)

        if groups is not None:
            split = GroupShuffleSplit(n_splits=1, test_size=self.val_frac,
                                      random_state=self.seed)
            tr, va = next(split.split(X, codes, np.asarray(groups)))
        else:
            idx = rng.permutation(len(X))
            n_va = int(len(X) * self.val_frac)
            va, tr = idx[:n_va], idx[n_va:]

        self.scaler_ = StandardScaler().fit(X[tr])
        Xs = np.clip(self.scaler_.transform(X), -10, 10).astype(np.float32)

        w = compute_class_weight("balanced", classes=np.unique(codes[tr]),
                                 y=codes[tr])
        full = np.ones(len(self.classes_))
        full[np.unique(codes[tr])] = np.sqrt(w)
        full = full / full.mean()

        dev = self._dev()
        net = _Net(X.shape[1], len(self.classes_), self.d, self.heads,
                   self.layers, self.dropout).to(dev)
        loss_fn = nn.CrossEntropyLoss(
            weight=torch.tensor(full, dtype=torch.float32, device=dev),
            label_smoothing=self.smoothing)
        opt = torch.optim.AdamW(net.parameters(), lr=self.lr,
                                weight_decay=self.weight_decay)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=self.max_epochs)

        Xtr = torch.tensor(Xs[tr], device=dev)
        ytr = torch.tensor(codes[tr], dtype=torch.long, device=dev)
        best, best_state, stale = -1.0, None, 0
        self.history_ = []
        for epoch in range(1, self.max_epochs + 1):
            net.train()
            order = torch.tensor(rng.permutation(len(tr)), device=dev)
            for i in range(0, len(tr), self.batch):
                b = order[i:i + self.batch]
                opt.zero_grad()
                loss = loss_fn(net(Xtr[b]), ytr[b])
                loss.backward()
                opt.step()
            sched.step()
            f1 = f1_score(codes[va], self._predict_codes(net, Xs[va], dev),
                          average="macro", zero_division=0)
            self.history_.append((epoch, float(loss.item()), f1))
            if f1 > best:
                best, stale = f1, 0
                best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
            else:
                stale += 1
                if stale >= self.patience:
                    break
        net.load_state_dict(best_state)
        self.net_, self.dev_ = net, dev
        self.best_epoch_ = max(self.history_, key=lambda h: h[2])[0]
        self.val_f1_ = best
        return self

    def predict(self, X):
        Xs = np.clip(self.scaler_.transform(np.asarray(X, dtype=np.float64)),
                     -10, 10).astype(np.float32)
        return self.classes_[self._predict_codes(self.net_, Xs, self.dev_)]
