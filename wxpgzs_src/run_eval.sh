#!/bin/bash
# ============================================================
# Network Security Threat Assessment System - batch evaluation
# Usage: bash run_eval.sh   (from wxpgzs_src/)
# Evaluates the corpora under ../inputs per the topology-binding
# rules in rerun_eval_v9.py; outputs to ../result_test/.
# ============================================================
# (原始中文说明保留如下 / original Chinese notes below)
# ============================================================
#  网络安全威胁评估系统 - Linux/macOS 批量评估启动脚本
#
#  用法:
#    bash run_eval.sh
#    bash run_eval.sh -t mytopo.yaml -d mydata/ -o myresult/
#    bash run_eval.sh --no-charts
# ============================================================

set -e

# 切换到脚本所在目录
cd "$(dirname "$0")"

# ---------- 默认参数 ----------
TOPOLOGY="40-host-network.yaml"
DATA_DIR="demo/data"          # 原工具演示数据（评估用 data 由 rerun_eval_v9.py 指定）
OUTPUT_DIR="result"
EXTRA_ARGS=""

# ---------- 解析命令行参数 ----------
while [[ $# -gt 0 ]]; do
    case "$1" in
        -t|--topology)
            TOPOLOGY="$2"; shift 2 ;;
        -d|--data-dir)
            DATA_DIR="$2"; shift 2 ;;
        -o|--output)
            OUTPUT_DIR="$2"; shift 2 ;;
        --no-charts)
            EXTRA_ARGS="$EXTRA_ARGS --no-charts"; shift ;;
        -q)
            EXTRA_ARGS="$EXTRA_ARGS -q"; shift ;;
        -h|--help)
            echo ""
            echo "网络安全威胁评估系统 - 批量评估脚本"
            echo ""
            echo "用法: bash run_eval.sh [选项]"
            echo ""
            echo "选项:"
            echo "  -t, --topology FILE    指定拓扑YAML文件 (默认: 40-host-network.yaml)"
            echo "  -d, --data-dir DIR     指定CSV数据目录  (默认: data/)"
            echo "  -o, --output DIR       指定输出目录     (默认: result/)"
            echo "  --no-charts            跳过图表生成"
            echo "  -q                     静默模式"
            echo "  -h, --help             显示帮助"
            echo ""
            echo "示例:"
            echo "  bash run_eval.sh"
            echo "  bash run_eval.sh -t mytopo.yaml -d mydata/ -o myresult/"
            echo "  bash run_eval.sh --no-charts"
            echo ""
            exit 0 ;;
        *)
            echo "[警告] 未知参数: $1"; shift ;;
    esac
done

# ---------- 检查 Python ----------
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "[错误] 未找到 Python，请确认已安装 Python 3.9+"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)

# ---------- 检查依赖 ----------
if ! $PYTHON -c "import flask; import yaml" &>/dev/null; then
    echo "[提示] 正在安装必要依赖..."
    $PYTHON -m pip install -r demo/link/requirements.txt
fi

# ---------- 检查 matplotlib ----------
if ! $PYTHON -c "import matplotlib" &>/dev/null; then
    if [[ "$EXTRA_ARGS" != *"--no-charts"* ]]; then
        echo "[提示] matplotlib 未安装，图表功能不可用。"
        echo "       如需图表：pip install matplotlib"
        echo "       本次将自动跳过图表生成。"
        EXTRA_ARGS="$EXTRA_ARGS --no-charts"
    fi
fi

# ---------- 显示配置 ----------
echo ""
echo "============================================================"
echo "  网络安全威胁评估系统 - 批量评估"
echo "============================================================"
echo "  拓扑文件:   $TOPOLOGY"
echo "  数据目录:   $DATA_DIR"
echo "  输出目录:   $OUTPUT_DIR"
echo "  额外参数:   $EXTRA_ARGS"
echo "============================================================"
echo ""

# ---------- 执行 ----------
$PYTHON cli.py -t "$TOPOLOGY" -d "$DATA_DIR" -o "$OUTPUT_DIR" $EXTRA_ARGS

echo ""
echo "[完成] 所有评估已结束。"
echo "结果保存在: $OUTPUT_DIR"
echo ""
