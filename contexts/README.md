# 用户上下文配置目录

这个目录包含各种平台和驱动的用户上下文配置文件，用于辅助 LLM 进行更准确的入口点选择。

## 可用配置

| 文件 | 平台 | 驱动 | 说明 |
|------|------|------|------|
| `rk3288.yaml` | Rockchip RK3288 | dw_mci_rockchip | RK3288 平台 MMC 驱动 |
| `kirin960.yaml` | Hisilicon Kirin 960 | dw_mci_hi3660 | Kirin 960 平台 MMC 驱动 |
| `imx28.yaml` | NXP i.MX28 | mxs_mmc | i.MX28 平台 MMC 驱动 |
| `minimal_example.yaml` | - | - | 最小配置示例 |

## 使用方法

### 命令行方式

```bash
python run_bug_localization.py \
    --log-file error.log \
    --enable-llm-log-analysis \
    --user-context contexts/rk3288.yaml
```

### 配置文件方式

在 `config/bug_localization_config.yaml` 中：

```yaml
scenarios:
  my_scenario:
    log_file: logs/error.log
    user_context_file: contexts/rk3288.yaml
```

## 创建自定义配置

### 1. 复制示例文件

```bash
cp contexts/minimal_example.yaml contexts/my_platform.yaml
```

### 2. 编辑配置

```yaml
platform: <您的平台名>
driver_hint: <驱动类型>
# ... 其他可选字段
```

### 3. 使用配置

```bash
python run_bug_localization.py \
    --log-file error.log \
    --enable-llm-log-analysis \
    --user-context contexts/my_platform.yaml
```

## 配置字段说明

### 必需字段

- `platform`: 硬件平台名称（如 RK3288）
- `driver_hint`: 驱动类型提示（如 dw_mci）

### 可选字段

- `vendor`: 硬件厂商
- `soc_model`: SoC 型号
- `driver_name`: 完整驱动名
- `subsystem`: 内核子系统
- `known_entry`: 已知入口函数
- `description`: 详细描述
- `exclude`: 排除的驱动列表

更多详情请参阅 [USER_CONTEXT_GUIDE.md](../USER_CONTEXT_GUIDE.md)

## 贡献新配置

如果您为新平台创建了配置文件，欢迎贡献！请确保：

1. 配置文件命名清晰（如 `<platform>_<driver>.yaml`）
2. 包含必要的注释说明
3. 测试配置文件可正常工作
4. 更新本 README 的配置列表
