#!/usr/bin/env python3
"""Artifact-grounded truth generator for the CSE 2026 paper numbers.

Computes every table cell and every narrative number of main.tex directly from the
anonymous artifact (anon_repo_v2) -- it never reads the paper.  Output:
  consistency/results_summary.json   (machine-readable truth + sources)
  RESULTS-SUMMARY.md                 (human-readable truth table, next to main.tex)

Sources (priority per the reuse manual: raw recompute > derived CSV > report md):
  T3  Table 3  : raw recompute, shipped pipeline (wxpgzs_src/cli.py) over inputs/cw/cw_r_eval_*
                 (per-episode split + per-episode decoy manifest).  Cached in consistency/cache.
  T5  Table 5  : results/cage4_pipeline_fixed/*/ep_*/metrics_table.csv last rows (+ steps from inputs/cage4)
  T4  Table 4  : report/phase5_report_cn_v9.md section 3.1 table (md report source; corpora not fully shipped)
  N*  narrative: cw_deep_dive CSVs, cross_arm per_episode.csv, v9 report tables, raw inputs.
Pipeline runs need the system python (matplotlib import is optional inside cli.py).
"""
import os, sys, csv, json, glob, re, time, shutil, tempfile, itertools, collections, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER_DIR = os.path.dirname(HERE)
_PARENT = os.path.dirname(HERE)   # inside the artifact (anon_repo_v2/consistency) the repo root is the parent directory
REPO = os.environ.get('CSE_REPO') or (_PARENT if os.path.isdir(os.path.join(_PARENT, 'wxpgzs_src')) else os.path.join(PAPER_DIR, 'anon_repo_v2'))
CACHE = os.path.join(HERE, 'cache')
DD = os.path.join(REPO, 'results/cw_deep_dive')
V9 = os.path.join(REPO, 'report/phase5_report_cn_v9.md')
USE_PIPELINE = '--no-pipeline' not in sys.argv

def mean(v): return st.mean(v)
def sd(v): return st.stdev(v) if len(v) > 1 else 0.0
def f3(x): return '%.3f' % (x + 0.0)

summary = {'_meta': {'repo': REPO, 'generated': time.strftime('%Y-%m-%d %H:%M:%S'), 'pipeline': USE_PIPELINE}}

# ----------------------------------------------------------------------------- helpers
def read_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def pipeline_last_rows(jobs, tag):
    """jobs: list of (key, topology, csv_rows, header, manifest_dict_or_None). Returns {key: last_row}."""
    cache_path = os.path.join(CACHE, f'pipeline_{tag}.json')
    os.makedirs(CACHE, exist_ok=True)
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    todo = [j for j in jobs if j[0] not in cache]
    if todo and USE_PIPELINE:
        sys.path.insert(0, os.path.join(REPO, 'wxpgzs_src'))
        import cli  # the shipped pipeline
        tmp = tempfile.mkdtemp(prefix='cse_gen_', dir=os.environ.get('TMPDIR', '/tmp'))
        for i, (key, topo, rows, hdr, man) in enumerate(todo):
            dst = os.path.join(tmp, 'ep.csv')
            with open(dst, 'w', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=hdr); w.writeheader()
                for r in rows: w.writerow(r)
            if man is not None:
                json.dump(man, open(dst + '.decoys.json', 'w'))
            res = cli.run_single_evaluation(topo, dst, os.path.join(tmp, 'out'), do_charts=False, verbose=False)
            if not res['success']:
                cache[key] = {'_error': res.get('error')}
                continue
            last = read_csv(res['table_path'])[-1]
            cache[key] = {k: last[k] for k in last}
            if i % 100 == 0:
                json.dump(cache, open(cache_path, 'w'))
        json.dump(cache, open(cache_path, 'w'))
        shutil.rmtree(tmp, ignore_errors=True)
    return {k: v for k, v in cache.items() if '_error' not in v}

def kendall(x, y):
    c = d = 0
    for i, j in itertools.combinations(range(len(x)), 2):
        s = (x[i] - x[j]) * (y[i] - y[j]); c += s > 0; d += s < 0
    return (c - d) / (len(x) * (len(x) - 1) / 2)

def ranks(v):
    idx = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and v[idx[j + 1]] == v[idx[i]]: j += 1
        for k in range(i, j + 1): r[idx[k]] = (i + j) / 2
        i = j + 1
    return r

def spearman(x, y):
    if len(set(x)) < 2 or len(set(y)) < 2: return None
    rx, ry = ranks(x), ranks(y); mx, my = mean(rx), mean(ry)
    num = sum((p - mx) * (q - my) for p, q in zip(rx, ry))
    den = (sum((p - mx) ** 2 for p in rx) * sum((q - my) ** 2 for q in ry)) ** 0.5
    return num / den if den else None

def v9_table(start_pat, n_rows):
    """Parse a markdown table following the first line matching start_pat."""
    lines = open(V9, encoding='utf-8').read().split('\n')
    start = next(i for i, l in enumerate(lines) if re.search(start_pat, l))
    rows = []
    for l in lines[start:start + n_rows]:
        cells = [c.strip().replace('**', '') for c in l.strip().strip('|').split('|')]
        rows.append(cells)
    return rows

