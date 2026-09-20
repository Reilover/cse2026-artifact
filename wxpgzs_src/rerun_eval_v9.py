#!/usr/bin/env python3
"""
v8 语料全量重评估驱动（R-1 批复：数据真实性第一位）
- 按单元映射重建 45 单元评估（v8 语料 → wxpgzs cli）
- topo 统一 40-host-network.yaml（wxpgzs 抽象拓扑，与 v7 一致）
- 用法: python3 rerun_eval_v8.py [--dry] [--only C2-M,W1-R50]
"""
import os, sys, glob, shutil, subprocess, argparse

WX = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# ── 布局自适应（v9.2）──────────────────────────────────────────────
# 同一份源码需在两种布局下工作，且包内运行不得写出包外：
#   ① 项目布局 <root>/wxpgzs/rerun_eval_v9.py          → 语料 <root>/data，
#                                                        输出 <root>/wxpgzs/result_v9
#   ② 包内布局 <pkg>/{wxpgzs_src,scripts}/rerun_eval_v9.py → 语料 <pkg>/inputs（127 CSV 扁平存放），
#                                                        输出 <pkg>/results/wxpgzs_pipeline_v9
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


_ROOT = _find_root(WX)
if _ROOT:
    BASE = _ROOT
    PKG = os.path.join(BASE, 'phase5_package')
    CORPUS = os.path.join(BASE, 'data')          # 项目布局：UNIT_CSV 模式相对 BASE 生效
    _PACKAGED = False
else:
    PKG = os.path.dirname(WX)
    BASE = os.path.dirname(PKG)
    CORPUS = os.path.join(PKG, 'inputs')         # 包内布局：按 basename 在 inputs/<env>/ 下匹配
    _PACKAGED = True
OUTBASE = os.path.join(PKG, 'results', 'wxpgzs_pipeline_v9') if _PACKAGED \
    else os.path.join(WX, 'result_v9')
PROJ = BASE
INP = os.path.join(PKG, 'inputs')
TOPO_MAP = {
    'cage1': f'{INP}/cage1/topology_meander.yaml',
    'cage2': f'{INP}/cage2/topology.yaml',
    'cage4': f'{INP}/cage4/topology.yaml',
    'idsgame': f'{INP}/idsgame/topology.yaml',
    'yt': f'{INP}/yt/topology.yaml',
}
def topo_for(unit, csv_path):
    """v9: 按单元/语料路径选择环境真实拓扑

    F6 修复（v9_4/cage4_honeypot_fix_plan.md §4.1 F6）：
      CAGE4 各集来自不同 seed 的场景实例，共用一张 inputs/cage4/topology.yaml
      → 30.9% 指标行的目标不在拓扑中（资产值查表为 0，DC/DI/DA 被污染）。
      现改为**优先读同目录逐集拓扑侧车** `<csv>.topology.yaml`，缺失时回退旧拓扑
      （对历史语料零行为变化）。
    """
    side = f'{csv_path}.topology.yaml'
    if os.path.exists(side):
        return side
    if unit.startswith('C1'): return TOPO_MAP['cage1']
    if unit.startswith('C2'): return TOPO_MAP['cage2']
    if unit.startswith('C4'): return TOPO_MAP['cage4']
    if unit.startswith(('I1','IDS')): return TOPO_MAP['idsgame']
    if unit.startswith('N1'):
        if 'tiny' in csv_path: return f'{INP}/nasim/topology_tiny.yaml'
        if 'small' in csv_path: return f'{INP}/nasim/topology_small.yaml'
        return f'{INP}/nasim/topology_medium.yaml'
    if unit.startswith(('Y1','YT')): return TOPO_MAP['yt']
    if unit.startswith('W1'):
        if '10host' in csv_path or '10h_' in csv_path: return f'{INP}/cw/topology_10h.yaml'
        if '25host' in csv_path or '25h_' in csv_path: return f'{INP}/cw/topology_25h.yaml'
        return f'{INP}/cw/topology_50h.yaml'
    return f'{WX}/40-host-network.yaml'

