import csv
import json
import os
import re
import statistics
import yaml


HOST_PATTERN = re.compile(r'^host\d+$', re.IGNORECASE)
HONEY_PATTERN = re.compile(r'^[a-f0-9]{32}$', re.IGNORECASE)
DECOY_PATTERN = re.compile(r'^decoy_\d+$', re.IGNORECASE)  # F3.2: CW deterministic decoy naming (decoy_01, decoy_02, ...)
DMZ_PATTERN = re.compile(r'^dmz\d+$', re.IGNORECASE)
SERVER_PATTERN = re.compile(r'^server\d+$', re.IGNORECASE)

NODE_TYPE_HOST = 'host'
NODE_TYPE_HONEY = 'honey'
NODE_TYPE_DMZ = 'dmz'
NODE_TYPE_SERVER = 'server'
NODE_TYPE_OTHER = 'other'

# CAGE4 节点类型关键字匹配（F2 修复）
# CAGE4 节点命名规则: {subnet}_user_host_{N} / {subnet}_server_host_{N}
CAGE4_USER_HOST_RE = re.compile(r'_user_host_\d+$')
CAGE4_SERVER_HOST_RE = re.compile(r'_server_host_\d+$')

ROUND_DIGITS = 10


def load_network_topology(yaml_file_path):
    """
    从YAML文件加载网络拓扑数据

    功能用途:
        解析网络拓扑YAML文件，提取所有节点信息、子网划分、接口连接
        和拓扑结构，为后续节点分类和网络分析提供基础数据。

    实现思路:
        1. 使用PyYAML加载YAML文件
        2. 提取hosts段：获取所有节点名称、子网归属和设备类型
        3. 提取subnets段：获取子网名称和IP范围
        4. 提取topology段：获取核心路由器下的子网-节点映射关系
        5. 提取interfaces段：获取节点间的直接连接关系
        6. 对无法解析的YAML返回空结构，保证调用方不崩溃

    参数:
        yaml_file_path (str): YAML拓扑文件路径

    返回:
        dict: 拓扑数据字典，包含以下键：
            - 'hosts' (dict): 节点名 -> {subnet, type, firewall, routes} 的映射
            - 'subnets' (dict): 子网名 -> {ip_range, router, firewall} 的映射
            - 'topology' (dict): 路由器的子网-节点拓扑结构
            - 'interfaces' (dict): 节点间的直连接口映射
            - 'all_node_names' (set): 拓扑中定义的所有节点名称集合
            - 'all_subnet_names' (set): 拓扑中定义的所有子网名称集合

    异常:
        FileNotFoundError: YAML文件不存在时抛出
        yaml.YAMLError: YAML格式错误时抛出
    """
    if not os.path.exists(yaml_file_path):
        raise FileNotFoundError(f"拓扑文件不存在: {yaml_file_path}")

    with open(yaml_file_path, 'r', encoding='utf-8') as f:
        raw_data = yaml.safe_load(f)

    if raw_data is None:
        raw_data = {}

    hosts_data = raw_data.get('hosts', {}) or {}
    subnets_data = raw_data.get('subnets', {}) or {}
    topology_data = raw_data.get('topology', {}) or {}
    interfaces_data = raw_data.get('interfaces', {}) or {}

    all_node_names = set(hosts_data.keys())
    all_subnet_names = set(subnets_data.keys())

    cleaned_hosts = {}
    for node_name, node_info in hosts_data.items():
        if not isinstance(node_info, dict):
            node_info = {}
        cleaned_hosts[node_name] = {
            'subnet': node_info.get('subnet', ''),
            'type': node_info.get('type', ''),
            'firewall': node_info.get('firewall', None),
            'routes': node_info.get('routes', None),
            # 修复 2: 保留 YAML 声明的 asset_value（修复 3 的前置条件）
            'asset_value': node_info.get('asset_value', None)
        }

    cleaned_subnets = {}
    for subnet_name, subnet_info in subnets_data.items():
        if not isinstance(subnet_info, dict):
            subnet_info = {}
        cleaned_subnets[subnet_name] = {
            'ip_range': subnet_info.get('ip_range', ''),
            'router': subnet_info.get('router', ''),
            'firewall': subnet_info.get('firewall', None),
            # 修复 4(F11) 记录字段：保留原始逻辑名（cw deploy_decoy 用 dmz_subnet 等
            # 逻辑名，topology 用 subnetN 键名，需要映射）
            '_orig_name': subnet_name,
            # ⚠️ 新增（2026-09-17）：**YAML 里声明的**子网逻辑名（如 dmz_subnet）。
            # 旧实现把 `_orig_name` 覆盖成拓扑键名（subnet0）⇒ 语料中出现的逻辑名
            # 既不在 all_subnet_names 里、也不在 `_orig_name` 里，无法被识别为子网，
            # 于是被当成普通节点计入资产分母（幻影子网资产，实测 control_value_total
            # 32→35）。此处只**新增**字段，不改既有 `_orig_name` 语义。
            '_orig_name_declared': (subnet_info.get('_orig_name') or subnet_name)
        }

    return {
        'hosts': cleaned_hosts,
        'subnets': cleaned_subnets,
        'topology': topology_data,
        'interfaces': interfaces_data,
        'all_node_names': all_node_names,
        'all_subnet_names': all_subnet_names
    }


