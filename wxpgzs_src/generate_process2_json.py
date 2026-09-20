import json
import re

HONEY_PATTERN = re.compile(r'^[a-f0-9]{32}$', re.IGNORECASE)
DECOY_PATTERN = re.compile(r'^decoy_\d+$', re.IGNORECASE)  # F3.2: CW deterministic decoy naming

# 1. 面向威胁效果的评估指标：
# 1.1 服务利用效果指标
# 1.1.1 节点控制率
def calculate_node_control_rate(total_nodes, controlled_nodes):
    """
    计算节点控制率

    参数:
        total_nodes (int): 总节点数 Nd（不包括蜜罐节点）
        controlled_nodes (int): 被攻击者控制的节点数 Hd（不包括蜜罐节点）

    返回:
        float: 节点控制率 φd = Hd / Nd
    """
    if total_nodes == 0:
        return 0.0
    return controlled_nodes / total_nodes

# 1.1.2 子网控制率
def calculate_subnet_control_rate(total_subnets, controlled_subnets):
    """
    计算子网控制率
    
    参数:
        total_subnets (int): 总子网数 Nw
        controlled_subnets (int): 被攻击者控制的子网数 Hw
    
    返回:
        float: 子网控制率 φw = Hw / Nw
    """
    if total_subnets == 0:
        return 0.0
    return controlled_subnets / total_subnets

# 1.1.3 控制价值
def calculate_control_value(asset_values, controlled_nodes):
    """
    计算控制价值

    计算方法:
        计算被控制节点的资产价值总和与全部节点资产价值总和之比。
        该比值反映了攻击者控制资产相对于总资产的重要性程度。
        当controlled_nodes为空或asset_values为空时，返回0.0。

    参数:
        asset_values (dict): 各节点的资产价值字典，
                            格式：{'node_name': value_level, ...}
                            资产价值等级 value_level (int)：1、3、5
                              1 - 较低价值（workstation）
                              3 - 中等价值（web_server、mail_server、ssh_jump_server、proxy_server）
                              5 - 较高价值（data_server、file_server）

        controlled_nodes (set 或 list): 被攻击者控制的节点名称集合

    返回:
        dict: 包含以下键值对的字典：
            - 'total_asset_value' (int): 全部资产价值总和
            - 'controlled_asset_value' (int): 被控制资产价值总和
            - 'assessment' (str): 定性评估结果
    """
    if not asset_values:
        return {
            'total_asset_value': 0,
            'controlled_asset_value': 0,
            'assessment': '无资产'
        }

    total_value = sum(asset_values.values())
    if total_value == 0:
        return {
            'total_asset_value': 0,
            'controlled_asset_value': 0,
            'assessment': '无价值'
        }

    controlled_value = sum(
        asset_values.get(node, 0) for node in controlled_nodes
    )

    ratio = controlled_value / total_value

    if ratio >= 0.8:
        assessment = '极高'
    elif ratio >= 0.6:
        assessment = '高'
    elif ratio >= 0.4:
        assessment = '中等'
    elif ratio >= 0.2:
        assessment = '低'
    else:
        assessment = '极低'

    return {
        'total_asset_value': total_value,
        'controlled_asset_value': controlled_value,
        'assessment': assessment
    }

# 1.2 信息收集效果
# 1.2.1 节点存活状态探测率
def calculate_node_alive_detection_rate(total_nodes, alive_detected_nodes):
    """
    计算节点存活状态探测率

    描述：
        pingsweep动作成功时，该节点存活被攻击者探测到。
        分母和分子均不包括蜜罐节点（honey）。

    参数:
        total_nodes (int): 总节点数 Nd（不包括蜜罐节点）
        alive_detected_nodes (int): 被攻击者探测到的存活节点数 Od（不包括蜜罐节点）

    返回:
        float: 节点存活状态探测率 χd = Od / Nd
    """
    if total_nodes == 0:
        return 0.0
    return alive_detected_nodes / total_nodes

# 1.2.2 节点基本信息探测率
def calculate_node_info_detection_rate(total_nodes, info_detected_nodes):
    """
    计算节点基本信息探测率

    描述：
        portscan动作成功时，该节点基本信息被攻击者探测到。
        分母和分子均不包括蜜罐节点（honey）。

    参数:
        total_nodes (int): 总节点数 Nd（不包括蜜罐节点）
        info_detected_nodes (int): 被攻击者探测到基本信息的节点数 Pd（不包括蜜罐节点）

    返回:
        float: 节点基本信息探测率 = Pd / Nd
    """
    if total_nodes == 0:
        return 0.0
    return info_detected_nodes / total_nodes

# 1.2.3 节点脆弱性信息探测率
def calculate_node_vulnerability_detection_rate(total_nodes, vulnerability_detected_nodes):
    """
    计算节点脆弱性信息探测率

    描述：
        discovery动作成功时，该节点脆弱性信息被攻击者探测到。
        分母和分子均不包括蜜罐节点（honey）。

    参数:
        total_nodes (int): 总节点数 Nd（不包括蜜罐节点）
        vulnerability_detected_nodes (int): 被攻击者探测到脆弱性信息的节点数 Rd（不包括蜜罐节点）

    返回:
        float: 节点脆弱性信息探测率 = Rd / Nd
    """
    if total_nodes == 0:
        return 0.0
    return vulnerability_detected_nodes / total_nodes

# 1.3 拒绝服务效果
# 1.3.1 节点失效率
def calculate_node_failure_rate(total_nodes, failed_nodes):
    """
    计算节点失效率

    描述：
        impact动作成功时，该节点因攻击而失效。
        分母和分子均不包括蜜罐节点（honey）。

    计算方法:
        按照公式 θd = Md / Nd 计算，即失效节点数除以总节点数。
        当总节点数为0时，返回0.0以避免除零错误。

    参数:
        total_nodes (int): 总节点数 Nd（不包括蜜罐节点）
        failed_nodes (int): 因攻击而失效无法正常工作的节点数 Md（不包括蜜罐节点）

    返回:
        float: 节点失效率 θd，取值范围：[0.0, 1.0]
    """
    if total_nodes == 0:
        return 0.0
    return failed_nodes / total_nodes


