#!/usr/bin/env python3
"""
调试 CALL 关系查询问题
用于排查为什么手动能找到但查询找不到的调用关系
"""
import sys
from pathlib import Path
from data.kg_interface import KnowledgeGraphInterface

def debug_call_relation(data_dir: str, caller_name: str, callee_name: str):
    """
    调试 caller -> callee 的调用关系

    Args:
        data_dir: 数据目录
        caller_name: 调用者函数名
        callee_name: 被调用者函数名
    """
    print(f"\n{'='*80}")
    print(f"调试 CALL 关系: {caller_name} -> {callee_name}")
    print(f"{'='*80}\n")

    # 初始化 KG
    kg = KnowledgeGraphInterface(data_dir)

    # ========== 步骤1: 查找 caller 实体 ==========
    print(f"[步骤1] 查找 caller 实体: {caller_name}")
    caller_entities = [e for e in kg.entity_by_id.values()
                       if e.get('name') == caller_name and e.get('type') == 'FUNCTION']

    if not caller_entities:
        print(f"  ❌ 未找到函数: {caller_name}")
        return

    print(f"  ✓ 找到 {len(caller_entities)} 个同名实体:")
    for e in caller_entities:
        print(f"    - ID={e['id']}, file={e.get('source_file', 'N/A')}")

    # ========== 步骤2: 查找 callee 实体 ==========
    print(f"\n[步骤2] 查找 callee 实体: {callee_name}")
    callee_entities = [e for e in kg.entity_by_id.values()
                       if e.get('name') == callee_name and e.get('type') == 'FUNCTION']

    if not callee_entities:
        print(f"  ❌ 未找到函数: {callee_name}")
        return

    print(f"  ✓ 找到 {len(callee_entities)} 个同名实体:")
    for e in callee_entities:
        print(f"    - ID={e['id']}, file={e.get('source_file', 'N/A')}")

    # ========== 步骤3: 检查等价 ID ==========
    print(f"\n[步骤3] 检查等价 ID（声明/实现）")
    for caller_entity in caller_entities:
        caller_id = caller_entity['id']
        equiv_ids = kg.get_equivalent_ids(caller_id)
        print(f"  caller ID={caller_id}:")
        print(f"    等价 IDs: {equiv_ids}")

    # ========== 步骤4: 遍历所有 CALLS 关系，查找匹配的 ==========
    print(f"\n[步骤4] 遍历 CALLS 关系")

    if 'CALLS' not in kg.relations:
        print("  ❌ 图谱中没有 CALLS 关系")
        return

    print(f"  图谱共有 {len(kg.relations['CALLS'])} 条 CALLS 关系")

    matched_relations = []
    for caller_entity in caller_entities:
        caller_id = caller_entity['id']
        equiv_ids = kg.get_equivalent_ids(caller_id)

        print(f"\n  检查 caller ID={caller_id} (等价IDs={equiv_ids}):")

        for rel in kg.relations['CALLS']:
            head_id = rel.get('head')
            tail_id = rel.get('tail')

            # 检查 head 是否匹配
            if head_id not in equiv_ids:
                continue

            # 打印所有从这个 caller 出发的 CALLS
            tail_entity = kg.entity_by_id.get(kg.normalize_id(tail_id))
            tail_name = tail_entity.get('name', 'UNKNOWN') if tail_entity else 'NOT_FOUND'

            print(f"    → tail ID={tail_id}, name={tail_name}, call_line={rel.get('call_line')}")

            # 检查是否匹配目标 callee
            if tail_name == callee_name:
                matched_relations.append(rel)
                print(f"      ✓ 匹配目标 callee!")

    # ========== 步骤5: 检查 ioctl_call 关系 ==========
    print(f"\n[步骤5] 检查 ioctl_call 关系")

    if 'ioctl_call' not in kg.relations:
        print("  ⓘ 图谱中没有 ioctl_call 关系")
    else:
        print(f"  图谱共有 {len(kg.relations['ioctl_call'])} 条 ioctl_call 关系")

        for caller_entity in caller_entities:
            caller_id = caller_entity['id']
            equiv_ids = kg.get_equivalent_ids(caller_id)

            print(f"\n  检查 caller ID={caller_id}:")

            for rel in kg.relations['ioctl_call']:
                head_id = rel.get('head')
                tail_raw = rel.get('tail')

                if head_id not in equiv_ids:
                    continue

                tail_ids = tail_raw if isinstance(tail_raw, list) else [tail_raw]

                for tail_id in tail_ids:
                    tail_entity = kg.entity_by_id.get(kg.normalize_id(tail_id))
                    tail_name = tail_entity.get('name', 'UNKNOWN') if tail_entity else 'NOT_FOUND'

                    print(f"    → tail ID={tail_id}, name={tail_name}")

                    if tail_name == callee_name:
                        matched_relations.append(rel)
                        print(f"      ✓ 匹配目标 callee!")

    # ========== 步骤6: 使用查询接口测试 ==========
    print(f"\n[步骤6] 使用查询接口测试")

    for caller_entity in caller_entities:
        caller_id = caller_entity['id']
        print(f"\n  测试 caller ID={caller_id}:")

        # 使用 _get_callees_with_lines 查询
        callees = kg._get_callees_with_lines(caller_id)
        print(f"    _get_callees_with_lines 返回 {len(callees)} 个 callee:")

        for callee_name_result, call_line, is_indirect in callees:
            marker = "✓" if callee_name_result == callee_name else " "
            print(f"      {marker} {callee_name_result} (line={call_line}, indirect={is_indirect})")

    # ========== 总结 ==========
    print(f"\n{'='*80}")
    print(f"总结:")
    if matched_relations:
        print(f"  ✓ 在图谱中找到 {len(matched_relations)} 条匹配的关系")
        for rel in matched_relations:
            print(f"    - {rel}")
    else:
        print(f"  ❌ 在图谱中未找到匹配的关系")
        print(f"\n  可能的原因:")
        print(f"    1. 关系的 head/tail ID 不匹配（检查 ID 标准化）")
        print(f"    2. 关系类型不是 CALLS 或 ioctl_call")
        print(f"    3. 关系加载时被过滤掉了")
        print(f"    4. 等价 ID 处理有问题")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("用法: python debug_call_relation.py <数据目录> <caller名称> <callee名称>")
        print("示例: python debug_call_relation.py /data/xuao/.../data dw_mci_probe mmc_add_host")
        sys.exit(1)

    data_dir = sys.argv[1]
    caller_name = sys.argv[2]
    callee_name = sys.argv[3]

    debug_call_relation(data_dir, caller_name, callee_name)
