#!/usr/bin/env python3
"""
测试子图选择器
验证基于日志或函数名选择子图的功能
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from llm import LLMClient
from utils.subgraph_selector import SubgraphSelector
from utils.logger import logger

# 定义子图元数据
SUBGRAPH_METADATA = {
    'mmc': {
        'name': 'MMC/SD Card Subsystem',
        'description': 'MMC、SD卡和SDIO驱动子系统，处理存储卡的初始化、读写、tuning等操作',
        'keywords': ['mmc', 'sd', 'sdio', 'card', 'tuning', 'dw_mci', 'sdhci'],
        'common_functions': [
            'mmc_alloc_host', 'mmc_rescan', 'mmc_add_host',
            'dw_mci_probe', 'dw_mci_execute_tuning', 'mmc_schedule_delayed_work'
        ]
    },
    'gpu': {
        'name': 'GPU Graphics',
        'description': 'GPU图形驱动子系统，包括DRM、显示控制器等',
        'keywords': ['drm', 'gpu', 'display', 'framebuffer', 'render'],
        'common_functions': ['drm_dev_register', 'drm_mode_create']
    },
    'net': {
        'name': 'Network Drivers',
        'description': '网络驱动子系统，包括以太网、无线网络等',
        'keywords': ['net', 'eth', 'network', 'skb', 'netdev', 'wireless'],
        'common_functions': ['netdev_register', 'eth_type_trans']
    },
    'usb': {
        'name': 'USB Subsystem',
        'description': 'USB驱动子系统，包括主机控制器、设备驱动等',
        'keywords': ['usb', 'ohci', 'ehci', 'xhci', 'gadget'],
        'common_functions': ['usb_register_driver', 'usb_submit_urb']
    },
    'i2c': {
        'name': 'I2C Bus',
        'description': 'I2C总线驱动子系统',
        'keywords': ['i2c', 'smbus'],
        'common_functions': ['i2c_add_adapter', 'i2c_transfer']
    },
    'spi': {
        'name': 'SPI Bus',
        'description': 'SPI总线驱动子系统',
        'keywords': ['spi'],
        'common_functions': ['spi_register_master', 'spi_sync']
    },
    'pci': {
        'name': 'PCI Bus',
        'description': 'PCI/PCIe总线驱动子系统',
        'keywords': ['pci', 'pcie'],
        'common_functions': ['pci_register_driver', 'pci_enable_device']
    }
}


def test_select_by_log():
    """测试基于错误日志选择子图"""
    print("\n" + "="*80)
    print("测试1: 基于错误日志选择子图")
    print("="*80)

    # 创建LLM客户端
    llm_client = LLMClient(
        backend='openai',
        model='gpt-4o-mini',
        base_url='http://10.12.208.86:8502',
        api_key=''
    )

    # 创建子图选择器
    selector = SubgraphSelector(
        llm_client=llm_client,
        base_data_dir='/data/xuao/code_kg_search/linux_test/data',
        subgraph_metadata=SUBGRAPH_METADATA
    )

    print(f"\n发现的子图: {selector.available_subgraphs}")

    # 测试用例1: MMC错误日志
    print("\n" + "-"*80)
    print("测试用例 1: MMC tuning错误日志")
    print("-"*80)

    mmc_log = """
ALL phases bad!
mmc0: tuning execution failed: -1
mmc0: error -1 whilst initialising MMC card
    """

    print(f"日志:\n{mmc_log}")
    selected = selector.select_by_log(mmc_log, top_k=3)
    print(f"\n✅ 选择的子图: {selected}")

    # 测试用例2: USB错误日志
    print("\n" + "-"*80)
    print("测试用例 2: USB设备错误日志")
    print("-"*80)

    usb_log = """
usb 1-1: device descriptor read/64, error -110
usb 1-1: device not accepting address 2, error -71
    """

    print(f"日志:\n{usb_log}")
    selected = selector.select_by_log(usb_log, top_k=3)
    print(f"\n✅ 选择的子图: {selected}")

    # 测试用例3: 网络错误日志
    print("\n" + "-"*80)
    print("测试用例 3: 网络驱动错误日志")
    print("-"*80)

    net_log = """