# 1.3.2 子网失效率
def calculate_subnet_failure_rate(total_subnets, failed_subnets):
    """
    计算子网失效率（网络失效率）

    描述：
        如果某个子网中所有节点（不包括蜜罐节点）都因攻击者成功执行impact动作而失效，
        则该子网被攻击者攻击并失效。

    计算方法:
        按照公式 θw = Mw / Nw 计算，即失效子网数除以总子网数。
        当总子网数为0时，返回0.0以避免除零错误。

    参数:
        total_subnets (int): 总子网数 Nw，取值范围：Nw >= 0
        failed_subnets (int): 因攻击而无法正常提供服务的子网数 Mw

    返回:
        float: 子网失效率 θw，取值范围：[0.0, 1.0]
    """
    if total_subnets == 0:
        return 0.0
    return failed_subnets / total_subnets


# 2. 基于威胁能力的指标函数
# 2.1 控制能力
# 2.1.1 控制范围
def calculate_horizontal_control_range(adjacency_matrix, controlled_nodes):
    """
    计算横向控制范围 s_h

    计算方法:
        基于网络拓扑的邻接表，计算攻击者在同一连通分量内
        能够控制的最大节点数。横向控制范围反映了攻击者在网络中
        的横向扩散广度。

        实现思路：
        1. 将受控节点按连通分量分组
        2. 对每个连通分量，计算每个节点的受控邻居数
        3. 取所有连通分量中的最大值

    参数:
        adjacency_matrix (dict): 网络邻接表，
                                格式：{'node_A': ['node_B', 'node_C'], ...}
        controlled_nodes (set): 被攻击者控制的节点名称集合

    返回:
        int: 横向控制范围 s_h
    """
    if not controlled_nodes or not adjacency_matrix:
        return 0

    controlled_set = set(controlled_nodes)
    visited = set()
    max_width = 0

    for start_node in controlled_set:
        if start_node in visited:
            continue

        component_nodes = set()
        stack = [start_node]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            if node not in controlled_set:
                continue
            visited.add(node)
            component_nodes.add(node)
            for neighbor in adjacency_matrix.get(node, []):
                if neighbor in controlled_set and neighbor not in visited:
                    stack.append(neighbor)

        neighbor_counts = []
        for node in component_nodes:
            controlled_neighbors = sum(
                1 for nb in adjacency_matrix.get(node, [])
                if nb in component_nodes
            )
            neighbor_counts.append(controlled_neighbors)

        if neighbor_counts:
            component_width = max(neighbor_counts)
            max_width = max(max_width, component_width)

    return max_width


def calculate_vertical_control_range(tree_structure, entry_node, controlled_nodes):
    """
    计算纵向控制范围 s_v

    计算方法:
        从攻击入口节点出发，计算到最远受控节点的最大深度（跳数）。

        实现思路：
        1. 以入口节点为根，使用BFS遍历树结构
        2. 记录每个受控节点到入口节点的距离
        3. 取最大距离作为纵向控制范围

    参数:
        tree_structure (dict): 网络树状结构邻接表，
                               格式：{'parent_node': ['child_node1', ...], ...}
        entry_node (str): 攻击入口节点名称
        controlled_nodes (set): 被攻击者控制的节点名称集合

    返回:
        int: 纵向控制范围 s_v
    """
    if (not controlled_nodes or not tree_structure
            or entry_node not in controlled_nodes):
        return 0

    from collections import deque

    max_depth = 0
    visited = {entry_node: 0}
    queue = deque([entry_node])

    while queue:
        current = queue.popleft()
        current_depth = visited[current]

        if current in controlled_nodes:
            max_depth = max(max_depth, current_depth)

        for neighbor in tree_structure.get(current, []):
            if neighbor not in visited:
                visited[neighbor] = current_depth + 1
                queue.append(neighbor)

    return max_depth


def calculate_control_scope(horizontal_range, vertical_range):
    """
    计算综合控制范围

    计算方法:
        按照公式 S = s_h × s_v 计算，即横向控制范围与纵向控制范围的乘积。

    参数:
        horizontal_range (int): 横向控制范围 s_h
        vertical_range (int): 纵向控制范围 s_v

    返回:
        float: 综合控制范围 S
    """
    return float(horizontal_range * vertical_range)



# 2.1.2 控制时间
def calculate_total_control_time(control_times):
    """
    计算总控制时间

    参数:
        control_times (list): 每个被控非蜜罐节点从首次被控到当前步的持续步数列表

    返回:
        float: 总控制时间 T = Σ t^{n_{*}}
    """
    return sum(control_times)

# 2.2 破坏能力
# 2.2.1 保密性破坏能力
def calculate_confidentiality_damage(asset_values, info_discovered_nodes):
    """
    计算保密性破坏能力 DC（v2优化版）

    计算方法:
        DC = 被探测节点资产价值总和 / 全部非蜜罐节点资产价值总和
        被探测节点 = portscan(基本信息暴露) ∪ discovery(脆弱性暴露) 的非蜜罐目标节点

    参数:
        asset_values (dict): {node_name: value(int), ...}
        info_discovered_nodes (set): 被探测到信息的非蜜罐节点集合

    返回:
        dict: {'dc_score', 'dc_level', 'exposed_asset_value', 'total_asset_value', 'assessment'}
    """
    if not asset_values or not info_discovered_nodes:
        return _empty_damage_result('dc', asset_values)

    total_value = sum(v for v in asset_values.values() if v > 0)
    if total_value == 0:
        return _empty_damage_result('dc', asset_values)

    exposed_value = sum(asset_values.get(n, 0) for n in info_discovered_nodes)
    dc_score = min(exposed_value / total_value, 1.0)

    return _build_damage_result('dc', dc_score, exposed_value, total_value)


# 2.2.2 完整性破坏能力
def calculate_integrity_damage(asset_values, controlled_nodes):
    """
    计算完整性破坏能力 DI（v2优化版）

    计算方法:
        DI = 被控节点资产价值总和 / 全部非蜜罐节点资产价值总和
        被控节点 = lateral-movement/privilege-escalation/impact 命中的非蜜罐节点

    参数:
        asset_values (dict): {node_name: value(int), ...}
        controlled_nodes (set): 被攻击者控制的非蜜罐节点集合

    返回:
        dict: {'di_score', 'di_level', 'compromised_asset_value', 'total_asset_value', 'assessment'}
    """
    if not asset_values or not controlled_nodes:
        return _empty_damage_result('di', asset_values)

    total_value = sum(v for v in asset_values.values() if v > 0)
    if total_value == 0:
        return _empty_damage_result('di', asset_values)

    compromised_value = sum(asset_values.get(n, 0) for n in controlled_nodes)
    di_score = min(compromised_value / total_value, 1.0)

    return _build_damage_result('di', di_score, compromised_value, total_value)


