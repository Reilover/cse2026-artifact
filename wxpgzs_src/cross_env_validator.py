#!/usr/bin/env python3
"""Phase 5.6: Cross-environment validation and analysis.

Reads all 30 experimental units' metrics_table.csv from wxpgzs/result/
and generates:
  1. cross_env_matrix.json       — 30 unit × 21 metric comparison matrix
  2. scale_ablation.json         — NASim + CW scale ablation analysis
  3. agent_comparison.json       — Cross-env agent strategy comparison
  4. cyborg_series_consistency.json — CAGE1 vs CAGE2 consistency
  5. info_gain_heatmap.png       — Information gain heatmap (wxpgzs vs native reward)
"""

import os, csv, json, glob
from collections import defaultdict
# ── 布局自适应（v9.2）──────────────────────────────────────────────
# 同一份源码需在两种布局下工作，且**包内运行绝不可写出包外**：
#   ① 项目布局 <root>/wxpgzs/xxx.py               → PKG=<root>/phase5_package
#   ② 包内布局 <pkg>/{wxpgzs_src,scripts}/xxx.py  → PKG=<pkg>
SRC = os.path.dirname(os.path.abspath(__file__))


def _is_pkg_root(d):
    """交付包根的特征：同时含 inputs/、wxpgzs_src/、report/（工作区根不含 wxpgzs_src/）。"""
    return all(os.path.isdir(os.path.join(d, x)) for x in ('inputs', 'wxpgzs_src', 'report'))


def _find_root(start):
    """定位项目根；包内布局返回 None。

    先判包特征再向上找根——否则当交付包被解压到**另一个项目内部**时，
    向上查找会越过包边界命中外层项目根，导致"包内运行写到包外"。
    （2026-09-11 实测踩到：包副本置于工作区内，composer 直接回写了工作区报告。）
    """
    if _is_pkg_root(os.path.dirname(start)):
        return None
    d = start
    for _ in range(4):
        if (os.path.isdir(os.path.join(d, 'phase5_package'))
                and os.path.isdir(os.path.join(d, 'wxpgzs'))):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


_ROOT = _find_root(SRC)
if _ROOT:
    BASE = _ROOT
    PKG = os.path.join(BASE, 'phase5_package')
    RES_DEF = os.path.join(BASE, 'wxpgzs', 'result_v9')
    _DATA_DIRS = [os.path.join(BASE, 'data', 'phase4')]
else:
    PKG = os.path.dirname(SRC)
    BASE = os.path.dirname(PKG)
    RES_DEF = os.path.join(PKG, 'results', 'wxpgzs_pipeline_v9')
    _DATA_DIRS = []
_DATA_DIRS.append(os.path.join(PKG, 'results'))


def data_file(name):
    """定位分析数据（cw_honeypot_analysis.json / cage4_10x_test.json）。

    随包发布时在 <PKG>/results/，工作区在 <root>/data/phase4/。
    """
    for d in _DATA_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f'找不到 {name}，已查找：{_DATA_DIRS}')


RESULT_DIR = os.environ.get('RES_DIR', RES_DEF)

