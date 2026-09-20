#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络安全威胁评估系统 - 命令行评估工具

功能：
  1. 单文件评估：指定拓扑YAML + 单个CSV，完成全流程计算并输出图表
  2. 批量评估：指定拓扑YAML + CSV目录，批量完成所有CSV的评估

用法：
  # 单文件评估
  python cli.py -t 40-host-network.yaml -c data/episode_90_20260131_050414.csv -o result/

  # 批量评估（data目录下所有CSV）
  python cli.py -t 40-host-network.yaml -d data/ -o result/

  # 仅计算，不生成图表
  python cli.py -t 40-host-network.yaml -c data/episode_90_20260131_050414.csv --no-charts

依赖：
  pip install matplotlib
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------- 确保项目根目录在 sys.path ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from generate_process2_json import (
    calculate_step_metrics,
    set_authoritative_honey,
    set_authoritative_honey_intervals,
    get_label_source,
    get_interval_source,
)


def _load_decoy_manifest(csv_path):
    """读取 <语料>.decoys.json 侧车。

    支持两种 schema：
      - `cw-decoy-manifest-01`（CW 侧，v9.4 Step 2）：只给**名字集合** → 静态节点口径；
      - `cw-decoy-manifest-02`（CAGE4 侧，F3）：记录带 first_seen_step / removed_step
        → **时相区间口径**，不进静态节点集合（诱饵宿主是真实主机，必须留在非蜜罐分母）。

    侧车与统一语料 CSV **同目录、同名加后缀** → 语料自携带、无需新增 CLI 参数，
    且天然满足"包内 inputs 自带可复现性"。
    未提供或解析失败 → ([], {}, 'regex')，即保持既有"正则判定"行为，**不报错**（E1/E4）。
    """
    import json as _json
    p = f"{csv_path}.decoys.json"
    if not os.path.exists(p):
        return [], {}, 'regex'
    try:
        with open(p, encoding='utf-8') as f:
            d = _json.load(f)
        schema = str(d.get('schema') or '')
        intervals = {}
        names = set()
        for ep in (d.get('episodes') or {}).values():
            for rec in (ep.get('decoys') or []):
                if isinstance(rec, dict):
                    n = rec.get('name')
                    if not n:
                        continue
                    if rec.get('first_seen_step') is not None:
                        intervals.setdefault(str(n), []).append(
                            (rec.get('first_seen_step'), rec.get('removed_step')))
                    else:
                        names.add(str(n))
                elif rec:
                    names.add(str(rec))
        if intervals:
            # schema-02：时相口径（CAGE4 语义）
            # 2026-09-18 诱饵剔除修复（用户拍板："DC 不应该计算对 decoy 节点的控制"）：
            # 实际导出（data/cage4_fix/corpus/*.topology.yaml）里诱饵是**独立拓扑条目**
            # （有自己的 asset_value），不再是"真实主机上的假服务"⇒ 旧实现返回 names=[]
            # 会让诱饵主机逃过 is_honey_node，被当普通主机计入红方战果
            # （分母 non_honey_total、DC/DI/DA 资产分母、被控集合三处污染，
            #   实测 C4-GNN ep001 被控资产 92 里 87 是诱饵）。
            # 现把诱饵主机名**同时**并入静态名字集合（names = 清单键集），source 仍为
            # 'manifest-interval'（_process2.json 的 label_source 溯源语义不变）。
            # 注意：时相区间登记保留不动——attacks_to_honey 的"部署前不算打蜜罐"
            # 时相语义由 is_honey_target 继续承载，与本处静态节点口径互补。
            interval_names = set(intervals.keys()) | names
            return sorted(interval_names), intervals, 'manifest-interval'
        return sorted(names), {}, ('manifest' if names else 'regex')
    except Exception as e:
        print(f"[decoy-manifest] 解析失败，回退正则判定: {e}")
        return [], {}, 'regex'
from generate_process_linked_list import generate_process_linked_list
from pre_process import preprocess_data