# 2.2.3 可用性破坏能力
def calculate_availability_damage(asset_values, failed_nodes):
    """
    计算可用性破坏能力 DA（v2优化版）

    计算方法:
        DA = 失效节点资产价值总和 / 全部非蜜罐节点资产价值总和
        失效节点 = 被 impact 命中的非蜜罐节点

    参数:
        asset_values (dict): {node_name: value(int), ...}
        failed_nodes (set): 被 impact 命中的非蜜罐节点集合

    返回:
        dict: {'da_score', 'da_level', 'failed_asset_value', 'total_asset_value', 'assessment'}
    """
    if not asset_values or not failed_nodes:
        return _empty_damage_result('da', asset_values)

    total_value = sum(v for v in asset_values.values() if v > 0)
    if total_value == 0:
        return _empty_damage_result('da', asset_values)

    failed_value = sum(asset_values.get(n, 0) for n in failed_nodes)
    da_score = min(failed_value / total_value, 1.0)

    return _build_damage_result('da', da_score, failed_value, total_value)


# 2.2.4 综合破坏能力
def calculate_comprehensive_damage(dc_result, di_result, da_result,
                                   w_c=0.35, w_i=0.35, w_a=0.30):
    """
    计算综合破坏能力 D

    计算方法:
        D = w_c * DC + w_i * DI + w_a * DA

    参数:
        dc_result (dict): calculate_confidentiality_damage 返回
        di_result (dict): calculate_integrity_damage 返回
        da_result (dict): calculate_availability_damage 返回
        w_c (float): 保密性权重，默认0.35
        w_i (float): 完整性权重，默认0.35
        w_a (float): 可用性权重，默认0.30

    返回:
        dict: {'d_score', 'd_level', 'dc_contribution', 'di_contribution',
               'da_contribution', 'assessment'}
    """
    dc_score = dc_result.get('dc_score', 0.0)
    di_score = di_result.get('di_score', 0.0)
    da_score = da_result.get('da_score', 0.0)

    dc_contrib = w_c * dc_score
    di_contrib = w_i * di_score
    da_contrib = w_a * da_score

    d_score = dc_contrib + di_contrib + da_contrib
    d_score = min(max(d_score, 0.0), 1.0)

    if d_score >= 0.8:
        d_level = 5
        assessment = '毁灭性破坏（CIA三元组全面受损）'
    elif d_score >= 0.6:
        d_level = 4
        assessment = '严重破坏（多维度严重受损）'
    elif d_score >= 0.4:
        d_level = 3
        assessment = '中等破坏（部分维度受损）'
    elif d_score >= 0.2:
        d_level = 2
        assessment = '轻微破坏（个别维度轻微受损）'
    elif d_score >= 0.05:
        d_level = 1
        assessment = '微弱破坏'
    else:
        d_level = 0
        assessment = '几乎无破坏'

    return {
        'd_score': round(d_score, 4),
        'd_level': d_level,
        'dc_contribution': round(dc_contrib, 4),
        'di_contribution': round(di_contrib, 4),
        'da_contribution': round(da_contrib, 4),
        'assessment': assessment
    }


def _empty_damage_result(prefix, asset_values):
    total_value = sum(v for v in asset_values.values() if v > 0) if asset_values else 0
    return {
        f'{prefix}_score': 0.0,
        f'{prefix}_level': 0,
        f'{prefix}_affected_asset_value': 0,
        'total_asset_value': total_value,
        'assessment': '无破坏'
    }


def _build_damage_result(prefix, score, affected_value, total_value):
    if score >= 0.8:
        level = 5
        assessment = '严重破坏'
    elif score >= 0.6:
        level = 4
        assessment = '较高破坏'
    elif score >= 0.4:
        level = 3
        assessment = '中等破坏'
    elif score >= 0.2:
        level = 2
        assessment = '较低破坏'
    else:
        level = 1
        assessment = '轻微破坏'

    return {
        f'{prefix}_score': round(score, 4),
        f'{prefix}_level': level,
        f'{prefix}_affected_asset_value': affected_value,
        'total_asset_value': total_value,
        'assessment': assessment
    }


# 2.3 传播能力
# 2.3.1 横向传播能力
def calculate_lateral_movement_propagation(lateral_movement_count, total_nodes):
    """
    计算横向传播能力

    描述：
        通过计算成功执行横向移动的动作次数与非蜜罐节点总数之比来量化横向传播能力。
        Alm为成功执行横向移动的动作次数，Nd为非蜜罐总节点数。

    计算方法:
        横向传播能力 Plm = Alm / Nd，取值范围[0, 1]。
        0 表示未发生横向传播，1 表示横向传播能力达到最强。

    参数:
        lateral_movement_count (int): 成功执行横向移动的动作次数 Alm
        total_nodes (int): 总节点数 Nd（不包括蜜罐节点）

    返回:
        dict: 包含以下键值对：
            - 'ratio' (float): 横向传播能力比例 Alm/Nd
            - 'assessment' (str): 传播等级定性评估
              '未发生横向传播'   (ratio == 0)
              '传播能力较弱'      (0 < ratio < 0.4)
              '传播能力一般'      (0.4 <= ratio < 0.8)
              '传播能力较强'      (ratio >= 0.8)
    """
    if total_nodes == 0:
        return {'ratio': 0.0, 'assessment': '无节点'}

    ratio = lateral_movement_count / total_nodes

    if lateral_movement_count == 0:
        assessment = '未发生横向传播'
    elif ratio < 0.4:
        assessment = '传播能力较弱'
    elif ratio < 0.8:
        assessment = '传播能力一般'
    else:
        assessment = '传播能力较强'

    return {'ratio': round(ratio, 4), 'assessment': assessment}

