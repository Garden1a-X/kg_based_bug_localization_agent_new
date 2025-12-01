#!/usr/bin/env python3
"""
调试路径搜索 - 查看为什么找不到路径
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from data.kg_interface import KnowledgeGraphInterface
from llm import LLMClient

def main():
    data_dir = "/data/xuao/code_kg_search/subgraph/drivers/mmc"
    start_func = "mmc_detect_change"
    end_func = "mmc_rescan"

    print("=" * 80)
    print("调试路径搜索")
    print("=" * 80)
    print(f"数据目录: {data_dir}")
    print(f"起点: {start_func}")
    print(f"终点: {end_func}")
    print()

    # 创建 LLM 客户端
    print("创建 LLM 客户端...")
    llm_client = LLMClient(
        backend='openai',
        model='gpt-4o-mini',
        base_url='http://10.12.208.86:8502',
        api_key=''
    )

    # 加载知识图谱（启用 LLM 检测）
    print("加载知识图谱（启用 LLM 间接调用检测）...")
    kg = KnowledgeGraphInterface(
        data_dir,
        enable_llm_detection=True,  # 重要！启用 LLM 检测
        llm_client=llm_client
    )
    print()

    # 检查起点函数
    print(f"检查起点函数: {start_func}")
    start_entity = kg.find_function(start_func)
    if start_entity:
        print(f"  ✓ 找到: ID={start_entity.get('id')}")
        print(f"    文件: {start_entity.get('source_file')}")
        print(f"    行号: {start_entity.get('start_line')}-{start_entity.get('end_line')}")

        # 检查直接调用
        start_id = start_entity.get('id')
        callees = kg.call_graph_with_lines.get(start_id, [])
        print(f"  ✓ 直接调用 {len(callees)} 个函数:")
        for callee_info in callees[:10]:
            if isinstance(callee_info, dict):
                callee_id = callee_info.get('callee_id')
                call_line = callee_info.get('call_line')
            else:
                callee_id = callee_info
                call_line = None

            callee = kg.entity_by_id.get(callee_id)
            if callee:
                if call_line:
                    print(f"      - {callee.get('name')} (行 {call_line})")
                else:
                    print(f"      - {callee.get('name')}")
    else:
        print(f"  ✗ 未找到")
    print()

    # 检查终点函数
    print(f"检查终点函数: {end_func}")
    end_entity = kg.find_function(end_func)
    if end_entity:
        print(f"  ✓ 找到: ID={end_entity.get('id')}")
        print(f"    文件: {end_entity.get('source_file')}")
        print(f"    行号: {end_entity.get('start_line')}-{end_entity.get('end_line')}")
    else:
        print(f"  ✗ 未找到")
    print()

    # 检查是否有已知的异步函数
    print(f"已知的异步函数: {len(kg.async_functions)} 个")
    print(f"  {list(kg.async_functions)[:5]}")
    print()

    # 执行路径搜索（开启调试）
    print("=" * 80)
    print("开始路径搜索（调试模式）")
    print("=" * 80)
    paths = kg.find_top_k_call_paths_with_indirect(
        start_func,
        end_func,
        max_depth=30,
        k=5,
        debug=True  # 开启调试！
    )

    print()
    print("=" * 80)
    print(f"搜索结果: 找到 {len(paths)} 条路径")
    print("=" * 80)

    for idx, path_info in enumerate(paths, 1):
        print(f"\n路径 {idx}:")
        print(f"  路径: {' -> '.join(path_info['path'])}")
        print(f"  得分: {path_info.get('score', 0):.3f}")
        print(f"  间接调用数: {path_info.get('indirect_call_count', 0)}")

        # 显示边信息
        edges = path_info.get('edges', [])
        for i, edge in enumerate(edges):
            if isinstance(edge, dict):
                edge_type = edge.get('type')
                print(f"    [{i}] {path_info['path'][i]} -> {path_info['path'][i+1]}")
                print(f"        类型: {edge_type}")
                if 'bridge' in edge:
                    print(f"        桥接: {edge['bridge']}")

    kg.close()


if __name__ == '__main__':
    main()
