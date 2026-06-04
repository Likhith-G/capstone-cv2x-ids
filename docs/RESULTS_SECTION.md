# Results: 5G C-V2X Dataset Generation and Baseline Evaluation

## 4.1 Simulation Environment

The dataset was generated using NS-3 (v3.42) with the 5G-LENA NR module. The scaled simulation topology models a 5G C-V2X highway corridor with four gNBs positioned sequentially to provide continuous coverage, serving 40 User Equipment (UE) nodes representing connected vehicles. Each UE transmits Basic Safety Messages (BSMs) at 10 Hz (ETSI CAM standard rate) via UDP to a remote MEC edge server through the 5G NR radio access network and Evolved Packet Core (EPC). The NR configuration uses Band n78 (3.5 GHz) with 20 MHz bandwidth in TDD mode. Vehicle mobility follows the `ConstantVelocityMobilityModel` with speeds uniformly distributed between 8--15 m/s (29--54 km/h), representative of urban arterial traffic.

Each simulation scenario runs for 600 seconds (10 minutes) with dynamic, per-scenario random seeds (43–54). In attack scenarios, 5 out of the 40 UEs (Nodes 0-4) act as attackers while the remaining 35 UEs transmit honest traffic, producing a realistic 1:7 attacker-to-honest ratio.

## 4.2 Attack Scenarios

The dataset encompasses 12 distinct scenarios covering two attack domains: network-layer and vehicular application-layer.

**Network-layer attacks (S01–S05)** are implemented via a custom C++ application that generates transport-layer flood traffic at varying rates, packet sizes, and burstiness profiles directed at the MEC server. Each attack type produces a distinct volumetric traffic fingerprint:

| Scenario | Attack Type | Injection Rate | Pkt Size | Traffic Pattern |
|----------|-------------|----------------|----------|-----------------|
| S01 | UDP Flood | 500 pps | 1024 B | Continuous |
| S02 | ICMP Flood | 200 pps | 64 B | Continuous |
| S03 | SYN Flood | 400 pps (avg) | 64 B | Burst (500 Hz for 200ms, 50ms pause) |
| S04 | HTTP Flood | 200 pps | 1460 B | Continuous |
| S05 | Slow DoS | 4 pps (avg) | 64 B | Intermittent (20 Hz for 500ms, 2000ms pause) |

**Vehicular-layer attacks (S06–S11)** manipulate the physical kinematics and metadata within the BSM payload while maintaining normal transmission rates (except S11):

| Scenario | Attack Type | Mechanism |
|----------|-------------|-----------|
| S06 | Position Spoofing | BSM payload claims a false position fixed at +500m from truth |
| S07 | Random Position | BSM claims random, highly erratic coordinates each cycle |
| S08 | Replay | Attacker retransmits previously cached BSMs |
| S09 | False Data Injection | BSM speed field inflated by a factor of 2.5–4.0x (random per packet) |
| S10 | Sybil | A single physical node cycles through 5 fake vehicle IDs |
| S11 | Vehicular DoS | BSM transmission rate is elevated to 1000 Hz |

## 4.3 Feature Extraction Pipeline

To overcome the limitations of aggregate FlowMonitor statistics, the pipeline implements per-packet logging directly at the application layer. These raw packet logs contain real NS-3 timestamps, true positions from the MobilityModel, claimed positions from payloads, and ground-truth labels. The logs are aggregated into 30-second overlapping time windows (15-second sliding step) per UE.

The feature set comprises 24 informative model features spanning two domains:

- **5G Network Features (18):** Packet counts (`n_pkts`, `n_bsm`, `n_flood`), `flood_ratio`, `total_bytes`, `pkt_rate`, `byte_rate`, inter-arrival time statistics (`mean_iat`, `std_iat`, `min_iat`, `max_iat`), separated BSM and flood IAT statistics (`bsm_mean_iat`, `bsm_std_iat`\*, `flood_mean_iat`, `flood_std_iat`), packet size statistics (`mean_pkt_size`, `std_pkt_size`), and `duration`.
- **Vehicular Context Features (10):** Positional deviation (`mean_pos_deviation`, `max_pos_deviation`), speed deviation (`mean_speed_deviation`, `max_speed_deviation`), sequence number anomalies, unique vehicle ID count, and message frequency (`msg_freq`).

