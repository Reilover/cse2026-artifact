# CAGE4 + CW Configuration and Naming Reference

> **Purpose**: explains every unit, variant, condition, and shorthand used in this evaluation package.
> **Coverage**: CW (24 units) + CAGE4 (7 units) = **31 units**.
> **Last updated**: 2026-09-20.

---

## 1. The Two Environments at a Glance

| Code | Full name | Type | Red agent | Blue agent | Units |
|---|---|---|---|---|---|
| **CW** | CyberWheel | honeypot simulation | RL / ART (scripted) | RL (arms A/B1/B2) | 24 |
| **CAGE4** | CAGE Challenge 4 (CybORG Enterprise) | enterprise-network simulation (CybORG family) | FiniteStateRedAgent (scripted) | GNN-PPO / HMARL ±Det / RL | 7 |

**31 units in total.**

---

## 2. CW Unit Naming (24 Units)

### 2.1 Naming formula

```
CW-{blue-arm}{topology-scale}{phase-suffix}
```

### 2.2 Blue arms

| Arm | Full name | Meaning | Training-phase decoys |
|---|---|---|---|
| **A** | sync-off | RL blue agent, trained with the red agent's observation loop disconnected (legacy condition); deployment decays to zero by training episodes 14--22 | deployable (decays to 0) |
| **B1** | RL + baseline reward | RL blue agent, reward = `reward_decoy_hits` (upstream default) | deployable |
| **B2** | RL + penalty variant | RL blue agent, co-trained with red-reward variant `reward_decoy_hits_penalized` (each successful decoy strike: −10 to the red agent's environment reward) | deployable |

### 2.3 Topology scales

| Suffix | Hosts | Subnets |
|---|---|---|
| `10host` | 10 | 5 |
| `25host` | 25 | 5+ |
| `50host` | 50 | 5+ |

### 2.4 Phase suffixes

| Suffix | Meaning | Episodes |
|---|---|---:|
| (none) = eval | evaluation rollout | 45 |
| **RT** | RL train rollout | 300 |
| **AT** | ART train rollout | 50 |
| **CWX-RT** | RL train ×10 steps (step sensitivity) | 10 |
| **CWX-AT** | ART train ×10 steps | 5 |

---

## 3. CAGE4 Unit Naming (7 Units)

| Unit | Blue agent | Weights source | Decoys/episode | Det meaning |
|---|---|---|---|---|
| **C4-GNN** | GNN-PPO (sampled) | cage-4-submission | ~50 hosts | — |
| **C4-GNN-Det** | GNN-PPO (deterministic) | same | 8–21 hosts | `set_deterministic(True)` |
| **C4-HMARL** | Hierarchical MARL (sampled) | same | ~50 hosts | — |
| **C4-HMARL-Det** | Hierarchical MARL (deterministic) | same | 8–21 hosts | ditto |
| **C4-DF** | RL (self-trained) | cage4_rl_trainer | 0 hosts | red = B-Line mode |
| **C4-FS** | RL (self-trained) | same | 0 hosts | red = Meander mode |
| **C4-RS** | RL (self-trained) | same | ~2 hosts | red = RandomSelect mode |

**Notes**:
* **GNN = GNN-PPO** (same weights; `gnn` is the exporter's shorthand)
* In **C4-DF/FS/RS** filenames, `b_line/meander/sleep` refers to the **CAGE4 red agent's** behavioral mode (not the blue agent)
* **C4-RS** previously used the wrong red agent (FSRA) due to a silent `RED_AGENT_MAP` fallback; fixed on 2026-09-18 and all three episodes re-exported

---

## 4. Experimental Conditions

### 4.1 Synchronization switch (CW)

| Condition | Meaning |
|---|---|
| `sync0` | `CYBERWHEEL_SYNC_RED_TARGETS=0`: red targets not synced to the blue side |
| `sync1` | `CYBERWHEEL_SYNC_RED_TARGETS=1`: red targets synced to the blue side |

Scripted red agents (ART) are unaffected by this switch.

### 4.2 Paired-experiment conditions (CAGE4)

| Condition | Meaning |
|---|---|
| **ON** | blue decoy deployment active |
| **OFF** | blue decoy deployment rewritten to a no-op |

### 4.3 Phases

| Term | Meaning |
|---|---|
| **train** | rollout during RL/ART blue-agent training |
| **eval** | rollout after training completes |
| **10×** | episode length ×10 |

---

## 5. Indicator Shorthands

| Code | Full name | Meaning |
|---|---|---|
| **D** | D-Score | 0.35×DC + 0.35×DI + 0.30×DA |
| **DC** | Damage-Confidentiality | share of asset value the red agent has *discovered* |
| **DI** | Damage-Integrity | share of asset value the red agent *controls* |
| **DA** | Damage-Availability | share of asset value the red agent has *disabled* |
| **ctrl** | node_control_rate | fraction of nodes controlled by the red agent |
| **det** | node_detect_rate | fraction of nodes discovered by the red agent |
| **H** | comprehensive_concealment_score | red agent's overall concealment |
| **Plm** | lateral_movement_ratio | red agent's lateral-movement ratio |

---

## 6. Key Files in This Package

| File / directory | Role |
|---|---|
| `inputs/cw/` | CW corpora (eval + train + EXP-1/2) |
| `inputs/cage4/` | CAGE4 corpora (baseline + variants + EXP-3) |
| `inputs/cw/topology_*.yaml` | the three CW topology definitions |
| `inputs/cage4/*.topology.yaml` | CAGE4 per-episode topology sidecars |
| `inputs/**/*.decoys.json` | decoy-manifest sidecars (schema `cw-decoy-manifest-01`) |
| `wxpgzs_src/cli.py` | pipeline entry point |
| `wxpgzs_src/pre_process.py` | preprocessing (phantom filtering + decoy removal) |
| `wxpgzs_src/generate_process2_json.py` | indicator computation (21 indicators) |
| `wxpgzs_src/action_vocab.yaml` | unified action vocabulary |
| `wxpgzs_src/success_semantics.yaml` | per-environment success-flag semantics |
| `results/cw_deep_dive/` | CW deep-dive analysis outputs |
| `results/cage4_pipeline_fixed/` | CAGE4 per-episode indicator tables |
| `report/phase5_report_cn_v9.md` | analysis report (CW + CAGE4; written in Chinese) |
| `topologies/` | topology mirrors |

---

## 7. Pipeline Source Files

| File | Role |
|---|---|
| `cli.py` | entry: `python3 cli.py -t <topology> -c <corpus.csv> -o <outdir>` |
| `pre_process.py` | corpus parsing → node-set construction (phantom filtering + decoy removal) → summary |
| `generate_process_linked_list.py` | attack-chain linked-list construction (column-format compatibility) |
| `generate_process2_json.py` | 21-indicator computation (decoys excluded from control/damage numerators and denominators) |
| `action_vocab.yaml` | unified red-action vocabulary |
| `success_semantics.yaml` | per-environment `success`-field reading rules |
| `rerun_eval_v9.py` | batch-evaluation driver (topology binding rules) |
| `run_eval.sh` | batch-evaluation shell script |
