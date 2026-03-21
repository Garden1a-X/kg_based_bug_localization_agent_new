# ioctl_fops_mapper

将 Linux 源码中的 `ioctl()` 调用点映射到对应的 `file_operations` 结构体实例（`.unlocked_ioctl` handler）。

该工具是图谱构建流程的最后一个环节，输出的映射文件可供 bug 定位系统在追踪调用链时使用：当遇到 `ioctl(fd, cmd)` 调用时，通过查询映射文件找到对应的 handler 函数，继续追踪调用链。

## 架构

```
mapper/
├── scanner.py        # 扫描 .c/.h 文件，找所有 ioctl() 调用点
├── fops_indexer.py   # 建立 handler → file_operations 索引（KG + 源码双路径）
└── mapper_agent.py   # 主 Agent：协调 scanner、indexer、LLM
```

**支持两层索引构建策略：**
1. **KG 查询**（需要 `--kg-data-dir`）：通过 `ASSIGNED_TO` 关系找 `unlocked_ioctl` handler
2. **源码扫描 fallback**：regex 扫 `.c` 文件中的 `.unlocked_ioctl = xxx` 赋值

**支持两层映射策略：**
1. **LLM 辅助**（需要 `--llm-backend`）：LLM 分析调用点上下文，识别设备/驱动，精确匹配
2. **启发式匹配 fallback**：基于文件路径和函数名相似度

## 安装

```bash
pip install -r requirements.txt
```

## 用法

```bash
# 最简：只扫源码（无 KG、无 LLM）
python run_ioctl_mapper.py \
    --linux-src /path/to/linux \
    --output output/ioctl_mappings.json

# 完整模式（KG + OpenAI 兼容接口）
python run_ioctl_mapper.py \
    --linux-src /path/to/linux \
    --kg-data-dir /path/to/kg/data \
    --llm-backend openai \
    --llm-base-url http://10.x.x.x:8502 \
    --llm-model gpt-4o-mini \
    --output output/ioctl_mappings.json

# Ollama 本地 LLM
python run_ioctl_mapper.py \
    --linux-src /path/to/linux \
    --llm-backend ollama \
    --llm-host http://localhost:11434 \
    --llm-model qwen3:4b \
    --output output/ioctl_mappings.json

# 快速测试（只扫 mmc 子系统，限制 50 个文件）
python run_ioctl_mapper.py \
    --linux-src /path/to/linux \
    --subdirs drivers/mmc \
    --max-files 50 \
    --output output/ioctl_mmc_test.json
```

## 输出格式

```json
{
  "generated_at": "2025-01-01T00:00:00",
  "stats": {
    "total_call_sites": 120,
    "mapped": 95,
    "unresolved": 25,
    "coverage": 0.792
  },
  "mappings": [
    {
      "call_site": {
        "file": "tools/testing/mmc/mmc_test.c",
        "line": 42,
        "caller_func": "test_ioctl",
        "line_content": "ret = ioctl(fd, MMC_IOC_CMD, &data);"
      },
      "resolution": {
        "fops_variable": "mmc_fops",
        "unlocked_ioctl_handler": "mmc_ioctl",
        "field_name": "unlocked_ioctl",
        "fops_source_file": "drivers/mmc/core/block.c",
        "driver_module": "mmc"
      },
      "confidence": 0.85,
      "method": "llm+source_scan",
      "reasoning": "..."
    }
  ],
  "unresolved": [...]
}
```

## 复用的组件

- `data/kg_interface.py`：拷贝自 [kg_based_bug_localization_agent_new](../kg_based_bug_localization_agent_new)
- `llm/llm_client.py` + `llm/backends/`：同上，裁剪为通用 LLM 接口
- `utils/source_code_reader.py`：同上