# ============================================================
#  尝试导入 matplotlib（可选依赖）
# ============================================================
try:
    import matplotlib
    matplotlib.use("Agg")  # 非交互后端，纯文件输出
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# ============================================================
#  中文字体探测（Windows / macOS / Linux）
# ============================================================
def _detect_chinese_font():
    """返回一个可用的中文字体名，若找不到则返回默认 sans-serif。"""
    candidates = [
        "Microsoft YaHei", "SimHei", "PingFang SC",
        "Noto Sans CJK SC", "WenQuanYi Micro Hei",
        "STHeiti", "Source Han Sans SC", "AR PL UMing CN",
    ]
    if not HAS_MPL:
        return "sans-serif"
    try:
        from matplotlib.font_manager import FontManager
        available = {f.name for f in FontManager().ttflist}
        for c in candidates:
            if c in available:
                return c
    except Exception:
        pass
    return "sans-serif"

CN_FONT = _detect_chinese_font()

# ============================================================
#  颜色与样式常量
# ============================================================
COLOR_CYCLE = ["#2B7BBD", "#E8722A", "#4DAF4A", "#984EA3",
               "#FF7F00", "#A65628", "#F781BF", "#999999"]
LINE_STYLES = ["-", "--", "-.", ":"]


def setup_matplotlib():
    """Configure matplotlib global style."""
    if not HAS_MPL:
        return
    # 使用检测到的中文字体作为 sans-serif 首选，避免图例乱码
    font_list = [CN_FONT, "DejaVu Sans", "Arial", "sans-serif"] if CN_FONT != "sans-serif" else ["DejaVu Sans", "Arial", "sans-serif"]
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": font_list,
        "axes.unicode_minus": False,
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.1,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "lines.linewidth": 1.5,
        "axes.titlesize": 13,
        "axes.labelsize": 10,
    })


# ============================================================
#  工具函数
# ============================================================
def get_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ──────────────────────────────────────────────────────────── 动作词表归一化（v9.4）
# 修复 R9 / Q2：45 单元中有 4 个（C4-GNN / C4-GNN-Det / C4-HMARL / C4-HMARL-Det）
# 的 action 列是 **CAGE4 原生动作名**，未过统一 kill-chain 词表，与报告 §2 的断言冲突。
# 按批复 D2-(b) 的处置：**保留 `action` 原列**（不销毁证据），
# 新增 `action_unified` 列承载归一化结果；映射表显式发布于 `action_vocab.yaml`。
# 数值不受影响：dc/di/da 均基于资产值（generate_process2_json.py:384/413/442）。
_ACTION_VOCAB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "action_vocab.yaml")


def _load_action_aliases():
    """读取 action_vocab.yaml 的 aliases；文件缺失/不可解析时退化为恒等映射（不阻断评估）。"""
    try:
        import yaml
        with open(_ACTION_VOCAB_PATH, encoding="utf-8") as f:
            vocab = yaml.safe_load(f) or {}
        return {str(k): str(v) for k, v in (vocab.get("aliases") or {}).items()}
    except Exception:
        return {}


_ACTION_ALIASES = _load_action_aliases()
_ACTION_UNRESOLVED = set()


def unify_action(action):
    """原生动作名 → 统一 kill-chain 名；未登记的按恒等处理，并记入 _ACTION_UNRESOLVED。"""
    a = str(action)
    if a in _ACTION_ALIASES:
        return _ACTION_ALIASES[a]
    if a:
        _ACTION_UNRESOLVED.add(a)
    return a


def flatten_metrics(step_metrics):
    """
    将嵌套的 step_metrics 展平为规整的 dict 列表，方便绘图。
    处理复杂类型（dict 子指标）时提取数值字段。
    """
    rows = []
    for item in step_metrics:
        m = item["metrics"]
        row = {
            "step": item["step"],
            "action": item["action"],                              # 原生名（证据，保持不变）
            "action_unified": unify_action(item["action"]),         # v9.4 归一化视图
            "source": item["source"],
            "target": item["target"],
            # 简单数值
            "node_control_rate": m["node_control_rate"],
            "subnet_control_rate": m["subnet_control_rate"],
            "node_alive_detection_rate": m["node_alive_detection_rate"],
            "node_info_detection_rate": m["node_info_detection_rate"],
            "node_vulnerability_detection_rate": m["node_vulnerability_detection_rate"],
            "node_detect_rate": m["node_detect_rate"],
            "total_control_time": m["total_control_time"],
            "node_failure_rate": m["node_failure_rate"],
            "subnet_failure_rate": m["subnet_failure_rate"],
            "horizontal_control_range": m["horizontal_control_range"],
            "vertical_control_range": m["vertical_control_range"],
            "control_scope": m["control_scope"],
            "behavior_concealment": m["behavior_concealment"],
            "network_concealment": m["network_concealment"],
            # 复合 dict 提取
            "lateral_movement_ratio": m["lateral_movement_propagation"]["ratio"],
            "comprehensive_concealment_score": m["comprehensive_concealment"]["comprehensive_score"],
            "control_value_total": m["control_value"]["total_asset_value"],
            "control_value_controlled": m["control_value"]["controlled_asset_value"],
            "dc_score": m["confidentiality_damage"]["dc_score"],
            "di_score": m["integrity_damage"]["di_score"],
            "da_score": m["availability_damage"]["da_score"],
            "d_score": m["comprehensive_damage"]["d_score"],
        }
        rows.append(row)
    return rows


