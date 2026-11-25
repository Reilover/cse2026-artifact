# Evaluation Artifact: A Multi-Dimensional Assessment Method for Cyber-Defense Simulation Environments (CSE 2026)

Self-contained evaluation package for two autonomous-cyber-defense (ACD) environments: CybORG CAGE Challenge 4 and Cyberwheel (CW). It contains the input episode corpora (including supplementary experiments), the assessment pipeline source code, and pre-computed results.

## Directory Layout

```
├── README.md                          this file
├── config_reference.md                shorthand and configuration reference (CW + CAGE4 only)
├── inputs/
│   ├── cw/                            all CW corpora (eval + train + supplementary EXP-1/2)
│   │   ├── cw_art_eval_*.csv          ART-defender evaluation rollouts
│   │   ├── cw_r_eval_*.csv            RL-defender evaluation rollouts (incl. EXP-1 sampled replicas)
│   │   ├── cw_r_train_B1var*.csv      EXP-2: ten scripted B1 variants
│   │   ├── *.decoys.json              decoy-manifest sidecars (one per CSV)
│   │   └── topology_{10h,25h,50h}.yaml
│   └── cage4/                         all CAGE4 corpora (3 baseline + 4 variant units + EXP-3 additions)
│       ├── ep_cage4_{b_line,meander,sleep}_rl_train_ep00{1..3}.csv
│       ├── ep_cage4_{gnn_ppo,hmarl}[_det]_eval_ep00{1..3}.csv
│       ├── *.decoys.json              decoy-manifest sidecars
│       └── *.topology.yaml            per-episode topology sidecars
├── wxpgzs_src/                        assessment pipeline source (10 files, directly runnable)
│   ├── cli.py                         entry point
│   ├── pre_process.py                 preprocessing (phantom filtering / decoy removal)
│   ├── generate_process_linked_list.py
│   ├── generate_process2_json.py      indicator computation (21 indicators)
│   ├── action_vocab.yaml              action vocabulary
│   ├── success_semantics.yaml         per-environment success-flag semantics
│   └── ...
├── results/
│   ├── cw_deep_dive/                  CW deep-dive analysis outputs
│   └── cage4_pipeline_fixed/          CAGE4 per-episode indicator tables (metrics_table.csv + _p.json)
├── report/
│   ├── phase5_report_cn_v9.md         analysis report (CW + CAGE4 only; in Chinese)
│   └── phase5_report_cn_v9.html       HTML version
└── topologies/
    ├── cw/                            CW topology mirror
    └── cage4/                         CAGE4 topology mirror (incl. C4-RS ep002/003 sidecars)
```

## Reproducing the Evaluation

Run from the package root:

```bash
cd wxpgzs_src

# Single CAGE4 episode (example: C4-GNN ep001)
python3 cli.py -t ../inputs/cage4/ep_cage4_gnn_ppo_eval_ep001.csv.topology.yaml \
               -c ../inputs/cage4/ep_cage4_gnn_ppo_eval_ep001.csv \
               -o ../result_test/

# Single CW episode (example: ART 10host)
python3 cli.py -t ../inputs/cw/topology_10h.yaml \
               -c ../inputs/cw/cw_art_eval_10host_sync0_s1.csv \
               -o ../result_test/

# Batch evaluation
bash run_eval.sh
```

Output: `result_test/<corpus-name>/metrics_table.csv` plus `_process2.json` (step-by-step and final-step indicator tables).

## Supplementary Experiments

The supplementary-experiment corpora (EXP-1/2/3) are merged into the corresponding `inputs/` directories:

| Experiment | Merged under | Corpus pattern |
|---|---|---|
| EXP-1 RL sampled replicas | `inputs/cw/cw_r_eval_A_sampled_*` | 25host / sync-on / 100 steps / 5 episodes |
| EXP-2 B1 distribution extension | `inputs/cw/cw_r_train_B1var*` | 25host / sync-on / 10k steps / 10 variants |
| EXP-3 CAGE4 n=3 | `inputs/cage4/ep_cage4_*_ep00{2,3}.*` | same configuration as ep001, different seeds |

Analysis results are in `report/`, Section 6.8.

## Note on the C4-RS Red Agent

The C4-RS corpus (sleep episodes) previously fell back silently to the wrong red agent (FSRA) via `RED_AGENT_MAP`. This has been fixed: all three episodes were re-exported with the correct `RandomSelectRedAgent`. The `inputs/cage4/ep_cage4_sleep_*` files in this package are the corrected data.

## Dependencies

Python 3.8+; dependencies are listed in the header comment of `wxpgzs_src/run_eval.sh`.
