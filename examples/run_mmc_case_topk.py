"""
演示Top-K路径搜索功能
展示如何使用call_line排序和返回多条路径
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from coordinator.master_coordinator import MasterCoordinator
from utils.logger import setup_logger, print_header
import json

# 配置日志
setup_logger()


def run_mmc_case_topk():
    """运行MMC案例 - Top-K路径搜索（使用子图自动选择 + LLM入口选择）"""

    # 甲方提供的错误日志（3行简单日志）
    mmc_error_log = """
ALL phases bad!
mmc0: tuning execution failed: -1
mmc0: error -1 whilst initialising MMC card
    """

    print_header("运行MMC案例 - Top-K路径搜索（子图自动选择 + LLM入口选择）")

    # 使用父目录（包含所有子图）
    data_dir = "/data/xuao/code_kg_search/linux_test/data"

    if not os.path.exists(data_dir):
        print(f"错误: 数据目录不存在 ({data_dir})")
        return

    # LLM配置
    llm_config = {
        'backend': 'openai',
        'model': 'gpt-4o-mini',
        'base_url': 'http://10.12.208.86:8502',
        'api_key': ''
    }

    # 创建协调器（启用子图自动选择 + LLM日志分析）
    coordinator = MasterCoordinator(
        data_dir=data_dir,
        llm_client=None,
        enable_llm_log_analysis=True,    # 启用LLM日志分析（含入口选择）
        enable_subgraph_selection=True,  # 启用子图自动选择
        llm_config=llm_config
    )

    try:
        # ========== 方式1：自动推断起止点，返回Top-K路径 ==========
        print("\n[方式1] 自动推断 + Top-5路径:")
        print("=" * 60)
        result1 = coordinator.process_top_k(
            mmc_error_log,
            k=5  # 返回最多5条路径
        )

        # 保存结果
        output_dir = project_root / 'output'
        output_dir.mkdir(exist_ok=True)

        with open(output_dir / 'mmc_case_topk_auto.json', 'w', encoding='utf-8') as f:
            json.dump(result1, f, indent=2, ensure_ascii=False)

        print(f"\n结果已保存到: {output_dir / 'mmc_case_topk_auto.json'}")

        # ========== 方式2：指定起止点 + 中间节点 + Top-K路径 ==========
        print("\n\n[方式2] 指定起止点+中间节点 + Top-5路径:")
        print("=" * 60)
        result2 = coordinator.process_top_k_with_specific_functions(
            mmc_error_log,
            start_func='dw_mci_pltfm_probe',
            end_func='dw_mci_execute_tuning',
            intermediate_funcs=[
                'mmc_attach_mmc',
                'mmc_execute_tuning',
                'dw_mci_hi3660_execute_tuning'
            ],
            k=5
        )

        with open(output_dir / 'mmc_case_topk_specific.json', 'w', encoding='utf-8') as f:
            json.dump(result2, f, indent=2, ensure_ascii=False)

        print(f"\n结果已保存到: {output_dir / 'mmc_case_topk_specific.json'}")

        # 显示对比
        print("\n\n" + "=" * 60)
        print("路径数量对比:")
        print("=" * 60)
        print(f"  方式1 (自动推断):     {result1.get('path_count', 0)} 条路径")
        print(f"  方式2 (指定起止点):   {result2.get('path_count', 0)} 条路径")

        # 显示call_line排序信息
        if result2.get('paths'):
            print("\n" + "=" * 60)
            print("路径详情（已按得分排序，考虑了调用行号）:")
            print("=" * 60)
            for idx, path in enumerate(result2['paths'][:3]):  # 只显示前3条
                avg_line = path.get('avg_call_line', 0)
                print(f"  路径#{idx+1}: 长度={path['length']}, "
                      f"间接调用={path['indirect_count']}, "
                      f"平均调用行号={avg_line:.1f}, "
                      f"得分={path['score']:.2f}")

    finally:
        coordinator.close()


def demo_topk_direct():
    """直接使用KG接口演示Top-K搜索"""
    from data.kg_interface import KnowledgeGraphInterface

    print_header("直接使用KG接口演示Top-K搜索")

    data_dir = "/data/xuao/code_kg_search/linux_test/data/mmc"
    if not os.path.exists(data_dir):
        data_dir = "/data/xuao/code_kg_search/linux_test/data"

    kg = KnowledgeGraphInterface(data_dir)

    try:
        # 测试Top-K路径搜索
        print("\n测试: 从 dw_mci_pltfm_probe 到 dw_mci_execute_tuning")
        print("=" * 60)

        paths = kg.find_top_k_call_paths_with_indirect(
            start='dw_mci_pltfm_probe',
            end='dw_mci_execute_tuning',
            max_depth=30,
            k=5,
            debug=True
        )

        print(f"\n找到 {len(paths)} 条路径:")
        for idx, path in enumerate(paths):
            print(f"\n路径 #{idx+1}:")
            print(f"  长度: {path['length']}")
            print(f"  间接调用: {path['indirect_count']}")
            print(f"  平均调用行号: {path.get('avg_call_line', 0):.1f}")
            print(f"  得分: {path['score']:.2f}")
            print(f"  路径: {' -> '.join(path['path'][:5])} ... {' -> '.join(path['path'][-3:])}")

    finally:
        kg.close()


def run_mmc_case_with_llm():
    """运行MMC案例 - 启用LLM间接调用检测 + 子图自动选择 + LLM入口选择"""

    print_header("运行MMC案例 - LLM全功能模式（间接调用检测 + 子图选择 + 入口选择）")

    # 甲方提供的错误日志
    mmc_error_log = """
