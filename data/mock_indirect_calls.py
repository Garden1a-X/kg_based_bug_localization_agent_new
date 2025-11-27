"""
Mock 间接调用关系数据
TODO: 临时模块，等知识图谱修复 ASSIGNED_TO 关系后删除

这个模块存放已知的间接调用关系，用于在图谱数据不完整时测试框架逻辑。
包括：
1. 异步调用（work_struct）
2. 函数指针（ops 表）

注意：
- 自 2024年 起，图谱已支持 CALLS 关系的 call_type="indirect" 标记
- 新的图谱结构中，间接调用的 tail 指向 FIELD 实体
- 通过查询 ASSIGNED_TO 关系即可获取目标函数
- 因此，MOCK_ASYNC_CALLS 和 MOCK_FUNCTION_POINTER_CALLS 已被注释掉
- 仅保留 MOCK_ASYNC_ASSIGNED_TO 作为 fallback
"""

# ============================================================
# TODO: 等图谱修复后删除这个文件
# ============================================================

# ============================================================
# 已注释：异步调用关系（已由图谱的 CALLS + ASSIGNED_TO 代替）
# ============================================================
# # 异步调用关系（工作队列）
# # 格式：{(caller_func, callee_func): bridge_info}
# MOCK_ASYNC_CALLS = {
#     # [位置8] mmc_schedule_delayed_work 异步调度 mmc_rescan
#     # 这是16节点完整路径中的真实异步调用断点
#     ("mmc_schedule_delayed_work", "mmc_rescan"): {
#         "bridge_type": "async",
#         "bridge_entity": "work_struct.func",
#         "init_func": "INIT_DELAYED_WORK",
#         "description": "mmc_schedule_delayed_work 通过 work_struct 异步调度 mmc_rescan"
#     },
#     # 可以添加更多已知的异步调用关系
# }
MOCK_ASYNC_CALLS = {}  # 已注释，保留空字典用于兼容性

# ============================================================
# 已注释：函数指针调用关系（已由图谱的 CALLS + ASSIGNED_TO 代替）
# ============================================================
# # 函数指针调用关系（ops 表）
# # 格式：{(caller_func, callee_func): bridge_info}
# MOCK_FUNCTION_POINTER_CALLS = {
#     # [位置14] mmc_execute_tuning → dw_mci_execute_tuning（函数指针/ops调用）
#     ("mmc_execute_tuning", "dw_mci_execute_tuning"): {
#         "bridge_type": "function_pointer",
#         "bridge_entity": "mmc_host_ops.execute_tuning",
#         "struct_name": "dw_mci_ops",
#         "field_name": "execute_tuning",
#         "description": "host->ops->execute_tuning() 指向 dw_mci_execute_tuning"
#     },
#
#     # [位置15] dw_mci_execute_tuning → dw_mci_hi3660_execute_tuning（函数指针/平台特定ops）
#     ("dw_mci_execute_tuning", "dw_mci_hi3660_execute_tuning"): {
#         "bridge_type": "function_pointer",
#         "bridge_entity": "dw_mci_drv_data.execute_tuning",
#         "struct_name": "dw_mci_drv_data",
#         "field_name": "execute_tuning",
#         "description": "平台特定的 execute_tuning 实现"
#     },
#
#     # 可以添加更多已知的函数指针关系
# }
MOCK_FUNCTION_POINTER_CALLS = {}  # 已注释，保留空字典用于兼容性

# 异步调用 ASSIGNED_TO 关系（字段赋值）
# 格式：{field_name: [function_names]}
# 表示哪些函数被赋值给了某个字段
MOCK_ASYNC_ASSIGNED_TO = {
    # detect 字段被赋值为 mmc_rescan
    # 例如：INIT_DELAYED_WORK(&host->detect, mmc_rescan)
    "detect": ["mmc_rescan"],

    # 可以添加更多字段赋值关系
    # "work": ["some_callback_func"],
}


def get_mock_async_bridge(caller: str, callee: str) -> dict:
    """
    获取 mock 的异步调用桥接信息

    TODO: 等图谱修复后删除此函数

    Args:
        caller: 调用者函数名
        callee: 被调用者函数名

    Returns:
        桥接信息 dict 或 None
    """
    return MOCK_ASYNC_CALLS.get((caller, callee))


