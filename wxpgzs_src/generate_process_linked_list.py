import csv
import json
import os

import yaml

# ── F1 修复（CAGE4 评估链路，见 v9_4/cage4_honeypot_fix_plan.md §4.1 F1）────────
# 原实现手写 _ACTION_NORMALIZE，键是"驼峰类名 lower"（无下划线），而
# cage4_variant_export.py:58-61 to_snake() 产出的是 snake_case（exploit_remote_service）
# → 全部未命中 → 12 个第三方 CAGE4 变体集 87–97% 的红方动作对指标不可见（DC≡0、DI≡DA）。
#
# 现改为**加载权威词表** wxpgzs/action_vocab.yaml（由 episode_adapter.py 派生），
# 并做大小写不敏感查找。已逐键核对：原 8 个键在 aliases 中均存在且映射目标相同
# → 严格超集，非 CAGE4 环境的行为不变（identity 映射除外，见 data/cage4_fix/REPORT.md §F1）。
_VOCAB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'action_vocab.yaml')
try:
    with open(_VOCAB_PATH, encoding='utf-8') as _f:
        _VOCAB = yaml.safe_load(_f) or {}
except Exception as _e:  # 词表缺失不得中断管线：回退到原手写表
    print(f"[action-vocab] 加载失败，回退内嵌映射: {_e}")
    _VOCAB = {}
_ACTION_NORMALIZE = {str(k).lower(): str(v) for k, v in (_VOCAB.get('aliases') or {}).items()}
if not _ACTION_NORMALIZE:
    _ACTION_NORMALIZE = {
        'discoverremotesystems': 'pingsweep',
        'discovernetworkservices': 'portscan',
        'privilegeescalate': 'privilege-escalation',
        'exploitremoteservice': 'exploit',
        'discoverdeception': 'discovery',
        'aggressiveservicediscovery': 'portscan',
        'stealthservicediscovery': 'discovery',
        'degradeservices': 'impact',
    }
# 指标分派（generate_process2_json.py:836-907）认识的动作名；其余名称对 DC/DI/DA
# 零贡献、只进 total_attacks。用于 M2 统计口径与自检。
_METRIC_DISPATCH_ACTIONS = {
    'pingsweep', 'portscan', 'discovery', 'lateral-movement', 'exploit',
    'privilege-escalation', 'impact',
}


def normalize_action_name(name):
    """把环境原生动作名归一为 wxpgzs 统一 kill-chain 名（大小写不敏感）。"""
    if name is None:
        return ''
    raw = str(name).strip()
    return _ACTION_NORMALIZE.get(raw.lower(), raw)


def generate_process_linked_list(csv_file_path, output_file_path):
    """
    生成红方攻击过程的链表表示
    
    参数:
        csv_file_path (str): CSV文件路径
        output_file_path (str): 输出JSON文件路径
    """
    # 读取CSV文件并提取红方操作
    red_operations = []
    
    with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        fieldnames = reader.fieldnames or []
        
        # Detect column naming convention:
        # Old format: red_action, red_action_src, red_action_dst, red_action_success
        # New CW format: red_act, red_action_src, red_dst, red_success
        col_action = ('red_act' if 'red_act' in fieldnames
                      else ('red_action_name' if 'red_action_name' in fieldnames else 'red_action'))
        col_src = 'red_action_src' if 'red_action_src' in fieldnames else 'red_src'
        col_dst = 'red_dst' if 'red_dst' in fieldnames else ('red_action_dst' if 'red_action_dst' in fieldnames else 'red_action_dest')
        col_success = 'red_success' if 'red_success' in fieldnames else 'red_action_success'
        
        for row in reader:
            step = int(row['step'])
            red_action = row[col_action]
            red_src = row.get(col_src, '')
            red_dst = row.get(col_dst, '')

            # S0 修复: 规范化非标准动作名 → F1 修复: 改为复用权威词表
            # wxpgzs/action_vocab.yaml 的 aliases（大小写/下划线不敏感）。
            red_action = normalize_action_name(red_action)

            # F8 修复: 移除 red_action_success 过滤器。
            # 各环境 success 语义不统一（TRUE 比例 12.5%~100%），
            # 过滤导致不同环境在不可比的子集上计算指标。
            # 现改为：所有非 sleep 的红方动作均进入攻击链表。
            # 仅过滤 sleep（非实质性动作），不按 success 过滤。
            # WP2.1: success 透传（TRUE/FALSE/UNKNOWN），供 confirmed_* 双口径指标使用
            raw_succ = row.get(col_success, '') or ''
            succ_norm = str(raw_succ).strip().upper()
            if succ_norm not in ('TRUE', 'FALSE'):
                succ_norm = 'UNKNOWN' if succ_norm else 'UNKNOWN'
            if red_action and red_action.lower() != 'sleep':
                red_operations.append({
                    'step': step,
                    'action': red_action,
                    'source': red_src,
                    'target': red_dst,
                    'success': succ_norm,
                    'operation_type': 'discovery' if red_action in ['pingsweep', 'portscan', 'discovery'] else 'movement'
                })
    
    # Build linked list as a flat list (avoid deep nesting for JSON serialization)
    linked_list = []
    for op in red_operations:
        linked_list.append({
            'step': op['step'],
            'action': op['action'],
            'source': op['source'],
            'target': op['target'],
            'success': op.get('success', 'UNKNOWN'),
            'operation_type': op['operation_type'],
        })
    
    # Build detailed process description
    process_description = []
    for op in red_operations:
        description = {
            'step': op['step'],
            'action': op['action'],
            'source': op['source'],
            'target': op['target'],
            'success': op.get('success', 'UNKNOWN'),
            'description': f"Step {op['step']}: {op['source']} via {op['action']} -> {op['target']} [{op.get('success', 'UNKNOWN')}]"
        }
        process_description.append(description)
    
    # 统计操作类型
    action_counts = {}
    for op in red_operations:
        action_counts[op['action']] = action_counts.get(op['action'], 0) + 1
    
    # 构建结果数据
    result = {
        'total_steps': len(red_operations),
        'action_counts': action_counts,
        'process_description': process_description,
        'linked_list': linked_list
    }
    
    # 保存结果
    with open(output_file_path, 'w', encoding='utf-8') as jsonfile:
        json.dump(result, jsonfile, ensure_ascii=False, indent=2)
    
    print(f"Linked list generated, saved to {output_file_path}")
    print(f"Total steps: {len(red_operations)}")
    print(f"Action type stats: {action_counts}")
    
    return result

if __name__ == "__main__":
    csv_file = "demo/data/episode_90_20260131_050414.csv"   # v9.3：演示资产移入 demo/
    output_file = "data/process_linked_list.json"
    generate_process_linked_list(csv_file, output_file)