Five features exhibit zero variance due to the `ConstantVelocityMobilityModel` and are dynamically filtered before classification: `bsm_std_iat`, `heading_change_rate`, `bsm_size_mean`, `bsm_size_std`, and `true_speed_std`. Four context features (`true_speed_mean`, `true_speed_std`, `distance_to_gnb`, `region_id`) are excluded as they correlate with node identity. After removing metadata, labels, zero-variance, and context columns, this leaves **24 informative features** from the 39 total columns.

## 4.4 Dataset Statistics and Separability

The dataset contains **18,240 rows** and **39 columns** with zero null or infinite values. The class distribution reflects the 30-second windowing across 40 nodes over 12 scenarios:
- **Benign:** 16,150 windows (88.5%)
- **Attacks:** 190 windows per attack type x 11 types = **2,090 attack windows total (11.46%)**

Table 1 highlights key feature separability, demonstrating that network and vehicular attacks manifest in entirely different feature spaces.

**Table 1: Feature Separability Profiles (Representative Means)**

| Feature | Benign | UDP Flood | Position Spoof | Vehicular DoS | FDI |
|---------|--------|-----------|----------------|---------------|-----|
| `flood_ratio` | 0.000 | >0.900 | 0.000 | 0.000 | 0.000 |
| `mean_pos_deviation` | 0.00 m | 0.00 m | ~500.0 m | 0.00 m | 0.00 m |
| `mean_speed_deviation` | 0.00 m/s | 0.00 m/s | 0.00 m/s | 0.00 m/s | >5.0 m/s |
| `n_pkts` (per window) | ~300 | >15,000 | ~300 | ~30,000 | ~300 |
| `unique_vehicle_ids` | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

*Note: The Sybil attack perfectly isolates `unique_vehicle_ids = 5`, while all other classes maintain 1.00.*

## 4.5 Baseline Classification and Feature Ablation

A Random Forest classifier (200 estimators, max depth 20) was evaluated to validate class separability. To prevent temporal data leakage caused by overlapping 30-second windows, evaluation was strictly performed using **StratifiedGroupKFold** cross-validation, grouping by `(scenario_id, node_id)`.

Furthermore, deterministic node context features (`true_speed_mean`, `distance_to_gnb`, `region_id`) were explicitly removed. A validation test confirmed that after proper seed randomisation across scenarios, a model trained *only* on `true_speed_mean` achieved an F1 score of 0.4968, proving that node identity leakage (context fingerprinting) was successfully eradicated.

### 4.5.1 Dual-Layer Feature Ablation Study

To mathematically prove the necessity of the dual-layer feature architecture, an ablation study was conducted on isolated feature subsets.

**Table 2: Baseline Classifier Results (Grouped CV, 5-Fold)**

| Configuration | Features Used | Macro F1 | Accuracy |
|--------------|----------|------------|----------|
| **Binary (Full Features)** | **24** | **1.0000** | **1.0000** |
| Binary (Network Features Only) | 17 | 0.8405 | 0.9479 |
| Binary (Vehicular Features Only) | 7 | 0.8308 | 0.9479 |
| Binary (No Position Features) | 22 | 0.9201 | 0.9688 |
| Binary (No Speed Features) | 22 | 0.9718 | 0.9896 |
| **Multi-class (12 classes)** | **24** | **1.0000** | **1.0000** |

**Key Findings:**
1. **Domain Isolation Failure:** When restricted to only Network Features, the model fails to detect vehicular payload anomalies (macro F1 drops to 0.8405). Conversely, Vehicular Features alone cannot detect low-volume network attacks like SlowDoS (macro F1 drops to 0.8308).
2. **Perfect Synthesis:** Combining both domains enables perfect separation (F1 = 1.0000). The perfect score is legitimate in this context: simulated network floods generate massive, pristine volumetric deviations (e.g., fixed PPS injection rates), while simulated vehicular attacks generate deterministic physical deviations. In a low-noise NS-3 environment, these are trivial decision boundaries for a Random Forest.