# ── Unit metadata ──────────────────────────────────────────────
UNIT_META = {
    'C1-M':  {'env': 'CAGE1', 'variant': 'Meander', 'category': 'agent'},
    'C1-R':  {'env': 'CAGE1', 'variant': 'Random', 'category': 'agent'},
    'C2-M':  {'env': 'CAGE2', 'variant': 'Meander', 'category': 'agent'},
    'C2-H':  {'env': 'CAGE2', 'variant': 'Heuristic', 'category': 'agent'},
    'C2-B':  {'env': 'CAGE2', 'variant': 'B_line', 'category': 'agent'},
    'C2-S':  {'env': 'CAGE2', 'variant': 'Sleep', 'category': 'agent'},
    'C4-FS': {'env': 'CAGE4', 'variant': 'FSRA+RL', 'category': 'agent'},
    'C4-DF': {'env': 'CAGE4', 'variant': 'DiscoveryFSRed+RL', 'category': 'agent'},
    'C4-RS': {'env': 'CAGE4', 'variant': 'RandomSelect+RL', 'category': 'agent'},
    'Y1-30': {'env': 'YT', 'variant': 'skill30', 'category': 'skill'},
    'Y1-50': {'env': 'YT', 'variant': 'skill50', 'category': 'skill'},
    'Y1-70': {'env': 'YT', 'variant': 'skill70', 'category': 'skill'},
    'N1-T':  {'env': 'NASim', 'variant': 'tiny', 'category': 'scale'},
    'N1-S':  {'env': 'NASim', 'variant': 'small', 'category': 'scale'},
    'N1-M':  {'env': 'NASim', 'variant': 'medium', 'category': 'scale'},
    'I1-0':  {'env': 'idsgame', 'variant': 'v0', 'category': 'difficulty'},
    'I1-3':  {'env': 'idsgame', 'variant': 'v3', 'category': 'difficulty'},
    'I1-6':  {'env': 'idsgame', 'variant': 'v6', 'category': 'difficulty'},
    'W1-A10': {'env': 'CW', 'variant': 'ART_eval_10', 'category': 'scale'},
    'W1-R10': {'env': 'CW', 'variant': 'RL_eval_10', 'category': 'scale'},
    'W1-A25': {'env': 'CW', 'variant': 'ART_eval_25', 'category': 'scale'},
    'W1-R25': {'env': 'CW', 'variant': 'RL_eval_25', 'category': 'scale'},
    'W1-A50': {'env': 'CW', 'variant': 'ART_eval_50', 'category': 'scale'},
    'W1-R50': {'env': 'CW', 'variant': 'RL_eval_50', 'category': 'scale'},
    'W1-AT10': {'env': 'CW', 'variant': 'ART_train_10', 'category': 'train_vs_eval'},
    'W1-RT10': {'env': 'CW', 'variant': 'RL_train_10', 'category': 'train_vs_eval'},
    'W1-AT25': {'env': 'CW', 'variant': 'ART_train_25', 'category': 'train_vs_eval'},
    'W1-RT25': {'env': 'CW', 'variant': 'RL_train_25', 'category': 'train_vs_eval'},
    'W1-AT50': {'env': 'CW', 'variant': 'ART_train_50', 'category': 'train_vs_eval'},
    'W1-RT50': {'env': 'CW', 'variant': 'RL_train_50', 'category': 'train_vs_eval'},
    # ── eval 代际单元（v7 扩展集）──
    'C2-M-Eval': {'env': 'CAGE2', 'variant': 'Meander_eval', 'category': 'train_vs_eval'},
    'IDS-PPO-v0': {'env': 'idsgame', 'variant': 'PPO_v0_eval', 'category': 'train_vs_eval'},
    'IDS-PPO-v3': {'env': 'idsgame', 'variant': 'PPO_v3_eval', 'category': 'train_vs_eval'},
    'IDS-PPO-v6': {'env': 'idsgame', 'variant': 'PPO_v6_eval', 'category': 'train_vs_eval'},
    'YT-PPO-skill10': {'env': 'YT', 'variant': 'PPO_skill10_eval', 'category': 'train_vs_eval'},
    'YT-PPO-skill20': {'env': 'YT', 'variant': 'PPO_skill20_eval', 'category': 'train_vs_eval'},
    'YT-PPO-skill30': {'env': 'YT', 'variant': 'PPO_skill30_eval', 'category': 'train_vs_eval'},
    'I1-0':  {'env': 'idsgame', 'variant': 'v0_train', 'category': 'difficulty'},
    'I1-3':  {'env': 'idsgame', 'variant': 'v3_train', 'category': 'difficulty'},
    'I1-6':  {'env': 'idsgame', 'variant': 'v6_train', 'category': 'difficulty'},
    'Y1-30': {'env': 'YT', 'variant': 'skill30_train', 'category': 'difficulty'},
    'Y1-50': {'env': 'YT', 'variant': 'skill50_train', 'category': 'difficulty'},
    'Y1-70': {'env': 'YT', 'variant': 'skill70_train', 'category': 'difficulty'},
    'C4-GNN': {'env': 'CAGE4', 'variant': 'GNN-PPO_eval', 'category': 'agent_variant'},
    'C4-GNN-Det': {'env': 'CAGE4', 'variant': 'GNN-PPO_det_eval', 'category': 'agent_variant'},
    'C4-HMARL': {'env': 'CAGE4', 'variant': 'HMARL_eval', 'category': 'agent_variant'},
    'C4-HMARL-Det': {'env': 'CAGE4', 'variant': 'HMARL_det_eval', 'category': 'agent_variant'},
    # ── W1X 10x 步长系列 ──
    'W1X-AT10host': {'env': 'CW', 'variant': 'ART_train_10_10x', 'category': 'step_10x'},
    'W1X-AT25host': {'env': 'CW', 'variant': 'ART_train_25_10x', 'category': 'step_10x'},
    'W1X-AT50host': {'env': 'CW', 'variant': 'ART_train_50_10x', 'category': 'step_10x'},
    'W1X-RT10host': {'env': 'CW', 'variant': 'RL_train_10_10x', 'category': 'step_10x'},
    'W1X-RT25host': {'env': 'CW', 'variant': 'RL_train_25_10x', 'category': 'step_10x'},
    'W1X-RT50host': {'env': 'CW', 'variant': 'RL_train_50_10x', 'category': 'step_10x'},
}

