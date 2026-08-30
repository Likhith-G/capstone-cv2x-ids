# Earlier coursework phase

RMIT engineering capstone, OENG1167. A group project supervised by A/Prof Ke
(Desmond) Wang with research mentor Mr. Kanwardeep Singh Gahlot. The group's
earlier VeReMi work is not in this repository.

Everything here is kept for reference. It is not used by the simulation or
analysis at the top level, and results reported in it should not be read as
current.

## What is here

| Directory | Contents |
|---|---|
| `dataset-expansion/` | ns-3 simulation over a 5G uplink to a MEC server, the windowing pipeline, and the generated dataset |
| `feature-engineering/` | ANOVA and mutual information ranking, top-k sweeps, SHAP plots |
| `classification/` | Random Forest, gradient boosting and MLP baselines |
| `federated-learning/` | FedAvg prototype, 60 experiments over two partitioning strategies |
| `RESULTS_SECTION.md` | results write-up, as submitted |
| `walkthrough.md` | walkthrough of the four workstreams |
| `Project_Proposal_Assessment1.pdf` | project proposal |

## How this differs from the current work

The simulation here uplinks safety messages to a MEC server over a 5G Uu link
rather than exchanging them directly over a PC5 sidelink. Mobility is constant
velocity, benign traffic is a fixed-rate message stream, and features are drawn
from traffic statistics and message payloads with nothing from the physical or
MAC layer. Some of them difference a claimed value against the simulator's true
position and speed, which a deployed roadside unit does not have.

Those choices are why the work was rebuilt rather than extended. The current
pipeline is described in the top-level [README](../README.md).

## Running it

The scripts here expect `dataset-expansion/output/train.csv`, `val.csv` and
`test.csv`. Regenerate them with:

```bash
cd ~/ns-allinone-3.42/ns-3.42
cp path/to/capstone/dataset-expansion/simulation/simulation.cc scratch/
cp path/to/capstone/dataset-expansion/pipeline/* pipeline/
bash pipeline/run_all.sh
```

Raw per-packet logs are around 837 MB and are excluded from the repository.