ALL phases bad!
mmc0: tuning execution failed: -1
mmc0: error -1 whilst initialising MMC card
    """

    # 使用父目录（包含所有子图）
    data_dir = "/data/xuao/code_kg_search/linux_test/data"

    if not os.path.exists(data_dir):
        print(f"错误: 数据目录不存在 ({data_dir})")
        return

    print("\n创建协调器（LLM全功能模式）...")
    print("  - LLM间接调用检测: 分析异步调用、函数指针等")
    print("  - 子图自动选择: 基于日志内容选择相关子图")
    print("  - LLM入口选择: 智能选择调用链起点，带置信度评估")
    print("  配置文件: config/indirect_call_detection.yaml\n")

    # LLM配置
    llm_config = {
        'backend': 'openai',
        'model': 'gpt-4o-mini',
        'base_url': 'http://10.12.208.86:8502',
        'api_key': ''
    }

    # 创建协调器，启用所有LLM功能
    coordinator = MasterCoordinator(
        data_dir=data_dir,
        llm_client=None,
        enable_llm_detection=True,       # 启用LLM间接调用检测
        enable_llm_log_analysis=True,    # 启用LLM日志分析（含入口选择）
        enable_subgraph_selection=True,  # 启用子图自动选择
        llm_config=llm_config
    )

    try:
        # ========== 方式1：自动推断起止点，返回Top-K路径 ==========
        print("\n[方式1] 自动推断 + Top-5路径 (LLM辅助):")
        print("=" * 60)
        result1 = coordinator.process_top_k(
            mmc_error_log,
            k=5  # 返回最多5条路径
        )

        # 保存结果
        output_dir = project_root / 'output'
        output_dir.mkdir(exist_ok=True)

        with open(output_dir / 'mmc_case_topk_llm_auto.json', 'w', encoding='utf-8') as f:
            json.dump(result1, f, indent=2, ensure_ascii=False)

        print(f"\n结果已保存到: {output_dir / 'mmc_case_topk_llm_auto.json'}")

        # ========== 方式2：指定起止点 + 中间节点 + Top-K路径 ==========
        print("\n\n[方式2] 指定起止点+中间节点 + Top-5路径 (LLM辅助):")
        print("=" * 60)
        result2 = coordinator.process_top_k_with_specific_functions(
            mmc_error_log,
            start_func='dw_mci_pltfm_probe',
            end_func='dw_mci_execute_tuning',
            intermediate_funcs=[
                'mmc_attach_mmc',
                'mmc_execute_tuning',
                'dw_mci_hi3660_execute_tuning'
            ],
            k=5
        )

        with open(output_dir / 'mmc_case_topk_llm_specific.json', 'w', encoding='utf-8') as f:
            json.dump(result2, f, indent=2, ensure_ascii=False)

        print(f"\n结果已保存到: {output_dir / 'mmc_case_topk_llm_specific.json'}")

        # 显示对比
        print("\n\n" + "=" * 60)
        print("路径数量对比:")
        print("=" * 60)
        print(f"  方式1 (自动推断):     {result1.get('path_count', 0)} 条路径")
        print(f"  方式2 (指定起止点):   {result2.get('path_count', 0)} 条路径")

        # 显示方式1的路径详情
        if result1.get('paths'):
            print("\n" + "=" * 60)
            print("路径详情（方式1，前3条）:")
            print("=" * 60)
            for idx, path in enumerate(result1['paths'][:3]):
                avg_line = path.get('avg_call_line', 0)
                print(f"  路径#{idx+1}: 长度={path['length']}, "
                      f"间接调用={path['indirect_count']}, "
                      f"平均调用行号={avg_line:.1f}, "
                      f"得分={path['score']:.2f}")

                # 检查是否使用了LLM检测的间接调用和Mock数据
                edges = path.get('edges', [])
                llm_edges = [e for e in edges if isinstance(e, dict) and e.get('bridge', {}).get('method') == 'llm_analysis']
                mock_edges = [e for e in edges if isinstance(e, dict) and e.get('bridge', {}).get('method') == 'mock_data']
                if llm_edges:
                    print(f"              ✓ 使用了 {len(llm_edges)} 个LLM检测的间接调用")
                if mock_edges:
                    print(f"              ⚠ 使用了 {len(mock_edges)} 个Mock数据的间接调用")

        # 显示方式2的路径详情
        if result2.get('paths'):
            print("\n" + "=" * 60)
            print("路径详情（方式2，前3条）:")
            print("=" * 60)
            for idx, path in enumerate(result2['paths'][:3]):
                avg_line = path.get('avg_call_line', 0)
                print(f"  路径#{idx+1}: 长度={path['length']}, "
                      f"间接调用={path['indirect_count']}, "
                      f"平均调用行号={avg_line:.1f}, "
                      f"得分={path['score']:.2f}")

                # 检查是否使用了LLM检测的间接调用和Mock数据
                edges = path.get('edges', [])
                llm_edges = [e for e in edges if isinstance(e, dict) and e.get('bridge', {}).get('method') == 'llm_analysis']
                mock_edges = [e for e in edges if isinstance(e, dict) and e.get('bridge', {}).get('method') == 'mock_data']
                if llm_edges:
                    print(f"              ✓ 使用了 {len(llm_edges)} 个LLM检测的间接调用")
                if mock_edges:
                    print(f"              ⚠ 使用了 {len(mock_edges)} 个Mock数据的间接调用")

        print("\n" + "=" * 60)
        print("说明:")
        print("=" * 60)
        print("  - 配置文件指定哪些函数需要LLM分析间接调用")
        print("  - 预处理阶段：LLM分析源码 → 提取字段名 → 查询图谱ASSIGNED_TO")
        print("  - BFS阶段：使用缓存的间接调用关系，无需重复调用LLM")
        print("  - 如果LLM检测失败，自动fallback到Mock数据")

    finally:
        coordinator.close()


def run_mmc_case_with_log_matching():
    """运行MMC案例 - 日志匹配 + 子图自动选择 + LLM入口选择 + Top-K路径搜索"""

    print_header("运行MMC案例 - 日志匹配 + 子图自动选择 + LLM入口选择")

    # 甲方提供的错误日志
    mmc_error_log = """
