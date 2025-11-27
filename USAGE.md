# Bug定位系统使用指南

本文档介绍如何使用Bug定位分析系统的通用入口脚本。

## 快速开始

### 方式1：命令行模式（推荐用于临时分析）

最简单的使用方式：

```bash
# 基于日志自动推断（使用子图自动选择）
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-subgraph-selection \
    --k 5
```

### 方式2：配置文件模式（推荐用于生产环境）

适合固定配置、反复使用的场景：

```bash
# 1. 复制配置文件模板
cp config/bug_localization_config.example.yaml config/bug_localization_config.yaml

# 2. 编辑配置文件（根据需要修改）
vim config/bug_localization_config.yaml

# 3. 使用预设场景运行
python run_with_config.py --scenario mmc_auto

# 4. 或直接输入日志
python run_with_config.py --log "mmc0: tuning execution failed: -1"
```

---

## 命令行模式详解

### 基本参数

| 参数 | 必需 | 说明 | 示例 |
|------|------|------|------|
| `--data-dir` | ✓ | 知识图谱数据目录 | `/data/.../data` |
| `--log` | ✓* | 错误日志文本 | `"mmc0: error -1"` |
| `--log-file` | ✓* | 错误日志文件 | `error.log` |
| `--k` | - | Top-K路径数量 | `5`（默认） |
| `--output` | - | 输出文件路径 | `output/result.json` |

\* `--log` 和 `--log-file` 二选一

### 模式选择

#### 模式1：自动推断（基于日志）

系统自动从日志中推断起点和终点函数：

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-subgraph-selection \
    --k 5
```

#### 模式2：手动指定起止点

当你明确知道起点和终点函数时：

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --start-func dw_mci_pltfm_probe \
    --end-func dw_mci_execute_tuning \
    --intermediate-funcs mmc_attach_mmc mmc_execute_tuning \
    --enable-subgraph-selection \
    --k 5
```

### 子图选择

#### 启用自动子图选择（推荐）

让LLM根据日志内容自动选择相关子图：

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \  # 父目录
    --log "mmc0: tuning execution failed: -1" \
    --enable-subgraph-selection \  # 启用自动选择
    --k 5
```

#### 手动指定子图

直接指定要使用的子图：

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-subgraph-selection \
    --subgraph mmc \  # 手动指定使用mmc子图
    --k 5
```

#### 传统方式（不启用子图选择）

直接指定子图路径，不启用自动选择：

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data/mmc \  # 直接指定子图目录
    --log "mmc0: tuning execution failed: -1" \
    --k 5
```

### LLM功能

#### 启用LLM间接调用检测

用于运行时分析delayed work等复杂间接调用：

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-llm-detection \  # 启用LLM间接调用检测
    --enable-subgraph-selection \
    --k 5
```

#### 启用LLM日志分析

使用LLM深度分析日志内容：

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-llm-log-analysis \  # 启用LLM日志分析
    --enable-subgraph-selection \
    --k 5
```

#### 自定义LLM服务

使用不同的LLM模型或服务：

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-subgraph-selection \
    --llm-model gpt-4 \
    --llm-base-url http://your-llm-server:8000 \
    --k 5
```

### 从文件读取日志

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log-file /path/to/error.log \  # 从文件读取日志
    --enable-subgraph-selection \
    --k 5
```

---

## 配置文件模式详解

### 配置文件结构

```yaml
# 基本配置
data_dir: "/data/xuao/code_kg_search/linux_test/data"
top_k: 5

# 子图自动选择
subgraph_selection:
  enabled: true  # 启用自动选择
  manual_subgraph: null  # 或指定子图名，如 "mmc"

# LLM配置
llm:
  detection:
    enabled: true  # 启用间接调用检测
  log_analysis:
    enabled: false  # 启用日志分析
  model: "gpt-4o-mini"
  base_url: "http://10.12.208.86:8502"

# 输出配置
output:
  directory: "output"
  filename: "result.json"

# 预设场景
scenarios:
  mmc_auto:
    description: "MMC错误自动推断"
    log_file: "examples/logs/mmc_error.log"
    mode: "auto"

  mmc_manual:
    description: "MMC错误手动指定"
    log_file: "examples/logs/mmc_error.log"
    mode: "manual"
    start_func: "dw_mci_pltfm_probe"
    end_func: "dw_mci_execute_tuning"
    intermediate_funcs:
      - "mmc_attach_mmc"
      - "mmc_execute_tuning"
```

### 使用预设场景

```bash
# 列出所有可用场景
python run_with_config.py