# ── Read all metrics ───────────────────────────────────────────
def read_final_metrics(uid):
    """Aggregate a unit across episodes: mean of each metric over the final
    rows of all episodes' metrics_table.csv.（v8 修复：原实现取 glob[0] 单集，
    与报告"单元均值"口径脱节）"""
    csv_files = sorted(glob.glob(os.path.join(RESULT_DIR, uid, '*', 'metrics_table.csv')))
    if not csv_files:
        return None
    acc = None
    for fp in csv_files:
        with open(fp) as f:
            reader = list(csv.reader(f))
        if len(reader) < 2:
            continue
        header, last = reader[0], reader[-1]
        row = dict(zip(header, last))
        if acc is None:
            acc = {k: [] for k in row}
        for k, v in row.items():
            acc[k].append(v)
    if acc is None:
        return None
    out = {}
    for k, vals in acc.items():
        try:
            nums = [float(v) for v in vals]
            out[k] = sum(nums) / len(nums)
        except ValueError:
            out[k] = vals[0]
    return out


all_metrics = {}
for uid in sorted(UNIT_META.keys()):
    m = read_final_metrics(uid)
    if m:
        all_metrics[uid] = m

print(f'Loaded {len(all_metrics)}/{len(UNIT_META)} units with metrics')
missing = [u for u in UNIT_META if u not in all_metrics]
if missing:
    print(f'  Missing (zero-attack baselines): {missing}')

# ── 1. Cross-environment matrix ────────────────────────────────
KEY_METRICS = ['node_control_rate', 'node_detect_rate', 'dc_score', 'di_score',
               'da_score', 'd_score', 'behavior_concealment', 'network_concealment',
               'comprehensive_concealment_score', 'lateral_movement_ratio',
               'control_scope', 'total_control_time']

cross_env = []
for uid in sorted(all_metrics.keys()):
    meta = UNIT_META.get(uid, {})
    m = all_metrics[uid]
    steps = m.get('step', '0')
    row = {
        'unit': uid,
        'env': meta.get('env', '?'),
        'variant': meta.get('variant', '?'),
        'steps': int(float(steps)) if str(steps).replace('.','',1).replace('-','',1).isdigit() else 0,
    }
    for km in KEY_METRICS:
        val = m.get(km, '0')
        try:
            row[km] = float(val)
        except ValueError:
            row[km] = 0.0
    cross_env.append(row)

with open(os.path.join(RESULT_DIR, 'cross_env_matrix.json'), 'w') as f:
    json.dump(cross_env, f, indent=2)
print(f'\n✅ cross_env_matrix.json: {len(cross_env)} units × {len(KEY_METRICS)} metrics')

# ── 2. Scale ablation (including CW train) ──────────────────────
scale_data = {
    'NASim': [],
    'CW_ART_eval': [],
    'CW_RL_eval': [],
    'CW_ART_train': [],
    'CW_RL_train': [],
}