def clean_string(value, default=''):
    """
    清洗字符串值，去除空白并处理异常输入

    功能用途:
        对CSV中的字符串字段进行标准化清洗，处理None、非字符串类型、
        空字符串等异常情况。

    实现思路:
        1. 若值为None，返回默认值
        2. 若值不是字符串类型，转换为字符串后去除首尾空白
        3. 若值为空字符串或仅含空白，返回默认值
        4. 否则返回去除首尾空白后的字符串

    参数:
        value (Any): 待清洗的原始值
        default (str): 当值为空时的默认返回值，默认''

    返回:
        str: 清洗后的字符串
    """
    if value is None:
        return default
    if not isinstance(value, str):
        value = str(value)
    stripped = value.strip()
    if not stripped:
        return default
    return stripped


def parse_bool(value_str, strict=False):
    """
    安全解析布尔值，支持多种格式

    功能用途:
        将CSV中的布尔字符串转换为Python布尔值，支持TRUE/FALSE、
        true/false、1/0、yes/no等多种表示格式，同时处理异常输入。

    实现思路:
        1. 先清洗输入字符串
        2. 检查是否为常见的真值表示（TRUE, true, 1, yes, y, t）
        3. 检查是否为常见的假值表示（FALSE, false, 0, no, n, f）
        4. 若strict=True且无法识别，抛出ValueError
        5. 若strict=False且无法识别，返回默认值False

    参数:
        value_str (str 或 None): 待解析的布尔字符串
        strict (bool): 是否启用严格模式，默认False

    返回:
        bool: 解析后的布尔值

    异常:
        ValueError: strict=True且值无法解析时抛出
    """
    cleaned = clean_string(value_str, None)
    if cleaned is None:
        if strict:
            raise ValueError(f"无法解析布尔值: {value_str}")
        return False

    upper = cleaned.upper()
    if upper in ('TRUE', 'TRUE', '1', 'YES', 'Y', 'T'):
        return True
    if upper in ('FALSE', 'FALSE', '0', 'NO', 'N', 'F'):
        return False

    if strict:
        raise ValueError(f"无法解析布尔值: '{value_str}'")
    return False


def parse_float_safe(value_str, default=0.0):
    """
    安全解析浮点数，处理各种异常格式

    功能用途:
        将CSV中的数值字符串转换为浮点数，处理空值、非数字字符、
        格式错误等异常情况。

    实现思路:
        1. 先清洗输入字符串
        2. 若清洗后为空，返回默认值
        3. 尝试使用float()转换
        4. 若转换失败（ValueError），返回默认值

    参数:
        value_str (str 或 None): 待解析的数值字符串
        default (float): 转换失败时的默认返回值，默认0.0

    返回:
        float: 解析后的浮点数
    """
    cleaned = clean_string(value_str, None)
    if cleaned is None:
        return default
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return default


def parse_int_safe(value_str, default=0):
    """
    安全解析整数，处理各种异常格式

    功能用途:
        将CSV中的数值字符串转换为整数，处理空值、非数字字符、
        小数格式等异常情况。

    实现思路:
        1. 先清洗输入字符串
        2. 若清洗后为空，返回默认值
        3. 先尝试int()直接转换
        4. 若失败则尝试float()再int()转换（处理"3.0"格式）
        5. 若仍然失败，返回默认值

    参数:
        value_str (str 或 None): 待解析的数值字符串
        default (int): 转换失败时的默认返回值，默认0

    返回:
        int: 解析后的整数
    """
    cleaned = clean_string(value_str, None)
    if cleaned is None:
        return default
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        try:
            return int(float(cleaned))
        except (ValueError, TypeError):
            return default


def is_valid_node_name(name):
    """
    验证节点名称是否有效

    功能用途:
        检查节点名称是否符合预期的命名规范，排除空字符串、
        纯空白字符串等无效名称。

    参数:
        name (str): 待验证的节点名称

    返回:
        bool: True表示有效，False表示无效
    """
    if name is None:
        return False
    if not isinstance(name, str):
        return False
    stripped = name.strip()
    return len(stripped) > 0