ALL phases bad!
mmc0: tuning execution failed: -1
mmc0: error -1 whilst initialising MMC card
    """

    # 使用父目录（包含所有子图）
    data_dir = "/data/xuao/code_kg_search/linux_test/data"

    if not os.path.exists(data_dir):
        print(f"错误: 数据目录不存在 ({data_dir})")
        return

    # LLM配置
    llm_config = {
        'backend': 'openai',
        'model': 'gpt-4o-mini',
        'base_url': 'http://10.12.208.86:8502',
        'api_key': ''
    }

    # 创建协调器（日志匹配 + LLM入口选择 + 子图自动选择）
    coordinator = MasterCoordinator(
        data_dir=data_dir,
        llm_client=None,
        enable_llm_log_analysis=True,    # 启用LLM日志分析（含入口选择）
        enable_subgraph_selection=True,  # 启用子图自动选择
        llm_config=llm_config
    )

    try:
        # 使用新的 process_top_k 方法（自动调用日志匹配）
        result = coordinator.process_top_k(
            mmc_error_log,
            k=5
        )

        # 保存结果
        output_dir = project_root / 'output'
        output_dir.mkdir(exist_ok=True)

        output_file = output_dir / 'mmc_case_log_matching.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n结果已保存到: {output_file}")

        # 显示路径详情
        if result.get('paths'):
            print("\n" + "=" * 60)
            print(f"找到 {len(result['paths'])} 条路径:")
            print("=" * 60)
            for idx, path in enumerate(result['paths'][:3]):  # 只显示前3条
                avg_line = path.get('avg_call_line', 0)
                print(f"\n路径 #{idx+1}:")
                print(f"  长度: {path['length']}")
                print(f"  间接调用: {path['indirect_count']}")
                print(f"  平均调用行号: {avg_line:.1f}")
                print(f"  得分: {path['score']:.2f}")

                # 显示路径（简化）
                path_str = ' → '.join(path['path'])
                if len(path_str) > 100:
                    path_str = ' → '.join(path['path'][:3]) + ' → ... → ' + ' → '.join(path['path'][-2:])
                print(f"  路径: {path_str}")

        print("\n" + "=" * 60)
        print("流程说明:")
        print("=" * 60)
        print("  1. 子图选择：LLM基于日志内容选择相关子图（mmc）")
        print("  2. 日志匹配：基于FAIL_MESSAGE实体的精确匹配")
        print("  3. 入口选择：LLM从候选入口中智能选择，或降级到日志函数")
        print("  4. 路径搜索：在知识图谱中搜索Top-K条最优调用路径")
        print("  5. 排序策略：考虑路径长度、间接调用数量、调用行号、关键函数覆盖率")

    finally:
        coordinator.close()


def run_mmc_case_traditional():
    """运行MMC案例 - 传统方式（不启用子图自动选择）"""

    # 甲方提供的错误日志（3行简单日志）
    mmc_error_log = """
