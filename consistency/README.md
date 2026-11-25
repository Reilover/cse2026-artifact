# consistency — number audit tooling for the paper

The paper's numbers are never typed by hand: they are computed from this artifact by a generator and
checked against the manuscript by a checker. Both scripts are plain Python 3 (standard library only).

| file | role |
|---|---|
| `generate_results_summary.py` | computes every table cell and narrative number of the paper from the artifact and writes `results_summary.json` (plus a human-readable `RESULTS-SUMMARY.md`). It never reads the paper. |
| `check_paper_consistency.py` | parses the manuscript tables, compares each printed number with `results_summary.json`, re-derives every narrative number as an exact string, and verifies the boolean claims. Exit code 0 only when everything agrees. |
| `fig_cage4_overview.manifest.json` | the bar labels printed on the paper's CAGE4 overview figure (transcribed from the PNG), compared with Table 5 by the checker. |
| `results_summary.json` | the generated truth (artifact truth for Tables 3 and 5, md-report truth for Table 4 and the three supplementary experiments). |

## Running

From this directory, with the system Python 3 (the pipeline needs matplotlib for an optional import):

```
python3 generate_results_summary.py          # first run evaluates 1,620 episodes (about 3 minutes) and caches them in cache/
python3 check_paper_consistency.py --paper <path/to/main.tex> --figdir <path/to/figures>
```

Both scripts locate the artifact root by themselves when they sit in `anon_repo_v2/consistency/`;
`CSE_REPO` / `--repo` override it.

## Source tiers (in order of authority)

1. **Raw recompute** (Table 3, the Spearman check, the simplex checks, the success-flag rates): the shipped
   pipeline in `wxpgzs_src/` over the episode logs in `inputs/`. The Cyberwheel evaluation files hold three
   episodes each; the generator splits them per episode and writes a per-episode decoy manifest, otherwise
   decoys of neighbouring episodes would be treated as authoritative honeypots.
2. **Derived CSV** (cross-arm, strike rates, training curves): `results/cw_deep_dive/` and
   `supplement_experiments_backup/cross_arm/`. The cross-arm corpus reproduces these CSVs exactly with the
   shipped pipeline.
3. **md report** (Table 4 and the step-sensitivity, same-red and paired-decoy experiments): the per-episode
   corpora of these experiments are not part of the artifact, so their values are taken from
   `report/phase5_report_cn_v9.md` and are labelled as such in `results_summary.json`.

## Provenance note on the Cyberwheel evaluation table

The paper's RL-evaluation table (18 cells, sync on/off) is the shipped-pipeline recompute. Its nine sync-on
cells reproduce the v9 report, section 3.1, to the report's four decimals. `results/cw_deep_dive/eval_episodes.csv`
is an earlier export (2026-09-17, before the honeypot-denominator fix of 2026-09-21): it agrees for arm A
(no decoys) and differs for the decoy-deploying arms B1/B2 (damage +0.001 to +0.016), so it documents the
deep-dive analyses of the report and is not the source of that table.