# ⚠️ 修复（2026-09-17 第三轮，用户决策 P1-(a)：模式过滤；2026-09-18 补丁③ Defender）==
# 语料的 src/dst 列里混有**非主机 token**，旧实现全部当节点计入分母/分子：
#   ① 阵营标签 'Red'/'Blue'（CAGE2/YT 导出器把动作主体写成阵营名）
#   ② CIDR 网段（pingsweep/discovery 的 dst 是子网网段，如 10.0.137.240/28）
#   ③ 蓝方 agent 标签 'Defender'（CAGE2/CAGE1 语料 blue_action_dst；
#      YT-PPO 语料 blue_action_src 同名——后者因 blue 目标列空实际不入节点集）
# 实测灌水：CAGE2 分母 +23~31%、CAGE4 +12%、CAGE1(C1-M) +1、YT +20~25%（CW 干净）。
# 判定：精确匹配阵营/agent 标签，或 CIDR 正则。**不动**蜜罐正则（decoy_NN 走 is_honey_node）。
_FACTION_LABELS = {'red', 'blue', 'defender'}
_CIDR_RE = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$')


def is_phantom_node_token(name: str) -> bool:
    n = name.strip().lower()
    return n in _FACTION_LABELS or bool(_CIDR_RE.match(n))


def split_targets(target_str):
    """
    将逗号分隔的目标字符串拆分为目标列表并清洗

    功能用途:
        解析CSV中以逗号分隔的目标字段（如red_action_dst、
        blue_action_target），去除空白和空字符串。

    实现思路:
        1. 清洗整个字符串
        2. 按逗号拆分为子串
        3. 对每个子串去空白，过滤空串
        4. 返回清洗后的目标列表

    参数:
        target_str (str 或 None): 逗号分隔的目标字符串

    返回:
        list: 清洗后的目标名称列表，可能为空列表
    """
    cleaned = clean_string(target_str, None)
    if cleaned is None:
        return []
    items = [item.strip() for item in cleaned.split(',')]
    return [item for item in items if item]


def classify_node_type(node_name, topology_data=None):
    """
    根据节点名称和拓扑信息分类节点类型

    功能用途:
        识别节点的类型归属，支持host、honey、dmz、server四种类型。
        优先根据命名模式判断，若拓扑数据可用则交叉验证并修正。

    实现思路:
        1. host类型：以'host'开头后跟数字（如host0、host19）
        2. honey类型：32位十六进制字符串（蜜罐节点hash标识）
        3. dmz类型：以'dmz'开头后跟数字（如dmz0）
        4. server类型：以'server'开头后跟数字（如server0）
        5. 若以上均不匹配，尝试从拓扑数据获取类型信息
        6. 仍无法确定则返回'other'

    参数:
        node_name (str): 节点名称
        topology_data (dict 或 None): 拓扑数据字典，用于交叉验证类型

    返回:
        str: 节点类型，可选值：'host', 'honey', 'dmz', 'server', 'other'
    """
    if not is_valid_node_name(node_name):
        return NODE_TYPE_OTHER

    name = node_name.strip().lower()

    if HOST_PATTERN.match(name):
        return NODE_TYPE_HOST

    if HONEY_PATTERN.match(name):
        return NODE_TYPE_HONEY

    # F3.2 修复: CW 确定性 decoy 命名（decoy_NN）识别为蜜罐
    if DECOY_PATTERN.match(name):
        return NODE_TYPE_HONEY

    # F1 修复: 通过拓扑 YAML 的 type 字段识别蜜罐
    if topology_data and topology_data.get('hosts'):
        host_info = topology_data['hosts'].get(node_name, {})
        topo_type = host_info.get('type', '').lower()
        if topo_type in ('honey', 'decoy'):
            return NODE_TYPE_HONEY

    if DMZ_PATTERN.match(name):
        return NODE_TYPE_DMZ

    if SERVER_PATTERN.match(name):
        return NODE_TYPE_SERVER

    if topology_data and topology_data.get('hosts'):
        host_info = topology_data['hosts'].get(node_name, {})
        topo_type = host_info.get('type', '')
        if topo_type == 'workstation':
            return NODE_TYPE_HOST
        if 'server' in topo_type.lower():
            return NODE_TYPE_SERVER
        # F2 修复: CAGE4 节点类型识别
        # CAGE4 节点如 contractor_network_subnet_user_host_4 → workstation
        # CAGE4 节点如 restricted_zone_a_subnet_server_host_0 → server
        if CAGE4_USER_HOST_RE.search(node_name):
            return NODE_TYPE_HOST
        if CAGE4_SERVER_HOST_RE.search(node_name):
            return NODE_TYPE_SERVER

    return NODE_TYPE_OTHER


