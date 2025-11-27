"""
测试基于图谱 ASSIGNED_TO 关系的间接调用检测

验证：
1. query_assigned_to_by_field_name() 方法
2. _get_callees_with_lines() 处理间接调用
3. BFS 搜索能否正确处理间接调用
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from data.kg_interface import KnowledgeGraphInterface
from utils.logger import setup_logger, print_header
from loguru import logger


def test_query_assigned_to():
    """测试 query_assigned_to_by_field_name() 方法"""
    print_header("测试 ASSIGNED_TO 查询")

    # 指定数据目录
    data_dir = "/data/xuao/code_kg_search/linux_test/data/mmc"
    if not os.path.exists(data_dir):
        data_dir = "/data/xuao/code_kg_search/linux_test/data"
        print(f"注意: MMC子图不存在，使用完整图谱 ({data_dir})")

    kg = KnowledgeGraphInterface(data_dir)

    # 测试一些已知的字段名
    test_fields = [
        "execute_tuning",  # 函数指针字段（MMC ops）
        "detect",          # 异步work字段
        "func",            # 通用work字段
        "init",            # 可能的初始化字段
    ]

    print("\n" + "="*60)
    print("测试字段名到函数的 ASSIGNED_TO 查询:")
    print("="*60)

    for field_name in test_fields:
        print(f"\n查询字段: {field_name}")
        print("-" * 40)

        functions = kg.query_assigned_to_by_field_name(field_name)

        if functions:
            print(f"✓ 找到 {len(functions)} 个目标函数:")
            for func in functions[:5]:  # 最多显示5个
                print(f"  - {func}")
            if len(functions) > 5:
                print(f"  ... 还有 {len(functions) - 5} 个")
        else:
            print(f"✗ 未找到目标函数")

    kg.close()


def test_get_callees_with_indirect():
    """测试 _get_callees_with_lines() 处理间接调用"""
    print_header("测试获取被调用函数（含间接调用）")

    data_dir = "/data/xuao/code_kg_search/linux_test/data/mmc"
    if not os.path.exists(data_dir):
        data_dir = "/data/xuao/code_kg_search/linux_test/data"

    kg = KnowledgeGraphInterface(data_dir)

    # 测试一些已知的函数（可能有间接调用）
    test_funcs = [
        "mmc_execute_tuning",           # 应该有函数指针调用
        "dw_mci_execute_tuning",        # 应该有函数指针调用
        "mmc_schedule_delayed_work",    # 可能有异步调用
    ]

    print("\n" + "="*60)
    print("测试函数的被调用者（含间接调用）:")
    print("="*60)

    for func_name in test_funcs:
        print(f"\n函数: {func_name}")
        print("-" * 40)

        # 获取函数ID
        func_entity = kg.find_function(func_name)
        if not func_entity:
            print(f"✗ 函数不存在")
            continue

        func_id = func_entity.get('id')
        if not func_id:
            print(f"✗ 函数没有ID")
            continue

        # 获取被调用函数（含行号）
        callees = kg._get_callees_with_lines(func_id)

        if callees:
            print(f"✓ 找到 {len(callees)} 个被调用函数:")
            for callee_name, call_line in callees[:10]:  # 最多显示10个
                line_str = f"行{call_line}" if call_line else "无行号"
                print(f"  - {callee_name} ({line_str})")
            if len(callees) > 10:
                print(f"  ... 还有 {len(callees) - 10} 个")
        else:
            print(f"✗ 未找到被调用函数")

    kg.close()


def test_bfs_with_indirect():
    """测试 BFS 搜索能否处理间接调用"""
    print_header("测试 BFS 搜索（含间接调用）")

    data_dir = "/data/xuao/code_kg_search/linux_test/data/mmc"
    if not os.path.exists(data_dir):
        data_dir = "/data/xuao/code_kg_search/linux_test/data"

    kg = KnowledgeGraphInterface(data_dir)

    # 测试已知的路径（应该包含间接调用）
    test_cases = [
        {
            "start": "dw_mci_pltfm_probe",
            "end": "dw_mci_hi3660_execute_tuning",
            "description": "完整路径（应该包含多个间接调用）"
        },
        {
            "start": "mmc_execute_tuning",
            "end": "dw_mci_execute_tuning",
            "description": "函数指针调用路径"
        },
    ]

    print("\n" + "="*60)
    print("测试路径搜索:")
    print("="*60)

    for case in test_cases:
        start = case["start"]
        end = case["end"]
        desc = case["description"]

        print(f"\n测试: {desc}")
        print(f"  起点: {start}")
        print(f"  终点: {end}")
        print("-" * 40)

        # 搜索路径（Top-3）
        paths = kg.find_top_k_call_paths_with_indirect(
            start=start,
            end=end,
            max_depth=30,
            k=3,
            debug=False  # 不输出详细调试信息
        )

        if paths:
            print(f"✓ 找到 {len(paths)} 条路径:")
            for idx, path_info in enumerate(paths):
                path = path_info['path']
                edges = path_info['edges']
                indirect_count = path_info['indirect_count']
                score = path_info['score']

                print(f"\n  路径 #{idx+1}: 长度={len(path)}, 间接调用={indirect_count}, 得分={score:.1f}")

                # 显示路径（简化）
                if len(path) <= 5:
                    path_str = ' → '.join(path)
                else:
                    path_str = ' → '.join(path[:3]) + ' → ... → ' + ' → '.join(path[-2:])
                print(f"    {path_str}")

                # 检查是否有间接调用边
                indirect_edges = [e for e in edges if isinstance(e, dict)]
                if indirect_edges:
                    print(f"    包含 {len(indirect_edges)} 个间接调用:")
                    for e in indirect_edges[:3]:
                        bridge_type = e.get('bridge', {}).get('bridge_type', 'unknown')
                        bridge_entity = e.get('bridge', {}).get('bridge_entity', 'unknown')
                        print(f"      - {bridge_type}: {bridge_entity}")
        else:
            print(f"✗ 未找到路径")

    kg.close()


def test_calls_relation_structure():
    """测试 CALLS 关系的结构（检查是否有新的字段）"""
    print_header("检查 CALLS 关系结构")

    data_dir = "/data/xuao/code_kg_search/linux_test/data/mmc"
    if not os.path.exists(data_dir):
        data_dir = "/data/xuao/code_kg_search/linux_test/data"

    kg = KnowledgeGraphInterface(data_dir)

    if 'CALLS' not in kg.relations:
        print("✗ 图谱中没有 CALLS 关系")
        kg.close()
        return

    calls_relations = kg.relations['CALLS']

    print(f"\n总共有 {len(calls_relations)} 条 CALLS 关系")

    # 统计有 call_type 字段的关系
    with_call_type = [r for r in calls_relations if 'call_type' in r]
    indirect_calls = [r for r in calls_relations if r.get('call_type') == 'indirect']

    print(f"包含 call_type 字段的: {len(with_call_type)} 条")
    print(f"其中 indirect 调用: {len(indirect_calls)} 条")

    if indirect_calls:
        print("\n示例间接调用关系（前5个）:")
        for i, rel in enumerate(indirect_calls[:5]):
            head_id = rel.get('head')
            tail_id = rel.get('tail')
            call_type = rel.get('call_type')
            target_type = rel.get('target_type')
            field_path = rel.get('field_path', [])

            # 获取函数名
            head_entity = kg.entity_by_id.get(head_id)
            tail_entity = kg.entity_by_id.get(tail_id)

            head_name = head_entity.get('name') if head_entity else f"ID:{head_id}"
            tail_name = tail_entity.get('name') if tail_entity else f"ID:{tail_id}"
            tail_type = tail_entity.get('type') if tail_entity else 'unknown'

            print(f"\n  #{i+1}:")
            print(f"    调用者: {head_name}")
            print(f"    目标: {tail_name} (类型: {tail_type})")
            print(f"    call_type: {call_type}")
            print(f"    target_type: {target_type}")
            print(f"    field_path: {field_path}")
    else:
        print("\n⚠ 未发现任何 indirect 调用关系")
        print("  这可能意味着：")
        print("  1. 图谱还未更新到新的结构")
        print("  2. 或者该子图中确实没有间接调用")

    kg.close()


def main():
    """主函数"""
    setup_logger()

    # 运行所有测试
    test_calls_relation_structure()
    print("\n" + "="*80 + "\n")

    test_query_assigned_to()
    print("\n" + "="*80 + "\n")

    test_get_callees_with_indirect()
    print("\n" + "="*80 + "\n")

    test_bfs_with_indirect()

    print("\n" + "="*80)
    print("测试完成！")
    print("="*80)


if __name__ == "__main__":
    main()
