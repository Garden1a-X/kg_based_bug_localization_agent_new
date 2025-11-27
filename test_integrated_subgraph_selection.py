#!/usr/bin/env python3
"""
测试MasterCoordinator集成子图自动选择功能

测试场景：
1. 启用子图自动选择 - 应该基于日志内容自动选择MMC子图
2. 手动指定子图 - 跳过自动选择，直接使用指定的子图
3. 不启用子图选择 - 使用默认行为（传统方式）
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from coordinator.master_coordinator import MasterCoordinator
from utils.logger import print_header


def test_automatic_subgraph_selection():
    """测试自动子图选择"""
    print("=" * 80)
    print("测试用例 1: 自动子图选择（基于MMC错误日志）")
    print("=" * 80)

    # MMC tuning错误日志（真实的3行日志）
    mmc_log = """
ALL phases bad!
mmc0: tuning execution failed: -1
mmc0: error -1 whilst initialising MMC card
"""

    # LLM配置
    llm_config = {
        'backend': 'openai',
        'model': 'gpt-4o-mini',
        'base_url': 'http://10.12.208.86:8502',
        'api_key': ''
    }

    # 数据目录（父目录，包含所有子图）
    data_dir = '/data/xuao/code_kg_search/linux_test/data'

    if not os.path.exists(data_dir):
        print(f"❌ 数据目录不存在: {data_dir}")
        return

    # 创建协调器，启用子图选择
    coordinator = MasterCoordinator(
        data_dir=data_dir,
        enable_llm_detection=True,
        enable_llm_log_analysis=True,
        enable_subgraph_selection=True,  # 启用子图自动选择
        llm_config=llm_config
    )

    print("\n启动分析流程...")
    print("期望：LLM应该自动选择 'mmc' 子图\n")

    try:
        # 使用 process_top_k（和之前的example一样）
        result = coordinator.process_top_k(mmc_log, k=5)

        print("\n" + "=" * 80)
        print("测试结果")
        print("=" * 80)

        if result['success']:
            print("✅ 分析成功完成")
            print(f"   找到 {result.get('path_count', 0)} 条路径")
            if result.get('paths'):
                best_path = result['paths'][0]
                print(f"   最佳路径长度: {best_path['length']}")
                print(f"   间接调用数: {best_path.get('indirect_count', 0)}")
        else:
            print("⚠️  分析部分成功或失败")
            if 'error' in result:
                print(f"   错误: {result['error']}")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        coordinator.close()


def test_manual_subgraph_override():
    """测试手动指定子图"""
    print("\n\n" + "=" * 80)
    print("测试用例 2: 手动指定子图（强制使用mmc子图）")
    print("=" * 80)

    mmc_log = """
ALL phases bad!
mmc0: tuning execution failed: -1
mmc0: error -1 whilst initialising MMC card
"""

    llm_config = {
        'backend': 'openai',
        'model': 'gpt-4o-mini',
        'base_url': 'http://10.12.208.86:8502',
        'api_key': ''
    }

    data_dir = '/data/xuao/code_kg_search/linux_test/data'

    if not os.path.exists(data_dir):
        print(f"❌ 数据目录不存在: {data_dir}")
        return

    # 创建协调器，启用子图选择
    coordinator = MasterCoordinator(
        data_dir=data_dir,
        enable_llm_detection=True,
        enable_llm_log_analysis=True,
        enable_subgraph_selection=True,
        llm_config=llm_config
    )

    print("\n启动分析流程...")
    print("期望：跳过LLM选择，直接使用手动指定的 'mmc' 子图\n")

    try:
        # 手动指定子图（使用 process_top_k_with_specific_functions + subgraph_override）
        result = coordinator.process_top_k_with_specific_functions(
            mmc_log,
            start_func='dw_mci_pltfm_probe',
            end_func='dw_mci_execute_tuning',
            intermediate_funcs=[
                'mmc_attach_mmc',
                'mmc_execute_tuning',
                'dw_mci_hi3660_execute_tuning'
            ],
            k=5,
            subgraph_override='mmc'  # 手动指定使用mmc子图
        )

        print("\n" + "=" * 80)
        print("测试结果")
        print("=" * 80)

        if result['success']:
            print("✅ 分析成功完成")
            print(f"   找到 {result.get('path_count', 0)} 条路径")
        else:
            print("⚠️  分析部分成功或失败")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        coordinator.close()


def test_without_subgraph_selection():
    """测试不启用子图选择（传统方式）"""
    print("\n\n" + "=" * 80)
    print("测试用例 3: 不启用子图选择（传统方式 - 直接指定子图路径）")
    print("=" * 80)

    mmc_log = """
ALL phases bad!
mmc0: tuning execution failed: -1
mmc0: error -1 whilst initialising MMC card
"""

    llm_config = {
        'backend': 'openai',
        'model': 'gpt-4o-mini',
        'base_url': 'http://10.12.208.86:8502',
        'api_key': ''
    }

    # 直接指定到mmc子图目录（传统方式）
    data_dir = '/data/xuao/code_kg_search/linux_test/data/mmc'

    if not os.path.exists(data_dir):
        print(f"❌ MMC子图目录不存在: {data_dir}")
        print("   尝试使用完整图谱...")
        data_dir = '/data/xuao/code_kg_search/linux_test/data'
        if not os.path.exists(data_dir):
            print(f"❌ 数据目录不存在: {data_dir}")
            return

    # 创建协调器，不启用子图选择（传统方式）
    coordinator = MasterCoordinator(
        data_dir=data_dir,
        enable_llm_detection=True,
        enable_llm_log_analysis=True,
        enable_subgraph_selection=False,  # 不启用子图选择
        llm_config=llm_config
    )

    print("\n启动分析流程...")
    print("期望：直接使用data_dir指定的图谱，不进行子图选择\n")

    try:
        # 使用 process_top_k（和之前的example一样）
        result = coordinator.process_top_k(mmc_log, k=5)

        print("\n" + "=" * 80)
        print("测试结果")
        print("=" * 80)

        if result['success']:
            print("✅ 分析成功完成")
            print(f"   找到 {result.get('path_count', 0)} 条路径")
            if result.get('paths'):
                best_path = result['paths'][0]
                print(f"   最佳路径长度: {best_path['length']}")
        else:
            print("⚠️  分析部分成功或失败")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        coordinator.close()


def main():
    """运行所有测试"""
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "MasterCoordinator子图选择集成测试" + " " * 23 + "║")
    print("╚" + "═" * 78 + "╝")
    print("\n注意：本测试使用 process_top_k() 方法，和之前能工作的example一样")
    print("      而不是使用 process() 方法\n")

    # 测试1：自动选择
    test_automatic_subgraph_selection()

    # 测试2：手动指定
    test_manual_subgraph_override()

    # 测试3：不启用子图选择（传统方式）
    test_without_subgraph_selection()

    print("\n\n" + "=" * 80)
    print("所有测试完成！")
    print("=" * 80)


if __name__ == '__main__':
    main()