# 2.4 隐蔽能力
# 2.4.1 行为隐蔽能力
def calculate_behavior_concealment_ability(total_attacks, attacks_to_honey):
    """
    计算行为隐蔽能力

    参数:
        total_attacks (int): 攻击总次数 Ac
        attacks_to_honey (int): 针对蜜罐节点的攻击次数 Ah

    返回:
        float: 行为隐蔽能力 Hht，取值范围：[0.0, 1.0]
    """
    if total_attacks == 0:
        return 1.0
    return 1.0 - attacks_to_honey / total_attacks


# 2.4.2 网络隐蔽能力
def calculate_network_concealment_ability(total_controlled_nodes, controlled_honey_nodes):
    """
    计算网络隐蔽能力

    参数:
        total_controlled_nodes (int): 攻击者已控制的所有节点总数 |h_v|
        controlled_honey_nodes (int): 被攻击者控制的蜜罐节点数 |h_h|

    返回:
        float: 网络隐蔽能力 H_nt，取值范围：[0.0, 1.0]
    """
    if total_controlled_nodes == 0:
        return 1.0
    return 1.0 - controlled_honey_nodes / total_controlled_nodes


# 2.4.3 综合隐蔽能力
def calculate_comprehensive_concealment_ability(behavior_concealment_score,
                                                network_concealment_score,
                                                w_behavior=0.5,
                                                w_network=0.5):
    """
    计算综合隐蔽能力

    计算方法:
        H_comprehensive = w_behavior × H_behavior + w_network × H_network

    参数:
        behavior_concealment_score (float): 行为隐蔽能力 H_behavior
        network_concealment_score (float): 网络隐蔽能力 H_network
        w_behavior (float): 行为隐蔽能力权重，默认0.5
        w_network (float): 网络隐蔽能力权重，默认0.5

    返回:
        dict: 包含以下键值对：
            - 'comprehensive_score' (float): 综合隐蔽能力得分
            - 'behavior_contribution' (float): 行为隐蔽贡献
            - 'network_contribution' (float): 网络隐蔽贡献
            - 'assessment' (str): 定性评估描述
    """
    behavior_contrib = w_behavior * behavior_concealment_score
    network_contrib = w_network * network_concealment_score

    comprehensive = behavior_contrib + network_contrib

    if comprehensive >= 0.7:
        assessment = '高隐蔽'
    elif comprehensive >= 0.4:
        assessment = '中等隐蔽'
    elif comprehensive >= 0.1:
        assessment = '低隐蔽'
    else:
        assessment = '几乎无隐蔽'

    return {
        'comprehensive_score': round(comprehensive, 4),
        'behavior_contribution': round(behavior_contrib, 4),
        'network_contribution': round(network_contrib, 4),
        'assessment': assessment
    }



# ─────────────── v9.4 Step 3（C 路线）：权威蜜罐登记（与名字解耦）───────────────
# 问题：蜜罐身份目前**只能**从名字推断（32-hex / decoy_NN，见 HONEY_PATTERN/DECOY_PATTERN），
#      而 agent 看到的主机名也是同一批字符串 —— 评估器打标签的特征与 agent 可见特征同源。
#      若策略学会"不打 decoy_*"，指标会记成满分隐蔽性，无法与"真识别诱饵"区分。
# 解法：CW 评测侧导出**与名字无关**的诱饵清单（来自环境 Network.decoys / Host.decoy，
#      见 cyberwheel/runners/rl_evaluator.py 的 --decoy-manifest），由 cli.py 在指标
#      计算前注入本登记表。判定口径为**并集**（登记表 ∪ 正则），保守以免漏判蜜罐。
# 溯源：label_source ∈ {'manifest','regex'}，由 cli.py 写入 _process2.json 顶层。
_AUTHORITATIVE_HONEY: set = set()
_LABEL_SOURCE = 'regex'

# ── F3 修复（v9_4/cage4_honeypot_fix_plan.md §4.1 F3）：时相诱饵区间登记 ──────
# CAGE4 的诱饵是**真实主机上的假服务**，主机名不变 → 节点级静态口径结构性不可见
# （attacks_to_honey≡0、behavior_concealment≡1.000 假满分）。
# 且诱饵**永久存活**（无 RemoveDecoy；Host.update 空实现），故用 [first_seen, ∞) 区间。
# 区间登记只影响 is_honey_target（攻击计数），**不影响 is_honey_node**
# ——诱饵宿主是真实主机，必须留在非蜜罐分母里（否则非蜜罐节点数会被误减）。
_AUTHORITATIVE_INTERVALS: dict = {}     # {hostname_lower: [(start, end_or_None), ...]}
_INTERVAL_SOURCE = 'regex'


def set_authoritative_honey_intervals(intervals, source='manifest-interval'):
    """注入时相诱饵区间登记。intervals: {host: [(start, end_or_None), ...]}。"""
    global _AUTHORITATIVE_INTERVALS, _INTERVAL_SOURCE
    clean = {}
    for name, spans in (intervals or {}).items():
        n = str(name).strip().lower()
        if not n:
            continue
        out = []
        for sp in (spans or []):
            try:
                if isinstance(sp, dict):
                    start, end = sp.get('first_seen_step'), sp.get('removed_step')
                else:
                    start, end = sp[0], sp[1]
            except Exception:
                continue
            try:
                start = int(start) if start is not None else None
            except Exception:
                start = None
            try:
                end = int(end) if end is not None else None
            except Exception:
                end = None
            if start is None:
                continue
            out.append((start, end))
        if out:
            clean[n] = sorted(out)
    _AUTHORITATIVE_INTERVALS = clean
    _INTERVAL_SOURCE = source if clean else 'regex'
    return len(clean)


def get_authoritative_intervals():
    return {k: list(v) for k, v in _AUTHORITATIVE_INTERVALS.items()}


def get_interval_source():
    return _INTERVAL_SOURCE


def clear_authoritative_intervals():
    set_authoritative_honey_intervals({}, 'regex')


def _in_registered_interval(node_name, step):
    """node 在 step 时刻是否处于已登记的诱饵存活区间（时相口径）。"""
    spans = _AUTHORITATIVE_INTERVALS.get(str(node_name).strip().lower())
    if not spans:
        return False
    try:
        s = int(step)
    except Exception:
        return False
    for start, end in spans:
        if start <= s and (end is None or s <= end):
            return True
    return False