def get_node_subnet(node_name, topology_data):
    """
    从拓扑数据中获取节点所属的子网名称

    功能用途:
        根据节点名称查询YAML拓扑数据，确定该节点属于哪个子网。
        拓扑数据中每个节点定义了其subnet属性，此函数进行安全查询。

    实现思路:
        1. 检查拓扑数据是否可用
        2. 从hosts中查找节点信息
        3. 返回subnet属性值

    参数:
        node_name (str): 节点名称
        topology_data (dict 或 None): 拓扑数据字典

    返回:
        str: 子网名称，若未找到则返回空字符串
    """
    if not topology_data or not topology_data.get('hosts'):
        return ''
    host_info = topology_data['hosts'].get(node_name)
    if host_info is None:
        return ''
    return host_info.get('subnet', '')


def parse_episode_csv(csv_file_path):
    """
    解析网络威胁过程CSV文件，提取红蓝双方的操作记录

    功能用途:
        逐行读取CSV格式的episode数据，清洗并验证每行数据的有效性，
        分别汇总红方攻击操作和蓝方防御操作，为后续统计计算做准备。

    实现思路:
        1. 以安全方式打开CSV文件，使用DictReader读取
        2. 对每一行，提取红方字段（action、src、dst、success、reward）
        3. 对每一行，提取蓝方字段（action、target、src、dst、success、reward）
        4. 记录每次成功deploy_decoy的step和目标子网
        5. 记录每个蜜罐节点首次被红方发现的step
        6. 根据deploy_history和honey_first_seen构建honey_subnet_map
        7. 对红方操作：若action和dst均有效，按dst拆分目标并累加统计
        8. 对蓝方操作：若action和target均有效，按target/src/dst合并目标并累加
        9. 记录行的总数量、跳过的无效行数量等元信息

    参数:
        csv_file_path (str): CSV episode文件路径

    返回:
        dict: 包含以下键的字典：
            - 'node_red' (dict): 红方按目标节点的操作汇总
            - 'node_blue' (dict): 蓝方按目标节点的操作汇总
            - 'honey_subnet_map' (dict): 蜜罐节点到部署子网的映射
            - 'total_rows' (int): CSV总行数
            - 'valid_rows' (int): 有效数据行数
            - 'skipped_rows' (int): 因数据异常跳过的行数

    异常:
        FileNotFoundError: CSV文件不存在时抛出
    """
    if not os.path.exists(csv_file_path):
        raise FileNotFoundError(f"CSV文件不存在: {csv_file_path}")

    node_red = {}
    node_blue = {}
    honey_first_seen = {}
    deployed_subnets = {}  # 修复 4(F11) 记录字段: {逻辑子网名: 首次成功部署 step}（不参与判定）
    deploy_history = []
    total_rows = 0
    skipped_rows = 0

    with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)

        if reader.fieldnames is None:
            raise ValueError(f"CSV文件缺少列头: {csv_file_path}")
        fieldnames = reader.fieldnames or []
        # Detect column naming convention (old vs new CW eval format)
        col_red_act = ('red_act' if 'red_act' in fieldnames
                       else ('red_action_name' if 'red_action_name' in fieldnames else 'red_action'))
        col_red_src = 'red_action_src' if 'red_action_src' in fieldnames else 'red_src'
        col_red_dst = 'red_dst' if 'red_dst' in fieldnames else ('red_action_dst' if 'red_action_dst' in fieldnames else 'red_action_dest')
        col_red_success = 'red_success' if 'red_success' in fieldnames else 'red_action_success'
        col_blue_act = ('blue_act' if 'blue_act' in fieldnames
                        else ('blue_action_name' if 'blue_action_name' in fieldnames else 'blue_action'))
        col_blue_dst = 'blue_dst' if 'blue_dst' in fieldnames else ('blue_action_dst' if 'blue_action_dst' in fieldnames else 'blue_action_dest')

        for row in reader:
            total_rows += 1

            step_raw = parse_int_safe(row.get('step', 0), 0)

            red_action = clean_string(row.get(col_red_act, ''))
            red_src = clean_string(row.get(col_red_src, ''))
            red_dst = clean_string(row.get(col_red_dst, ''))
            red_success = parse_bool(row.get(col_red_success, ''))
            red_reward = parse_float_safe(row.get('red_reward', 0), 0.0)

            blue_action = clean_string(row.get(col_blue_act, ''))
            blue_target_str = clean_string(row.get(col_blue_dst, ''))
            blue_src_str = clean_string(row.get('blue_action_src', ''))
            blue_dst_str = clean_string(row.get('blue_action_dst', ''))
            blue_success = parse_bool(row.get('blue_action_success', ''))
            blue_reward = parse_float_safe(row.get('blue_reward', 0), 0.0)

            # 修复 4(F11) 记录字段：收集子网级蜜罐部署（逻辑子网名 → 首次部署 step）。
            # 2026-09-04 决议：子网级蜜罐判定已移除，此字段仅作记录，不参与蜜罐判定
            if (blue_action in ('deploy_decoy', 'deploydecoy')
                    and blue_success
                    and blue_target_str):
                targets_deploy = split_targets(blue_target_str)
                for tgt in targets_deploy:
                    if is_valid_node_name(tgt):
                        deploy_history.append((step_raw, tgt))
                        if tgt not in deployed_subnets:
                            deployed_subnets[tgt] = step_raw

            if red_action and red_dst:
                targets_red = split_targets(red_dst)
                for target in targets_red:
                    if HONEY_PATTERN.match(target.strip().lower()):
                        if target not in honey_first_seen:
                            honey_first_seen[target] = step_raw

            row_has_data = False

            if red_action and red_dst:
                targets_red = split_targets(red_dst)
                for target in targets_red:
                    if not is_valid_node_name(target) or is_phantom_node_token(target):
                        continue
                    row_has_data = True
                    if target not in node_red:
                        node_red[target] = {
                            'total': 0, 'success': 0, 'failure': 0,
                            'actions': {}, 'rewards': []
                        }
                    node_red[target]['total'] += 1
                    if red_success:
                        node_red[target]['success'] += 1
                    else:
                        node_red[target]['failure'] += 1
                    node_red[target]['actions'][red_action] = (
                        node_red[target]['actions'].get(red_action, 0) + 1
                    )
                    node_red[target]['rewards'].append(red_reward)

            if blue_action and blue_target_str:
                targets_blue_raw = split_targets(blue_target_str)
                targets_blue_src = split_targets(blue_src_str)
                targets_blue_dst = split_targets(blue_dst_str)
                all_blue_targets = set(targets_blue_raw + targets_blue_src + targets_blue_dst)

                for target in all_blue_targets:
                    if not is_valid_node_name(target) or is_phantom_node_token(target):
                        continue
                    row_has_data = True
                    if target not in node_blue:
                        node_blue[target] = {
                            'total': 0, 'success': 0, 'failure': 0,
                            'actions': {}, 'rewards': []
                        }
                    node_blue[target]['total'] += 1
                    if blue_success:
                        node_blue[target]['success'] += 1
                    else:
                        node_blue[target]['failure'] += 1
                    node_blue[target]['actions'][blue_action] = (
                        node_blue[target]['actions'].get(blue_action, 0) + 1
                    )
                    node_blue[target]['rewards'].append(blue_reward)

            if not row_has_data:
                skipped_rows += 1

    valid_rows = total_rows - skipped_rows

    honey_subnet_map = {}
    if deploy_history and honey_first_seen:
        deploy_history.sort(key=lambda x: x[0])
        for honey_name, first_step in honey_first_seen.items():
            assigned_subnet = ''
            for dep_step, dep_subnet in deploy_history:
                if dep_step <= first_step:
                    assigned_subnet = dep_subnet
                else:
                    break
            if assigned_subnet:
                honey_subnet_map[honey_name] = assigned_subnet

    return {
        'node_red': node_red,
        'node_blue': node_blue,
        'honey_subnet_map': honey_subnet_map,
        'deployed_subnets': deployed_subnets,
        'total_rows': total_rows,
        'valid_rows': valid_rows,
        'skipped_rows': skipped_rows
    }


