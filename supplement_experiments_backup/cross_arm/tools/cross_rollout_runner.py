#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CW 交叉臂（cross-arm）rollout runner。

3×3 矩阵：红方 checkpoint ∈ {A, B1, B2} × 蓝方 checkpoint ∈ {A, B1, B2}。
复用 data/cw_supplement/tools/cw_rollout_runner.py 的 EXP-1 模式（逐行复刻
rl_evaluator.evaluate() 主循环，但 CSV / 诱饵清单直接写到 cross_arm/corpus/，
不写 external_envs 包内 action_logs）。

每个进程跑 1 集 × 100 步，独立 --seed（configure_evaluation 里 set_seed），
与 EXP-1「每集不同种子」口径一致；5 集 = 种子 101..105。

用法：
  python3 cross_rollout_runner.py --red-arm A --blue-arm B1 --seed 101 \
      [--num-steps 100]
输出（OUTDIR 默认 data/cw_supplement/cross_arm/corpus/）：
  cw_r_cross_red{X}_blue{Y}_25host_s1_sync1_s{seed}.csv
  cw_r_cross_red{X}_blue{Y}_25host_s1_sync1_s{seed}.csv.decoys.json
  cw_r_cross_red{X}_blue{Y}_25host_s1_sync1_s{seed}.csv.run.json
