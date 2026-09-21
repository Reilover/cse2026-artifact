#!/usr/bin/env bash
# 用 wxpgzs cli.py 评估交叉臂全部语料 → cross_arm/metrics/<stem>/metrics_table.csv
set -u
ROOT=/home/xxl/MyExperiments/E4ACD
PY=python3
WXP=$ROOT/wxpgzs
TOPO=$ROOT/phase5_package_v9_5/inputs/cw/topology_25h.yaml
CROSS=$ROOT/data/cw_supplement/cross_arm
export PYTHONPATH="$WXP:${PYTHONPATH:-}"
mkdir -p "$CROSS/metrics"

CSVS=$(ls "$CROSS"/corpus/cw_r_cross_*.csv 2>/dev/null | grep -v decoys)
echo "共 $(echo "$CSVS" | wc -l) 份语料"
rc=0
for c in $CSVS; do
  stem=$(basename "$c" .csv)
  [ -f "$CROSS/metrics/$stem/metrics_table.csv" ] && { echo "SKIP $stem"; continue; }
  if ( cd "$WXP" && $PY cli.py -t "$TOPO" -c "$c" -o "$CROSS/metrics" -q --no-charts ) \
      > "$CROSS/metrics/$stem.pipeline.log" 2>&1; then
    echo "OK   $stem"
  else
    echo "FAIL $stem（见 metrics/$stem.pipeline.log）"; rc=1
  fi
done
echo "评估完成 $(date -Is)"
exit $rc