def compute_node_statistics(node_name, red_data, blue_data):
    """
    计算单个节点的详细攻击/防御统计信息

    功能用途:
        对单个节点，基于红方攻击和蓝方防御的汇总数据，
        计算成功率、reward的均值/最大值/最小值等衍生指标。

    实现思路:
        1. 从red_data/blue_data中获取该节点的原始统计数据
        2. 计算红方成功率、reward均值、最大值、最小值
        3. 计算蓝方成功率、reward均值、最大值、最小值
        4. 所有浮点数保留ROUND_DIGITS位小数
        5. 若总操作数为空，各统计值均为0或默认值

    参数:
        node_name (str): 节点名称
        red_data (dict): 红方操作汇总数据（parse_episode_csv返回的node_red）
        blue_data (dict): 蓝方操作汇总数据（parse_episode_csv返回的node_blue）

    返回:
        dict: 包含red_attacks和blue_defenses两个子字典的统计结果
    """
    red = red_data.get(node_name, {
        'total': 0, 'success': 0, 'failure': 0,
        'actions': {}, 'rewards': []
    })
    blue = blue_data.get(node_name, {
        'total': 0, 'success': 0, 'failure': 0,
        'actions': {}, 'rewards': []
    })

    red_total = red['total']
    red_success_rate = red['success'] / red_total if red_total > 0 else 0.0
    red_rewards = red['rewards']
    red_avg = statistics.mean(red_rewards) if red_rewards else 0.0
    red_max = max(red_rewards) if red_rewards else 0.0
    red_min = min(red_rewards) if red_rewards else 0.0

    blue_total = blue['total']
    blue_success_rate = blue['success'] / blue_total if blue_total > 0 else 0.0
    blue_rewards = blue['rewards']
    blue_avg = statistics.mean(blue_rewards) if blue_rewards else 0.0
    blue_max = max(blue_rewards) if blue_rewards else 0.0
    blue_min = min(blue_rewards) if blue_rewards else 0.0

    return {
        'red_attacks': {
            'total': red_total,
            'success': red['success'],
            'failure': red['failure'],
            'actions': dict(red['actions']),
            'rewards': list(red_rewards),
            'success_rate': round(red_success_rate, ROUND_DIGITS),
            'avg_reward': round(red_avg, ROUND_DIGITS),
            'max_reward': red_max,
            'min_reward': red_min
        },
        'blue_defenses': {
            'total': blue_total,
            'success': blue['success'],
            'failure': blue['failure'],
            'actions': dict(blue['actions']),
            'rewards': list(blue_rewards),
            'success_rate': round(blue_success_rate, ROUND_DIGITS),
            'avg_reward': round(blue_avg, ROUND_DIGITS),
            'max_reward': blue_max,
            'min_reward': blue_min
        }
    }


