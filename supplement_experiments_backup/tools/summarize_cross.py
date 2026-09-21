#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交叉臂结果汇总：读取 corpus + metrics，构建 3×3 矩阵。

每格（9 组合 × 5 集）：
  * d_score      : wxpgzs metrics_table.csv 最后一行（全 episode 聚合）
  * strike_rate  : red_action_dst ∈ 诱饵清单（manifest 并集口径）的步数 / 总步数
                   （any-target 主口径 + success 子口径）
  * ctrl_rate    : node_control_rate 终值 / 全集均值
  * decoys       : 蓝方诱饵部署数（manifest count）
输出：
  cross_arm/per_episode.csv       每集明细
  cross_arm/matrix.json           3×3 聚合（供 md 生成）
  cross_arm/cross_arm_results.md  人读矩阵报告
"""
import csv
import glob
import json
import os
import statistics

PROJ = "/home/xxl/MyExperiments/E4ACD"
CROSS = f"{PROJ}/data/cw_supplement/cross_arm"
ARMS = ["A", "B1", "B2"]


def load_decoy_names(csv_path):
    p = f"{csv_path}.decoys.json"
    names = set()
    if os.path.exists(p):
        d = json.load(open(p))
        for ep in d.get("episodes", {}).values():
            names |= {r["name"] for r in ep.get("decoys", [])}
        return names, "manifest"
    return set(), "regex"


def strike_rate(csv_path, names, success_only=False):
    rows = list(csv.DictReader(open(csv_path)))
    dst = "red_action_dst" if "red_action_dst" in rows[0] else "red_action_dest"
    ok = "red_action_success"
    hit = 0
    for r in rows:
        if r[dst] in names and (not success_only or r[ok].strip().upper() == "TRUE"):
            hit += 1
    return hit / len(rows)


def metrics_for(stem):
    f = f"{CROSS}/metrics/{stem}/metrics_table.csv"
    if not os.path.exists(f):
        return None
    rows = list(csv.DictReader(open(f)))
    last = rows[-1]
    return {
        "d_score": float(last["d_score"]),
        "ctrl_final": float(last["node_control_rate"]),
        "ctrl_mean": statistics.fmean(float(r["node_control_rate"]) for r in rows),
    }


def collect():
    per_ep = []
    for f in sorted(glob.glob(f"{CROSS}/corpus/cw_r_cross_*.csv")):
        if f.endswith(".decoys.json"):
            continue
        stem = os.path.basename(f)[:-4]
        parts = stem.split("_")  # cw r cross red{X} blue{Y} 25host s1 sync1 s{seed}
        red_arm = parts[3].replace("red", "")
        blue_arm = parts[4].replace("blue", "")
        seed = int(parts[8].replace("s", ""))
        names, src = load_decoy_names(f)
        m = metrics_for(stem)
        if m is None:
            print(f"[warn] 缺 metrics: {stem}")
            continue
        run = json.load(open(f + ".run.json"))
        per_ep.append({
            "stem": stem, "red_arm": red_arm, "blue_arm": blue_arm, "seed": seed,
            "steps": run["num_steps"], "decoys_deployed": len(names),
            "strike_rate_any": strike_rate(f, names),
            "strike_rate_success": strike_rate(f, names, True),
            "decoy_source": src, **m,
        })
    return per_ep


def agg(per_ep):
    """→ {red_arm: {blue_arm: {metric: mean/std/...}}}"""
    out = {}
    for ra in ARMS:
        out[ra] = {}
        for ba in ARMS:
            eps = [e for e in per_ep if e["red_arm"] == ra and e["blue_arm"] == ba]
            def ms(key):
                vals = [e[key] for e in eps]
                return {
                    "mean": statistics.fmean(vals),
                    "std": statistics.stdev(vals) if len(vals) > 1 else 0.0,
                    "n": len(vals),
                    "vals": vals,
                }
            out[ra][ba] = {
                "d_score": ms("d_score"),
                "strike_any": ms("strike_rate_any"),
                "strike_succ": ms("strike_rate_success"),
                "ctrl_final": ms("ctrl_final"),
                "ctrl_mean": ms("ctrl_mean"),
                "decoys": ms("decoys_deployed"),
                "seeds": sorted(e["seed"] for e in eps),
            }
    return out


def fmt(v):
    return f"{v:.4f}"


def build_md(per_ep, m):
    lines = []
    ap = lines.append
    ap("# CW 交叉臂（Cross-Arm）评估结果 — 3×3 矩阵")
    ap("")
    ap("- **设计**：固定红方 checkpoint，分别在 3 个蓝方 checkpoint 环境中评估（行内对比 = 蓝方供给侧效应）；固定蓝方换红方（列内对比 = 红方策略效应）。")
    ap("- **checkpoint**：`V94_Retrain{A,B1,B2}_25host_s1/{red,blue}_agent.pt`，混合目录 `V94_Cross_red{X}_blue{Y}`。")
    ap("- **口径**：拓扑 25host（`topology_25h.yaml` / `25-host-network.yaml`）、`CYBERWHEEL_SYNC_RED_TARGETS=1`（sync1）、每组合 5 集 × 100 步（种子 101–105，每集独立进程独立种子，与 EXP-1 口径一致）、deterministic。")
    ap("- **指标**：D-Score = wxpgzs `metrics_table.csv` 末行聚合值；decoy-strike 率 = 红方动作目标 ∈ 诱饵清单（`.decoys.json` 并集口径，any-target）的步数占比；控制率 = `node_control_rate`（终值 / 全集均值）；蓝方部署数 = 每集诱饵清单条数均值。")
    ap("- **产物**：语料 `data/cw_supplement/cross_arm/corpus/`（45 × csv+.decoys.json+.run.json）；wxpgzs 指标 `cross_arm/metrics/`；每集明细 `cross_arm/per_episode.csv`。")
    ap("")

    ap("## 1. D-Score 矩阵（均值 ± std，n=5）")
    ap("")
    ap("| red \\ blue | " + " | ".join(f"blue_{ba}" for ba in ARMS) + " |")
    ap("|---|" + "---|" * len(ARMS))
    for ra in ARMS:
        cells = []
        for ba in ARMS:
            d = m[ra][ba]["d_score"]
            cell = f"{fmt(d['mean'])} ± {fmt(d['std'])}"
            if ra == ba:
                cell = f"**{cell}**"
            cells.append(cell)
        ap(f"| **red_{ra}** | " + " | ".join(cells) + " |")
    ap("")

    ap("## 2. decoy-strike 率矩阵（any-target，均值，n=5）")
    ap("")
    ap("| red \\ blue | " + " | ".join(f"blue_{ba}" for ba in ARMS) + " |")
    ap("|---|" + "---|" * len(ARMS))
    for ra in ARMS:
        cells = []
        for ba in ARMS:
            d = m[ra][ba]["strike_any"]
            cell = f"{d['mean']*100:.2f}%"
            if ra == ba:
                cell = f"**{cell}**"
            cells.append(cell)
        ap(f"| **red_{ra}** | " + " | ".join(cells) + " |")
    ap("")

    ap("## 3. decoy-strike 率矩阵（success 子口径，均值，n=5）")
    ap("")
    ap("| red \\ blue | " + " | ".join(f"blue_{ba}" for ba in ARMS) + " |")
    ap("|---|" + "---|" * len(ARMS))
    for ra in ARMS:
        cells = []
        for ba in ARMS:
            d = m[ra][ba]["strike_succ"]
            cell = f"{d['mean']*100:.2f}%"
            if ra == ba:
                cell = f"**{cell}**"
            cells.append(cell)
        ap(f"| **red_{ra}** | " + " | ".join(cells) + " |")
    ap("")

    ap("## 4. 控制率矩阵（node_control_rate 终值，均值，n=5）")
    ap("")
    ap("| red \\ blue | " + " | ".join(f"blue_{ba}" for ba in ARMS) + " |")
    ap("|---|" + "---|" * len(ARMS))
    for ra in ARMS:
        cells = []
        for ba in ARMS:
            d = m[ra][ba]["ctrl_final"]
            cell = f"{d['mean']*100:.2f}%"
            if ra == ba:
                cell = f"**{cell}**"
            cells.append(cell)
        ap(f"| **red_{ra}** | " + " | ".join(cells) + " |")
    ap("")

    ap("## 5. 蓝方部署数矩阵（每集诱饵清单条数均值，n=5）")
    ap("")
    ap("| red \\ blue | " + " | ".join(f"blue_{ba}" for ba in ARMS) + " |")
    ap("|---|" + "---|" * len(ARMS))
    for ra in ARMS:
        cells = []
        for ba in ARMS:
            d = m[ra][ba]["decoys"]
            cell = f"{d['mean']:.1f} ± {d['std']:.1f}"
            if ra == ba:
                cell = f"**{cell}**"
            cells.append(cell)
        ap(f"| **red_{ra}** | " + " | ".join(cells) + " |")
    ap("")

    ap("## 6. 行/列对比")
    ap("")
    ap("### 行内对比（同一红方，换蓝方 ⇒ 蓝方部署行为 / 供给侧效应）")
    ap("")
    ap("| 红方 | 对角线基线 D-Score | 行内 Δ（max−min） | strike 率随蓝方变化 |")
    ap("|---|---|---|---|")
    for ra in ARMS:
        diag = m[ra][ra]["d_score"]["mean"]
        row_ds = [m[ra][ba]["d_score"]["mean"] for ba in ARMS]
        row_sr = [m[ra][ba]["strike_any"]["mean"] for ba in ARMS]
        ap(f"| red_{ra} | {fmt(diag)} | {fmt(max(row_ds)-min(row_ds))} | "
           f"{min(row_sr)*100:.2f}% – {max(row_sr)*100:.2f}% |")
    ap("")

    ap("### 列内对比（同一蓝方，换红方 ⇒ 红方策略差异 / 奖励驱动学习效应）")
    ap("")
    ap("| 蓝方 | 对角线基线 D-Score | 列内 Δ（max−min） | strike 率随红方变化 |")
    ap("|---|---|---|---|")
    for ba in ARMS:
        diag = m[ba][ba]["d_score"]["mean"]
        col_ds = [m[ra][ba]["d_score"]["mean"] for ra in ARMS]
        col_sr = [m[ra][ba]["strike_any"]["mean"] for ra in ARMS]
        ap(f"| blue_{ba} | {fmt(diag)} | {fmt(max(col_ds)-min(col_ds))} | "
           f"{min(col_sr)*100:.2f}% – {max(col_sr)*100:.2f}% |")
    ap("")

    # 效应量分解（对角线 vs 非对角，简单双因素方差式描述）
    diag_ds = [m[a][a]["d_score"]["mean"] for a in ARMS]
    off_ds = [m[ra][ba]["d_score"]["mean"] for ra in ARMS for ba in ARMS if ra != ba]
    diag_sr = [m[a][a]["strike_any"]["mean"] for a in ARMS]
    off_sr = [m[ra][ba]["strike_any"]["mean"] for ra in ARMS for ba in ARMS if ra != ba]
    red_range = max(max(m[a][b]["d_score"]["mean"] for b in ARMS) - min(m[a][b]["d_score"]["mean"] for b in ARMS) for a in ARMS)
    blue_range = max(max(m[a][b]["d_score"]["mean"] for a in ARMS) - min(m[a][b]["d_score"]["mean"] for a in ARMS) for b in ARMS)
    red_range_sr = max(max(m[a][b]["strike_any"]["mean"] for b in ARMS) - min(m[a][b]["strike_any"]["mean"] for b in ARMS) for a in ARMS)
    blue_range_sr = max(max(m[a][b]["strike_any"]["mean"] for a in ARMS) - min(m[a][b]["strike_any"]["mean"] for a in ARMS) for b in ARMS)
    ap("## 7. 效应量速览")
    ap("")
    ap(f"- 对角线（self-play 基线）D-Score：{', '.join(f'{a}: {fmt(v)}' for a, v in zip(ARMS, diag_ds))}；极差 {fmt(max(diag_ds)-min(diag_ds))}")
    ap(f"- 非对角（交叉）D-Score 均值：{fmt(statistics.fmean(off_ds))}（对角均值 {fmt(statistics.fmean(diag_ds))}）")
    ap(f"- **红方主效应**（列内极差最大值）：D-Score {fmt(red_range)}；strike 率 {red_range_sr*100:.2f}%")
    ap(f"- **蓝方主效应**（行内极差最大值）：D-Score {fmt(blue_range)}；strike 率 {blue_range_sr*100:.2f}%")
    ap(f"- 对角 strike 率：{', '.join(f'{a}: {v*100:.2f}%' for a, v in zip(ARMS, diag_sr))}；非对角 strike 率均值 {statistics.fmean(off_sr)*100:.2f}%")
    ap("")
    return "\n".join(lines)


def main():
    per_ep = collect()
    if not per_ep:
        raise SystemExit("没有可汇总的语料")
    # 期望 45 集
    n_expect = 9 * 5
    if len(per_ep) != n_expect:
        print(f"[warn] 集数 {len(per_ep)} != 期望 {n_expect}")
    with open(f"{CROSS}/per_episode.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(per_ep[0].keys()))
        w.writeheader()
        w.writerows(per_ep)
    m = agg(per_ep)
    with open(f"{CROSS}/matrix.json", "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)
    md = build_md(per_ep, m)
    with open(f"{CROSS}/cross_arm_results.md", "w", encoding="utf-8") as f:
        f.write(md)
    print(f"OK：{len(per_ep)} 集 → per_episode.csv / matrix.json / cross_arm_results.md")


if __name__ == "__main__":
    main()
