#!/usr/bin/env python3
"""
直接测试图谱中的调用关系
用于诊断 BFS 搜索问题
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from data.kg_interface import KnowledgeGraphInterface


def test_direct_call(data_dir: str, start_func: str, end_func: str):
    """测试从起点到终点的直接调用"""

    print("=" * 80)
    print("图谱调用关系测试")
    print("=" * 80)

    kg = KnowledgeGraphInterface(data_dir)

    try:
        # 1. 检查起点是否存在
        print(f"\n[1] 检查起点函数: {start_func}")
        start_nodes = kg.search_entity_by_name(start_func, entity_type='FUNCTION')
        if start_nodes:
            print(f"    ✓ 找到起点: {len(start_nodes)} 个节点")
            for node in start_nodes:
                print(f"      - ID: {node.get('id')}, 文件: {node.get('source_file', 'N/A')}")
        else:
            print(f"    ✗ 未找到起点")
            return

        # 2. 检查终点是否存在
        print(f"\n[2] 检查终点函数: {end_func}")
        end_nodes = kg.search_entity_by_name(end_func, entity_type='FUNCTION')
        if end_nodes:
            print(f"    ✓ 找到终点: {len(end_nodes)} 个节点")
            for node in end_nodes:
                print(f"      - ID: {node.get('id')}, 文件: {node.get('source_file', 'N/A')}")
        else:
            print(f"    ✗ 未找到终点")
            return

        # 3. 检查直接调用关系
        print(f"\n[3] 检查从 {start_func} 的直接调用:")
        start_id = start_nodes[0]['id']

        # 查询直接调用（CALLS 关系）
        query = """
        MATCH (start)-[call:CALLS]->(target)
        WHERE start.id = $start_id
        RETURN target.id as id, target.name as name, target.type as type,
               call.call_type as call_type, call.call_line as call_line
        LIMIT 20
        """

        results = kg.execute_query(query, {'start_id': start_id})

        if results:
            print(f"    ✓ 找到 {len(results)} 个直接调用:")
            for i, result in enumerate(results, 1):
                print(f"      {i}. {result['name']} (ID: {result['id']}, "
                      f"类型: {result['call_type']}, 行号: {result['call_line']})")

                # 检查是否包含终点
                if result['name'] == end_func:
                    print(f"         ✓✓✓ 这就是终点函数！")
        else:
            print(f"    ✗ 未找到任何直接调用")

        # 4. 测试 BFS 搜索
        print(f"\n[4] 测试 BFS 搜索 (深度限制: 10):")
        paths = kg.find_top_k_call_paths_with_indirect(
            start=start_func,
            end=end_func,
            max_depth=10,
            k=5,
            debug=True
        )

        if paths:
            print(f"    ✓ 找到 {len(paths)} 条路径:")
            for i, path in enumerate(paths, 1):
                print(f"\n    路径 #{i}:")
                print(f"      长度: {path['length']}")
                print(f"      得分: {path['score']:.2f}")
                print(f"      路径: {' -> '.join(path['path'])}")
        else:
            print(f"    ✗ 未找到任何路径")
            print(f"\n    可能的原因:")
            print(f"      1. 深度限制太小（尝试增加 max_depth）")
            print(f"      2. 图谱中的边方向不对（检查 CALLS 关系方向）")
            print(f"      3. 函数名不完全匹配（检查大小写、空格）")

        # 5. 测试反向搜索（从终点到起点）
        print(f"\n[5] 测试反向搜索（从终点到起点）:")
        paths_reverse = kg.find_top_k_call_paths_with_indirect(
            start=end_func,
            end=start_func,
            max_depth=10,
            k=5,
            debug=True
        )

        if paths_reverse:
            print(f"    ✓ 反向找到 {len(paths_reverse)} 条路径")
            print(f"    → 这说明图谱方向可能是反的！")
        else:
            print(f"    ✗ 反向也未找到路径")

    finally:
        kg.close()

    print("\n" + "=" * 80)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='测试图谱调用关系')
    parser.add_argument('--data-dir', required=True, help='数据目录')
    parser.add_argument('--start-func', required=True, help='起点函数')
    parser.add_argument('--end-func', required=True, help='终点函数')

    args = parser.parse_args()

    test_direct_call(args.data_dir, args.start_func, args.end_func)