def build_node_table(all_node_names, detailed_stats, topology_data=None,
                     honey_subnet_map=None):
    """
    构建节点汇总表

    功能用途:
        将详细统计数据精简为node_table格式，每条记录包含节点名称、
        类型、红方总攻击数、成功率、攻击行为列表、蓝方总防御数、
        成功率、防御行为列表等核心字段。

    实现思路:
        1. 遍历所有节点名称
        2. 对每个节点，从detailed_stats获取红/蓝统计数据
        3. 调用classify_node_type确定节点类型
        4. 对蜜罐节点，优先从honey_subnet_map获取子网归属
        5. 对非蜜罐节点，调用get_node_subnet获取子网归属
        6. 提取action名称列表
        7. 组装node_table行记录

    参数:
        all_node_names (set): 所有节点名称集合
        detailed_stats (dict): compute_node_statistics的输出字典
        topology_data (dict 或 None): 拓扑数据字典
        honey_subnet_map (dict 或 None): 蜜罐节点到子网的映射，
                                         格式：{honey_hash: subnet_name}

    返回:
        list: node_table记录列表，每条记录为dict格式
    """
    if honey_subnet_map is None:
        honey_subnet_map = {}

    node_table = []
    for name in all_node_names:
        stats = detailed_stats.get(name, {})
        red = stats.get('red_attacks', {
            'total': 0, 'success_rate': 0.0, 'actions': {}
        })
        blue = stats.get('blue_defenses', {
            'total': 0, 'success_rate': 0.0, 'actions': {}
        })

        node_type = classify_node_type(name, topology_data)

        if node_type == NODE_TYPE_HONEY:
            subnet = honey_subnet_map.get(name, '')
        else:
            subnet = get_node_subnet(name, topology_data)

        red_action_list = list(red['actions'].keys())
        blue_action_list = list(blue['actions'].keys())

        node_table.append({
            'node_name': name,
            'node_type': node_type,
            'subnet': subnet,
            'red_total_attacks': red['total'],
            'red_success_rate': red['success_rate'],
            'red_actions': red_action_list,
            'blue_total_defenses': blue['total'],
            'blue_success_rate': blue['success_rate'],
            'blue_actions': blue_action_list
        })

    return node_table