# 使用指定场景
python run_with_config.py --scenario mmc_auto
python run_with_config.py --scenario mmc_manual
python run_with_config.py --scenario usb_auto
```

### 使用自定义配置文件

```bash
python run_with_config.py --config my_config.yaml --scenario mmc_auto
```

### 直接输入日志（使用配置文件中的其他设置）

```bash
python run_with_config.py --log "mmc0: tuning execution failed: -1"
```

---

## 输出结果

### JSON输出格式

结果会保存为JSON文件（默认：`output/result.json`）：

```json
{
  "success": true,
  "path_count": 5,
  "paths": [
    {
      "path": ["dw_mci_pltfm_probe", "dw_mci_probe", ..., "dw_mci_execute_tuning"],
      "length": 25,
      "indirect_count": 3,
      "score": 0.85,
      "avg_call_line": 156.3,
      "matched_key_functions": ["mmc_attach_mmc", "mmc_execute_tuning"],
      "breaks": [...],
      "edges": [...]
    },
    ...
  ],
  "parsed_log": {...},
  "entities": {...}
}
```

### 控制台输出

运行时会在控制台显示：
- 配置信息摘要
- 分析流程进度（步骤1/5、2/5等）
- 实体定位结果
- 调用链详情
- 分析结果摘要

---

## 常见使用场景

### 场景1：快速分析一个错误日志

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-subgraph-selection \
    --k 3
```

### 场景2：批量分析多个日志文件

```bash
#!/bin/bash
for log in logs/*.log; do
    echo "分析 $log ..."
    python run_bug_localization.py \
        --data-dir /data/xuao/code_kg_search/linux_test/data \
        --log-file "$log" \
        --enable-subgraph-selection \
        --output "output/$(basename $log .log).json" \
        --k 5
done
```

### 场景3：使用配置文件管理多个项目

```bash
# 项目A的配置
python run_with_config.py --config config/project_a.yaml --scenario default

# 项目B的配置
python run_with_config.py --config config/project_b.yaml --scenario default
```

### 场景4：调试模式（查看详细日志）

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-subgraph-selection \
    --verbose \
    --k 5
```

---

## 最佳实践

### 1. 数据目录选择

- ✅ **推荐**：使用父目录 + 启用子图自动选择
  ```bash
  --data-dir /data/.../data --enable-subgraph-selection
  ```

- ⚠️ **可选**：直接指定子图目录（传统方式）
  ```bash
  --data-dir /data/.../data/mmc
  ```

### 2. Top-K设置

- 一般分析：`--k 3`（速度快）
- 详细分析：`--k 5`（平衡）
- 深度分析：`--k 10`（全面但慢）

### 3. LLM功能

- 间接调用检测（`--enable-llm-detection`）：适用于复杂的异步调用场景
- 日志分析（`--enable-llm-log-analysis`）：适用于日志信息不明确时
- 子图选择（`--enable-subgraph-selection`）：**强烈推荐始终启用**

### 4. 输出管理

- 使用有意义的输出文件名：
  ```bash
  --output "output/mmc_tuning_error_$(date +%Y%m%d).json"
  ```

- 保存日志输出到文件：
  ```bash
  python run_bug_localization.py ... 2>&1 | tee analysis.log
  ```

---

## 故障排查

### 问题1：找不到数据目录

```
错误: 数据目录不存在: /data/...
```

**解决**：检查 `--data-dir` 路径是否正确，确保目录存在且有读权限。

### 问题2：无法定位起点或终点

```
✗ 无法定位起点或终点，分析终止
```

**解决**：
1. 尝试启用LLM日志分析：`--enable-llm-log-analysis`
2. 切换到手动指定模式，明确指定起止点函数
3. 检查日志格式是否包含关键函数信息

### 问题3：LLM服务不可用

```
ERROR: OpenAI 后端推理失败: Access denied
```

**解决**：
1. 检查 `--llm-base-url` 是否正确
2. 验证LLM服务是否可访问
3. 如果不需要LLM功能，可以不启用相关选项

### 问题4：子图选择失败

```
WARNING: 未选择到子图，使用默认图谱
```

**解决**：
1. 检查数据目录下是否有子图目录
2. 尝试手动指定子图：`--subgraph mmc`
3. 或使用传统方式，直接指定子图路径

---

## 参数快速参考

### 必需参数
- `--data-dir PATH` - 数据目录
- `--log TEXT` 或 `--log-file PATH` - 错误日志

### 可选参数
- `--k INT` - Top-K路径数量（默认：5）
- `--output PATH` - 输出文件（默认：output/result.json）
- `--verbose` - 详细日志

### 模式参数
- `--start-func NAME` - 起点函数
- `--end-func NAME` - 终点函数
- `--intermediate-funcs NAME [NAME ...]` - 中间节点

### 子图参数
- `--enable-subgraph-selection` - 启用自动选择
- `--subgraph NAME` - 手动指定子图

### LLM参数
- `--enable-llm-detection` - 启用间接调用检测
- `--enable-llm-log-analysis` - 启用日志分析
- `--llm-model NAME` - LLM模型（默认：gpt-4o-mini）
- `--llm-base-url URL` - LLM服务地址

---

## 帮助信息

获取完整的参数说明：

```bash
python run_bug_localization.py --help
python run_with_config.py --help
```