eth0: link is not ready
eth0: failed to bring up PHY
    """

    print(f"日志:\n{net_log}")
    selected = selector.select_by_log(net_log, top_k=3)
    print(f"\n✅ 选择的子图: {selected}")


def test_select_by_functions():
    """测试基于函数名选择子图"""
    print("\n" + "="*80)
    print("测试2: 基于函数名选择子图")
    print("="*80)

    # 创建LLM客户端
    llm_client = LLMClient(
        backend='openai',
        model='gpt-4o-mini',
        base_url='http://10.12.208.86:8502',
        api_key=''
    )

    # 创建子图选择器
    selector = SubgraphSelector(
        llm_client=llm_client,
        base_data_dir='/data/xuao/code_kg_search/linux_test/data',
        subgraph_metadata=SUBGRAPH_METADATA
    )

    # 测试用例1: MMC函数
    print("\n" + "-"*80)
    print("测试用例 1: MMC相关函数")
    print("-"*80)

    mmc_functions = [
        'dw_mci_pltfm_probe',
        'dw_mci_hi3660_execute_tuning',
        'mmc_rescan'
    ]

    print(f"函数列表:\n{chr(10).join(f'  - {f}' for f in mmc_functions)}")
    selected = selector.select_by_functions(mmc_functions, top_k=3)
    print(f"\n✅ 选择的子图: {selected}")

    # 测试用例2: USB函数
    print("\n" + "-"*80)
    print("测试用例 2: USB相关函数")
    print("-"*80)

    usb_functions = [
        'usb_hcd_platform_probe',
        'usb_add_hcd',
        'ehci_setup'
    ]

    print(f"函数列表:\n{chr(10).join(f'  - {f}' for f in usb_functions)}")
    selected = selector.select_by_functions(usb_functions, top_k=3)
    print(f"\n✅ 选择的子图: {selected}")

    # 测试用例3: 混合函数（I2C + GPIO）
    print("\n" + "-"*80)
    print("测试用例 3: 混合函数")
    print("-"*80)

    mixed_functions = [
        'i2c_adapter_probe',
        'gpio_request',
        'pinctrl_init'
    ]

    print(f"函数列表:\n{chr(10).join(f'  - {f}' for f in mixed_functions)}")
    selected = selector.select_by_functions(mixed_functions, top_k=3)
    print(f"\n✅ 选择的子图: {selected}")


def test_fallback_mode():
    """测试无LLM时的fallback模式"""
    print("\n" + "="*80)
    print("测试3: Fallback模式（无LLM）")
    print("="*80)

    # 创建选择器，不提供LLM客户端
    selector = SubgraphSelector(
        llm_client=None,
        base_data_dir='/data/xuao/code_kg_search/linux_test/data',
        subgraph_metadata=SUBGRAPH_METADATA
    )

    print("\n使用关键字匹配（不使用LLM）\n")

    # 测试MMC日志
    mmc_log = "mmc0: tuning execution failed"
    print(f"日志: {mmc_log}")
    selected = selector.select_by_log(mmc_log, top_k=3)
    print(f"✅ 选择的子图: {selected}")

    # 测试函数名
    print()
    functions = ['dw_mci_probe', 'mmc_rescan']
    print(f"函数: {functions}")
    selected = selector.select_by_functions(functions, top_k=3)
    print(f"✅ 选择的子图: {selected}")


def main():
    """运行所有测试"""
    print("="*80)
    print("子图选择器测试")
    print("="*80)

    try:
        # 测试1: 基于日志选择
        test_select_by_log()

        # 测试2: 基于函数名选择
        test_select_by_functions()

        # 测试3: Fallback模式
        test_fallback_mode()

        print("\n" + "="*80)
        print("✅ 所有测试完成！")
        print("="*80)

    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