def build_summary(all_node_names, topology_data):
    """
    构建预处理结果的总览信息

    功能用途:
        根据所有节点名称和拓扑数据，统计各类节点的数量和名称列表，
        包括host节点数、蜜罐节点数、dmz节点数、server节点数、
        子网信息等，为后续威胁评估提供总览数据。

    实现思路:
        1. 遍历all_node_names，对每个节点调用classify_node_type分类
        2. 将节点分别归入hosts、honeys、dmzs、servers列表
        3. 统计各类节点数量
        4. 从拓扑数据中提取子网数量和名称列表
        5. 统计拓扑中定义的总节点数
        6. 汇总组装summary字典

    参数:
        all_node_names (set): 所有节点名称集合
        topology_data (dict): 拓扑数据字典

    返回:
        dict: summary汇总字典
    """
    host_nodes = []
    honey_nodes = []
    dmz_nodes = []
    server_nodes = []

    for name in all_node_names:
        ntype = classify_node_type(name, topology_data)
        if ntype == NODE_TYPE_HOST:
            host_nodes.append(name)
        elif ntype == NODE_TYPE_HONEY:
            honey_nodes.append(name)
        elif ntype == NODE_TYPE_DMZ:
            dmz_nodes.append(name)
        elif ntype == NODE_TYPE_SERVER:
            server_nodes.append(name)

    subnet_names = []
    total_subnets = 0
    if topology_data and topology_data.get('all_subnet_names'):
        subnet_names = sorted(topology_data['all_subnet_names'])
        total_subnets = len(subnet_names)

    topology_total_nodes = 0
    if topology_data and topology_data.get('all_node_names'):
        topology_total_nodes = len(topology_data['all_node_names'])

    return {
        'total_nodes': len(all_node_names),
        'non_honey_node_count': len(all_node_names) - len(honey_nodes),
        'topology_nodes_total': topology_total_nodes,
        'host_nodes_count': len(host_nodes),
        'host_nodes': sorted(host_nodes),
        'honey_nodes_count': len(honey_nodes),
        'honey_nodes': sorted(honey_nodes),
        'dmz_nodes_count': len(dmz_nodes),
        'dmz_nodes': sorted(dmz_nodes),
        'server_nodes_count': len(server_nodes),
        'server_nodes': sorted(server_nodes),
        'total_subnets': total_subnets,
        'subnets': subnet_names
}


ASSET_VALUE_MAP = {
    'workstation': 1,
    'server': 3,
    'web_server': 3,
    'mail_server': 3,
    'ssh_jump_server': 3,
    'proxy_server': 3,
    'data_server': 5,
    'file_server': 5
}


def build_asset_values(all_node_names, topology_data):
    """
    根据YAML拓扑中节点的设备类型分配资产价值等级

    功能用途:
        从拓扑数据的hosts段读取每个节点的type属性，映射到对应的
        资产价值等级。蜜罐节点(honey)资产价值为0。

    实现思路:
        1. 遍历all_node_names
        2. 对每个节点调用classify_node_type判断类型
        3. 蜜罐节点资产价值=0
        4. 非蜜罐节点从YAML的hosts→type读取设备类型
        5. 通过ASSET_VALUE_MAP映射到资产价值整数(1/3/5)
        6. 未匹配的设备类型默认为1

    参数:
        all_node_names (set): 所有节点名称集合
        topology_data (dict): 拓扑数据字典

    返回:
        dict: {node_name: asset_value(int), ...}
    """
    asset_values = {}

    for name in all_node_names:
        ntype = classify_node_type(name, topology_data)

        if ntype == NODE_TYPE_HONEY:
            asset_values[name] = 0
            continue

        value = 1
        if topology_data and topology_data.get('hosts'):
            host_info = topology_data['hosts'].get(name)
            if host_info:
                # 修复 3: 优先读取 YAML 显式声明的 asset_value，
                # 仅当缺失时回退到 ASSET_VALUE_MAP 类型映射
                yaml_av = host_info.get('asset_value', None)
                if yaml_av is not None:
                    try:
                        value = int(yaml_av)
                    except (TypeError, ValueError):
                        device_type = host_info.get('type', '')
                        if device_type in ASSET_VALUE_MAP:
                            value = ASSET_VALUE_MAP[device_type]
                else:
                    device_type = host_info.get('type', '')
                    if device_type in ASSET_VALUE_MAP:
                        value = ASSET_VALUE_MAP[device_type]

        asset_values[name] = value

    return asset_values