### 4.5.2 Feature Importance Analysis

Gini importance extracted from the Random Forest confirms the model utilizes features from both domains simultaneously:
1. `mean_pos_deviation` (Vehicular): Primary discriminator for Position Spoofing, Random Position, and Replay attacks (due to stale coordinate lag).
2. `n_flood` / `flood_ratio` (Network): Primary discriminators for all 5 network-layer DoS attacks.
3. `mean_speed_deviation` (Vehicular): Exclusively isolates the False Data Injection class.
4. `unique_vehicle_ids` (Vehicular): Exclusively isolates the Sybil attack class.

## 4.6 Train / Val / Test Partitioning

To support federated learning and centralized deep learning experiments, the dataset was strictly split into a 70/15/15 ratio. 

Standard random splitting (like `GroupShuffleSplit`) frequently results in missing attack classes in the smaller validation and test sets. To guarantee complete representation, the split was performed at the node level *stratified within each scenario*. 

This splitting logic guarantees that:
1. An entire node's 600-second timeline is kept strictly within a single split (preventing temporal sliding-window leakage).
2. All 12 attack types are perfectly represented in the train, validation, and test sets.

| Split | Rows | Nodes (Groups) | Benign | Attack |
|-------|------|----------------|--------|--------|
| Train | 12,350 (67.7%) | 325 | 11,096 | 1,254 |
| Validation | 2,736 (15.0%) | 72 | 2,318 | 418 |
| Test | 3,154 (17.3%) | 83 | 2,736 | 418 |

## 4.7 Dataset Validation

An automated verification suite was executed against the final dataset, passing all internal integrity checks:
- **Structural Integrity:** 18,240 rows exactly conserved across splits; zero overlapping groups.
- **Physical Plausibility:** Positive durations, strictly positive inter-arrival times, no `NaN` or `Inf` values.
- **Leakage Eradication:** Deterministic context features excluded; target class distributions verified.

## 4.8 Discussion and Known Limitations

The dataset successfully resolves the structural flaws of earlier pipeline iterations by enforcing strict Grouped Cross-Validation, randomising mobility seeds per scenario, and natively parsing packets at the application layer to remove synthetic bounding logic. 

However, the following limitations remain documented for transparency:
1. **Constant Velocity Mobility:** Vehicles travel in straight lines at constant speeds. Consequently, features like `heading_change_rate` exhibit exactly zero variance. Integration with a microscopic traffic simulator (e.g., SUMO) is required for realistic urban mobility.
2. **Pristine Attack Signals:** The deterministic nature of NS-3 means attack signatures (e.g., 500m fixed position offsets, exact flood rates) lack the stochastic noise present in real-world measurements, resulting in artificially high F1 scores. 
3. **Replay Attack Detection Mechanism:**

   The feature selection pipeline did not select `seq_anomaly` — it ranked below the k=15 cutoff in both binary and multiclass evaluations. Replay attacks (S08) are instead detected via `mean_pos_deviation`: when an attacker retransmits cached BSMs from 5 seconds ago, the claimed coordinates lag behind the vehicle's true trajectory by the distance traveled in that interval. At vehicle speeds of 8–15 m/s, this produces 40–75m of positional deviation per window, which `mean_pos_deviation` captures cleanly.

   **Why `seq_anomaly` is weak:** The naive detection threshold (`seq_jump < 0` or `seq_jump > 100`) only triggers on ~2.6% of replay windows. The attacker reuses cached BSMs that retain monotonically increasing sequence numbers from the original cache period — these replayed sequences do not violate the jump threshold. The feature is structurally unable to detect replay attacks where the sequence gap falls within the normal range.

   **Real-world implication:** The `mean_pos_deviation`-based detection would fail against **position-coherent replay attacks** where the attacker interpolates or adjusts replayed coordinates to match expected trajectories. More robust approaches for future work include: (a) cryptographic nonce-based freshness checks embedded in BSM payloads (ETSI TS 103 097), (b) timestamp-aware sequence analysis using sliding-window entropy or autocorrelation, and (c) cross-vehicle plausibility checks where neighboring vehicles corroborate each other's claimed positions.

