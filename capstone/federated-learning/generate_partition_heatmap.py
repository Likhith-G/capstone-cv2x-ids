"""
Generate Figure 11: Dirichlet non-IID partition heatmap.
Shows class distribution across FL clients under alpha = 100, 1.0, 0.5, 0.1
and scenario-based partitioning (C=5 clients in all panels).
Saved to: output/figures/partition_heatmap.png
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

SEED = 42
rng  = np.random.default_rng(SEED)

# ── Attack-type labels (12 classes) ──────────────────────────────────────────
CLASSES = [
    'Benign', 'UDP Flood', 'ICMP Flood', 'SYN Flood',
    'HTTP Flood', 'Slow DoS', 'Pos. Spoof', 'Rand. Pos.',
    'Replay', 'False Data Inj.', 'Sybil', 'Veh. DoS',
]
K = len(CLASSES)   # 12
C = 5              # clients

# ── Simulate Dirichlet partitions ─────────────────────────────────────────────
def dirichlet_partition(alpha, n_classes, n_clients, seed):
    rng_local = np.random.default_rng(seed)
    # Draw proportions per class across clients
    props = rng_local.dirichlet([alpha] * n_clients, size=n_classes)  # (K, C)
    return props  # rows=classes, cols=clients

# ── Scenario-based partition: each client owns disjoint attack scenarios ───────
def scenario_partition(n_classes, n_clients):
    # Client 0 gets Benign + 2 attacks; remaining 4 clients get 2-3 attacks each
    mat = np.zeros((n_classes, n_clients))
    # Benign is shared roughly by all clients
    mat[0, :] = 0.20  # each client sees ~20% of benign
    # Assign attack classes exclusively
    attack_indices = list(range(1, n_classes))
    np.random.seed(42)
    np.random.shuffle(attack_indices)
    chunks = np.array_split(attack_indices, n_clients)
    for c_idx, chunk in enumerate(chunks):
        for cls_idx in chunk:
            mat[cls_idx, c_idx] = 1.0
    # Normalise each class row so proportions sum to 1
    row_sums = mat.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    mat = mat / row_sums
    return mat

alphas = [100, 1.0, 0.5, 0.1]
partition_data = {}
for a in alphas:
    partition_data[f'α = {a}'] = dirichlet_partition(a, K, C, seed=42)
partition_data['Scenario-\nbased'] = scenario_partition(K, C)

titles = list(partition_data.keys())
n_panels = len(titles)   # 5

# ── Plot ───────────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, n_panels, figsize=(15, 5.2), constrained_layout=True)
fig.patch.set_facecolor('white')

cmap = plt.cm.Blues

client_labels = [f'Client {i+1}' for i in range(C)]

for ax, title, key in zip(axes, titles, titles):
    mat = partition_data[key]   # shape (K, C)
    im = ax.imshow(mat, aspect='auto', cmap=cmap, vmin=0, vmax=1,
                   interpolation='nearest')

    ax.set_xticks(range(C))
    ax.set_xticklabels(client_labels, fontsize=7, rotation=30, ha='right')
    ax.set_yticks(range(K))
    if ax == axes[0]:
        ax.set_yticklabels(CLASSES, fontsize=7.5)
    else:
        ax.set_yticklabels([])

    ax.set_title(title, fontsize=9.5, fontweight='bold', pad=6)

    # Annotate cells with proportion value
    for r in range(K):
        for c in range(C):
            val = mat[r, c]
            colour = 'white' if val > 0.55 else '#1A1A1A'
            ax.text(c, r, f'{val:.2f}', ha='center', va='center',
                    fontsize=5.8, color=colour)

    # Grid lines
    for x in np.arange(-0.5, C, 1):
        ax.axvline(x, color='white', linewidth=0.6)
    for y in np.arange(-0.5, K, 1):
        ax.axhline(y, color='white', linewidth=0.6)

# Shared colour bar
cbar = fig.colorbar(im, ax=axes, orientation='vertical',
                    fraction=0.015, pad=0.02, shrink=0.85)
cbar.set_label('Proportion of class assigned to client', fontsize=8)
cbar.ax.tick_params(labelsize=7)

fig.suptitle(
    'Figure 11: Dirichlet Non-IID Partition Heatmap — Class Distribution Across '
    'Federated Learning Clients (C = 5)\n'
    'As α decreases from 100 (near-IID) to 0.1 (extreme skew), '
    'individual clients receive increasingly unequal attack-type distributions. '
    'Scenario-based partitioning assigns entirely disjoint attack types per client.',
    fontsize=8, y=-0.02, ha='center',
)

out_path = 'output/figures/partition_heatmap.png'
plt.savefig(out_path, dpi=180, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved: {out_path}')
