"""
子图元数据配置
定义Linux驱动子系统的描述、关键字和常见函数
"""

SUBGRAPH_METADATA = {
    'mmc': {
        'name': 'MMC/SD Card Subsystem',
        'description': 'MMC、SD卡和SDIO驱动子系统，处理存储卡的初始化、读写、tuning、DMA传输等操作',
        'keywords': ['mmc', 'sd', 'sdio', 'card', 'tuning', 'dw_mci', 'sdhci', 'emmc'],
        'common_functions': [
            'mmc_alloc_host', 'mmc_rescan', 'mmc_add_host', 'mmc_remove_host',
            'dw_mci_probe', 'dw_mci_execute_tuning', 'mmc_schedule_delayed_work',
            'sdhci_add_host', 'mmc_detect_change'
        ]
    },
    'usb': {
        'name': 'USB Subsystem',
        'description': 'USB驱动子系统，包括主机控制器、设备驱动、USB gadget等',
        'keywords': ['usb', 'ohci', 'ehci', 'xhci', 'gadget', 'hcd', 'urb'],
        'common_functions': [
            'usb_register_driver', 'usb_submit_urb', 'usb_hcd_probe',
            'usb_add_hcd', 'ehci_setup', 'xhci_init', 'usb_control_msg'
        ]
    },
    'net': {
        'name': 'Network Drivers',
        'description': '网络驱动子系统，包括以太网、无线网络、网络协议等',
        'keywords': ['net', 'eth', 'network', 'skb', 'netdev', 'wireless', 'wifi', 'phy'],
        'common_functions': [
            'netdev_register', 'eth_type_trans', 'alloc_etherdev',
            'register_netdev', 'netif_rx', 'napi_schedule'
        ]
    },
    'pci': {
        'name': 'PCI/PCIe Bus',
        'description': 'PCI/PCIe总线驱动子系统，管理PCI设备的枚举、配置和资源分配',
        'keywords': ['pci', 'pcie'],
        'common_functions': [
            'pci_register_driver', 'pci_enable_device', 'pci_set_master',
            'pci_request_regions', 'pci_iomap'
        ]
    },
    'i2c': {
        'name': 'I2C Bus',
        'description': 'I2C总线驱动子系统，支持I2C/SMBus设备通信',
        'keywords': ['i2c', 'smbus'],
        'common_functions': [
            'i2c_add_adapter', 'i2c_transfer', 'i2c_register_driver',
            'i2c_smbus_read_byte', 'i2c_new_device'
        ]
    },
    'spi': {
        'name': 'SPI Bus',
        'description': 'SPI总线驱动子系统，支持SPI设备通信',
        'keywords': ['spi'],
        'common_functions': [
            'spi_register_master', 'spi_sync', 'spi_register_driver',
            'spi_setup', 'spi_async'
        ]
    },
    'gpio': {
        'name': 'GPIO Subsystem',
        'description': 'GPIO子系统，管理通用输入输出引脚',
        'keywords': ['gpio', 'gpiochip'],
        'common_functions': [
            'gpio_request', 'gpio_set_value', 'gpiochip_add',
            'gpio_to_irq', 'gpio_direction_output'
        ]
    },
    'pinctrl': {
        'name': 'Pin Control Subsystem',
        'description': 'Pin控制子系统，管理引脚复用和配置',
        'keywords': ['pinctrl', 'pinmux', 'pinconf'],
        'common_functions': [
            'pinctrl_register', 'pinctrl_get', 'pinctrl_select_state',
            'devm_pinctrl_get'
        ]
    },
    'clk': {
        'name': 'Clock Framework',
        'description': '时钟框架，管理系统时钟的配置和控制',
        'keywords': ['clk', 'clock'],
        'common_functions': [
            'clk_register', 'clk_prepare_enable', 'clk_get_rate',
            'clk_set_rate', 'devm_clk_get'
        ]
    },
    'regulator': {
        'name': 'Regulator Framework',
        'description': '电源调节器框架，管理电压和电流调节',
        'keywords': ['regulator', 'voltage', 'vreg'],
        'common_functions': [
            'regulator_register', 'regulator_enable', 'regulator_get',
            'regulator_set_voltage', 'regulator_disable'
        ]
    },
    'dma': {
        'name': 'DMA Engine',
        'description': 'DMA引擎子系统，管理直接内存访问操作',
        'keywords': ['dma', 'dmaengine'],
        'common_functions': [
            'dma_request_channel', 'dmaengine_prep_slave_sg',
            'dmaengine_submit', 'dma_async_issue_pending'
        ]
    },
    'rtc': {
        'name': 'RTC (Real-Time Clock)',
        'description': '实时时钟子系统',
        'keywords': ['rtc'],
        'common_functions': [
            'rtc_device_register', 'rtc_read_time', 'rtc_set_time',
            'devm_rtc_device_register'
        ]
    },
    'pwm': {
        'name': 'PWM Subsystem',
        'description': '脉宽调制子系统',
        'keywords': ['pwm'],
        'common_functions': [
            'pwm_request', 'pwm_config', 'pwm_enable',
            'pwmchip_add'
        ]
    },
    'watchdog': {
        'name': 'Watchdog',
        'description': '看门狗定时器子系统',
        'keywords': ['watchdog', 'wdt'],
        'common_functions': [
            'watchdog_register_device', 'watchdog_notify_pretimeout'
        ]
    },
    'input': {
        'name': 'Input Subsystem',
        'description': '输入设备子系统，包括键盘、鼠标、触摸屏等',
        'keywords': ['input', 'keyboard', 'mouse', 'touchscreen'],
        'common_functions': [
            'input_register_device', 'input_event', 'input_report_key',
            'input_allocate_device'
        ]
    },
    'gpu': {
        'name': 'GPU Graphics',
        'description': 'GPU图形驱动子系统，包括DRM、显示控制器等',
        'keywords': ['drm', 'gpu', 'display', 'framebuffer', 'render', 'kms'],
        'common_functions': [
            'drm_dev_register', 'drm_mode_create', 'drm_gem_object_init',
            'drm_atomic_helper_commit'
        ]
    },
    'block': {
        'name': 'Block Layer',
        'description': '块设备层，管理块设备的I/O操作',
        'keywords': ['block', 'blkdev', 'request', 'bio'],
        'common_functions': [
            'blk_init_queue', 'blk_queue_make_request', 'register_blkdev',
            'blk_mq_init_queue'
        ]
    },
    'scsi': {
        'name': 'SCSI Subsystem',
        'description': 'SCSI存储子系统',
        'keywords': ['scsi', 'sd', 'sg'],
        'common_functions': [
            'scsi_add_host', 'scsi_scan_host', 'scsi_host_alloc',
            'scsi_execute'
        ]
    },
    'ata': {
        'name': 'ATA/SATA',
        'description': 'ATA/SATA存储驱动',
        'keywords': ['ata', 'sata', 'ahci'],
        'common_functions': [
            'ata_host_register', 'ata_host_activate', 'ahci_platform_init_host'
        ]
    },
    'mtd': {
        'name': 'MTD (Memory Technology Device)',
        'description': 'MTD子系统，用于Flash等存储设备',
        'keywords': ['mtd', 'nand', 'nor', 'flash'],
        'common_functions': [
            'mtd_device_register', 'nand_scan', 'add_mtd_partitions'
        ]
    },
    'iio': {
        'name': 'Industrial I/O',
        'description': '工业I/O子系统，用于ADC、DAC、传感器等',
        'keywords': ['iio', 'adc', 'dac', 'sensor'],
        'common_functions': [
            'iio_device_register', 'iio_trigger_register', 'iio_push_event'
        ]
    },
    'thermal': {
        'name': 'Thermal Management',
        'description': '热管理子系统',
        'keywords': ['thermal', 'cooling', 'temperature'],
        'common_functions': [
            'thermal_zone_device_register', 'thermal_cooling_device_register'
        ]
    },
    'hwmon': {
        'name': 'Hardware Monitoring',
        'description': '硬件监控子系统，监测温度、电压、风扇等',
        'keywords': ['hwmon', 'sensor', 'temperature', 'voltage'],
        'common_functions': [
            'hwmon_device_register', 'devm_hwmon_device_register_with_groups'
        ]
    },
    'leds': {
        'name': 'LED Subsystem',
        'description': 'LED子系统',
        'keywords': ['led', 'backlight'],
        'common_functions': [
            'led_classdev_register', 'devm_led_classdev_register'
        ]
    },
    'sound': {
        'name': 'Sound (ALSA)',
        'description': '音频子系统(ALSA)',
        'keywords': ['sound', 'alsa', 'audio', 'pcm', 'codec'],
        'common_functions': [
            'snd_soc_register_card', 'snd_pcm_new', 'snd_card_register'
        ]
    },
    'media': {
        'name': 'Media Subsystem',
        'description': '多媒体子系统，包括摄像头、视频编解码等',
        'keywords': ['media', 'v4l2', 'video', 'camera'],
        'common_functions': [
            'video_register_device', 'v4l2_device_register'
        ]
    },
    'bluetooth': {
        'name': 'Bluetooth',
        'description': '蓝牙子系统',
        'keywords': ['bluetooth', 'bt', 'hci'],
        'common_functions': [
            'hci_register_dev', 'bt_sock_register'
        ]
    },
    'tty': {
        'name': 'TTY/Serial',
        'description': 'TTY和串口子系统',
        'keywords': ['tty', 'serial', 'uart'],
        'common_functions': [
            'uart_register_driver', 'uart_add_one_port', 'tty_register_driver'
        ]
    },
    'platform': {
        'name': 'Platform Devices',
        'description': '平台设备驱动',
        'keywords': ['platform', 'platform_device', 'platform_driver'],
        'common_functions': [
            'platform_driver_register', 'platform_device_register'
        ]
    },
    'of': {
        'name': 'Device Tree',
        'description': '设备树(Device Tree)支持',
        'keywords': ['of', 'devicetree', 'dt'],
        'common_functions': [
            'of_match_device', 'of_property_read_u32', 'of_get_named_gpio'
        ]
    },
    'irqchip': {
        'name': 'Interrupt Controllers',
        'description': '中断控制器',
        'keywords': ['irq', 'irqchip', 'interrupt'],
        'common_functions': [
            'irq_domain_add_linear', 'irq_set_chip_and_handler'
        ]
    },
    'firmware': {
        'name': 'Firmware Loader',
        'description': '固件加载器',
        'keywords': ['firmware'],
        'common_functions': [
            'request_firmware', 'release_firmware'
        ]
    },
    'power': {
        'name': 'Power Management',
        'description': '电源管理',
        'keywords': ['power', 'pm', 'suspend', 'resume'],
        'common_functions': [
            'pm_runtime_enable', 'pm_runtime_get_sync', 'register_pm_notifier'
        ]
    }
}