# ============================================================
#  图表生成函数  (9 组图表)
# ============================================================
def chart_node_control_rates(rows, output_dir, prefix):
    """图1：节点控制率 & 子网控制率 趋势"""
    if not HAS_MPL:
        return None
    steps = [r["step"] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(steps, [r["node_control_rate"] for r in rows],
            marker="o", markersize=3, color=COLOR_CYCLE[0], label="Node Control Rate φd")
    ax.plot(steps, [r["subnet_control_rate"] for r in rows],
            marker="s", markersize=3, color=COLOR_CYCLE[1], label="Subnet Control Rate φw")
    ax.set_xlabel("Step")
    ax.set_ylabel("Control Rate")
    ax.set_title("Node & Subnet Control Rate Trend")
    ax.legend()
    ax.set_ylim(-0.02, 1.05)
    path = os.path.join(output_dir, f"{prefix}_node_control_rate.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def chart_detection_rates(rows, output_dir, prefix):
    """图2：信息收集 — 三类探测率 + 综合探测率"""
    if not HAS_MPL:
        return None
    steps = [r["step"] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(steps, [r["node_alive_detection_rate"] for r in rows],
            marker=".", color=COLOR_CYCLE[0], label="Liveness Detection Rate")
    ax.plot(steps, [r["node_info_detection_rate"] for r in rows],
            marker=".", color=COLOR_CYCLE[1], label="Basic Info Detection Rate")
    ax.plot(steps, [r["node_vulnerability_detection_rate"] for r in rows],
            marker=".", color=COLOR_CYCLE[2], label="Vulnerability Detection Rate")
    ax.plot(steps, [r["node_detect_rate"] for r in rows],
            linestyle="--", color=COLOR_CYCLE[3], label="Comprehensive Detection Rate", linewidth=2.2)
    ax.set_xlabel("Step")
    ax.set_ylabel("Detection Rate")
    ax.set_title("Node Information Detection Trend")
    ax.legend(ncol=2)
    ax.set_ylim(-0.02, 1.05)
    path = os.path.join(output_dir, f"{prefix}_node_info_detection.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def chart_control_value(rows, output_dir, prefix):
    """图3：控制价值 — 被控资产 vs 总资产"""
    if not HAS_MPL:
        return None
    steps = [r["step"] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.fill_between(steps, [r["control_value_controlled"] for r in rows],
                    alpha=0.3, color=COLOR_CYCLE[0], label="Controlled Asset Value")
    ax.plot(steps, [r["control_value_total"] for r in rows],
            linestyle="--", color=COLOR_CYCLE[1], label="Total Asset Value", linewidth=2)
    ax.set_xlabel("Step")
    ax.set_ylabel("Asset Value")
    ax.set_title("Node Control Value Trend")
    ax.legend()
    path = os.path.join(output_dir, f"{prefix}_node_control_value.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def chart_control_time(rows, output_dir, prefix):
    """图4：总控制时间"""
    if not HAS_MPL:
        return None
    steps = [r["step"] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.fill_between(steps, [r["total_control_time"] for r in rows],
                    alpha=0.35, color=COLOR_CYCLE[2])
    ax.plot(steps, [r["total_control_time"] for r in rows],
            marker="o", markersize=3, color=COLOR_CYCLE[2])
    ax.set_xlabel("Step")
    ax.set_ylabel("Cumulative Steps")
    ax.set_title("Total Control Time Trend")
    path = os.path.join(output_dir, f"{prefix}_total_control_time.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def chart_control_scope(rows, output_dir, prefix):
    """图5：综合控制范围 S = s_h × s_v"""
    if not HAS_MPL:
        return None
    steps = [r["step"] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(steps, [r["horizontal_control_range"] for r in rows],
            marker=".", color=COLOR_CYCLE[0], label="Horizontal Scope s_h")
    ax.plot(steps, [r["vertical_control_range"] for r in rows],
            marker=".", color=COLOR_CYCLE[1], label="Vertical Scope s_v")
    ax.plot(steps, [r["control_scope"] for r in rows],
            linestyle="--", color=COLOR_CYCLE[2], label="Comprehensive Scope S", linewidth=2.2)
    ax.set_xlabel("Step")
    ax.set_ylabel("Scope")
    ax.set_title("Comprehensive Control Scope Trend")
    ax.legend()
    path = os.path.join(output_dir, f"{prefix}_control_scope.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def chart_lateral_movement(rows, output_dir, prefix):
    """图6：横向传播能力"""
    if not HAS_MPL:
        return None
    steps = [r["step"] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(steps, [r["lateral_movement_ratio"] for r in rows],
            marker="o", markersize=3, color=COLOR_CYCLE[1])
    ax.set_xlabel("Step")
    ax.set_ylabel("Alm / Nd")
    ax.set_title("Lateral Movement Capability Trend")
    ax.set_ylim(-0.02, None)
    path = os.path.join(output_dir, f"{prefix}_lateral_movement.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def chart_concealment(rows, output_dir, prefix):
    """图7：隐蔽能力（行为/网络/综合）"""
    if not HAS_MPL:
        return None
    steps = [r["step"] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(steps, [r["behavior_concealment"] for r in rows],
            marker=".", color=COLOR_CYCLE[0], label="Behavior Concealment H_bt")
    ax.plot(steps, [r["network_concealment"] for r in rows],
            marker=".", color=COLOR_CYCLE[1], label="Network Concealment H_nt")
    ax.plot(steps, [r["comprehensive_concealment_score"] for r in rows],
            linestyle="--", color=COLOR_CYCLE[2], label="Comprehensive Concealment H", linewidth=2.2)
    ax.set_xlabel("Step")
    ax.set_ylabel("Concealment")
    ax.set_title("Concealment Capability Trend")
    ax.legend()
    ax.set_ylim(-0.02, 1.05)
    path = os.path.join(output_dir, f"{prefix}_concealment.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def chart_damage(rows, output_dir, prefix):
    """图8：综合破坏能力 D（含 CIA 子贡献）"""
    if not HAS_MPL:
        return None
    steps = [r["step"] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(steps, [r["dc_score"] for r in rows],
            marker=".", color=COLOR_CYCLE[0], label="Confidentiality DC")
    ax.plot(steps, [r["di_score"] for r in rows],
            marker=".", color=COLOR_CYCLE[1], label="Integrity DI")
    ax.plot(steps, [r["da_score"] for r in rows],
            marker=".", color=COLOR_CYCLE[2], label="Availability DA")
    ax.plot(steps, [r["d_score"] for r in rows],
            linestyle="--", color=COLOR_CYCLE[3], label="Comprehensive Damage D", linewidth=2.2)
    ax.set_xlabel("Step")
    ax.set_ylabel("Damage Capability")
    ax.set_title("Comprehensive Damage Capability Trend")
    ax.legend(ncol=2)
    ax.set_ylim(-0.02, 1.05)
    path = os.path.join(output_dir, f"{prefix}_damage_capability.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def chart_action_distribution(step_metrics, output_dir, prefix):
    """图9：攻击类型分布（柱状图）"""
    if not HAS_MPL:
        return None
    from collections import Counter
    actions = [s["action"] for s in step_metrics]
    cnt = Counter(actions)
    labels = list(cnt.keys())
    values = list(cnt.values())
    colors = [COLOR_CYCLE[i % len(COLOR_CYCLE)] for i in range(len(labels))]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(labels, values, color=colors, edgecolor="white", linewidth=0.6)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + max(values) * 0.02,
                str(v), ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Count")
    ax.set_title("Attack Type Distribution")
    path = os.path.join(output_dir, f"{prefix}_attack_type_distribution.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def chart_failure_rates(rows, output_dir, prefix):
    """图10（补充）：节点失效率 & 子网失效率"""
    if not HAS_MPL:
        return None
    steps = [r["step"] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(steps, [r["node_failure_rate"] for r in rows],
            marker="o", markersize=3, color=COLOR_CYCLE[4], label="Node Failure Rate θd")
    ax.plot(steps, [r["subnet_failure_rate"] for r in rows],
            marker="s", markersize=3, color=COLOR_CYCLE[5], label="Subnet Failure Rate θw")
    ax.set_xlabel("Step")
    ax.set_ylabel("Failure Rate")
    ax.set_title("Node & Subnet Failure Rate Trend")
    ax.legend()
    ax.set_ylim(-0.02, 1.05)
    path = os.path.join(output_dir, f"{prefix}_failure_rate.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def generate_all_charts(step_metrics, output_dir, prefix="eval"):
    """
    生成全部评估图表，返回生成文件路径列表。
    """
    if not HAS_MPL:
        print("[!] matplotlib 未安装，跳过图表生成。请执行: pip install matplotlib")
        return []

    setup_matplotlib()
    rows = flatten_metrics(step_metrics)
    os.makedirs(output_dir, exist_ok=True)

    charts = [
        ("Node Control Rate",            chart_node_control_rates),
        ("Node Info Detection",          chart_detection_rates),
        ("Node Control Value",           chart_control_value),
        ("Total Control Time",           chart_control_time),
        ("Control Scope",                chart_control_scope),
        ("Lateral Movement",             chart_lateral_movement),
        ("Concealment Capability",       chart_concealment),
        ("Damage Capability",            chart_damage),
        ("Attack Type Distribution",     chart_action_distribution),
        ("Failure Rate",                 chart_failure_rates),
    ]

    generated = []
    for name, func in charts:
        try:
            if name == "Attack Type Distribution":
                path = func(step_metrics, output_dir, prefix)
            else:
                path = func(rows, output_dir, prefix)
            if path:
                generated.append(path)
        except Exception as e:
            print(f"[!] Chart [{name}] generation failed: {e}")

    return generated


# ============================================================
#  表格导出
# ============================================================
def export_metrics_csv(step_metrics, output_path):
    """
    将 step_metrics 导出为 CSV 表格（27 列：5 列元数据 + 22 列指标）。
    """
    if not step_metrics:
        return None
    rows = flatten_metrics(step_metrics)
    if not rows:
        return None

    fieldnames = list(rows[0].keys())
    # 2026-09-04: 改为无 BOM 的 utf-8（与 L3 全库清理后的语料一致，保证重跑逐字节可复现）
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


# ============================================================
#  核心评估流程
# ============================================================
def run_single_evaluation(yaml_path, csv_path, output_dir,
                          do_charts=True, verbose=True):
    """
    对单个 CSV 文件执行完整评估流程：

    1. 预处理 (pre_process)
    2. 生成攻击链表 (generate_process_linked_list)
    3. 计算每步指标 (calculate_step_metrics)
    4. 导出 CSV 表格
    5. 生成图表 PNG

    返回: dict {success, csv_file, total_steps, table_path, charts, elapsed}
    """
    start = time.time()

    # 校验输入
    if not os.path.exists(yaml_path):
        return {"success": False, "error": f"Topology file not found: {yaml_path}"}
    if not os.path.exists(csv_path):
        return {"success": False, "error": f"CSV file not found: {csv_path}"}

    csv_basename = os.path.splitext(os.path.basename(csv_path))[0]
    run_output_dir = os.path.join(output_dir, csv_basename)
    os.makedirs(run_output_dir, exist_ok=True)

    # 临时中间文件放在 output 目录下
    processed_file = os.path.join(run_output_dir, "_processed.json")
    linked_file = os.path.join(run_output_dir, "_process_linked_list.json")
    metrics_file = os.path.join(run_output_dir, "_process2.json")

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Evaluating: {os.path.basename(csv_path)}")
        print(f"{'='*60}")

    # -------- Step 1: 预处理 --------
    if verbose:
        print("[1/4] Data preprocessing ...", end=" ", flush=True)
    try:
        result = preprocess_data(yaml_path, csv_path, processed_file)
        if verbose:
            s = result["summary"]
            print(f"Done ({s['total_nodes']} nodes, {s['total_subnets']} subnets)")
    except Exception as e:
        return {"success": False, "error": f"Preprocessing failed: {e}"}

    # -------- Step 2: 攻击链表 --------
    if verbose:
        print("[2/4] Attack chain reconstruction ...", end=" ", flush=True)
    try:
        linked_result = generate_process_linked_list(csv_path, linked_file)
        if verbose:
            print(f"Done ({linked_result['total_steps']} steps)")
    except Exception as e:
        return {"success": False, "error": f"Attack chain reconstruction failed: {e}"}

    # -------- Step 3: 指标计算 --------
    if verbose:
        print("[3/4] Multi-dimension metric calculation ...", end=" ", flush=True)
    try:
        with open(processed_file, "r", encoding="utf-8") as f:
            processed_data = json.load(f)
        with open(linked_file, "r", encoding="utf-8") as f:
            linked_list_data = json.load(f)

        # v9.4 Step 2+3（C 路线）：若语料旁有诱饵清单，注入权威蜜罐集合（与名字解耦）
        # F3（CAGE4 修复）：schema-02 清单走**时相区间**，不进静态节点集合
        _honey_names, _honey_intervals, _label_src = _load_decoy_manifest(csv_path)
        set_authoritative_honey(_honey_names, _label_src)
        set_authoritative_honey_intervals(_honey_intervals, _label_src)

        metrics_results = calculate_step_metrics(processed_data, linked_list_data)

        # 溯源：记录标签来源与清单规模（写入 _process2.json 顶层，**不改 26/27 列指标表**）
        metrics_results['label_source'] = _label_src
        metrics_results['authoritative_honey_count'] = len(_honey_names)
        metrics_results['authoritative_decoy_interval_count'] = len(_honey_intervals)
        metrics_results['interval_source'] = get_interval_source()

        with open(metrics_file, "w", encoding="utf-8") as f:
            json.dump(metrics_results, f, ensure_ascii=False, indent=2)
        if verbose:
            print(f"Done ({metrics_results['total_steps']} steps)")
    except Exception as e:
        return {"success": False, "error": f"Metric calculation failed: {e}"}

    step_metrics = metrics_results.get("step_metrics", [])

    # -------- Step 4: 表格导出 --------
    if verbose:
        print("[4/4] Result output ...", end=" ", flush=True)
    table_path = export_metrics_csv(step_metrics,
                                     os.path.join(run_output_dir, "metrics_table.csv"))

    # -------- Step 5: 图表生成 --------
    charts = []
    if do_charts:
        charts = generate_all_charts(step_metrics, run_output_dir, prefix=csv_basename)
    if verbose:
        print(f"Done (CSV: {1 if table_path else 0}, Charts: {len(charts)})")

    elapsed = round(time.time() - start, 2)

    # 清理中间文件
    # WP2.2: 保留 _process2.json（含 confirmed_* 双口径 statistics），其余清理
    for tmp in [processed_file, linked_file]:
        try:
            os.remove(tmp)
        except Exception:
            pass

    return {
        "success": True,
        "csv_file": csv_basename,
        "total_steps": metrics_results.get("total_steps", 0),
        "table_path": table_path,
        "charts": charts,
        "elapsed": elapsed,
    }


# ============================================================
#  批量评估
# ============================================================
def run_batch_evaluation(yaml_path, csv_dir, output_dir,
                         do_charts=True, verbose=True):
    """
    批量评估 csv_dir 中所有 CSV 文件。
    返回汇总列表。
    """
    csv_files = sorted(
        f for f in os.listdir(csv_dir) if f.lower().endswith(".csv")
    )
    if not csv_files:
        print(f"[!] No CSV files found in directory {csv_dir}")
        return []

    print(f"\nFound {len(csv_files)} CSV file(s) to evaluate")
    print(f"Topology: {yaml_path}")
    print(f"Output:   {output_dir}\n")

    results = []
    for i, fname in enumerate(csv_files, 1):
        csv_path = os.path.join(csv_dir, fname)
        print(f"\n[{i}/{len(csv_files)}] ", end="")
        res = run_single_evaluation(yaml_path, csv_path, output_dir,
                                     do_charts=do_charts, verbose=verbose)
        results.append(res)
        if not res["success"]:
            print(f"  [✗] Failed: {res.get('error', 'Unknown error')}")
        else:
            print(f"  [✓] Done ({res['elapsed']}s, {res['total_steps']} steps)")

    return results


def print_batch_summary(results):
    """打印批量评估汇总报告。"""
    total = len(results)
    ok = sum(1 for r in results if r.get("success"))
    fail = total - ok
    total_steps = sum(r.get("total_steps", 0) for r in results if r.get("success"))
    total_time = sum(r.get("elapsed", 0) for r in results)

    print(f"\n{'='*60}")
    print(f"  Batch Evaluation Summary")
    print(f"{'='*60}")
    print(f"  Total: {total}  |  Success: {ok}  |  Failed: {fail}")
    print(f"  Total steps: {total_steps}  |  Total time: {total_time:.1f}s")
    if total > 0:
        print(f"  Avg time: {total_time / total:.1f}s/file")
    print(f"{'='*60}\n")

    if fail > 0:
        print("Failures:")
        for r in results:
            if not r.get("success"):
                print(f"  - {r.get('csv_file', '?')}: {r.get('error', 'Unknown')}")

    # 打印各文件最终指标汇总
    print("\nFinal Step Metrics Overview:")
    print(f"{'CSV File':<45} {'Steps':>5} {'CtrlRate':>8} {'Conceal':>8} {'Damage D':>8}")
    print("-" * 74)
    for r in results:
        if not r.get("success"):
            continue
        # 尝试读取最后一步的指标
        last_metrics = None
        csv_basename = r.get("csv_file", "")
        out_dir = os.path.join(
            os.path.dirname(r.get("table_path", "")) if r.get("table_path") else "",
        )
        metrics_file = os.path.join(out_dir, "_process2.json")
        # 已被清理，直接读 table
        table_path = r.get("table_path")
        if table_path and os.path.exists(table_path):
            with open(table_path, "r", encoding="utf-8-sig") as f:
                reader = list(csv.DictReader(f))
                if reader:
                    last = reader[-1]
                    print(
                        f"  {csv_basename:<43} "
                        f"{r['total_steps']:>5} "
                        f"{float(last.get('node_control_rate',0)):>8.4f} "
                        f"{float(last.get('comprehensive_concealment_score',0)):>8.4f} "
                        f"{float(last.get('d_score',0)):>8.4f}"
                    )

    print(f"\nResults saved to: {os.path.dirname(r.get('table_path','')) if ok else 'None'}")


# ============================================================
#  argparse 命令行入口
# ============================================================
def build_parser():
    parser = argparse.ArgumentParser(
        description="Network Security Threat Assessment System - CLI Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py -t 40-host-network.yaml -c data/episode_90_20260131_050414.csv
  python cli.py -t 40-host-network.yaml -d data/ -o result/batch/
  python cli.py -t 40-host-network.yaml -c data/episode_90.csv --no-charts
        """,
    )
    parser.add_argument(
        "-t", "--topology", required=True,
        help="网络拓扑 YAML 文件路径",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-c", "--csv",
        help="单个 CSV episode 文件路径（单文件模式）",
    )
    group.add_argument(
        "-d", "--csv-dir",
        help="CSV 文件所在目录（批量模式）",
    )
    parser.add_argument(
        "-o", "--output", default="result/",
        help="输出目录（默认: result/）",
    )
    parser.add_argument(
        "--no-charts", action="store_true",
        help="跳过图表生成，仅输出 CSV 表格",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="静默模式，减少输出",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # 检查 matplotlib
    if not args.no_charts and not HAS_MPL:
        print("[!] matplotlib 未安装，将跳过图表生成。")
        print("    安装: pip install matplotlib")
        args.no_charts = True

    verbose = not args.quiet
    yaml_path = args.topology
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    do_charts = not args.no_charts

    if args.csv:
        # ----- 单文件模式 -----
        csv_path = args.csv
        res = run_single_evaluation(yaml_path, csv_path, output_dir,
                                     do_charts=do_charts, verbose=verbose)
        if not res["success"]:
            print(f"\n[✗] Evaluation failed: {res.get('error')}")
            sys.exit(1)

        print(f"\n[✓] Evaluation complete!")
        print(f"    File: {res['csv_file']}")
        print(f"    Total steps: {res['total_steps']}")
        print(f"    Elapsed: {res['elapsed']}s")
        if res["table_path"]:
            print(f"    Table: {res['table_path']}")
        if res["charts"]:
            print(f"    Charts: {len(res['charts'])} file(s)")
            for c in res["charts"]:
                print(f"      - {os.path.basename(c)}")

    else:
        # ----- 批量模式 -----
        csv_dir = args.csv_dir
        results = run_batch_evaluation(yaml_path, csv_dir, output_dir,
                                        do_charts=do_charts, verbose=verbose)
        print_batch_summary(results)

        fail_count = sum(1 for r in results if not r.get("success"))
        if fail_count > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