for row in cross_env:
    env = row['env']
    var = row['variant']
    ctrl = row['node_control_rate']
    dscore = row['d_score']
    hosts = 0
    if var == 'tiny': hosts = 3
    elif var == 'small': hosts = 8
    elif var == 'medium': hosts = 16
    elif '10' in var: hosts = 10
    elif '25' in var: hosts = 25
    elif '50' in var: hosts = 50

    if env == 'NASim' and var in ('tiny', 'small', 'medium'):
        scale_data['NASim'].append({'hosts': hosts, 'ctrl_rate': ctrl, 'd_score': dscore, 'unit': row['unit']})
    elif env == 'CW' and var.startswith('ART_eval'):
        scale_data['CW_ART_eval'].append({'hosts': hosts, 'ctrl_rate': ctrl, 'd_score': dscore, 'unit': row['unit']})
    elif env == 'CW' and var.startswith('RL_eval'):
        scale_data['CW_RL_eval'].append({'hosts': hosts, 'ctrl_rate': ctrl, 'd_score': dscore, 'unit': row['unit']})
    elif env == 'CW' and var.startswith('ART_train') and not row['unit'].startswith('W1X'):
        scale_data['CW_ART_train'].append({'hosts': hosts, 'ctrl_rate': ctrl, 'd_score': dscore, 'unit': row['unit']})
    elif env == 'CW' and var.startswith('RL_train') and not row['unit'].startswith('W1X'):
        scale_data['CW_RL_train'].append({'hosts': hosts, 'ctrl_rate': ctrl, 'd_score': dscore, 'unit': row['unit']})

for key in scale_data:
    scale_data[key].sort(key=lambda x: x['hosts'])

with open(os.path.join(RESULT_DIR, 'scale_ablation.json'), 'w') as f:
    json.dump(scale_data, f, indent=2)
print(f'✅ scale_ablation.json: NASim({len(scale_data["NASim"])}) + CW_ART({len(scale_data["CW_ART_eval"])}) + CW_RL({len(scale_data["CW_RL_eval"])})')

# ── 3. Agent comparison ────────────────────────────────────────
agent_data = defaultdict(list)
for row in cross_env:
    if row['env'] in ('CAGE2', 'CAGE4', 'CW'):
        agent_data[row['env']].append({
            'unit': row['unit'],
            'variant': row['variant'],
            'ctrl_rate': row['node_control_rate'],
            'detect_rate': row['node_detect_rate'],
            'd_score': row['d_score'],
            'conceal': row['comprehensive_concealment_score'],
        })

with open(os.path.join(RESULT_DIR, 'agent_comparison.json'), 'w') as f:
    json.dump(dict(agent_data), f, indent=2)
print(f'✅ agent_comparison.json: {len(agent_data)} environments')

# ── 4. CAGE1 vs CAGE2 consistency ──────────────────────────────
cyborg_consistency = {}
for uid in ['C1-M', 'C2-M']:
    if uid in all_metrics:
        m = all_metrics[uid]
        cyborg_consistency[uid] = {
            'env': UNIT_META[uid]['env'],
            'ctrl_rate': float(m.get('node_control_rate', 0)),
            'detect_rate': float(m.get('node_detect_rate', 0)),
            'd_score': float(m.get('d_score', 0)),
            'conceal': float(m.get('comprehensive_concealment_score', 0)),
            'steps': int(m.get('step', 0)),
        }

with open(os.path.join(RESULT_DIR, 'cyborg_series_consistency.json'), 'w') as f:
    json.dump(cyborg_consistency, f, indent=2)
print(f'✅ cyborg_series_consistency.json: {len(cyborg_consistency)} units')

# ── Summary ─────────────────────────────────────────────────────
print(f'\n{"="*60}')
print(f'Phase 5.6 Complete: 4 analysis outputs generated')
print(f'{"="*60}')