def get_mock_function_pointer_bridge(caller: str, callee: str) -> dict:
    """
    获取 mock 的函数指针桥接信息

    TODO: 等图谱修复后删除此函数

    Args:
        caller: 调用者函数名
        callee: 被调用者函数名

    Returns:
        桥接信息 dict 或 None
    """
    return MOCK_FUNCTION_POINTER_CALLS.get((caller, callee))


def has_mock_indirect_call(caller: str, callee: str) -> bool:
    """
    检查是否存在 mock 的间接调用关系

    TODO: 等图谱修复后删除此函数

    Args:
        caller: 调用者函数名
        callee: 被调用者函数名

    Returns:
        是否存在间接调用关系
    """
    return (
        (caller, callee) in MOCK_ASYNC_CALLS or
        (caller, callee) in MOCK_FUNCTION_POINTER_CALLS
    )


def get_all_mock_relations():
    """
    获取所有 mock 关系（用于调试）

    TODO: 等图谱修复后删除此函数

    Returns:
        所有 mock 关系的列表
    """
    relations = []

    for (caller, callee), info in MOCK_ASYNC_CALLS.items():
        relations.append({
            "type": "async",
            "caller": caller,
            "callee": callee,
            "info": info
        })

    for (caller, callee), info in MOCK_FUNCTION_POINTER_CALLS.items():
        relations.append({
            "type": "function_pointer",
            "caller": caller,
            "callee": callee,
            "info": info
        })

    return relations


def get_mock_indirect_callees(caller: str) -> list:
    """
    获取某个函数的所有 mock 间接调用目标

    TODO: 等图谱修复后删除此函数

    Args:
        caller: 调用者函数名

    Returns:
        [(callee, bridge_info), ...] 列表
    """
    indirect_callees = []

    # 检查异步调用
    for (c, callee), info in MOCK_ASYNC_CALLS.items():
        if c == caller:
            indirect_callees.append((callee, info))

    # 检查函数指针
    for (c, callee), info in MOCK_FUNCTION_POINTER_CALLS.items():
        if c == caller:
            indirect_callees.append((callee, info))

    return indirect_callees


def get_mock_async_assigned_to(field_name: str) -> list:
    """
    获取 mock 的异步调用 ASSIGNED_TO 关系

    TODO: 等图谱修复后删除此函数

    Args:
        field_name: 字段名（如 'detect'）

    Returns:
        被赋值给该字段的函数名列表（如 ['mmc_rescan']）
    """
    return MOCK_ASYNC_ASSIGNED_TO.get(field_name, [])


# ============================================================
# 失败消息实体和关系（新增）
# TODO: 等图谱包含FAIL_MESSAGE和FAIL_TEMPLATE后删除
# ============================================================

# FAIL_MESSAGE 实体
# 从源码中的错误打印语句提取的失败消息
# 字段严格遵循图谱定义，不添加额外字段
MOCK_FAIL_MESSAGES = {
    "msg_4157273": {
        "id": "4157273",
        "name": 'dev_err(host->dev, "All phases bad!\\n")',
        "type": "FAIL_MESSAGE",
        "scope": "dw_mci_hi3660_execute_tuning",
        "source_file": "drivers/mmc/host/dw_mmc-hi3660.c",
        "start_line": 150,
        "end_line": 150
    },
    "msg_4157274": {
        "id": "4157274",
        "name": 'pr_err("%s: tuning execution failed: %d\\n", mmc_hostname(host), err)',
        "type": "FAIL_MESSAGE",
        "scope": "mmc_execute_tuning",
        "source_file": "drivers/mmc/core/core.c",
        "start_line": 1200,
        "end_line": 1201
    },
    "msg_4157275": {
        "id": "4157275",
        "name": 'pr_err("%s: error %d whilst initialising MMC card\\n", mmc_hostname(host), err)',
        "type": "FAIL_MESSAGE",
        "scope": "mmc_attach_mmc",
        "source_file": "drivers/mmc/core/mmc.c",
        "start_line": 2100,
        "end_line": 2101
    },
    # 干扰项：相同的错误消息在不同函数中
    "msg_4157276": {
        "id": "4157276",
        "name": 'dev_err(host->dev, "All phases bad!\\n")',
        "type": "FAIL_MESSAGE",
        "scope": "dw_mci_rk3288_execute_tuning",
        "source_file": "drivers/mmc/host/dw_mmc-rk3288.c",
        "start_line": 200,
        "end_line": 200
    }
}