def set_authoritative_honey(names, source='manifest'):
    """注入权威蜜罐集合（来自诱饵清单）。names 为空则视为未提供，回退正则。

    2026-09-18 适配：source **透传**（非空时）——cli.py 的 schema-02 分支现同时
    返回诱饵主机名与 source='manifest-interval'，旧实现会把 _LABEL_SOURCE 覆盖成
    'manifest'，使 get_label_source() 与 cli 写入 _process2.json 的 label_source
    溯源值分叉。现在非空 names 保留调用方给的 source；空 names 仍回退 'regex'。
    """
    global _AUTHORITATIVE_HONEY, _LABEL_SOURCE
    _AUTHORITATIVE_HONEY = {str(n).strip().lower() for n in (names or []) if str(n).strip()}
    _LABEL_SOURCE = source if _AUTHORITATIVE_HONEY else 'regex'
    return len(_AUTHORITATIVE_HONEY)


def get_authoritative_honey():
    return set(_AUTHORITATIVE_HONEY)


def get_label_source():
    return _LABEL_SOURCE


def clear_authoritative_honey():
    """清空登记表（每个 episode 计算前应调用，避免跨集串味）。"""
    set_authoritative_honey([], 'regex')
    clear_authoritative_intervals()


def is_honey_node(node_name, node_type_map=None):
    """判断节点是否为蜜罐（F1 修复：支持 topology type:honey/decoy）。
    
    优先通过 32-hex 正则匹配，其次通过 node_type_map（来自 processed_data
    的 node_table，其中 type 为 'honey' 的节点）判断。
    F3.2 修复: 额外支持 CW 确定性 decoy 命名（decoy_NN）。
    v9.4 Step 3（C 路线）: **权威清单优先** —— 命中清单即判为蜜罐（与名字无关），
    未命中时继续走正则/type_map（并集口径，保守以免漏判）。
    """
    name = node_name.strip().lower()
    if _AUTHORITATIVE_HONEY and name in _AUTHORITATIVE_HONEY:
        return True
    if HONEY_PATTERN.match(name):
        return True
    if DECOY_PATTERN.match(name):
        return True
    if node_type_map and node_name in node_type_map:
        return node_type_map[node_name] == 'honey'
    return False


def is_honey_target(node_name, step, node_type_map=None, deployed_subnets=None,
                    node_subnet_map=None):
    """蜜罐攻击判定（节点级口径 + F3 时相区间口径）。

    2026-09-04 决议：移除 F11 子网级判定（原"节点所在子网已部署诱饵且
    step >= 部署 step 即视为攻击蜜罐"），仅保留节点级判定——节点本身是
    蜜罐节点（32-hex / decoy_NN / node_table type='honey'）才计入
    attacks_to_honey。

    F3 修复（v9_4/cage4_honeypot_fix_plan.md §4.1 F3）：**新增时相区间登记**。
    若节点在 step 时刻处于已登记的诱饵存活区间 [first_seen, removed_or_∞)，
    即判为蜜罐目标。该口径与静态正则/清单是**并集**关系（保守以免漏判），
    故 CW 与历史语料语义完全不变（无区间登记时行为与修复前逐位一致）。
    """
    if _AUTHORITATIVE_INTERVALS and _in_registered_interval(node_name, step):
        return True
    return is_honey_node(node_name, node_type_map)