def preprocess_data(yaml_file_path, csv_file_path, output_file_path):
    """
    主预处理函数：加载拓扑和episode数据，生成processed.json

    功能用途:
        整合网络拓扑数据和威胁过程数据，通过数据清洗、格式转换、
        特征提取等预处理步骤，生成标准化的processed.json文件，
        供后续威胁评估指标体系使用。

    实现思路:
        1. 加载YAML网络拓扑数据（节点信息、子网划分、拓扑结构）
        2. 加载CSV episode数据（红方攻击、蓝方防御操作记录）
        3. 合并拓扑节点和CSV中出现的节点，形成完整节点列表
        4. 对每个节点计算红/蓝双方的详细统计指标
        5. 构建node_table汇总表
        6. 构建summary总览信息
        7. 组装最终结果并写入JSON文件

    参数:
        yaml_file_path (str): YAML拓扑文件路径
        csv_file_path (str): CSV episode文件路径
        output_file_path (str): 输出JSON文件路径

    返回:
        dict: 预处理结果字典，包含以下键：
            - 'summary' (dict): 总览统计信息
            - 'node_table' (list): 节点汇总表
            - 'detailed_stats' (dict): 节点详细统计
            - 'topology_map' (dict): 拓扑结构映射

    异常:
        FileNotFoundError: 输入文件不存在时抛出
        yaml.YAMLError: YAML格式错误时抛出
        ValueError: CSV格式异常时抛出
    """
    if not os.path.exists(yaml_file_path):
        raise FileNotFoundError(f"拓扑文件不存在: {yaml_file_path}")
    if not os.path.exists(csv_file_path):
        raise FileNotFoundError(f"CSV文件不存在: {csv_file_path}")

    topology_data = load_network_topology(yaml_file_path)
    episode_data = parse_episode_csv(csv_file_path)

    node_red = episode_data['node_red']
    node_blue = episode_data['node_blue']

    all_node_names = set(list(node_red.keys()) + list(node_blue.keys()))
    topology_node_names = topology_data.get('all_node_names', set())
    all_node_names = all_node_names | topology_node_names

    subnet_names = set(topology_data.get('all_subnet_names', set()) or set())
    # ⚠️ 修复（2026-09-17，C1 重跑暴露）：`all_subnet_names` 存的是**拓扑内部键**
    # （subnet0/1/2），而语料/日志里的子网往往以 **YAML 逻辑名**（`_orig_name`，如
    # dmz_subnet）出现 ⇒ 旧实现减不掉它们，逻辑名被当成普通节点计入 `all_node_names`
    # （进而进 total_asset_value / 分母），形成"幻影子网资产"。CW 侧 B 臂的 deploy_decoy
    # 行一直携带该别名，2026-09-17 起 remove_decoy 行也携带（N1 修复）⇒ 影响面扩大。
    # 修法：把逻辑名并入排除集（hosts 与 subnet 同名在本项目拓扑中不存在）。
    subnet_names |= {info.get(k) for info in
                     (topology_data.get('subnets', {}) or {}).values()
                     if isinstance(info, dict)
                     for k in ('_orig_name', '_orig_name_declared') if info.get(k)}
    all_node_names = all_node_names - subnet_names

    detailed_stats = {}
    for name in all_node_names:
        detailed_stats[name] = compute_node_statistics(name, node_red, node_blue)

    node_table = build_node_table(all_node_names, detailed_stats, topology_data,
                                  episode_data.get('honey_subnet_map'))
    summary = build_summary(all_node_names, topology_data)
    asset_values = build_asset_values(all_node_names, topology_data)

    topology_map = {}
    if topology_data:
        topology_map = {
            'subnets': topology_data.get('subnets', {}),
            'topology': topology_data.get('topology', {}),
            'interfaces': topology_data.get('interfaces', {})
        }

    # 修复 4(F11) 记录字段：将 deploy_decoy 的逻辑子网名（如 dmz_subnet）映射为
    # topology 子网键（如 subnet0）。2026-09-04 决议：仅作记录，不参与蜜罐判定
    deployed_subnets_topo = {}
    orig_to_key = {}
    for key, info in (topology_data.get('subnets', {}) or {}).items():
        orig = info.get('_orig_name', '') if isinstance(info, dict) else ''
        if orig:
            orig_to_key[orig] = key
    for orig_name, dep_step in (episode_data.get('deployed_subnets', {}) or {}).items():
        key = orig_to_key.get(orig_name, orig_name)
        if key not in deployed_subnets_topo or dep_step < deployed_subnets_topo[key]:
            deployed_subnets_topo[key] = dep_step

    result = {
        'summary': summary,
        'node_table': node_table,
        'detailed_stats': detailed_stats,
        'topology_map': topology_map,
        'asset_values': asset_values,
        'deployed_subnets': deployed_subnets_topo
    }

    output_dir = os.path.dirname(output_file_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Preprocessing complete, result saved to {output_file_path}")
    print(f"Total nodes: {len(all_node_names)}")
    print(f"Host nodes: {summary['host_nodes_count']}")
    print(f"Honeypot nodes: {summary['honey_nodes_count']}")
    print(f"DMZ nodes: {summary['dmz_nodes_count']}")
    print(f"Server nodes: {summary['server_nodes_count']}")
    print(f"Subnets: {summary['total_subnets']}")

    return result


if __name__ == "__main__":
    import sys

    DEFAULT_YAML = "40-host-network.yaml"
    DEFAULT_CSV = "demo/episode_90_20260131_050414.csv"   # v9.3：演示资产移入 demo/
    DEFAULT_OUTPUT = "data/processed.json"

    yaml_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_YAML
    csv_file = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_CSV
    output_file = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_OUTPUT

    preprocess_data(yaml_file, csv_file, output_file)
