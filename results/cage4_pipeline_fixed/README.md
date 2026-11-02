# CAGE4 Pipeline Results (Fixed Evaluation Chain)

Per-episode indicator outputs of the repaired evaluation pipeline
(2026-09-16 fix: action-name normalization, exploit-target resolution,
persistent decoy model, per-episode topology sidecars), one directory per
episode: `metrics_table.csv` (per-step indicators; final row = final-step
values) and `_process2.json` (reconstructed attack process).

## 2026-11-02 regeneration note

- `C4-RS/ep_cage4_sleep_rl_train_ep001` replaced: the previously shipped
  output was produced with an intermediate sidecar topology that matched
  only 30 of the 91 recorded red actions (the pre-H6 out-of-topology
  pathology). The current output matches all 91 actions and is exactly
  what `cli.py -t ep_cage4_sleep_rl_train_ep001.csv.topology.yaml`
  reproduces from the shipped corpus.
- `C4-DF` ep002/ep003 and `C4-FS` ep002/ep003 added: the package
  previously shipped only ep001 for these units. The added outputs are
  byte-identical in provenance to ep001 (same pipeline invocation, same
  sidecar-topology convention).

All 7 units x 3 episodes now ship complete. Every output in this
directory is reproducible from `inputs/cage4/` + `wxpgzs_src/cli.py`
with the per-episode `<episode>.csv.topology.yaml` sidecars, e.g.:

    cd wxpgzs_src
    python3 cli.py -t ../inputs/cage4/ep_cage4_gnn_ppo_eval_ep001.csv.topology.yaml \
                    -c ../inputs/cage4/ep_cage4_gnn_ppo_eval_ep001.csv \
                    -o /tmp/check --no-charts

Aggregates over the three episodes per unit (mean +/- std of the final
row) correspond to the camera-ready Tables 5-6 and Fig. 3 of the paper.