def calculate_step_metrics(processed_data, linked_list_data):
    """
    计算每一步的八个指标数据
    
    参数:
        processed_data (dict): 预处理数据
        linked_list_data (dict): 链表数据
    
    返回:
        dict: 包含每一步指标数据的字典
    """
    # 获取基本统计信息
    non_honey_total = processed_data['summary']['non_honey_node_count']
    total_subnets = processed_data['summary']['total_subnets']
    asset_values = processed_data.get('asset_values', {})

    # ── 诱饵剔除（2026-09-18，用户拍板："诱饵不参与红方战果指标"）─────────────
    # 缺陷：CAGE4 诱饵是独立拓扑条目（schema-02 清单给名字+时相），旧口径下
    # is_honey_node 不认识它们 ⇒ ①分母 non_honey_total 把诱饵当普通主机；
    # ②asset_values 含诱饵资产（C4-GNN ep001：诱饵资产 87/143）⇒ DC/DI/DA/控制价值
    # 分母虚高、被控诱饵资产计入分子（controlled_asset_value 92 里 87 是诱饵）；
    # ③info_discovered/failed_nodes/三个检测集合的分子含诱饵。
    # 处置（与 cli.py 的清单注入配套，CW 的 decoy_NN 正则路径本就覆盖，行为不变）：
    #   * honey_names = 权威清单 ∪ 时相区间键集（静态节点口径， Episode 级近似：
    #     某主机一旦成为诱饵，其诱饵身份对**全 episode** 的战果口径生效——
    #     攻击时相语义仍由 is_honey_target 的区间判定单独承载，不受影响）；
    #   * 分母扣减：non_honey_total 来自 pre_process（其蜜罐识别不含权威清单），
    #     用 **原 asset_values 键集**（=pre_process 的语料节点全集）与 honey_names
    #     求交扣减。近似假设：诱饵主机必然同时出现在拓扑与语料节点全集
    #     （红方对诱饵的成功动作使其进入 node_red / 侧车名字来自拓扑条目），
    #     故该交集即"被误计入分母的诱饵数"。
    #   * 保留：attacks_to_honey / controlled_honey_count / confirmed_* 双口径 /
    #     total_control_time / concealment 三式（蜜罐交互=暴露红方，语义正确）。
    honey_names = get_authoritative_honey() | set(_AUTHORITATIVE_INTERVALS.keys())
    if honey_names:
        _corpus_nodes = {str(k).strip().lower()
                         for k in processed_data.get('asset_values', {})}
        non_honey_total = max(0, non_honey_total - len(honey_names & _corpus_nodes))
        asset_values = {k: v for k, v in asset_values.items()
                        if str(k).strip().lower() not in honey_names}

    node_table = processed_data.get('node_table', [])
    # F1 修复: 构建 node_type_map 用于增强蜜罐识别
    node_type_map = {entry['node_name']: entry.get('node_type', '') for entry in node_table
                     if entry.get('node_type') == 'honey'}
    # 修复 4(F11): 子网级蜜罐部署信息（{topology子网键: 首次部署 step}）
    deployed_subnets = processed_data.get('deployed_subnets', {}) or {}
    node_subnet_map = {}
    subnet_non_honey_nodes = {}
    for entry in node_table:
        name = entry['node_name']
        sn = entry.get('subnet', '')
        node_subnet_map[name] = sn
        if sn and not is_honey_node(name, node_type_map):
            if sn not in subnet_non_honey_nodes:
                subnet_non_honey_nodes[sn] = set()
            subnet_non_honey_nodes[sn].add(name)

    adjacency_matrix = {}
    topology_interfaces = processed_data.get('topology_map', {}).get('interfaces', {})
    for node_a, neighbors in topology_interfaces.items():
        if node_a not in adjacency_matrix:
            adjacency_matrix[node_a] = []
        for node_b in neighbors:
            adjacency_matrix[node_a].append(node_b)
            if node_b not in adjacency_matrix:
                adjacency_matrix[node_b] = []
            adjacency_matrix[node_b].append(node_a)

    subnet_node_lists = {}
    for node_name in node_subnet_map:
        sn = node_subnet_map[node_name]
        if sn:
            if sn not in subnet_node_lists:
                subnet_node_lists[sn] = []
            subnet_node_lists[sn].append(node_name)

    for sn, node_list in subnet_node_lists.items():
        for i, node_a in enumerate(node_list):
            if node_a not in adjacency_matrix:
                adjacency_matrix[node_a] = []
            for node_b in node_list[i + 1:]:
                if node_b not in adjacency_matrix[node_a]:
                    adjacency_matrix[node_a].append(node_b)
                if node_b not in adjacency_matrix:
                    adjacency_matrix[node_b] = []
                if node_a not in adjacency_matrix[node_b]:
                    adjacency_matrix[node_b].append(node_a)

    # 初始化统计变量
    controlled_nodes = set()
    alive_detected_nodes = set()
    info_detected_nodes = set()
    vulnerability_detected_nodes = set()
    non_honey_lateral_movement_count = 0
    honey_lateral_movement_count = 0    # 诱饵剔除（2026-09-18）：打诱饵的横向移动数

    # WP2.2: confirmed_* 双口径（success==TRUE 子集，不改原口径）
    # 语义注册表见 wxpgzs/success_semantics.yaml；UNKNOWN 视为未确认
    confirmed_controlled_nodes = set()
    confirmed_lateral_movement_count = 0
    confirmed_attacks_to_honey = 0
    pingsweep_count = 0
    portscan_count = 0
    lateral_movement_count = 0
    detection_count = 0
    non_honey_controlled_count = 0
    failed_nodes = set()
    entry_node = None
    node_first_controlled_at = {}
    total_attacks = 0
    attacks_to_honey = 0

    # 获取所有步骤的操作数据
    process_steps = linked_list_data['process_description']

    # M2 修复（CAGE4 评估链路 v9_4/cage4_honeypot_fix_plan.md §4.3 M2）：
    # 统计"动作名未落入下面分派表"的行数。这些行只贡献 total_attacks，
    # 对 DC/DI/DA 零贡献，却把隐蔽性分母 Ac 灌水（Ah≡0 → H_bt≡1.000）。
    # 计数写入 _process2.json 顶层（不改 26 列指标表），供验收与报告剔除失真。
    _dispatch_actions = {'pingsweep', 'portscan', 'discovery', 'lateral-movement',
                         'exploit', 'privilege-escalation', 'impact'}
    _unrecognized_names = {}
    unrecognized_action_rows = 0

    # 计算每一步的指标
    step_metrics = []

    for step_idx, operation in enumerate(process_steps):
        step = operation['step']
        action = operation['action']
        target = operation['target']
        source = operation['source']

        # 更新统计数据
        if action == 'pingsweep':
            pingsweep_count += 1
            if not is_honey_target(target, step, node_type_map, deployed_subnets, node_subnet_map):
                alive_detected_nodes.add(target)
            else:
                attacks_to_honey += 1
        elif action == 'portscan':
            portscan_count += 1
            if not is_honey_target(target, step, node_type_map, deployed_subnets, node_subnet_map):
                info_detected_nodes.add(target)
            else:
                attacks_to_honey += 1
        elif action == 'discovery':
            if not is_honey_target(target, step, node_type_map, deployed_subnets, node_subnet_map):
                vulnerability_detected_nodes.add(target)
            else:
                attacks_to_honey += 1
        elif action in ('lateral-movement', 'exploit'):
            # F9 修复: exploit 等同于 lateral-movement（获取节点控制权）
            lateral_movement_count += 1
            # 诱饵剔除（2026-09-18）：Alm（横向传播分子）只计非诱饵目标。
            # 体检发现 non_honey_lateral_movement_count 一直被统计却从未被使用
            # （ Plm 分子用的原始 lateral_movement_count 含打诱饵的横向移动，
            #   属"诱饵计入红方战果"同一缺陷族）。此处按**静态**蜜罐口径计数：
            # 打诱饵的横向移动不算红方传播能力（时相语义只留给 attacks_to_honey）。
            if is_honey_node(target, node_type_map):
                honey_lateral_movement_count += 1
            controlled_nodes.add(target)
            # WP2.2: confirmed 子集（仅 success==TRUE 计入确认口径）
            _confirmed = operation.get('success') == 'TRUE'
            if _confirmed:
                confirmed_lateral_movement_count += 1
                confirmed_controlled_nodes.add(target)
            if not is_honey_target(target, step, node_type_map, deployed_subnets, node_subnet_map):
                non_honey_lateral_movement_count += 1
                if target and target not in node_first_controlled_at:
                    node_first_controlled_at[target] = step
                # S0 修复: 仅当 target 非空时才设置 entry_node
                # 空 target（DST 未映射）会导致 entry_node=''，BFS 从空字符串出发找不到邻居 → s_v=0
                if entry_node is None and target:
                    entry_node = target
            else:
                attacks_to_honey += 1
                if _confirmed:
                    confirmed_attacks_to_honey += 1
        elif action == 'privilege-escalation':
            controlled_nodes.add(target)
            _confirmed = operation.get('success') == 'TRUE'
            if _confirmed:
                confirmed_controlled_nodes.add(target)
            # 修复 1: 仅当目标是蜜罐时才计入 attacks_to_honey。
            # 原条件用 "target not in node_first_controlled_at" 分流，导致对已控制
            # 非蜜罐节点的重复提权被误判为蜜罐攻击，隐蔽性被系统性压低
            if is_honey_target(target, step, node_type_map, deployed_subnets, node_subnet_map):
                attacks_to_honey += 1
                if _confirmed:
                    confirmed_attacks_to_honey += 1
            else:
                if target not in node_first_controlled_at:
                    node_first_controlled_at[target] = step
                # S0 修复: 任何控制节点的动作都应有机会设置 entry_node
                if entry_node is None and target:
                    entry_node = target
        elif action == 'impact':
            controlled_nodes.add(target)
            _confirmed = operation.get('success') == 'TRUE'
            if _confirmed:
                confirmed_controlled_nodes.add(target)
            if not is_honey_target(target, step, node_type_map, deployed_subnets, node_subnet_map):
                failed_nodes.add(target)
                if target not in node_first_controlled_at:
                    node_first_controlled_at[target] = step
                # S0 修复: impact 也能控制节点，设置 entry_node
                if entry_node is None and target:
                    entry_node = target
            else:
                attacks_to_honey += 1

        total_attacks += 1
        if action not in _dispatch_actions:
            unrecognized_action_rows += 1
            _unrecognized_names[action] = _unrecognized_names.get(action, 0) + 1

        # ── 诱饵剔除（2026-09-18）：战果集合的分子统一扣掉诱饵节点 ─────────────
        # （每步执行一次的集合差，幂等；后续步骤新插入的诱饵名也会被再次扣掉。
        #   controlled_nodes 不在此列——诱饵被控要如实进 controlled_honey_count，
        #   由 non_honey_controlled（is_honey_node 已含权威清单）单独承载非诱饵战果。）
        if honey_names:
            alive_detected_nodes -= honey_names
            info_detected_nodes -= honey_names
            vulnerability_detected_nodes -= honey_names
            failed_nodes -= honey_names

        non_honey_controlled = set(n for n in controlled_nodes if not is_honey_node(n, node_type_map))
        non_honey_controlled_count = len(non_honey_controlled)
        controlled_honey_count = len(controlled_nodes) - non_honey_controlled_count

        controlled_subnets = set()
        for n in non_honey_controlled:
            sn = node_subnet_map.get(n, '')
            if sn:
                controlled_subnets.add(sn)

        failed_subnets = set()
        for sn, nodes_in_sn in subnet_non_honey_nodes.items():
            if nodes_in_sn and nodes_in_sn.issubset(failed_nodes):
                failed_subnets.add(sn)

        # 聚合全部探测节点（三类探测并集）
        all_detected = alive_detected_nodes | info_detected_nodes | vulnerability_detected_nodes
        node_detect_rate = len(all_detected) / non_honey_total if non_honey_total > 0 else 0.0

        # 使用函数计算指标
        node_control_rate = calculate_node_control_rate(non_honey_total, non_honey_controlled_count)
        subnet_control_rate = calculate_subnet_control_rate(total_subnets, len(controlled_subnets))
        node_alive_detection_rate = calculate_node_alive_detection_rate(
            non_honey_total, len(alive_detected_nodes))
        node_info_detection_rate = calculate_node_info_detection_rate(
            non_honey_total, len(info_detected_nodes))
        node_vulnerability_detection_rate = calculate_node_vulnerability_detection_rate(
            non_honey_total, len(vulnerability_detected_nodes))

        # 计算总控制时间（每个非蜜罐节点从首次被控到当前步的持续步数累加）
        control_times = [
            step - node_first_controlled_at.get(n, step) + 1
            for n in non_honey_controlled
        ]
        total_control_time = calculate_total_control_time(control_times)

        # 计算横向传播能力
        # 诱饵剔除（2026-09-18）：分子改用"总横向移动 − 打诱饵的横向移动"，
        # 不再把对诱饵的横向移动算作红方传播能力。
        lateral_movement_propagation = calculate_lateral_movement_propagation(
            lateral_movement_count - honey_lateral_movement_count, non_honey_total)

        # 计算隐蔽能力
        behavior_concealment = calculate_behavior_concealment_ability(
            total_attacks, attacks_to_honey)
        total_controlled_all = len(controlled_nodes)
        network_concealment = calculate_network_concealment_ability(
            total_controlled_all, controlled_honey_count)
        comprehensive_concealment = calculate_comprehensive_concealment_ability(
            behavior_concealment, network_concealment)

        # 计算控制价值
        control_value_result = calculate_control_value(asset_values, non_honey_controlled)

        # 计算破坏能力
        info_discovered = info_detected_nodes | vulnerability_detected_nodes
        dc_result = calculate_confidentiality_damage(asset_values, info_discovered)
        di_result = calculate_integrity_damage(asset_values, non_honey_controlled)
        da_result = calculate_availability_damage(asset_values, failed_nodes)
        comprehensive_damage = calculate_comprehensive_damage(
            dc_result, di_result, da_result)

        # 计算节点失效率和子网失效率
        node_failure_rate = calculate_node_failure_rate(non_honey_total, len(failed_nodes))
        subnet_failure_rate = calculate_subnet_failure_rate(total_subnets, len(failed_subnets))

        # 计算控制范围
        horizontal_range = calculate_horizontal_control_range(
            adjacency_matrix, non_honey_controlled)
        vertical_range = calculate_vertical_control_range(
            adjacency_matrix, entry_node, non_honey_controlled)
        control_scope = calculate_control_scope(horizontal_range, vertical_range)

        # 保存当前步骤的指标
        step_metrics.append({
            'step': step,
            'action': action,
            'source': source,
            'target': target,
            'metrics': {
                'node_control_rate': round(node_control_rate, 4),
                'subnet_control_rate': round(subnet_control_rate, 4),
                'node_alive_detection_rate': round(node_alive_detection_rate, 4),
                'node_info_detection_rate': round(node_info_detection_rate, 4),
                'node_vulnerability_detection_rate': round(node_vulnerability_detection_rate, 4),
                'node_detect_rate': round(node_detect_rate, 4),
                'total_control_time': round(total_control_time, 2),
                'lateral_movement_propagation': lateral_movement_propagation,
                'behavior_concealment': round(behavior_concealment, 4),
                'network_concealment': round(network_concealment, 4),
                'comprehensive_concealment': comprehensive_concealment,
                'control_value': control_value_result,
                'node_failure_rate': round(node_failure_rate, 4),
                'subnet_failure_rate': round(subnet_failure_rate, 4),
                'horizontal_control_range': horizontal_range,
                'vertical_control_range': vertical_range,
                'control_scope': round(control_scope, 1),
                'confidentiality_damage': dc_result,
                'integrity_damage': di_result,
                'availability_damage': da_result,
                'comprehensive_damage': comprehensive_damage
            },
            'statistics': {
                'controlled_devices': len(controlled_nodes),
                'non_honey_controlled': non_honey_controlled_count,
                'controlled_subnets': len(controlled_subnets),
                'alive_detected_nodes': len(alive_detected_nodes),
                'info_detected_nodes': len(info_detected_nodes),
                'vulnerability_detected_nodes': len(vulnerability_detected_nodes),
                'all_detected_nodes': len(all_detected),
                'pingsweep_count': pingsweep_count,
                'portscan_count': portscan_count,
                'lateral_movement_count': lateral_movement_count,
                # 诱饵剔除（2026-09-18）：横向移动的诱饵/非诱饵拆分（溯源用）
                'honey_lateral_movement_count': honey_lateral_movement_count,
                'non_honey_lateral_movement_count':
                    lateral_movement_count - honey_lateral_movement_count,
                'detection_count': detection_count,
                'failed_nodes': len(failed_nodes),
                'failed_subnets': len(failed_subnets),
                'horizontal_control_range': horizontal_range,
                'vertical_control_range': vertical_range,
                'total_attacks': total_attacks,
                'attacks_to_honey': attacks_to_honey,
                'controlled_honey_count': controlled_honey_count,
                # WP2.2: confirmed_* 双口径（success==TRUE 子集；UNKNOWN 视为未确认）
                'confirmed_controlled': len(confirmed_controlled_nodes & set(n for n in controlled_nodes if not is_honey_node(n, node_type_map))),
                'confirmed_lateral_movement_count': confirmed_lateral_movement_count,
                'confirmed_attacks_to_honey': confirmed_attacks_to_honey
            }
        })
    
    # M2 修复：未识别动作计数（初始化于指标循环之前，见上文）
    return {
        'total_steps': len(process_steps),
        'step_metrics': step_metrics,
        'red_nonsleep_rows': len(process_steps),
        'unrecognized_action_rows': unrecognized_action_rows,
        'unrecognized_action_names': _unrecognized_names,
        'dispatch_actions': sorted(_dispatch_actions),
    }