# ----------------------------------------------------------------------------- T3 (raw recompute)
def cw_eval_jobs(success_only=False):
    jobs = []
    for f in sorted(glob.glob(os.path.join(REPO, 'inputs/cw/cw_r_eval_[AB]*_s[123]_sync[01]_s[1-5].csv'))):
        if 'sampled' in f: continue
        parts = os.path.basename(f)[:-4].split('_')
        arm, size, ts, sync, es = parts[3], parts[4], parts[5][1:], parts[6][4:], parts[7][1:]
        allrows = read_csv(f); hdr = list(allrows[0].keys()); man = json.load(open(f + '.decoys.json'))
        topo = os.path.join(REPO, 'inputs/cw/topology_%s.yaml' % size.replace('host', 'h'))
        for ep in sorted({r['episode'] for r in allrows}):
            rows = [dict(r) for r in allrows if r['episode'] == ep]
            if success_only:
                for r in rows:
                    if str(r.get('red_action_success')).strip().lower() != 'true': r['red_action_name'] = 'nothing'
            m2 = dict(man); m2['episodes'] = {ep: man['episodes'][ep]}
            jobs.append((f'{arm}|{size}|{ts}|{sync}|{es}|{ep}', topo, rows, hdr, m2))
    return jobs

T3COLS = {'Node Ctrl.': 'node_control_rate', 'Detect': 'node_detect_rate', 'Damage': 'd_score'}
summary['t3'] = {'source': 'raw recompute: shipped pipeline over inputs/cw/cw_r_eval_* (per-episode split + per-episode decoy manifest); mean +- sample std over 45 episodes per cell', 'cells': {}}
summary['_raw3'] = {}
summary['_spearman'] = {}
if USE_PIPELINE:
    raw = pipeline_last_rows(cw_eval_jobs(), 'cw_eval_all')
    assert len(raw) == 810, len(raw)
    summary['_meta']['t3_episodes'] = len(raw)
    cells = collections.defaultdict(list)
    for k, last in raw.items():
        arm, size, ts, sync, es, ep = k.split('|')
        summary['_raw3'][k] = {c: float(last[c]) for c in ('node_control_rate', 'node_detect_rate', 'd_score', 'comprehensive_concealment_score', 'behavior_concealment', 'network_concealment', 'dc_score', 'di_score', 'da_score')}
        cells[(arm, size, int(sync))].append(summary['_raw3'][k])
    for (arm, size, sync), v in sorted(cells.items(), key=lambda kv: (kv[0][0], int(kv[0][1][:-4]), kv[0][2])):
        assert len(v) == 45, (arm, size, sync, len(v))
        summary['t3']['cells'][f'{arm}|{size}|{sync}'] = {col: {'mean': mean(x[c] for x in v), 'sd': sd([x[c] for x in v])} for col, c in T3COLS.items()}
        summary['t3']['cells'][f'{arm}|{size}|{sync}']['_raw'] = v
    # --- Spearman rank sensitivity (success-only recomputation), all 810 episodes, 54 configurations
    raw_ok = pipeline_last_rows(cw_eval_jobs(success_only=True), 'cw_eval_success_only')
    assert len(raw_ok) == 810, len(raw_ok)
    IND = ['node_control_rate', 'subnet_control_rate', 'control_value', 'node_alive_detection_rate', 'node_info_detection_rate', 'node_vulnerability_detection_rate', 'node_detect_rate',
           'node_failure_rate', 'subnet_failure_rate', 'horizontal_control_range', 'vertical_control_range', 'control_scope', 'total_control_time', 'lateral_movement_ratio',
           'behavior_concealment', 'network_concealment', 'comprehensive_concealment_score', 'dc_score', 'di_score', 'da_score', 'd_score']
    def val(last, ind):
        if ind == 'control_value':
            tot = float(last['control_value_total']); return float(last['control_value_controlled']) / tot if tot else 0.0
        return float(last[ind])
    groups = collections.defaultdict(list)
    for k in raw:
        groups['|'.join(k.split('|')[:4])].append(k)
    assert len(groups) == 54
    rho = {}
    for ind in IND:
        x = [mean(val(raw[k], ind) for k in g) for g in groups.values()]
        y = [mean(val(raw_ok[k], ind) for k in g) for g in groups.values()]
        rho[ind] = spearman(x, y)
    defined = {k: v for k, v in rho.items() if v is not None}
    xchk = {}
    for l in open(V9, encoding='utf-8').read().split('\n'):
        c = [x.strip() for x in l.strip().strip('|').split('|')]
        mm = re.match(r'^CW-R(\d+)host-(A|B1|B2)$', c[0]) if c else None
        if mm and len(c) > 10 and c[1] == '45':
            key = '%s|%shost|1' % (mm.group(2), mm.group(1))
            gen = summary['t3']['cells'][key]
            xchk[key] = {'md_d': float(c[4].split()[0]), 'md_ctrl': float(c[8].split()[0]), 'md_det': float(c[9].split()[0]),
                         'gen_d': gen['Damage']['mean'], 'gen_ctrl': gen['Node Ctrl.']['mean'], 'gen_det': gen['Detect']['mean'],
                         'md_sd_d': float(c[4].split()[-1]), 'gen_sd_d': gen['Damage']['sd']}
            xchk[key]['max_abs_diff'] = max(abs(xchk[key]['md_d'] - xchk[key]['gen_d']), abs(xchk[key]['md_ctrl'] - xchk[key]['gen_ctrl']), abs(xchk[key]['md_det'] - xchk[key]['gen_det']))
    summary['t3']['md_crosscheck'] = {'source': 'v9 report section 3.1 rows CW-R<scale>host-<arm> (sync-on cells, 45 episodes); means must agree with the recompute to 1e-4', 'cells': xchk, 'n': len(xchk), 'max_abs_diff': max(v['max_abs_diff'] for v in xchk.values())}
    summary['_spearman'] = {'source': 'shipped pipeline, all 810 RL eval episodes (15 per configuration x 54 arm-scale-trainseed-sync configurations), all-action vs success-only (failed red actions blanked)', 'configs': 54,
                            'undefined': sorted(k for k, v in rho.items() if v is None), 'n_defined': len(defined), 'median': mean(sorted(defined.values())[len(defined) // 2 - 1:len(defined) // 2 + 1]) if len(defined) % 2 == 0 else st.median(defined.values()),
                            'rho': {k: v for k, v in rho.items()}}
    # --- which structural patterns of Table 3 survive the counting convention (the paper may only claim those that do)
    def _cm(d, a, sz, sy, c):
        v = [float(d[k][c]) for k in d if k.split('|')[0] == a and k.split('|')[1] == sz and k.split('|')[3] == str(sy)]
        assert len(v) == 45, (a, sz, sy, len(v)); return mean(v)
    _C3 = ('d_score', 'node_control_rate', 'node_detect_rate'); _A3 = ('A', 'B1', 'B2'); _S3 = ('10host', '25host', '50host')
    summary['_patterns'] = {'source': 'cell means over 45 episodes under both counting conventions (all_action = Table 3; success_only = failed red actions blanked)'}
    for _n, _d in (('all_action', raw), ('success_only', raw_ok)):
        summary['_patterns'][_n] = {
            'peak25': {c: all(_cm(_d, a, '25host', sy, c) > max(_cm(_d, a, '10host', sy, c), _cm(_d, a, '50host', sy, c)) for a in _A3 for sy in (0, 1)) for c in _C3},
            'b2_gt_b1': {c: all(_cm(_d, 'B2', sz, sy, c) > _cm(_d, 'B1', sz, sy, c) for sz in _S3 for sy in (0, 1)) for c in _C3},
            'b1_lt_a_lt_b2_50h': {c: all(_cm(_d, 'B1', '50host', sy, c) < _cm(_d, 'A', '50host', sy, c) < _cm(_d, 'B2', '50host', sy, c) for sy in (0, 1)) for c in _C3},
            'a_gt_b2_10h': {c: all(_cm(_d, 'A', '10host', sy, c) > _cm(_d, 'B2', '10host', sy, c) for sy in (0, 1)) for c in _C3},
            'b2_on_gt_off': {c: all(_cm(_d, 'B2', sz, 1, c) > _cm(_d, 'B2', sz, 0, c) for sz in _S3) for c in _C3}}

# ----------------------------------------------------------------------------- T5 (CAGE4)
UNITS = [('GNN-PPO', 'C4-GNN/ep_cage4_gnn_ppo_eval', 'gnn_ppo_eval'), ('GNN-PPO-det', 'C4-GNN-Det/ep_cage4_gnn_ppo_det_eval', 'gnn_ppo_det_eval'),
         ('H-MARL', 'C4-HMARL/ep_cage4_hmarl_eval', 'hmarl_eval'), ('H-MARL-det', 'C4-HMARL-Det/ep_cage4_hmarl_det_eval', 'hmarl_det_eval'),
         ('RL baseline (B-line)', 'C4-DF/ep_cage4_b_line_rl_train', 'b_line_rl_train'), ('RL baseline (Meander)', 'C4-FS/ep_cage4_meander_rl_train', 'meander_rl_train'),
         ('RL baseline (R.-Select)', 'C4-RS/ep_cage4_sleep_rl_train', 'sleep_rl_train')]
T5TOP = [('Steps', None), ('Node Ctrl.', 'node_control_rate'), ('Subnet Ctrl.', 'subnet_control_rate'), ('Failure', 'node_failure_rate'), ('Damage', 'd_score'), ('Lat.-Mov.', 'lateral_movement_ratio')]
T5BOT = [('Confidentiality', 'dc_score'), ('Integrity', 'di_score'), ('Availability', 'da_score'), ('Damage D', 'd_score'), ('Conceal.', 'comprehensive_concealment_score')]
summary['t5'] = {'source': 'results/cage4_pipeline_fixed/*/ep_*/metrics_table.csv last row (3 episodes per configuration, mean +- sample std); Steps = mean count of red_action != sleep in inputs/cage4/ep_*.csv (rounded)', 'units': {}}
summary['_c4eps'] = {}
for name, pat, inp in UNITS:
    eps = []; steps = []; d80 = []; firstc = []
    files = sorted(glob.glob(os.path.join(REPO, 'results/cage4_pipeline_fixed', pat + '_ep00*/metrics_table.csv')))
    assert len(files) == 3, (name, len(files))
    for mf in files:
        rows = read_csv(mf); last = rows[-1]
        eps.append({k: float(last[k]) for k in ('node_control_rate', 'subnet_control_rate', 'node_failure_rate', 'd_score', 'lateral_movement_ratio', 'dc_score', 'di_score', 'da_score', 'comprehensive_concealment_score', 'behavior_concealment', 'network_concealment')})
        le80 = [r for r in rows if int(float(r['step'])) <= 80]
        d80.append(float(le80[-1]['d_score']) if le80 else 0.0)
        fc = next((int(float(r['step'])) for r in rows if float(r['control_value_controlled']) > 0), None)
        firstc.append(fc)
        epfile = os.path.join(REPO, 'inputs/cage4', os.path.basename(os.path.dirname(mf)) + '.csv')
        acts = [r['red_action'] for r in read_csv(epfile)]
        steps.append(sum(1 for a in acts if a != 'sleep'))
    summary['_c4eps'][name] = {'eps': eps, 'steps': steps, 'd80': d80, 'first_compromise': firstc}
    u = {'steps_mean': mean(steps), 'steps': round(mean(steps))}
    for col, c in T5TOP[1:]: u[c] = {'mean': mean(e[c] for e in eps), 'sd': sd([e[c] for e in eps])}
    for col, c in T5BOT: u[c] = {'mean': mean(e[c] for e in eps), 'sd': sd([e[c] for e in eps])}
    summary['t5']['units'][name] = u

# ----------------------------------------------------------------------------- T4 (v9 report, md source)
summary['t4'] = {'source': 'md report source: report/phase5_report_cn_v9.md section 3.1 table (rows CW-AT/CWX-AT/CW-RT/CWX-RT); underlying per-episode metrics of the training corpora are not shipped in full', 'units': {}}
lines = open(V9, encoding='utf-8').read().split('\n')
for l in lines:
    m = re.match(r'^\s*\|\s*(CW[XY]?-[AR]T\d+host)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*(\d+)\s*\|\s*([\d.]+)(?: ± ([\d.]+))?\s*\|\s*([\d.]+)(?: ± ([\d.]+))?\s*\|\s*([\d.]+)(?: ± ([\d.]+))?\s*\|', l)
    if m and l.find('±') > 0:
        g = m.groups()
        # columns after n_rows: subnet-fail, DC, D, DI | control, detect, conceal  (order verified against CW-AT10host row)
        summary['t4']['units'][g[0]] = {'episodes': int(g[1]), 'steps': float(g[2]), 'n_rows': int(g[3])}
        rest = [c.strip() for c in l.strip().strip('|').split('|')][4:]
        nums = []
        for c in rest:
            mm = re.match(r'^([\d.]+)(?: ± ([\d.]+))?', c)
            if mm: nums.append((float(mm.group(1)), float(mm.group(2)) if mm.group(2) else None))
        summary['t4']['units'][g[0]]['_nums'] = nums

# second (3-decimal) rendering of the same table in the md: rows whose second cell is the environment tag
for l in lines:
    c = [x.strip() for x in l.strip().strip('|').split('|')]
    if len(c) > 10 and c[0] in summary['t4']['units'] and c[1] == 'CW':
        summary['t4']['units'][c[0]]['_md3'] = {'ctrl': c[5], 'det': c[6], 'D': c[7]}
assert all('_md3' in u for u in summary['t4']['units'].values())

# ----------------------------------------------------------------------------- narrative from derived CSVs / raw inputs
N = {}
N['sources'] = {}
# strike rates (decoy/(decoy+real) of successful core actions, sync-on unit means)
cal = read_csv(os.path.join(DD, 'eval_caliber_by_cell.csv'))
b1 = {r['size']: float(r['core_decoy']) / (float(r['core_decoy']) + float(r['core_real'])) for r in cal if r['arm'] == 'B1' and r['family'] == 'RL'}
b2 = {r['size']: float(r['core_decoy']) / (float(r['core_decoy']) + float(r['core_real'])) for r in cal if r['arm'] == 'B2' and r['family'] == 'RL'}
N['strike_b1'] = {k: v * 100 for k, v in b1.items()}; N['strike_b2'] = {k: v * 100 for k, v in b2.items()}
N['cut_pct'] = {k: (1 - b2[k] / b1[k]) * 100 for k in b1}
N['deploy_per_ep_sync_on'] = [float(r['deploy_per_ep']) for r in cal if r['arm'] in ('B1', 'B2') and r['family'] == 'RL']
N['deploy_A'] = [float(r['deploy_per_ep']) for r in cal if r['arm'] == 'A']
N['sources']['strike'] = 'results/cw_deep_dive/eval_caliber_by_cell.csv'
# redirection significance
pr = read_csv(os.path.join(DD, 'paired_redirection.csv'))
N['redirect_p_real'] = {r['size']: float(r['p_real']) for r in pr if r['pair'] == 'B2 vs B1' and r['sync'] == '1'}
N['redirect_d_real'] = {r['size']: float(r['d_real']) for r in pr if r['pair'] == 'B2 vs B1' and r['sync'] == '1'}
N['sources']['redirect'] = 'results/cw_deep_dive/paired_redirection.csv (B2 vs B1, sync-on, n=45 paired)'
# cross-arm (per-episode recompute)
ca = read_csv(os.path.join(REPO, 'supplement_experiments_backup/cross_arm/per_episode.csv'))
Dm = collections.defaultdict(list); S = collections.defaultdict(list); dep = collections.defaultdict(list)
for r in ca:
    Dm[(r['red_arm'], r['blue_arm'])].append(float(r['d_score'])); S[(r['red_arm'], r['blue_arm'])].append(float(r['strike_rate_any'])); dep[(r['red_arm'], r['blue_arm'])].append(float(r['decoys_deployed']))
assert len(ca) == 45 and all(len(v) == 5 for v in Dm.values())
Dmean = {k: mean(v) for k, v in Dm.items()}
ARMS = ['A', 'B1', 'B2']
N['crossarm'] = {'col_range_red': max(max(Dmean[(r_, b)] for r_ in ARMS) - min(Dmean[(r_, b)] for r_ in ARMS) for b in ARMS),
                 'row_range_blue': max(max(Dmean[(r_, b)] for b in ARMS) - min(Dmean[(r_, b)] for b in ARMS) for r_ in ARMS),
                 'offdiag': mean([Dmean[(r_, b)] for r_ in ARMS for b in ARMS if r_ != b]), 'diag': mean([Dmean[(r_, r_)] for r_ in ARMS]),
                 'strike_max': {r_: max(mean(x) for (rr, b), x in S.items() if rr == r_) for r_ in ARMS},
                 'armA_deploys_all': all(x == 0 for (r_, b), v in dep.items() if b == 'A' for x in v), 'n': len(ca)}
N['sources']['crossarm'] = 'supplement_experiments_backup/cross_arm/per_episode.csv (45 episodes)'
# v9 md anchors
v9 = open(V9, encoding='utf-8').read()
def grab(pat, conv=float, group=1):
    m = re.search(pat, v9); assert m, pat
    return conv(m.group(group))
def v9row(unit):
    row = next(l for l in v9.split('\n') if l.startswith('| ' + unit + ' |') and re.search(r'−[\d.]+（−[\d.]+%）', l))
    c = [x.strip().replace('**', '') for x in row.strip().strip('|').split('|')]
    cn = re.search(r'(\d+)/(\d+)', c[4])
    return {'pct': float(re.search(r'−([\d.]+)%', c[3]).group(1)), 'consistent': int(cn.group(1)), 'n': int(cn.group(2)), 'p_holm': float(c[6])}
N['paired'] = {'HMARL': v9row('C4-HMARL')['pct'], 'GNN': v9row('C4-GNN')['pct'], 'HMARL-Det': v9row('C4-HMARL-Det'), 'GNN-Det': v9row('C4-GNN-Det'),
               'decoy_det_per_ep': re.search(r'GNN-Det 实际落地诱饵仅 ([\d.]+) 主机/集 vs 采样版 ([\d.]+)', v9).groups(), 'absorb_lo': grab(r'ON 时 \*\*([\d.]+)%–([\d.]+)% 的攻击步打在诱饵上'), 'absorb_hi': grab(r'ON 时 \*\*[\d.]+%–([\d.]+)% 的攻击步打在诱饵上'),
               'design': 'v9 section 6.7: 4 variants x 2 conditions x 45 paired rollouts (seeds 43..87), sign-flip permutation 20,000 resamples, two-sided, Holm m=4'}
N['same_red'] = {'contractor': [grab(r'\| ent \| \*\*rl_bline\*\*（基线） \| \*\*([\d.]+)\*\*'), grab(r'\| ent \| rl_meander \| \*\*([\d.]+)\*\*'), grab(r'\| ent \| rl_sleep \| \*\*([\d.]+)\*\*')],
                 'learned': [grab(r'\| ent \| hmarl \| ([\d.]+)'), grab(r'\| ent \| gnn_ppo \| ([\d.]+)'), grab(r'\| ent \| hmarl_det \| ([\d.]+)'), grab(r'\| ent \| gnn_ppo_det \| ([\d.]+)')], 'rollouts': grab(r'共 \*\*(\d+) rollout\*\*', conv=int)}
N['stepsens'] = {'cells': 72, 'n_pos': grab(r'(\d+)/36 逐格全为正', conv=int)}
N['stepsens']['arms1000'] = [float(x) for x in re.search(r'\| \*\*A > B1 > B2\*\*（([\d.]+) / ([\d.]+) / ([\d.]+)） \|', v9).groups()]
N['art_eval'] = {'10': grab(r'\| CW-A10host \| 15 \| 100\.0 \| 1500 \| ([\d.]+) ±'), '25': grab(r'\| CW-A25host \| 15 \| 100\.0 \| 1500 \| ([\d.]+) ±'), '25_sd': grab(r'\| CW-A25host \| 15 \| 100\.0 \| 1500 \| [\d.]+ ± ([\d.]+)'), '50': grab(r'\| CW-A50host \| 15 \| 100\.0 \| 1500 \| ([\d.]+) ±'), 'ctrl25': grab(r'\| CW-A25host \| 15 \| 100\.0 \| 1500 \| [\d.]+ ± [\d.]+ \| [\d.]+ ± [\d.]+ \| [\d.]+ ± [\d.]+ \| [\d.]+ ± [\d.]+ \| ([\d.]+) ±')}
cq = {r['corpus']: r for r in read_csv(os.path.join(DD, 'corpus_quality.csv'))}
N['art_loops_pct'] = float(cq['art_train(1x)']['pct_in_runs_ge100']); N['sources']['art_loops'] = 'results/cw_deep_dive/corpus_quality.csv'
# official scores
def blue_reward_sums(inp):
    out = []
    for f in sorted(glob.glob(os.path.join(REPO, f'inputs/cage4/ep_cage4_{inp}_ep00*.csv'))):
        out.append(sum(float(r['blue_reward']) for r in read_csv(f)))
    return out
N['official'] = {n: mean(blue_reward_sums(i)) for n, _, i in UNITS[:4]}
# decoy hosts per episode (manifests) for CAGE4 learned units
def decoy_counts(inp):
    out = []
    for f in sorted(glob.glob(os.path.join(REPO, f'inputs/cage4/ep_cage4_{inp}_ep00*.csv.decoys.json'))):
        d = json.load(open(f)); out.append(sum(len(e.get('decoys') or []) for e in d['episodes'].values()))
    return out
N['decoys_per_ep'] = {n: decoy_counts(i) for n, _, i in UNITS}
# success-flag rate: red actions excluding sleep/nothing and subnet scans, share flagged TRUE, pooled per corpus
SCANS = {'pingsweep', 'portscan', 'discover_remote_systems', 'sleep', 'nothing', 'None', ''}
def flag_rate(files, act, suc):
    tot = ok = 0
    for f in files:
        for r in read_csv(f):
            if (r.get(act) or '') in SCANS: continue
            tot += 1; ok += str(r.get(suc)).strip().lower() == 'true'
    return ok / tot * 100 if tot else None
N['flag'] = {'cw_art_eval': flag_rate(sorted(glob.glob(os.path.join(REPO, 'inputs/cw/cw_art_eval_*_sync1_s*.csv'))), 'red_action_name', 'red_action_success'),
             'cw_rl_eval': flag_rate(sorted(glob.glob(os.path.join(REPO, 'inputs/cw/cw_r_eval_[AB]*_s[123]_sync[01]_s[1-5].csv'))), 'red_action_name', 'red_action_success'),
             'cage4_learned': [flag_rate(sorted(glob.glob(os.path.join(REPO, f'inputs/cage4/ep_cage4_{i}_ep00*.csv'))), 'red_action', 'red_action_success') for _, _, i in UNITS[:4]],
             'cage4_contractor': [flag_rate(sorted(glob.glob(os.path.join(REPO, f'inputs/cage4/ep_cage4_{i}_ep00*.csv'))), 'red_action', 'red_action_success') for _, _, i in UNITS[4:]]}
N['sources']['flag'] = 'raw inputs: share of red actions (excluding sleep/nothing and subnet scans) whose success flag is TRUE, pooled over the corpus'
# same flag rate restricted to the md definition of core attacks (exploit / lateral-movement / privilege-escalation / impact); record only, not cited
CORE = {'exploit_remote_system', 'lateral-movement', 'privilege_escalate', 'impact', 'exploit_remote_service', 'privilege_escalate'}
def core_rate(files, act, suc):
    tot = ok = 0
    for f in files:
        for r in read_csv(f):
            if (r.get(act) or '') not in CORE: continue
            tot += 1; ok += str(r.get(suc)).strip().lower() == 'true'
    return ok / tot * 100 if tot else None
N['flag_core'] = {'cw_rl_eval': core_rate(sorted(glob.glob(os.path.join(REPO, 'inputs/cw/cw_r_eval_[AB]*_s[123]_sync[01]_s[1-5].csv'))), 'red_action_name', 'red_action_success'),
                  'cage4_learned': [core_rate(sorted(glob.glob(os.path.join(REPO, f'inputs/cage4/ep_cage4_{i}_ep00*.csv'))), 'red_action', 'red_action_success') for _, _, i in UNITS[:4]]}
N['sources']['flag_core'] = 'raw inputs: the same success-flag rate restricted to the md core attacks (exploit / lateral-movement / privilege-escalation / impact); recorded to show that the paper does NOT use this denominator'
# arm-A sync-off evaluation: episodes and decoy records counted from the per-episode manifests (sanity: the same count on sync-on B1/B2 manifests must be > 0)
def manifest_decoys(pattern):
    files = sorted(glob.glob(os.path.join(REPO, pattern))); eps = rec = 0
    for f in files:
        d = json.load(open(f)); eps += len(d['episodes'])
        rec += sum(len(e.get('decoys') or []) for e in d['episodes'].values())
    return {'files': len(files), 'episodes': eps, 'decoy_records': rec}
N['sync_off_A'] = manifest_decoys('inputs/cw/cw_r_eval_A_*_sync0_*.csv.decoys.json')
_chk_on = manifest_decoys('inputs/cw/cw_r_eval_B[12]_*_sync1_*.csv.decoys.json')
assert N['sync_off_A']['decoy_records'] == 0 and _chk_on['decoy_records'] > 0 and N['sync_off_A']['episodes'] == 3 * 45, (N['sync_off_A'], _chk_on)
N['sources']['sync_off_A'] = 'inputs/cw/cw_r_eval_A_*_sync0_*.csv.decoys.json (per-episode decoy manifests; three scales x 45 episodes)'
if USE_PIPELINE: N['patterns'] = summary['_patterns']
# Table 2 counts
def count_eps(pattern):
    n = 0
    for f in glob.glob(os.path.join(REPO, pattern)):
        if f.endswith('.decoys.json') or f.endswith('.topology.yaml'): continue
        n += len({r['episode'] for r in read_csv(f)}) if 'episode' in read_csv(f)[0] else 1
    return n
N['t2'] = {'cw_eval_rl': len(cw_eval_jobs()) if USE_PIPELINE else None, 'cw_eval_art': sum(len({r['episode'] for r in read_csv(f)}) for f in glob.glob(os.path.join(REPO, 'inputs/cw/cw_art_eval_*_sync1_s*.csv'))),
           'cw_sampled': sum(len({r['episode'] for r in read_csv(f)}) for f in glob.glob(os.path.join(REPO, 'inputs/cw/cw_r_eval_A_sampled_*_s*.csv'))), 'cw_variants': len(glob.glob(os.path.join(REPO, 'inputs/cw/cw_r_train_B1var*_ep*.csv'))),
           'cage4': len(glob.glob(os.path.join(REPO, 'inputs/cage4/ep_*.csv'))), 'cw_eval_rl_files': len(glob.glob(os.path.join(REPO, 'inputs/cw/cw_r_eval_[AB][12]_*_sync[01]_s[1-5].csv'))) + len(glob.glob(os.path.join(REPO, 'inputs/cw/cw_r_eval_A_*_sync[01]_s[1-5].csv')))}
# topology facts
cnt = [int(re.search(r'^\s*node_count:\s*(\d+)', open(f, encoding='utf-8').read(), re.M).group(1)) for f in sorted(glob.glob(os.path.join(REPO, 'inputs/cage4/*.topology.yaml')))]
sub = {int(re.search(r'^\s*subnet_count:\s*(\d+)', open(f, encoding='utf-8').read(), re.M).group(1)) for f in glob.glob(os.path.join(REPO, 'inputs/cage4/*.topology.yaml'))}
N['cage4_hosts'] = (min(cnt), max(cnt)); N['cage4_subnets'] = sorted(sub); N['cage4_topologies'] = len(cnt)
def cw_subnets(path):
    txt = open(path, encoding='utf-8').read()
    m = re.search(r'^subnets:\n(.*?)(?=^[A-Za-z_]+:|\Z)', txt, re.M | re.S)
    return len(re.findall(r'^  [A-Za-z0-9_]+:', m.group(1), re.M)) if m else -1
N['cw_subnets'] = {k: cw_subnets(os.path.join(REPO, 'inputs/cw/topology_%s.yaml' % k)) for k in ('10h', '25h', '50h')}
N['sources']['topology'] = 'inputs/cage4/*.topology.yaml meta.node_count/subnet_count; inputs/cw/topology_*.yaml subnets section'
N['sources']['t2'] = 'inputs/cw and inputs/cage4 file/episode counts; training-corpus episode counts (300 per scale B1, 50 per scale ART, 10/5 long-horizon) from v9 section 3.1 (md source; only ep001 of each training run is shipped)'
# training curves (Fig. 2 claims)
tc = read_csv(os.path.join(DD, 'train_curves.csv'))
curve = collections.defaultdict(lambda: collections.defaultdict(list))
for r in tc: curve[(r['arm'], r['size'])][int(r['episode'])].append((float(r['deploys']), float(r['hits'])))
def first_permanent_zero(series):
    eps = sorted(series); last_nz = max((e for e in eps if series[e] > 0), default=0)
    return last_nz + 1
def _dep(arm, size, e): return mean(x[0] for x in curve[(arm, size)][e])
def _hits(arm, size, e): return mean(x[1] for x in curve[(arm, size)][e])
N['fig2'] = {'A_deploy_zero_from': {s: first_permanent_zero({e: _dep('A', s, e) for e in curve[('A', s)]}) for s in ('10host', '25host', '50host')},
             'A_hits_max': max(_hits('A', s, e) for s in ('10host', '25host', '50host') for e in curve[('A', s)]),
             'B2_hits_lt_B1': all(_hits('B2', s, e) <= _hits('B1', s, e) + 1e-9 for s in ('10host', '25host', '50host') for e in curve[('B1', s)] if e in curve[('B2', s)]),
             'columns': list(tc[0].keys()), 'rows': len(tc)}
N['fig2']['A_first_zero'] = {s: min(e for e in curve[('A', s)] if _dep('A', s, e) == 0) for s in ('10host', '25host', '50host')}
N['fig2']['A_deploys_ep14_21_max'] = {s: max(_dep('A', s, e) for e in range(14, 22) if e in curve[('A', s)]) for s in ('10host', '25host', '50host')}
N['sources']['fig2'] = 'results/cw_deep_dive/train_curves.csv (3-seed means, 100 episodes per scale)'
# byte identity of ART 10k prefix
try:
    asi = read_csv(os.path.join(DD, 'art_sync_identity.csv')); N['art_sync_identity'] = asi
except Exception: pass

# D-simplex (grid step 0.05 -> 231 points)
def D(c, w): return c[0] * w[0] + c[1] * w[1] + c[2] * w[2]
GRID = [(a / 20, b / 20, round(1 - a / 20 - b / 20, 10)) for a in range(21) for b in range(21 - a)]
assert len(GRID) == 231
c4m = {n: tuple(mean(e[k] for e in summary['_c4eps'][n]['eps']) for k in ('dc_score', 'di_score', 'da_score')) for n, _, _ in UNITS}
learned = [n for n, _, _ in UNITS[:4]]; contractor = [n for n, _, _ in UNITS[4:]]
gaps = [min(D(c4m[u], w) for u in learned) - max(D(c4m[u], w) for u in contractor) for w in GRID]
ref7 = [D(c4m[u], (0.35, 0.35, 0.30)) for u in learned + contractor]
taus = [kendall(ref7, [D(c4m[u], w) for u in learned + contractor]) for w in GRID]
N['simplex_cage4'] = {'min_gap': min(gaps), 'min_tau': min(taus), 'points': len(GRID)}
if USE_PIPELINE:
    cwm = {k: tuple(mean(x[c] for x in v['_raw']) for c in ('dc_score', 'di_score', 'da_score')) for k, v in summary['t3']['cells'].items()}
    def armsize(k, a, s, sy): return cwm[f'{a}|{s}|{sy}']
    def b2b1(w): return all(D(armsize(None, 'B2', s, sy), w) > D(armsize(None, 'B1', s, sy), w) for s in ('10host', '25host', '50host') for sy in (0, 1))
    def peak(w): return all(D(armsize(None, a, '25host', sy), w) > max(D(armsize(None, a, '10host', sy), w), D(armsize(None, a, '50host', sy), w)) for a in ('A', 'B1', 'B2') for sy in (0, 1))
    inbox = [w for w in GRID if all(0.15 - 1e-9 <= x <= 0.55 + 1e-9 for x in w)]
    viol = [w for w in GRID if not (b2b1(w) and peak(w))]
    nb = [w for w in GRID if all(abs(w[i] - (0.35, 0.35, 0.30)[i]) <= 0.1 + 1e-9 for i in range(3))]
    N['simplex_cw'] = {'box_points': len(inbox), 'box_violations': sum(1 for w in inbox if not (b2b1(w) and peak(w))), 'violations': len(viol), 'min_wA_violation': min(w[2] for w in viol),
                       'pm01_points': len(nb), 'pm01_b2b1_peak_hold': all(b2b1(w) and peak(w) for w in nb),
                       'violators_all_wA_ge_06': all(w[2] >= 0.6 - 1e-9 for w in viol), 'violators_wA_ge_06_with_other_ge_06': sum(1 for w in viol if w[2] >= 0.6 - 1e-9 and max(w[0], w[1]) >= 0.6 - 1e-9),
                       'violators_only_C_or_I_ge_06': sum(1 for w in viol if w[2] < 0.6 - 1e-9)}
    # H composite (concealment) over the 18 evaluation cells: both components strictly below 1 for every non-arm-A cell
    N['h_strict'] = all(max(mean(x['behavior_concealment'] for x in v['_raw']), mean(x['network_concealment'] for x in v['_raw'])) < 1.0 for k, v in summary['t3']['cells'].items() if not k.startswith('A|'))
    N['h_cells'] = {k: {'conceal': mean(x['comprehensive_concealment_score'] for x in v['_raw']), 'Hb': mean(x['behavior_concealment'] for x in v['_raw']), 'Hn': mean(x['network_concealment'] for x in v['_raw'])} for k, v in summary['t3']['cells'].items()}
summary['narrative'] = N

# ----------------------------------------------------------------------------- write
os.makedirs(HERE, exist_ok=True)
json.dump(summary, open(os.path.join(HERE, 'results_summary.json'), 'w'), indent=1, default=str)

# ----------------------------------------------------------------------------- human table
L = []
L.append('# RESULTS-SUMMARY (artifact truth, generated by generate_results_summary.py -- do not edit by hand)')
L.append('Generated: %s  | repo: %s  | pipeline recompute: %s' % (summary['_meta']['generated'], REPO, USE_PIPELINE))
L.append('')
L.append('## Table 3 -- Cyberwheel RL evaluation (mean +- sample std over 45 episodes per cell)')
L.append('Source: ' + summary['t3']['source'])
L.append('')
L.append('| Arm | Scale | Sync | Node Ctrl. | Detect | Damage |')
L.append('|---|---|---|---|---|---|')
for k, v in summary['t3']['cells'].items():
    arm, size, sync = k.split('|')
    L.append('| %s | %s | %s | %s | %s | %s |' % (arm, size.replace('host', ''), 'on' if sync == '1' else 'off', ' ± '.join([f3(v['Node Ctrl.']['mean']), f3(v['Node Ctrl.']['sd'])]), ' ± '.join([f3(v['Detect']['mean']), f3(v['Detect']['sd'])]), ' ± '.join([f3(v['Damage']['mean']), f3(v['Damage']['sd'])])))
L.append('')
L.append('## Table 5 -- CAGE4 final-step indicators (mean +- sample std over three episodes)')
L.append('Source: ' + summary['t5']['source'])
L.append('')
L.append('| Defender | Steps | Node Ctrl. | Subnet Ctrl. | Failure | Damage | Lat.-Mov. | DC | DI | DA | Conceal. |')
L.append('|---|---|---|---|---|---|---|---|---|---|---|')
for name, _, _ in UNITS:
    u = summary['t5']['units'][name]
    L.append('| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (name, u['steps'], ' ± '.join([f3(u['node_control_rate']['mean']), f3(u['node_control_rate']['sd'])]), ' ± '.join([f3(u['subnet_control_rate']['mean']), f3(u['subnet_control_rate']['sd'])]),
             ' ± '.join([f3(u['node_failure_rate']['mean']), f3(u['node_failure_rate']['sd'])]), ' ± '.join([f3(u['d_score']['mean']), f3(u['d_score']['sd'])]), '%.1f ± %.1f' % (u['lateral_movement_ratio']['mean'], u['lateral_movement_ratio']['sd']),
             ' ± '.join([f3(u['dc_score']['mean']), f3(u['dc_score']['sd'])]), ' ± '.join([f3(u['di_score']['mean']), f3(u['di_score']['sd'])]), ' ± '.join([f3(u['da_score']['mean']), f3(u['da_score']['sd'])]), ' ± '.join([f3(u['comprehensive_concealment_score']['mean']), f3(u['comprehensive_concealment_score']['sd'])])))
L.append('')
L.append('## Table 4 -- Cyberwheel training / long-horizon units (md report source)')
L.append('Source: ' + summary['t4']['source'])
for u, d in summary['t4']['units'].items():
    L.append('- %s: episodes %d, steps %s, nums %s' % (u, d['episodes'], d['steps'], d['_nums']))
L.append('')
L.append('## Narrative numbers')
for k, v in N.items():
    if k == 'sources': continue
    L.append('- %s: %s' % (k, json.dumps(v, default=str)))
if summary['_spearman']:
    L.append('- spearman (undefined: %s): %s' % (summary['_spearman']['undefined'], json.dumps({k: (round(v, 3) if v is not None else None) for k, v in summary['_spearman']['rho'].items()})))
    L.append('- spearman median: %.3f over %d indicators' % (summary['_spearman']['median'], summary['_spearman']['n_defined']))
if summary.get('_patterns'): L.append('- table-3 structural patterns under both counting conventions: %s' % json.dumps(summary['_patterns']))
L.append('')
L.append('## Sources')
for k, v in N['sources'].items(): L.append('- %s: %s' % (k, v))
out_md = os.environ.get('CSE_SUMMARY_MD', os.path.join(PAPER_DIR, 'RESULTS-SUMMARY.md'))
open(out_md, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('wrote', out_md, '| T3 cells', len(summary['t3']['cells']), '| T5 units', len(summary['t5']['units']), '| T4 units', len(summary['t4']['units']), '| spearman', bool(summary['_spearman']))
