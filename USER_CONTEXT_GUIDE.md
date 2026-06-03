# 用户上下文功能使用指南

## 概述

用户上下文功能允许您提供额外的平台、驱动等信息，帮助 LLM 更准确地选择调用链入口点。

## 为什么需要用户上下文？

当错误日志信息较少时（如只有 "mmc0: tuning failed"），LLM 无法确定具体使用的是哪个驱动（dw_mci、sdhci、mxs_mmc 等）。此时，提供用户上下文可以：

- **提高置信度**：从 30% 提升到 80%+
- **避免降级模式**：直接选择正确的入口，而不是使用日志最上层函数
- **减少分析时间**：无需多次尝试或手动指定

## 使用方式

### 方式1：命令行 (run_bug_localization.py)

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log-file error.log \
    --enable-llm-log-analysis \
    --user-context contexts/rk3288.yaml \
    --k 5
```

### 方式2：配置文件 (run_with_config.py)

编辑 `config/bug_localization_config.yaml`：

```yaml
scenarios:
  mmc_rk3288:
    description: "RK3288 平台 MMC 问题"
    mode: auto
    log_file: logs/mmc_error.log
    user_context_file: contexts/rk3288.yaml  # ← 指定上下文文件
```

运行：
```bash
python run_with_config.py --scenario mmc_rk3288
```

## 上下文文件格式

### 最小配置

```yaml
# contexts/minimal.yaml
platform: RK3288
driver_hint: dw_mci
```

### 完整配置

```yaml
# contexts/rk3288.yaml

# 硬件平台信息
platform: RK3288                  # 平台名称
vendor: Rockchip                  # 硬件厂商
soc_model: RK3288                 # SoC 型号

# 驱动信息
driver_hint: dw_mci               # 驱动类型提示
driver_name: dw_mci_rockchip      # 具体驱动名
subsystem: mmc                    # 子系统

# 已知入口（可选）
known_entry: dw_mci_rockchip_probe

# 功能模块（可选）
feature: tuning
operation: card_init

# 自由描述（可选）
description: |
  Rockchip RK3288 平台
  使用 DesignWare MMC 控制器的 Rockchip 定制版本
  驱动文件：drivers/mmc/host/dw_mmc-rockchip.c

# 已知路径提示（可选）
known_path_hints:
  - dw_mci_rockchip_probe
  - mmc_add_host
  - mmc_start_host

# 排除信息（可选）
exclude:
  - sdhci
  - mxs_mmc
```

## 可用字段说明

### 核心字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `platform` | 硬件平台名称 | RK3288, Kirin 960 |
| `driver_hint` | 驱动类型提示 | dw_mci, sdhci, mxs_mmc |
| `vendor` | 硬件厂商 | Rockchip, Hisilicon, NXP |
| `driver_name` | 完整驱动名 | dw_mci_rockchip |

### 可选字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `subsystem` | 内核子系统 | mmc, usb, net |
| `known_entry` | 已知的入口函数 | dw_mci_rockchip_probe |
| `feature` | 相关功能模块 | tuning, dma_transfer |
| `operation` | 具体操作 | card_init, suspend |
| `description` | 自由文本描述 | （详细说明） |
| `known_path_hints` | 已知路径片段 | 函数名列表 |
| `exclude` | 排除的驱动 | 函数名列表 |

### 自定义字段

您可以添加任何自定义字段，LLM 会尝试理解：

```yaml
board: Firefly-RK3288
kernel_version: 5.10.0
custom_patches: true
issue_type: initialization_failure
```

## 效果对比

### 无用户上下文

```bash
$ python run_bug_localization.py --log-file error.log --enable-llm-log-analysis

⚠️  需要更多信息才能确定完整调用链入口
已启用降级模式：使用日志函数 'mmc_start_request' 作为起点
置信度: 30% (低)

💡 建议提供:
  • 硬件平台信息（如 RK3288, i.MX28）
  • 驱动类型提示（如 dw_mci, mxs_mmc）
```

### 提供用户上下文

```bash
$ python run_bug_localization.py --log-file error.log --enable-llm-log-analysis \
    --user-context contexts/rk3288.yaml

✓ 入口函数: dw_mci_rockchip_probe
置信度: 85% (高)
推理: 基于用户提供的平台信息(RK3288)和驱动提示(dw_mci)，
      确定为 Rockchip 平台的 DesignWare MMC 驱动
```

## 示例文件

项目提供了多个平台的示例配置：

- `contexts/rk3288.yaml` - Rockchip RK3288
- `contexts/kirin960.yaml` - Hisilicon Kirin 960
- `contexts/imx28.yaml` - NXP i.MX28
- `contexts/minimal_example.yaml` - 最小配置示例

## 使用建议

### 1. 第一次运行

如果不确定需要什么信息，先不提供用户上下文：

```bash
python run_bug_localization.py --log-file error.log --enable-llm-log-analysis
```

系统会提示需要哪些信息。

### 2. 创建上下文文件

根据提示创建上下文文件：

```yaml
# contexts/my_platform.yaml
platform: <您的平台>
driver_hint: <提示的驱动类型>
```

### 3. 再次运行

使用上下文文件重新运行：

```bash
python run_bug_localization.py --log-file error.log --enable-llm-log-analysis \
    --user-context contexts/my_platform.yaml
```

### 4. 复用配置

同一平台的其他问题可以复用相同的上下文文件。

## 常见问题

### Q: 必须提供用户上下文吗？

A: 不是必须的。如果日志信息足够详细（如包含驱动名），系统可以自动判断。但提供上下文可以提高准确性。

### Q: 如果提供了错误的信息会怎样？

A: LLM 会结合日志和用户上下文综合判断。如果发现矛盾，会降低置信度并提示。

### Q: 可以提供多个平台的配置吗？

A: 一次只能使用一个上下文文件。但您可以为不同场景创建多个文件。

### Q: 字段顺序重要吗？

A: 不重要。YAML 格式不关心字段顺序。

### Q: 可以使用中文吗？

A: 可以。LLM 支持中英文混合。

## 进阶用法

### 配置文件中的场景管理

```yaml
# config/bug_localization_config.yaml
scenarios:
  mmc_rk3288_init:
    description: "RK3288 初始化问题"
    mode: auto
    log_file: logs/rk3288_init.log
    user_context_file: contexts/rk3288.yaml

  mmc_rk3288_runtime:
    description: "RK3288 运行时问题"
    mode: auto
    log_file: logs/rk3288_runtime.log
    user_context_file: contexts/rk3288.yaml

  mmc_kirin_tuning:
    description: "Kirin 960 tuning 问题"
    mode: auto
    log_file: logs/kirin_tuning.log
    user_context_file: contexts/kirin960.yaml
```

### 条件性上下文

对于某些场景，可以在上下文中提供条件信息：

```yaml
# contexts/flexible.yaml
platform: RK3288 or RK3399
driver_hint: dw_mci
description: |
  适用于 Rockchip RK3288 和 RK3399 平台
  两者都使用 dw_mci 驱动，但具体实现略有不同
```

## 相关文档

- [ENTRY_POINT_SELECTION.md](ENTRY_POINT_SELECTION.md) - 入口选择功能说明
- [LLM_CONFIDENCE_IMPROVEMENT.md](LLM_CONFIDENCE_IMPROVEMENT.md) - 置信度评估机制
- [README.md](README.md) - 项目总体说明

## 支持

如有问题，请：
1. 检查日志输出中的错误信息
2. 验证 YAML 文件格式是否正确
3. 查看示例文件作为参考