"""
import argparse
import csv
import json
import os
import sys
import time
from types import SimpleNamespace

PROJ = os.environ.get("E4ACD_ROOT", "/home/xxl/MyExperiments/E4ACD")
CW_DIR = os.path.join(PROJ, "external_envs", "cyberwheel")
PKG_CFG = os.path.join(CW_DIR, "cyberwheel", "data", "configs", "environment")
BASE_CFG = os.path.join(PKG_CFG, "_v94_eval_B1_25host_s1.yaml")  # A/B1/B2 三份仅差 experiment_name/graph_name

# ── 先解析 CLI，再设置环境变量，最后才 import cyberwheel ─────────────────────────
# （red_sync.SYNC_RED_TARGETS 在 import 时读环境变量）
p = argparse.ArgumentParser()
p.add_argument("--red-arm", choices=["A", "B1", "B2"], required=True)
p.add_argument("--blue-arm", choices=["A", "B1", "B2"], required=True)
p.add_argument("--seed", type=int, required=True)
p.add_argument("--num-steps", type=int, default=100)
p.add_argument("--outdir", default=os.path.join(PROJ, "data", "cw_supplement", "cross_arm", "corpus"))
ARGS = p.parse_args()

os.environ["CYBERWHEEL_SYNC_RED_TARGETS"] = "1"     # sync1 口径
os.environ["CYBERWHEEL_DETERMINISTIC"] = "true"     # 同既有 eval 口径

OUTDIR = os.path.abspath(ARGS.outdir)
os.makedirs(OUTDIR, exist_ok=True)
STEM = f"cw_r_cross_red{ARGS.red_arm}_blue{ARGS.blue_arm}_25host_s1_sync1_s{ARGS.seed}"
OUT_CSV = os.path.join(OUTDIR, STEM + ".csv")

sys.path.insert(0, CW_DIR)

import torch  # noqa: E402
import yaml  # noqa: E402

from cyberwheel.runners.rl_evaluator import RLEvaluator  # noqa: E402
from cyberwheel.utils.red_sync import sync_red_targets  # noqa: E402


def build_args():
    """沿用 v9.4 eval 配置，仅换 experiment_name（→ 混合模型目录）/ graph_name / seed / 集数。"""
    with open(BASE_CFG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["experiment_name"] = f"V94_Cross_red{ARGS.red_arm}_blue{ARGS.blue_arm}"
    cfg["graph_name"] = f"V94Cross_red{ARGS.red_arm}_blue{ARGS.blue_arm}_s{ARGS.seed}"
    cfg["seed"] = ARGS.seed
    cfg["num_episodes"] = 1
    cfg["num_steps"] = ARGS.num_steps
    return SimpleNamespace(**cfg)


def fmt_num(v):
    """整数值的 float 去掉 .0（与既有语料观感一致）。"""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def run_episode(ev):
    """主循环：逐行复刻 rl_evaluator.evaluate()，仅替换日志落点与清单落点。"""
    num_steps = ev.args.num_steps
    obs, _ = ev.env.reset()
    # evaluate() 循环前的初始化（原版在 evaluate() 开头做，这里等价补齐）
    ev.action_mask = {
        a: torch.zeros(ev.agents[a]["max_action_space_size"], dtype=torch.bool).to(ev.device)
        for a in ev.agents}
    ev.rewards = {a: [0] for a in ev.agents}
    ev.total_reward = 0
    episode_decoys = {}
    decoy_err = None
    red_hit_steps = 0  # 红方动作命中诱饵的步数（any-target，供 run.json 快查）
    t0 = time.time()
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["episode", "step", "reward", "red_action_name",
                    "red_action_success", "red_action_src", "red_action_dest",
                    "red_reward", "blue_action_name", "blue_action_success",
                    "blue_action_src", "blue_action_dest", "blue_reward"])

        for step in range(num_steps):
            actions = {}
            # v9.4 C 路线：掩码计算**之前**同步红方动作空间（与包内 evaluate 一致）
            if sync_red_targets(ev.env):
                ev._sync_total = getattr(ev, "_sync_total", 0) + 1
            action_masks = ev.env.action_mask

            for agent in ev.agents:
                agent_obs = torch.Tensor(obs[agent]).to(ev.device)
                mask = ev.mask_actions(action_masks[agent], ev.action_mask[agent])
                ev.action_mask[agent] = mask
                action, _, _, _ = ev.policy[agent].get_action_and_value(
                    agent_obs, action_mask=mask)
                actions[agent] = action

            obs, rew, done, _, info = ev.env.step(actions)

            # 诱饵并集（与 evaluator._accumulate_decoys 同口径：含随后被 remove 的）
            try:
                decoys = getattr(getattr(ev.env, "network", None), "decoys", {}) or {}
                for name, host in list(decoys.items()):
                    if name not in episode_decoys:
                        subnet = getattr(getattr(host, "subnet", None), "name", "") or ""
                        episode_decoys[name] = {
                            "name": name, "subnet": subnet, "first_seen_step": step}
            except Exception as e:  # pragma: no cover
                decoy_err = f"read network.decoys failed: {e}"

            if info.get("red_action_dst", "") in episode_decoys:
                red_hit_steps += 1

            w.writerow([
                0, step, fmt_num(rew),
                info.get("red_action", ""), info.get("red_action_success", False),
                info.get("red_action_src", ""), info.get("red_action_dst", ""),
                fmt_num(info.get("red_reward", 0)),
                info.get("blue_action", ""), info.get("blue_action_success", False),
                info.get("blue_action_src", ""), info.get("blue_action_dst", ""),
                fmt_num(info.get("blue_reward", 0)),
            ])
    wall = time.time() - t0
    return episode_decoys, decoy_err, red_hit_steps, wall


def main():
    args = build_args()
    print(f"[cross] red={ARGS.red_arm} blue={ARGS.blue_arm} seed={ARGS.seed} "
          f"steps={ARGS.num_steps} sync=1 exp={args.experiment_name}", flush=True)
    t0 = time.time()
    ev = RLEvaluator(args)
    ev.configure_evaluation()
    ev.load_models()
    print(f"[cross] env+models ready in {time.time()-t0:.1f}s "
          f"(agents={list(ev.agents)}, red_rl={args.agent_config['red']['rl']})", flush=True)

    episode_decoys, decoy_err, red_hit_steps, wall = run_episode(ev)

    # 诱饵清单（与 cw_rollout_runner.write_manifest 同 schema）
    man = {
        "schema": "cw-decoy-manifest-01",
        "source": {
            "network": "25-host-network.yaml",
            "graph_name": args.graph_name,
            "sync_red_targets": True,
            "num_episodes": 1,
            "seed": ARGS.seed,
            "num_steps": ARGS.num_steps,
            "red_checkpoint": f"V94_Retrain{ARGS.red_arm}_25host_s1/red_agent.pt",
            "blue_checkpoint": f"V94_Retrain{ARGS.blue_arm}_25host_s1/blue_agent.pt",
            "checkpoint_experiment": args.experiment_name,
            "runner": "data/cw_supplement/cross_arm/tools/cross_rollout_runner.py",
        },
        "episodes": {"0": {"count": len(episode_decoys),
                           "decoys": list(episode_decoys.values())}},
    }
    if decoy_err:
        man["episodes"]["0"]["error"] = decoy_err
    man_path = OUT_CSV + ".decoys.json"
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=2, ensure_ascii=False)

    summary = {
        "red_arm": ARGS.red_arm, "blue_arm": ARGS.blue_arm,
        "csv": OUT_CSV, "seed": ARGS.seed,
        "num_steps": ARGS.num_steps, "sync_red_targets": True,
        "wall_sec": round(wall, 1),
        "decoy_unique": len(episode_decoys),
        "red_hit_steps_inproc": red_hit_steps,
    }
    with open(OUT_CSV + ".run.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"[cross] DONE {os.path.basename(OUT_CSV)} decoys={len(episode_decoys)} "
          f"red_hit_steps={red_hit_steps} wall={wall:.1f}s", flush=True)


if __name__ == "__main__":
    main()