ALL phases bad!
mmc0: tuning execution failed: -1
mmc0: error -1 whilst initialising MMC card
    """

    print_header("运行MMC案例 - 传统方式（直接指定子图路径）")

    # 直接指定子图路径（传统方式）
    data_dir = "/data/xuao/code_kg_search/linux_test/data/mmc"

    # 如果MMC子图不存在，回退到完整数据
    if not os.path.exists(data_dir):
        data_dir = "/data/xuao/code_kg_search/linux_test/data"
        print(f"注意: MMC子图不存在，使用完整图谱 ({data_dir})")

    # 创建协调器（不启用子图自动选择 - 传统方式）
    coordinator = MasterCoordinator(
        data_dir=data_dir,
        llm_client=None,
        enable_subgraph_selection=False  # 不启用子图自动选择
    )

    try:
        # ========== 方式1：自动推断起止点，返回Top-K路径 ==========
        print("\n[方式1] 自动推断 + Top-5路径:")
        print("=" * 60)
        result1 = coordinator.process_top_k(
            mmc_error_log,
            k=5  # 返回最多5条路径
        )

        # 保存结果
        output_dir = project_root / 'output'
        output_dir.mkdir(exist_ok=True)

        with open(output_dir / 'mmc_case_topk_traditional_auto.json', 'w', encoding='utf-8') as f:
            json.dump(result1, f, indent=2, ensure_ascii=False)

        print(f"\n结果已保存到: {output_dir / 'mmc_case_topk_traditional_auto.json'}")

        # ========== 方式2：指定起止点 + 中间节点 + Top-K路径 ==========
        print("\n\n[方式2] 指定起止点+中间节点 + Top-5路径:")
        print("=" * 60)
        result2 = coordinator.process_top_k_with_specific_functions(
            mmc_error_log,
            start_func='dw_mci_pltfm_probe',
            end_func='dw_mci_execute_tuning',
            intermediate_funcs=[
                'mmc_attach_mmc',
                'mmc_execute_tuning',
                'dw_mci_hi3660_execute_tuning'
            ],
            k=5
        )

        with open(output_dir / 'mmc_case_topk_traditional_specific.json', 'w', encoding='utf-8') as f:
            json.dump(result2, f, indent=2, ensure_ascii=False)

        print(f"\n结果已保存到: {output_dir / 'mmc_case_topk_traditional_specific.json'}")

        # 显示对比
        print("\n\n" + "=" * 60)
        print("路径数量对比:")
        print("=" * 60)
        print(f"  方式1 (自动推断):     {result1.get('path_count', 0)} 条路径")
        print(f"  方式2 (指定起止点):   {result2.get('path_count', 0)} 条路径")

    finally:
        coordinator.close()


def main():
    """主函数"""
    if len(sys.argv) > 1:
        if sys.argv[1] == '--direct':
            # 直接测试KG接口
            demo_topk_direct()
        elif sys.argv[1] == '--llm':
            # 测试LLM辅助检测 + 子图自动选择
            run_mmc_case_with_llm()
        elif sys.argv[1] == '--log-match':
            # 测试日志匹配集成 + 子图自动选择
            run_mmc_case_with_log_matching()
        elif sys.argv[1] == '--traditional':
            # 测试传统方式（不启用子图自动选择）
            run_mmc_case_traditional()
        else:
            print("用法:")
            print("  python run_mmc_case_topk.py                # 标准模式（启用子图自动选择）")
            print("  python run_mmc_case_topk.py --direct       # 直接测试KG接口")
            print("  python run_mmc_case_topk.py --llm          # LLM辅助检测 + 子图自动选择")
            print("  python run_mmc_case_topk.py --log-match    # 日志匹配 + 子图自动选择")
            print("  python run_mmc_case_topk.py --traditional  # 传统方式（不启用子图选择）")
    else:
        # 完整流程测试
        run_mmc_case_topk()


if __name__ == "__main__":
    main()