# HAS_MESSAGE 关系
# 格式：{function_name: [message_ids]}
# 表示某个函数包含哪些失败消息
MOCK_HAS_MESSAGE_RELATIONS = {
    "dw_mci_hi3660_execute_tuning": ["msg_4157273"],
    "mmc_execute_tuning": ["msg_4157274"],
    "mmc_attach_mmc": ["msg_4157275"],
    "dw_mci_rk3288_execute_tuning": ["msg_4157276"]  # 干扰项
}


def get_mock_fail_messages() -> dict:
    """
    获取所有 mock 的失败消息实体

    TODO: 等图谱修复后删除此函数

    Returns:
        失败消息实体字典
    """
    return MOCK_FAIL_MESSAGES


def get_mock_fail_message_by_id(msg_id: str) -> dict:
    """
    根据ID获取失败消息实体

    TODO: 等图谱修复后删除此函数

    Args:
        msg_id: 消息ID

    Returns:
        失败消息实体 dict 或 None
    """
    return MOCK_FAIL_MESSAGES.get(msg_id)


def get_mock_messages_by_function(func_name: str) -> list:
    """
    获取某个函数的所有失败消息

    TODO: 等图谱修复后删除此函数

    Args:
        func_name: 函数名

    Returns:
        失败消息实体列表 [message_dict, ...]
    """
    msg_ids = MOCK_HAS_MESSAGE_RELATIONS.get(func_name, [])
    return [MOCK_FAIL_MESSAGES[msg_id] for msg_id in msg_ids if msg_id in MOCK_FAIL_MESSAGES]


def _extract_message_pattern(fail_message_name: str) -> str:
    """
    从FAIL_MESSAGE的name字段提取用于日志匹配的模式

    Args:
        fail_message_name: FAIL_MESSAGE实体的name字段（如 'pr_err("xxx", ...)'）

    Returns:
        用于匹配的正则模式
    """
    import re

    # 提取引号内的字符串
    # 匹配第一个双引号内的内容
    string_match = re.search(r'"([^"]+)"', fail_message_name)
    if not string_match:
        return None

    template = string_match.group(1)

    # 将格式化占位符替换为通配符
    # %s, %d, %u, %x 等 -> .*
    pattern = re.sub(r'%[sduxXfgGp]', r'.*?', template)

    # 转义特殊字符
    pattern = re.escape(pattern)

    # 还原通配符（之前被escape了）
    pattern = pattern.replace(r'\.\*\?', '.*?')

    # 移除换行符标记
    pattern = pattern.replace(r'\\n', '')

    return pattern


def match_log_to_fail_messages(log_text: str) -> list:
    """
    从日志文本匹配到失败消息实体

    TODO: 等图谱修复后删除此函数

    Args:
        log_text: 错误日志文本

    Returns:
        匹配到的失败消息列表 [(msg_dict, matched_text), ...]
    """
    import re

    matches = []
    for msg_id, msg_data in MOCK_FAIL_MESSAGES.items():
        # 从name字段提取匹配模式
        pattern = _extract_message_pattern(msg_data.get('name', ''))
        if pattern and re.search(pattern, log_text, re.IGNORECASE):
            # 提取匹配的文本
            match_obj = re.search(pattern, log_text, re.IGNORECASE)
            matched_text = match_obj.group(0) if match_obj else ''
            matches.append((msg_data, matched_text))

    return matches


def get_functions_from_log(log_text: str) -> list:
    """
    从日志文本推断相关的函数（基于失败消息匹配）

    TODO: 等图谱修复后删除此函数

    Args:
        log_text: 错误日志文本

    Returns:
        相关函数名列表 [func_name, ...]
    """
    matches = match_log_to_fail_messages(log_text)
    functions = []

    for msg_data, _ in matches:
        func_name = msg_data.get('scope')
        if func_name and func_name not in functions:
            functions.append(func_name)

    return functions

