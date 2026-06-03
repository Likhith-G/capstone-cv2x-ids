# Results: Dataset Generation and Baseline Evaluation

## 4.1 Simulation Environment

The v3.0 dataset was generated using NS-3 (v3.42) with the 5G-LENA NR module. The scaled simulation topology models a 5G C-V2X highway corridor with four gNBs positioned sequentially to provide continuous coverage, serving 40 User Equipment (UE) nodes representing connected vehicles. Each UE transmits Basic Safety Messages (BSMs) at 10 Hz (ETSI CAM standard rate) via UDP to a remote MEC edge server through the 5G NR radio access network and Evolved Packet Core (EPC). The NR configuration uses Band n78 (3.5 GHz) with 20 MHz bandwidth in TDD mode. Vehicle mobility follows the `ConstantVelocityMobilityModel` with speeds uniformly distributed between 8--15 m/s (29--54 km/h), representative of urban arterial traffic.

Each simulation scenario runs for 600 seconds (10 minutes) with dynamic, per-scenario random seeds (43–54). In attack scenarios, 5 out of the 40 UEs (Nodes 0-4) act as attackers while the remaining 35 UEs transmit honest traffic, producing a realistic 1:7 attacker-to-honest ratio.

## 4.2 Attack Scenarios

The dataset encompasses 12 distinct scenarios covering two attack domains: network-layer and vehicular application-layer.

**Network-layer attacks (S01–S05)** are implemented via a custom C++ application that generates transport-layer flood traffic at varying rates, packet sizes, and burstiness profiles directed at the MEC server. Each attack type produces a distinct volumetric traffic fingerprint:

| Scenario | Attack Type | Injection Rate | Pkt Size | Traffic Pattern |
|----------|-------------|----------------|----------|-----------------|
| S01 | UDP Flood | 500 pps | 1024 B | Continuous |
| S02 | ICMP Flood | 200 pps | 64 B | Continuous |
| S03 | SYN Flood | 400 pps | 64 B | Continuous |
| S04 | HTTP Flood | 200 pps | 1460 B | Continuous |
| S05 | Slow DoS | 10 pps | 64 B | Intermittent, low-rate |

**Vehicular-layer attacks (S06–S11)** manipulate the physical kinematics and metadata within the BSM payload while maintaining normal transmission rates (except S11):

| Scenario | Attack Type | Mechanism |
|----------|-------------|-----------|
| S06 | Position Spoofing | BSM payload claims a false position fixed at +500m from truth |
| S07 | Random Position | BSM claims random, highly erratic coordinates each cycle |
| S08 | Replay | Attacker retransmits previously cached BSMs |
| S09 | False Data Injection | BSM speed field is artificially inflated by +50% |
| S10 | Sybil | A single physical node cycles through 5 fake vehicle IDs |
| S11 | Vehicular DoS | BSM transmission rate is elevated to 1000 Hz |

## 4.3 Feature Extraction Pipeline

To overcome the limitations of aggregate FlowMonitor statistics, the v3.0 pipeline implements per-packet logging directly at the application layer. These raw packet logs contain real NS-3 timestamps, true positions from the MobilityModel, claimed positions from payloads, and ground-truth labels. The logs are aggregated into 30-second overlapping time windows (15-second sliding step) per UE.

The feature set comprises 23 informative model features spanning two domains:

- **5G Network Features (18):** Packet counts (`n_pkts`, `n_bsm`, `n_flood`), `flood_ratio`, `total_bytes`, `pkt_rate`, `byte_rate`, inter-arrival time statistics (`mean_iat`, `std_iat`, `min_iat`, `max_iat`), separated BSM and flood IAT statistics (`bsm_mean_iat`, `bsm_std_iat`\*, `flood_mean_iat`, `flood_std_iat`), packet size statistics (`mean_pkt_size`, `std_pkt_size`), and `duration`.
- **Vehicular Context Features (10):** Positional deviation (`mean_pos_deviation`, `max_pos_deviation`), speed deviation (`mean_speed_deviation`, `max_speed_deviation`), sequence number anomalies, unique vehicle ID count, and message frequency (`msg_freq`).

Five features exhibit zero variance due to the `ConstantVelocityMobilityModel` and are dynamically filtered before classification: `bsm_std_iat`, `heading_change_rate`, `bsm_size_mean`, `bsm_size_std`, and `true_speed_std`. This leaves **23 informative features** from the 28 non-metadata, non-label columns.

## 4.4 Dataset Statistics and Separability

The final dataset contains **18,240 rows** and **39 columns** with zero null or infinite values. The class distribution reflects the 30-second windowing across 40 nodes over 12 scenarios:
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
| **Binary (Full Features)** | **23** | **1.0000** | **1.0000** |
| Binary (Network Features Only) | 15 | 0.8405 | 0.9479 |
| Binary (Vehicular Features Only) | 7 | 0.8308 | 0.9479 |
| Binary (No Position Features) | 21 | 0.9201 | 0.9688 |
| Binary (No Speed Features) | 21 | 0.9718 | 0.9896 |
| **Multi-class (12 classes)** | **23** | **1.0000** | **1.0000** |

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

The v3 dataset successfully resolves the structural flaws of earlier pipeline iterations by enforcing strict Grouped Cross-Validation, randomising mobility seeds per scenario, and natively parsing packets at the application layer to remove synthetic bounding logic. 

However, the following limitations remain documented for transparency:
1. **Constant Velocity Mobility:** Vehicles travel in straight lines at constant speeds. Consequently, features like `heading_change_rate` exhibit exactly zero variance. Integration with a microscopic traffic simulator (e.g., SUMO) is required for realistic urban mobility.
2. **Pristine Attack Signals:** The deterministic nature of NS-3 means attack signatures (e.g., 500m fixed position offsets, exact flood rates) lack the stochastic noise present in real-world measurements, resulting in artificially high F1 scores. 
3. **Replay Attack Detection:** The naive `seq_anomaly` feature only triggers on ~2.6% of replay windows. Replay attacks are instead successfully detected via `mean_pos_deviation` (as the replayed BSMs contain stale, lagging physical coordinates that deviate from the true vehicle trajectory). A more robust sequence analysis algorithm is needed for future work.
4. **Class Imbalance:** The dataset is naturally skewed towards the benign class (88.5%). Downstream federated learning models must utilize stratified sampling, class weighting, or focal loss mechanisms to prevent collapse.