# 单元 → v8 语料 glob（相对 E4ACD 根）
UNIT_CSV = {
    'C1-M':        ['data/ep_cage1_meander_train_ep00[234].csv'],
    'C1-R':        ['data/phase4/cage1/ep_cage1_random_train_ep00*.csv'],  # v8 生成失败(GetUsers签名变更)，回退 v7
    'C2-B':        ['data/ep_cage2_b_line_train_ep001.csv'],
    'C2-H':        ['data/ep_cage2_heuristic_train_ep001.csv'],
    'C2-M':        ['data/ep_cage2_meander_train_ep001.csv'],
    'C2-S':        ['data/ep_cage2_sleep_train_ep001.csv'],
    'C4-DF':       ['data/ep_cage4_b_line_rl_train_ep001.csv'],
    'C4-FS':       ['data/ep_cage4_meander_rl_train_ep001.csv'],
    'C4-RS':       ['data/ep_cage4_sleep_rl_train_ep001.csv'],
    'C4-GNN':      ['data/phase4/cage4_variants/ep_cage4_gnn_ppo_eval_ep00[123].csv'],
    'C4-GNN-Det':  ['data/phase4/cage4_variants/ep_cage4_gnn_ppo_det_eval_ep00[123].csv'],
    'C4-HMARL':    ['data/phase4/cage4_variants/ep_cage4_hmarl_eval_ep00[123].csv'],
    'C4-HMARL-Det':['data/phase4/cage4_variants/ep_cage4_hmarl_det_eval_ep00[123].csv'],
    'I1-0':        ['data/ep_idsgame_v0_train_ep001.csv'],
    'I1-3':        ['data/ep_idsgame_v3_train_ep001.csv'],
    'I1-6':        ['data/ep_idsgame_v6_train_ep001.csv'],
    'N1-M':        ['data/ep_nasim_medium_train_ep001.csv'],
    'N1-S':        ['data/ep_nasim_small_train_ep001.csv'],
    'N1-T':        ['data/ep_nasim_tiny_train_ep001.csv'],
    # CW 全系：success 语义 v7→v8 无修复变化（RedActionReturn 本就正确），
    # v8 evaluate 模式不产 CSV（历史遗留）→ 回退 v7 语料（注册表标注代际）
    'W1-A10':      ['data/phase4/cw/ep_cw_art_eval_10host_ep00[123].csv'],
    'W1-A25':      ['data/phase4/cw/ep_cw_art_eval_25host_ep00[123].csv'],
    'W1-A50':      ['data/phase4/cw/ep_cw_art_eval_50host_ep00[123].csv'],
    'W1-AT10':     ['data/phase4/cw/ep_cw_art_train_10host_train_ep001.csv'],
    'W1-AT25':     ['data/phase4/cw/ep_cw_art_train_25host_train_ep001.csv'],
    'W1-AT50':     ['data/phase4/cw/ep_cw_art_train_50host_train_ep001.csv'],
    'W1-R10':      ['data/phase4/cw/ep_cw_rl_eval_10host_ep00[123].csv'],
    'W1-R25':      ['data/phase4/cw/ep_cw_rl_eval_25host_ep00[123].csv'],
    'W1-R50':      ['data/phase4/cw/ep_cw_rl_eval_50host_ep00[123].csv'],
    'W1-RT10':     ['data/phase4/cw/ep_cw_rl_train_10host_train_ep001.csv'],
    'W1-RT25':     ['data/phase4/cw/ep_cw_rl_train_25host_train_ep001.csv'],
    'W1-RT50':     ['data/phase4/cw/ep_cw_rl_train_50host_train_ep001.csv'],
    'Y1-30':       ['data/ep_yt_skill30_train_ep001.csv'],
    'Y1-50':       ['data/ep_yt_skill50_train_ep001.csv'],
    'Y1-70':       ['data/ep_yt_skill70_train_ep001.csv'],
    # ── eval 代际单元（v8 batch1 产出）──
    'C2-M-Eval': ['data/ep_cage2_meander_eval_ep00[123].csv'],
    'IDS-PPO-v0': ['data/ep_idsgame_ppo_v0_eval_ep00[123].csv'],
    'IDS-PPO-v3': ['data/ep_idsgame_ppo_v3_eval_ep00[123].csv'],
    'IDS-PPO-v6': ['data/ep_idsgame_ppo_v6_eval_ep00[123].csv'],
    'YT-PPO-skill10': ['data/ep_yt_ppo_skill10_eval_ep00[123].csv'],
    'YT-PPO-skill20': ['data/ep_yt_ppo_skill20_eval_ep00[123].csv'],
    'YT-PPO-skill30': ['data/ep_yt_ppo_skill30_eval_ep00[123].csv'],
    # W1X 10x 系列: CW 语料 success 语义无修复变化（RedActionReturn 本就正确），保留 v7 语料
    'W1X-AT10host': ['data/phase4/cw_10x/ep_cw_art_train_10host_10x_ep001*.csv'],
    'W1X-AT25host': ['data/phase4/cw_10x/ep_cw_art_train_25host_10x_ep001*.csv'],
    'W1X-AT50host': ['data/phase4/cw_10x/ep_cw_art_train_50host_10x_ep001*.csv'],
    'W1X-RT10host': ['data/phase4/cw_10x/ep_cw_rl_train_10host_10x_ep001*.csv'],
    'W1X-RT25host': ['data/phase4/cw_10x/ep_cw_rl_train_25host_10x_ep001*.csv'],
    'W1X-RT50host': ['data/phase4/cw_10x/ep_cw_rl_train_50host_10x_ep001*.csv'],
}

