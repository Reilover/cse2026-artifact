# CAGE4 + CW 独立评估包

自包含：仅含 CAGE4 与 CW 两个环境的输入语料（含补充实验数据）、评估管线源码、结果与分析报告。

## 目录结构

```
├── README.md                          本文件
├── config_reference.md                全部简称与配置说明（仅 CW + CAGE4）
├── inputs/
│   ├── cw/                            CW 全部语料（eval + train + 补充实验 EXP-1/2）
│   │   ├── cw_art_eval_*.csv          ART 蓝方评估 rollout
│   │   ├── cw_r_eval_*.csv            RL 蓝方评估 rollout（含 EXP-1 采样复制）
│   │   ├── cw_r_train_B1var*.csv      EXP-2 B1 脚本 10 变体
│   │   ├── *.decoys.json              诱饵清单侧车（每个 CSV 配对）
│   │   └── topology_{10h,25h,50h}.yaml
│   └── cage4/                         CAGE4 全部语料（基线 3 单元 + 变体 4 单元 + EXP-3 补集）
│       ├── ep_cage4_{b_line,meander,sleep}_rl_train_ep00{1..3}.csv
│       ├── ep_cage4_{gnn_ppo,hmarl}[_det]_eval_ep00{1..3}.csv
│       ├── *.decoys.json              诱饵清单侧车
│       └── *.topology.yaml            逐集拓扑侧车
├── wxpgzs_src/                        评估管线源码（10 文件，直接可跑）
│   ├── cli.py                         入口
│   ├── pre_process.py                 预处理（含幻影过滤/诱饵剔除）
│   ├── generate_process_linked_list.py
│   ├── generate_process2_json.py      指标计算（21 项）
│   ├── action_vocab.yaml              动作词表
│   ├── success_semantics.yaml         每环境 success 读法
│   └── ...
├── results/
│   ├── cw_deep_dive/                  CW 深度分析产物
│   └── cage4_pipeline_fixed/          CAGE4 修复后逐集指标表（metrics_table.csv + _p.json）
├── report/
│   ├── phase5_report_cn_v9.md         分析报告（仅 CW + CAGE4）
│   └── phase5_report_cn_v9.html       HTML 版
└── topologies/
    ├── cw/                            CW 拓扑镜像
    └── cage4/                         CAGE4 拓扑镜像（含 C4-RS ep002/003 新侧车）
```

## 复现评估

所有命令在包根目录执行：

```bash
cd wxpgzs_src

# CAGE4 单集评估（以 C4-GNN ep001 为例）
python3 cli.py -t ../inputs/cage4/ep_cage4_gnn_ppo_eval_ep001.csv.topology.yaml \
               -c ../inputs/cage4/ep_cage4_gnn_ppo_eval_ep001.csv \
               -o ../result_test/

# CW 单集评估（以 ART 10host 为例）
python3 cli.py -t ../inputs/cw/topology_10h.yaml \
               -c ../inputs/cw/cw_art_eval_10host_sync0_s1.csv \
               -o ../result_test/

# 批量评估
bash run_eval.sh
```

产出：`result_test/<语料名>/metrics_table.csv` + `_process2.json`

## 补充实验说明

补充实验（EXP-1/2/3）的语料已**归并**到 `inputs/` 对应环境目录中：

| 实验 | 归并位置 | 语料模式 |
|---|---|---|
| EXP-1 RL 采样复制 | `inputs/cw/cw_r_eval_A_sampled_*` | 25host/sync1/100 步/5 集 |
| EXP-2 B1 分布扩展 | `inputs/cw/cw_r_train_B1var*` | 25host/sync1/10k 步/10 变体 |
| EXP-3 CAGE4 n=3 | `inputs/cage4/ep_cage4_*_ep00{2,3}.*` | 与 ep001 同配置，不同种子 |

分析结果见 `report/` §6.8。

## C4-RS 红方修复说明

C4-RS（sleep 语料）此前因 `RED_AGENT_MAP` 静默回退用了错误的红方（FSRA）。本轮已修复并用正确的 `RandomSelectRedAgent` 重导 3 集。包内 `inputs/cage4/ep_cage4_sleep_*` 为修复后的正确数据（详见报告附录 E #29）。

## 依赖

Python 3.8+，依赖包见 `wxpgzs_src/run_eval.sh` 头部注释。