4. **Class Imbalance:** The dataset is naturally skewed towards the benign class (88.5%). Downstream federated learning models must utilize stratified sampling, class weighting, or focal loss mechanisms to prevent collapse.

## 4.9 Dropout Robustness Check Under Non-IID Conditions

To evaluate whether standard regularization mitigates FL performance degradation under extreme data heterogeneity, Dropout(p=0.2) was applied after each hidden layer of the MLP and tested on the two worst-performing FedAvg configurations (C=5, α=0.1, E=1 and C=5, scenario-based, E=1), each averaged across 3 seeds.

**Table 4: Dropout Robustness Check (mean±std across 3 seeds)**

| Configuration | Metric | Original | Dropout=0.2 | Delta |
|---------------|--------|----------|-------------|-------|
| C=5, α=0.1, E=1 (Dirichlet) | Macro F1 | 0.6336±0.1755 | 0.4872±0.2437 | -0.1464 |
| C=5, scenario, E=1 | Macro F1 | 0.3951±0.1144 | 0.4952±0.1148 | +0.1001 |

The effect is configuration-dependent. Under Dirichlet partitioning (skewed but overlapping class distributions), dropout constrains model capacity and slows convergence within the 50-round budget (F1 drops by 0.15). Under scenario-based partitioning (completely disjoint attack types per client), dropout acts as implicit regularization against local overfitting, improving F1 by 0.10. This mixed result confirms that generic regularization is insufficient for non-IID FL — targeted approaches like FedProx, which directly constrains local weight divergence via a proximal term, are better suited and will be evaluated in Part B.

## 4.10 Federated Learning Communication Overhead

The FedAvg prototype (Section 5.3 of the FL workstream) reports FL training communication costs of 14.6 MB (C=3) and 24.4 MB (C=5) over 50 global rounds, compared to 0.75 MB for a one-time centralized dataset upload — a 19–32x overhead. **This ratio is an artifact of the small simulation dataset** (12,350 training samples × 64 bytes/sample) and does not reflect production communication economics.

In a real C-V2X deployment, centralized training requires **continuous raw data streaming** from vehicles to a central server, not a single static upload. Each vehicle transmits BSMs at 10 Hz with ~300 bytes per message (SAE J2735), producing a raw data stream of 3,000 bytes/sec per vehicle.

**Table 3: Break-Even Analysis — FL vs Centralized Streaming**

| Metric | Value |
|--------|-------|
| MLP model size | 12,780 parameters (51,120 bytes) |
| One FL model update (upload) | 51,120 bytes |
| Time for 1 vehicle to stream equivalent raw data | **17 seconds** |
| FL cost per RSU over 50 rounds (C=5, bidirectional) | 5.1 MB |
| Raw stream from 8 vehicles per RSU | 24 KB/s |
| Time for raw streaming to match total FL training cost | **~3.5 minutes** |
| Raw data from 8 vehicles over 10-minute session | 14.4 MB (2.8x the FL cost) |

After just 17 seconds of driving, a single vehicle has already streamed more raw data than one complete model weight upload. An RSU serving 8 vehicles surpasses the entire 50-round FL training budget within approximately 3.5 minutes — less than a single traffic light cycle. Over a typical 10-minute urban driving session, raw streaming generates 2.8x more data than the full FL training cost.

At production scale with hundreds of vehicles per RSU, the ratio inverts dramatically: FL sends periodic 51 KB weight updates while centralized streaming grows linearly with vehicle count. Crucially, FL also never transmits raw BSM feature data to a central server, preserving driver location privacy — a compliance requirement under GDPR and equivalent frameworks governing GPS trajectory data.