def resolve(pats):
    """语料定位。

    项目布局：UNIT_CSV 的模式（data/**）相对项目根 glob；
    包内布局：语料已按环境扁平存放于 inputs/<env>/，故取模式 basename 匹配
              （如 data/phase4/cw/ep_cw_rl_eval_50host_ep00[123].csv → inputs/cw/…）。
    """
    out = []
    for p in pats:
        if _PACKAGED:
            m = sorted(glob.glob(os.path.join(CORPUS, '*', os.path.basename(p))))
        else:
            m = sorted(glob.glob(os.path.join(BASE, p)))
        out.extend(m if m else [os.path.join(BASE, p) if not _PACKAGED else p])
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--only', default='')
    a = ap.parse_args()
    only = set(x for x in a.only.split(',') if x)

    ok = fail = miss = 0
    for unit, pats in UNIT_CSV.items():
        if only and unit not in only:
            continue
        csvs = resolve(pats)
        existing = [c for c in csvs if os.path.exists(c)]
        if not existing:
            print(f'[MISS] {unit}: 无 v8 语料 {pats}')
            miss += 1
            continue
        outdir = os.path.join(OUTBASE, unit)
        os.makedirs(outdir, exist_ok=True)
        for c in existing:
            epname = os.path.splitext(os.path.basename(c))[0]
            epdir = os.path.join(outdir, epname)
            cmd = [PY, 'cli.py', '-t', topo_for(unit, c), '-c', c, '-o', epdir, '-q']
            if a.dry:
                print(f'[DRY] {unit}/{epname}')
                continue
            r = subprocess.run(cmd, cwd=WX, capture_output=True, text=True, timeout=600)
            if r.returncode == 0:
                # cli 的 -o 会再嵌一层 <csv_basename>/ → 自动展平到
                # OUTBASE/<UNIT>/<ep>/{metrics_table.csv,_process2.json,*.png}
                inner = os.path.join(epdir, epname)
                if os.path.isdir(inner):
                    for _f in os.listdir(inner):
                        shutil.move(os.path.join(inner, _f), os.path.join(epdir, _f))
                    os.rmdir(inner)
                ok += 1
                print(f'[OK] {unit}/{epname}')
            else:
                fail += 1
                print(f'[FAIL] {unit}/{epname}: {r.stderr[-200:]}')
    print(f'\n完成: OK={ok} FAIL={fail} MISS={miss}')

if __name__ == '__main__':
    main()
