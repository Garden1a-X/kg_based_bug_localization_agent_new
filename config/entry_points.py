"""
入口点配置

定义不同子系统的可能入口点（驱动probe函数、用户态API等）
用于辅助LLM判断调用链起点
"""

# 入口点集合配置
ENTRY_POINT_SETS = {
    'mmc': {
        'description': 'MMC/SD/SDIO 子系统',
        'ko_init': [
            # Designware MMC
            'dw_mci_pltfm_probe',
            'dw_mci_probe',
            # Freescale MXS MMC
            'mxs_mmc_probe',
            # Renesas SDHI
            'renesas_sdhi_probe',
            'renesas_sdhi_internal_dmac_probe',
            # SDHCI 系列
            'sdhci_pci_probe',
            'sdhci_acpi_probe',
            'sdhci_pltfm_probe',
            # MTK MMC
            'msdc_drv_probe',
            # Qualcomm SDHCI
            'sdhci_msm_probe',
        ],
        'sdk_api': [
            # MMC 用户态 API（如果有）
        ],
        'keywords': ['mmc', 'sd', 'sdio', 'tuning', 'card', 'emmc']
    },

    'usb': {
        'description': 'USB 子系统',
        'ko_init': [
            'usb_hcd_platform_probe',
            'usb_hcd_pci_probe',
            'ehci_platform_probe',
            'ehci_pci_probe',
            'ohci_platform_probe',
            'xhci_pci_probe',
            'xhci_plat_probe',
            'dwc3_probe',
            'dwc2_driver_probe',
        ],
        'sdk_api': [
            'usb_register_driver',
            'usb_device_open',
        ],
        'keywords': ['usb', 'hcd', 'ehci', 'ohci', 'xhci', 'dwc']
    },

    'net': {
        'description': '网络设备驱动',
        'ko_init': [
            'e1000_probe',
            'e1000e_probe',
            'igb_probe',
            'ixgbe_probe',
            'rtl8169_probe',
            'bcm_enet_probe',
            'stmmac_pltfm_probe',
            'hns3_probe',
        ],
        'sdk_api': [
            'register_netdev',
            'alloc_etherdev',
        ],
        'keywords': ['net', 'eth', 'network', 'nic', 'ethernet']
    },

    'i2c': {
        'description': 'I2C 总线驱动',
        'ko_init': [
            'i2c_adapter_probe',
            'i2c_dw_probe',
            'i2c_gpio_probe',
            'i2c_imx_probe',
        ],
        'sdk_api': [
            'i2c_register_driver',
        ],
        'keywords': ['i2c', 'smbus']
    },

    'spi': {
        'description': 'SPI 总线驱动',
        'ko_init': [
            'spi_controller_probe',
            'spi_pci_probe',
            'spi_rockchip_probe',
        ],
        'sdk_api': [
            'spi_register_driver',
        ],
        'keywords': ['spi']
    },

    'pcie': {
        'description': 'PCIe 驱动',
        'ko_init': [
            'pcie_port_probe',
            'pci_driver_probe',
            'dw_pcie_host_init',
        ],
        'sdk_api': [],
        'keywords': ['pcie', 'pci']
    },

    'block': {
        'description': '块设备驱动',
        'ko_init': [
            'nvme_probe',
            'ahci_probe',
            'ata_device_add',
        ],
        'sdk_api': [],
        'keywords': ['block', 'nvme', 'ahci', 'ata', 'scsi']
    },

    'gpu': {
        'description': 'GPU 驱动',
        'ko_init': [
            'drm_dev_register',
            'amdgpu_driver_load_kms',
            'i915_driver_probe',
        ],
        'sdk_api': [],
        'keywords': ['drm', 'gpu', 'display']
    },
}


# 平台到驱动的映射（可选，用于辅助判断）
PLATFORM_DRIVER_MAP = {
    # Rockchip 平台
    'rk3288': 'dw_mci_pltfm_probe',
    'rk3399': 'dw_mci_pltfm_probe',

    # Freescale/NXP 平台
    'imx28': 'mxs_mmc_probe',
    'imx6': 'sdhci_esdhc_imx_probe',
    'imx8': 'sdhci_esdhc_imx_probe',

    # Renesas 平台
    'r8a7795': 'renesas_sdhi_probe',
    'r8a7796': 'renesas_sdhi_probe',

    # MTK 平台
    'mt8173': 'msdc_drv_probe',
    'mt8183': 'msdc_drv_probe',

    # Qualcomm 平台
    'msm8916': 'sdhci_msm_probe',
    'msm8996': 'sdhci_msm_probe',
}


def get_candidate_entries_for_subgraph(subgraph_name: str) -> dict:
    """
    获取指定子图的候选入口点

    Args:
        subgraph_name: 子图名称（如 'mmc', 'usb'）

    Returns:
        {
            'ko_init': [...],
            'sdk_api': [...],
            'description': '...'
        }
    """
    return ENTRY_POINT_SETS.get(subgraph_name, {
        'ko_init': [],
        'sdk_api': [],
        'description': 'Unknown subsystem'
    })


def get_all_entry_points() -> list:
    """获取所有子系统的入口点（扁平化列表）"""
    all_entries = []
    for subsystem, config in ENTRY_POINT_SETS.items():
        all_entries.extend(config.get('ko_init', []))
        all_entries.extend(config.get('sdk_api', []))
    return list(set(all_entries))  # 去重


def suggest_entry_by_platform(platform: str) -> str:
    """
    根据平台名称建议入口函数

    Args:
        platform: 平台名称（如 'rk3288', 'imx6'）

    Returns:
        建议的入口函数名，如果未找到返回 None
    """
    platform_lower = platform.lower()
    return PLATFORM_DRIVER_MAP.get(platform_lower)