def save_step_metrics_results(results, output_file):
    """
    保存每一步指标计算结果到JSON文件
    
    参数:
        results (dict): 指标计算结果
        output_file (str): 输出文件路径
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"每一步指标计算结果已保存到 {output_file}")

def main():
    """
    主函数：读取预处理数据和链表数据，计算每一步的八个指标，保存结果
    """
    # 读取预处理数据
    with open('data/processed.json', 'r', encoding='utf-8') as f:
        processed_data = json.load(f)
    
    # 读取链表数据
    with open('data/process_linked_list.json', 'r', encoding='utf-8') as f:
        linked_list_data = json.load(f)
    
    # 计算每一步的指标
    step_metrics_results = calculate_step_metrics(processed_data, linked_list_data)
    
    # 保存结果
    save_step_metrics_results(step_metrics_results, 'data/process2.json')
    
    # 打印示例（第38步的指标）
    print("\n第38步的指标示例：")
    for step_data in step_metrics_results['step_metrics']:
        if step_data['step'] == 38:
            metrics = step_data['metrics']
            print(f"节点控制率 φd = {metrics['node_control_rate']:.4f}")
            print(f"子网控制率 φw = {metrics['subnet_control_rate']:.4f}")
            print(f"节点存活探测率 χd = {metrics['node_alive_detection_rate']:.4f}")
            print(f"节点基本信息探测率 = {metrics['node_info_detection_rate']:.4f}")
            print(f"节点脆弱性信息探测率 = {metrics['node_vulnerability_detection_rate']:.4f}")
            print(f"总控制时间 T = {metrics['total_control_time']:.2f}")
            lp = metrics['lateral_movement_propagation']
            print(f"横向传播能力 Plm = {lp['ratio']:.4f}, 评级: {lp['assessment']}")
            print(f"行为隐蔽能力 H_bt = {metrics['behavior_concealment']:.4f}")
            print(f"网络隐蔽能力 H_nt = {metrics['network_concealment']:.4f}")
            cc = metrics['comprehensive_concealment']
            print(f"综合隐蔽能力 H = {cc['comprehensive_score']:.4f}, 评级: {cc['assessment']}")
            cv = metrics['control_value']
            print(f"控制价值 Vc = {cv['controlled_asset_value']}/{cv['total_asset_value']}, 评级: {cv['assessment']}")
            print(f"节点失效率 θd = {metrics['node_failure_rate']:.4f}")
            print(f"子网失效率 θw = {metrics['subnet_failure_rate']:.4f}")
            print(f"横向控制范围 s_h = {metrics['horizontal_control_range']}")
            print(f"纵向控制范围 s_v = {metrics['vertical_control_range']}")
            print(f"综合控制范围 S = {metrics['control_scope']:.1f}")
            dc = metrics['confidentiality_damage']
            di = metrics['integrity_damage']
            da = metrics['availability_damage']
            cd = metrics['comprehensive_damage']
            print(f"保密性破坏 DC = {dc['dc_score']:.4f}, level={dc['dc_level']}, {dc['assessment']}")
            print(f"完整性破坏 DI = {di['di_score']:.4f}, level={di['di_level']}, {di['assessment']}")
            print(f"可用性破坏 DA = {da['da_score']:.4f}, level={da['da_level']}, {da['assessment']}")
            print(f"综合破坏 D = {cd['d_score']:.4f}, level={cd['d_level']}, {cd['assessment']}")
            break

if __name__ == "__main__":
    main()