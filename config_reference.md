# CAGE4 + CW 配置与简称参考手册

> **用途**：解释本独立评估包中所有单元、变体、条件与简称的含义。
> **覆盖范围**：CW（24 单元）+ CAGE4（7 单元）= **31 单元**。
> **最后更新**：2026-09-20。

---

## 1. 两个环境一览

| 环境代号 | 全称 | 类型 | 红方 | 蓝方 | 单元数 |
|---|---|---|---|---|---|
| **CW** | CyberWheel | 蜜罐仿真（自研仓库） | RL / ART（脚本型） | RL（A/B1/B2 臂） | 24 |
| **CAGE4** | CAGE Challenge 4（CybORG Enterprise） | 企业网络仿真（CybORG 系） | FiniteStateRedAgent（脚本型） | GNN-PPO / HMARL ±Det / RL | 7 |

**合计 31 单元**。

---

## 2. CW 单元命名规则（24 单元）

### 2.1 命名公式

```
CW-{蓝方臂}{拓扑规模}{阶段后缀}
```

### 2.2 蓝方臂

| 臂 | 全称 | 含义 | 训练期诱饵 |
|---|---|---|---|
| **A** | ART | 脚本型蓝方，按阈值自动部署诱饵 | **可部署** |
| **B1** | RL + 基线奖励 | RL 蓝方，奖励 = `reward_decoy_hits`（上游原样） | 可部署 |
| **B2** | RL + 惩罚变体 | RL 蓝方，奖励 = `reward_decoy_hits_penalized`（命中诱饵额外 −10） | 可部署 |

### 2.3 拓扑规模

| 后缀 | 主机数 | 子网数 |
|---|---|---|
| `10host` | 10 | 5 |
| `25host` | 25 | 5+ |
| `50host` | 50 | 5+ |

### 2.4 阶段后缀

| 后缀 | 含义 | episode 数 |
|---|---|---:|
| （无）= eval | 评估 rollout | 45 |
| **RT** | RL Train（训练 rollout） | 300 |
| **AT** | ART Train | 50 |
| **CWX-RT** | RL Train **10×**（步长敏感性） | 10 |
| **CWX-AT** | ART Train **10×** | 5 |

---

## 3. CAGE4 单元命名规则（7 单元）

| 单元 | 蓝方 | 权重来源 | 部署诱饵/集 | Det 含义 |
|---|---|---|---|---|
| **C4-GNN** | GNN-PPO（采样） | cage-4-submission | ~50 主机 | — |
| **C4-GNN-Det** | GNN-PPO（确定性） | 同上 | 8~21 主机 | `set_deterministic(True)` |
| **C4-HMARL** | Hierarchical MARL（采样） | 同上 | ~50 主机 | — |
| **C4-HMARL-Det** | Hierarchical MARL（确定性） | 同上 | 8~21 主机 | 同上 |
| **C4-DF** | RL（自训） | cage4_rl_trainer | 0 主机 | 红方=B-Line 模式 |
| **C4-FS** | RL（自训） | 同上 | 0 主机 | 红方=Meander 模式 |
| **C4-RS** | RL（自训） | 同上 | ~2 主机 | 红方=RandomSelect 模式 |

**注意**：
* **GNN = GNN-PPO**（同权重，`gnn` 是导出脚本的简称）
* **C4-DF/FS/RS** 文件名中的 `b_line/meander/sleep` 指的是 **CAGE4 红方**行为模式（不是蓝方）
* **C4-RS** 历史上曾因配置错误使用 FSRA 红方，2026-09-18 已修复并重导 3 集（详见报告附录 E #29）

---

## 4. 实验条件简称

### 4.1 同步开关（CW）

| 条件 | 含义 |
|---|---|
| `sync0` | `CYBERWHEEL_SYNC_RED_TARGETS=0`：红方目标不同步到蓝方 |
| `sync1` | `CYBERWHEEL_SYNC_RED_TARGETS=1`：红方目标同步到蓝方 |

脚本型红方（ART）不受此开关影响。

### 4.2 配对实验条件（CAGE4）

| 条件 | 含义 |
|---|---|
| **ON** | 蓝方诱饵部署正常 |
| **OFF** | 蓝方诱饵部署被改写为空动作 |

### 4.3 阶段

| 术语 | 含义 |
|---|---|
| **train** | RL/ART 蓝方训练期的 rollout |
| **eval** | 训练完成后的评估 rollout |
| **10×** | episode 长度 ×10 |

---

## 5. 指标简称

| 简称 | 全称 | 含义 |
|---|---|---|
| **D** | D-Score | 0.35×DC + 0.35×DI + 0.30×DA |
| **DC** | Damage-Capability | 红方已"发现"的资产价值占比 |
| **DI** | Damage-Integrity | 红方已"控制"的资产价值占比 |
| **DA** | Damage-Availability | 红方已"破坏/失效"的资产价值占比 |
| **ctrl** | node_control_rate | 红方控制的节点占比 |
| **det** | node_detect_rate | 红方发现的节点占比 |
| **H** | comprehensive_concealment_score | 红方综合隐蔽性 |
| **Plm** | lateral_movement_ratio | 红方横向移动比率 |

---

## 6. 本包内关键文件

| 文件/目录 | 作用 |
|---|---|
| `inputs/cw/` | CW 评估语料（eval + train + 补充实验 EXP-1/2） |
| `inputs/cage4/` | CAGE4 评估语料（基线 + 变体 + EXP-3 补集） |
| `inputs/cw/topology_*.yaml` | CW 三种拓扑定义 |
| `inputs/cage4/*.topology.yaml` | CAGE4 逐集拓扑侧车 |
| `inputs/**/*.decoys.json` | 诱饵清单侧车（schema `cw-decoy-manifest-01`） |
| `wxpgzs_src/cli.py` | 评估管线入口 |
| `wxpgzs_src/pre_process.py` | 预处理（含幻影过滤 + 诱饵剔除） |
| `wxpgzs_src/generate_process2_json.py` | 指标计算（21 项） |
| `wxpgzs_src/action_vocab.yaml` | 统一动作词表 |
| `wxpgzs_src/success_semantics.yaml` | 每环境 success 字段读法 |
| `results/cw_deep_dive/` | CW 深度分析产物 |
| `results/cage4_pipeline_fixed/` | CAGE4 逐集指标表 |
| `report/phase5_report_cn_v9.md` | 分析报告（仅 CW + CAGE4） |
| `topologies/` | 拓扑镜像 |

---

## 7. 评估管线源码说明

| 文件 | 作用 |
|---|---|
| `cli.py` | 入口：`python3 cli.py -t <topology> -c <corpus.csv> -o <outdir>` |
| `pre_process.py` | 语料解析 → 节点集构建（含幻影过滤 + 诱饵剔除）→ summary |
| `generate_process_linked_list.py` | 动作链表构建（含列格式兼容） |
| `generate_process2_json.py` | 21 项指标计算（诱饵从控制/损伤分子分母剔除） |
| `action_vocab.yaml` | 红方动作名统一词表 |
| `success_semantics.yaml` | 每环境 `success` 字段的读法规则 |
| `rerun_eval_v9.py` | 批量评估驱动（含拓扑绑定规则） |
| `run_eval.sh` | 批量评估 shell 脚本 |