# Quick analysis
print(f'\nScale Ablation:')
print(f'  NASim: tiny={scale_data["NASim"][0]["ctrl_rate"]:.3f} → small={scale_data["NASim"][1]["ctrl_rate"]:.3f} → medium={scale_data["NASim"][2]["ctrl_rate"]:.3f}')
if scale_data['CW_ART_eval']:
    print(f'  CW ART: 10={scale_data["CW_ART_eval"][0]["ctrl_rate"]:.3f} → 25={scale_data["CW_ART_eval"][1]["ctrl_rate"]:.3f} → 50={scale_data["CW_ART_eval"][2]["ctrl_rate"]:.3f}')
if scale_data['CW_RL_eval']:
    print(f'  CW RL:  10={scale_data["CW_RL_eval"][0]["ctrl_rate"]:.3f} → 25={scale_data["CW_RL_eval"][1]["ctrl_rate"]:.3f} → 50={scale_data["CW_RL_eval"][2]["ctrl_rate"]:.3f}')
if scale_data['CW_ART_train']:
    print(f'  CW ART train: 10={scale_data["CW_ART_train"][0]["ctrl_rate"]:.3f} → 25={scale_data["CW_ART_train"][1]["ctrl_rate"]:.3f} → 50={scale_data["CW_ART_train"][2]["ctrl_rate"]:.3f}')
if scale_data['CW_RL_train']:
    print(f'  CW RL train:  10={scale_data["CW_RL_train"][0]["ctrl_rate"]:.3f} → 25={scale_data["CW_RL_train"][1]["ctrl_rate"]:.3f} → 50={scale_data["CW_RL_train"][2]["ctrl_rate"]:.3f}')

print(f'\nCAGE1 vs CAGE2 (Meander):')
print(f'  C1-M: CtrlRate={cyborg_consistency["C1-M"]["ctrl_rate"]:.4f}, D-Score={cyborg_consistency["C1-M"]["d_score"]:.4f}')
print(f'  C2-M: CtrlRate={cyborg_consistency["C2-M"]["ctrl_rate"]:.4f}, D-Score={cyborg_consistency["C2-M"]["d_score"]:.4f}')
# ── 5. Info gain heatmap (G7) ──────────────────────────────────
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    # Build heatmap: 7 environments × 4 key metrics
    env_names = ['CAGE1', 'CAGE2', 'CAGE4', 'YT', 'NASim', 'idsgame', 'CW']
    metrics = ['ctrl_rate', 'detect_rate', 'd_score', 'conceal']
    metric_labels = ['CtrlRate', 'Detect', 'D-Score', 'Conceal']
    
    heatmap = np.zeros((len(env_names), len(metrics)))
    for i, env in enumerate(env_names):
        env_rows = [r for r in cross_env if r['env'] == env]
        if env_rows:
            for j, m in enumerate(metrics):
                vals = [r.get(f'node_{m}' if m in ('ctrl_rate',) else 
                              (f'node_{m}' if 'detect' in m else
                               m if m == 'd_score' else
                               'comprehensive_concealment_score'), 0) for r in env_rows]
                # Use the right key mapping
                if m == 'ctrl_rate':
                    vals = [r['node_control_rate'] for r in env_rows]
                elif m == 'detect_rate':
                    vals = [r['node_detect_rate'] for r in env_rows]
                elif m == 'd_score':
                    vals = [r['d_score'] for r in env_rows]
                elif m == 'conceal':
                    vals = [r['comprehensive_concealment_score'] for r in env_rows]
                heatmap[i][j] = np.mean(vals) if vals else 0
    
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(heatmap, cmap='YlOrRd', aspect='auto')
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(metric_labels)
    ax.set_yticks(range(len(env_names)))
    ax.set_yticklabels(env_names)
    ax.set_title('Cross-Environment wxpgzs Metric Heatmap')
    plt.colorbar(im, ax=ax, label='Mean Value')
    
    for i in range(len(env_names)):
        for j in range(len(metrics)):
            ax.text(j, i, f'{heatmap[i][j]:.3f}', ha='center', va='center',
                    fontsize=8, color='black' if heatmap[i][j] < 0.6 else 'white')
    
    plt.tight_layout()
    plt.savefig(os.path.join(RESULT_DIR, 'info_gain_heatmap.png'), dpi=150)
    print(f'\n✅ info_gain_heatmap.png generated')
except ImportError as e:
    print(f'\n⚠️  Heatmap skipped: {e}')