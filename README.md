# Bug定位系统 - 基于知识图谱与LLM

一个基于知识图谱的Linux内核Bug定位系统，结合大语言模型(LLM)实现智能调用链追踪。支持**子图自动选择**、**Top-K路径搜索**和**间接调用检测**。

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## 📋 目录

- [核心特性](#核心特性)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [使用方式](#使用方式)
- [配置说明](#配置说明)
- [项目结构](#项目结构)
- [依赖项](#依赖项)
- [测试](#测试)
- [文档](#文档)

---

## 🎯 核心特性

### 1. 子图自动选择 ⭐ NEW

- **智能选择**：基于错误日志内容，LLM自动选择最相关的Linux驱动子系统（MMC、USB、Network等30+个子系统）
- **元数据驱动**：详细的子系统元数据（关键字、常见函数、描述）指导LLM选择
- **灵活模式**：支持自动选择、手动指定或传统方式（直接指定子图路径）

```bash
# 自动选择mmc子图
python run_bug_localization.py \
    --data-dir /data/.../data \  # 父目录
    --log "mmc0: tuning execution failed: -1" \
    --enable-subgraph-selection  # LLM自动选择
```

### 2. Top-K路径搜索

- **多路径分析**：返回Top-K条从入口到错误点的调用链
- **智能评分**：综合考虑路径长度、间接调用数量、调用行号、关键函数覆盖率
- **关键函数检测**：自动识别日志中的关键函数并优先选择包含这些函数的路径

### 3. LLM辅助间接调用检测

- **函数指针调用**：LLM分析源码提取结构体字段，查询图谱ASSIGNED_TO关系
- **异步调用检测**：识别`schedule_*`、`queue_work`等异步调度，追踪工作队列回调
- **延迟工作分析**：检测`schedule_delayed_work`并提取工作结构体字段

### 4. 统一LLM客户端架构

- **多后端支持**：支持OpenAI API、Ollama本地部署、vLLM等OpenAI兼容服务
- **灵活切换**：通过配置即可在不同LLM后端间切换（无需修改代码）
- **专用方法**：针对不同场景的专用接口（日志分析、代码关系分析、参数提取等）
- **易于扩展**：基于策略模式，可轻松添加新的LLM后端

### 5. 双模式支持

- **自动推断模式**：从日志自动提取入口函数、错误点和关键函数
- **手动指定模式**：显式指定起点、终点和中间节点，适用于已知调用链的场景

---

## 🏗️ 系统架构

```
┌───────────────────────────────────────────────────────────────────┐
│                      MasterCoordinator                             │
│                      (主协调器)                                      │
└──────────────┬────────────────────────────────────────────────────┘
               │
       ┌───────┼───────┬──────────┬──────────────┬─────────────┐
       │       │       │          │              │             │
       ▼       ▼       ▼          ▼              ▼             ▼
  ┌────────┬────────┬──────┬──────────┬──────────────┬────────────┐
  │Subgraph│  Log   │Entity│  Chain   │ Source Code  │LLM Indirect│
  │Selector│ Parser │Locator│ Tracer  │Bridge Finder │Call Detector│
  └────────┴────────┴────────┴──────┴──────────────┴────────────┘
               │
               ▼
       ┌───────────────┐        ┌─────────────────┐
       │ KG Interface  │───────►│   LLM Client    │
       │ (知识图谱)     │        │  (统一接口)      │
       └───────────────┘        └─────────────────┘
               │                        │
               ▼                        ▼
       ┌───────────────┐        ┌─────────────────┐
       │   Neo4j DB    │        │ OpenAI/vLLM/... │
       │   (图数据库)   │        │  (LLM后端)       │
       └───────────────┘        └─────────────────┘
```

### 核心组件

| 组件 | 职责 | 主要功能 |
|------|------|----------|
| **SubgraphSelector** | 子图智能选择 | 基于日志/函数名选择最相关子图 |
| **LogParser** | 日志解析 | 提取错误码、关键函数、推断入口/错误点 |
| **EntityLocator** | 实体定位 | 在图谱中查找函数实体（精确/模糊匹配） |
| **ChainTracer** | 调用链追踪 | Top-K路径搜索、断点修复、间接调用检测 |
| **SourceCodeBridgeFinder** | 源码桥接 | LLM分析源码连接断开的路径段 |
| **KGInterface** | 图谱接口 | 统一的知识图谱查询接口 |
| **LLMClient** | LLM客户端 | 统一的LLM调用接口，支持多后端 |

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖：
- `neo4j` - 图数据库驱动
- `openai` - OpenAI API客户端
- `pyyaml` - YAML配置文件支持（可选）
- `rich` - 美化控制台输出

### 2. 准备知识图谱数据

确保知识图谱数据已经构建并存储在Neo4j数据库中，或者使用导出的JSON格式数据：

```bash
# 数据目录结构
/data/xuao/code_kg_search/linux_test/data/
├── mmc/              # MMC子图
│   ├── entities.json
│   ├── relations.json
│   └── call_lines.json
├── usb/              # USB子图
├── net/              # 网络子图
└── ...               # 其他子图
```

### 3. 配置LLM服务

系统支持多种LLM后端，可通过配置灵活切换：

#### 选项1：OpenAI-compatible API（默认）

```bash
# 使用默认配置（vLLM服务）
# 默认：http://10.12.208.86:8502，模型：gpt-4o-mini
python run_bug_localization.py ...

# 或自定义OpenAI-compatible服务
python run_bug_localization.py \
    --llm-base-url http://your-server:8000 \
    --llm-model your-model-name \
    ...
```

#### 选项2：Ollama本地部署（推荐用于华为内网）

```bash
# 方式1：通过命令行参数（需修改run_bug_localization.py支持）
# 目前请使用配置文件模式或示例脚本

# 方式2：配置文件模式（推荐）
# 编辑 config/bug_localization_config.yaml:
llm:
  backend: "ollama"
  host: "http://10.78.108.45:11434"
  model: "qwen3:4b-instruct-2507-fp16"

# 然后运行
python run_with_config.py --scenario mmc_auto
```

#### 选项3：华为内部OpenAI-compatible服务

```bash
# 编辑 config/bug_localization_config.yaml:
llm:
  backend: "openai"
  base_url: "http://openai.md.huawei.com/"
  api_key: "your_huawei_api_key"
  model: "DS-V3-0324"  # 或 DS-R1-05xx, gpt-oss-120b, qwen3-coder-480b

# 然后运行
python run_with_config.py --scenario mmc_auto
```

#### 测试LLM连接

```bash
# 测试Ollama连接
python test_ollama_connection.py

# 查看支持的配置
cat config/bug_localization_config.example.yaml
```

### 4. 运行第一个分析

**方式1：命令行模式（推荐用于快速测试）**

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-subgraph-selection \
    --k 5
```

**方式2：配置文件模式（推荐用于生产环境）**

```bash
# 1. 复制配置模板
cp config/bug_localization_config.example.yaml config/bug_localization_config.yaml

# 2. 编辑配置文件
vim config/bug_localization_config.yaml

# 3. 运行预设场景
python run_with_config.py --scenario mmc_auto
```

**方式3：使用示例脚本**

```bash
# 标准模式（启用子图自动选择）
python examples/run_mmc_case_topk.py

# LLM辅助检测模式
python examples/run_mmc_case_topk.py --llm

# 传统模式（不启用子图选择）
python examples/run_mmc_case_topk.py --traditional
```

---

## 💡 使用方式

### 命令行模式

#### 自动推断模式（基于日志）

最简单的使用方式，系统自动分析日志并推断起止点：

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-subgraph-selection \
    --k 5 \
    --output output/result.json
```

#### 手动指定模式

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

#### 从文件读取日志

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log-file error.log \
    --enable-subgraph-selection \
    --k 5
```

#### 启用LLM辅助功能

```bash
# 启用间接调用检测
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-llm-detection \
    --enable-subgraph-selection \
    --k 5

# 启用日志分析
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-llm-log-analysis \
    --enable-subgraph-selection \
    --k 5
```

### 配置文件模式

适合固定配置、反复使用的场景：

#### 1. 配置文件示例

```yaml
# bug_localization_config.yaml
data_dir: "/data/xuao/code_kg_search/linux_test/data"
top_k: 5

subgraph_selection:
  enabled: true
  manual_subgraph: null  # 或指定 "mmc"

llm:
  detection:
    enabled: true
  log_analysis:
    enabled: false

  # LLM后端选择（支持 'openai' 或 'ollama'）
  backend: "openai"

  # OpenAI-compatible配置
  model: "gpt-4o-mini"
  base_url: "http://10.12.208.86:8502"
  api_key: ""

  # Ollama配置（如需使用，将backend改为"ollama"并取消注释）
  # backend: "ollama"
  # host: "http://10.78.108.45:11434"
  # model: "qwen3:4b-instruct-2507-fp16"

output:
  directory: "output"
  filename: "result.json"

scenarios:
  mmc_auto:
    description: "MMC错误自动推断"
    log_file: "examples/logs/mmc_error.log"
    mode: "auto"
```

#### 2. 使用预设场景

```bash
# 列出所有可用场景
python run_with_config.py

# 运行指定场景
python run_with_config.py --scenario mmc_auto
python run_with_config.py --scenario mmc_manual
```

### 输出结果

分析结果会保存为JSON格式：

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
      "matched_key_functions": ["mmc_attach_mmc", "mmc_execute_tuning"]
    }
  ]
}
```

控制台也会显示实时进度和结果摘要。

---

## ⚙️ 配置说明

### 子图选择配置

```bash
# 启用自动选择（推荐）
--enable-subgraph-selection

# 手动指定子图
--enable-subgraph-selection --subgraph mmc

# 传统方式（不启用子图选择）
--data-dir /data/.../data/mmc  # 直接指定子图路径
```

### LLM功能配置

```bash
# 间接调用检测（用于运行时分析delayed work等）
--enable-llm-detection

# 日志分析（使用LLM深度分析日志）
--enable-llm-log-analysis

# 自定义LLM服务
--llm-model gpt-4
--llm-base-url http://your-server:8000
```

### Top-K配置

```bash
# 返回路径数量
--k 5  # 默认值

# 一般分析：--k 3（快速）
# 详细分析：--k 5（平衡）
# 深度分析：--k 10（全面）
```

---

## 📁 项目结构

```
kg_based_bug_localization_agent/
├── agents/                      # Agent模块
│   ├── base_agent.py            # Agent基类
│   ├── log_parser_agent.py      # 日志解析Agent
│   ├── entity_locator_agent.py  # 实体定位Agent
│   ├── chain_tracer_agent.py    # 调用链追踪Agent
│   └── source_code_bridge_finder.py  # 源码桥接Agent
├── coordinator/                 # 协调器
│   └── master_coordinator.py    # 主协调器
├── data/                        # 数据层
│   ├── kg_interface.py          # 知识图谱接口
│   └── mock_indirect_calls.py   # Mock数据（用于fallback）
├── llm/                         # LLM模块
│   ├── llm_client.py            # 统一LLM客户端
│   ├── backends/                # LLM后端
│   │   ├── base.py              # 后端基类
│   │   ├── openai_backend.py    # OpenAI兼容后端
│   │   ├── ollama_backend.py    # Ollama本地部署后端
│   │   └── local_backend.py     # 本地后端（占位）
│   └── openai_client.py         # 旧版客户端（向后兼容）
├── utils/                       # 工具模块
│   ├── logger.py                # 日志工具
│   ├── subgraph_selector.py     # 子图选择器
│   ├── llm_indirect_call_detector.py  # LLM间接调用检测
│   └── source_code_reader.py    # 源码读取工具
├── config/                      # 配置
│   ├── subgraph_metadata.py     # 子图元数据（30+子系统）
│   └── bug_localization_config.example.yaml  # 配置文件模板
├── examples/                    # 示例脚本
│   └── run_mmc_case_topk.py     # MMC案例示例
├── run_bug_localization.py      # 主入口脚本（命令行模式）
├── run_with_config.py           # 主入口脚本（配置文件模式）
├── test_*.py                    # 测试脚本
├── test_ollama_connection.py   # Ollama连通性测试
├── verify_graph_structure.py   # 图谱结构验证工具
├── USAGE.md                     # 详细使用文档
└── README.md                    # 本文件
```

---

## 📦 依赖项

### 必需依赖

```txt
neo4j>=5.0.0              # Neo4j图数据库驱动
openai>=1.0.0             # OpenAI API客户端（用于OpenAI-compatible后端）
requests>=2.28.0          # HTTP请求库（用于Ollama后端）
rich>=13.0.0              # 美化控制台输出
```

### 可选依赖

```txt
pyyaml>=6.0               # YAML配置文件支持（用于配置文件模式）
```

### LLM后端依赖说明

- **OpenAI-compatible后端**：需要 `openai` 库（适用于OpenAI API、vLLM、华为内部服务等）
- **Ollama后端**：需要 `requests` 库（HTTP直接通信）

### Python版本

- Python 3.8+

---

## 🧪 测试

### 运行单元测试

```bash
# 测试子图选择器
python test_subgraph_selector.py

# 测试集成功能
python test_integrated_subgraph_selection.py

# 测试间接调用图谱
python test_indirect_calls_graph.py

# 测试日志匹配
python test_log_matching.py
```

### 验证图谱结构

```bash
python verify_graph_structure.py /data/xuao/code_kg_search/linux_test/data/mmc
```

---

## 📚 文档

- [USAGE.md](USAGE.md) - 详细使用指南（参数说明、最佳实践、故障排查）
- [TOP_K_FEATURE.md](TOP_K_FEATURE.md) - Top-K路径搜索特性文档
- [INTEGRATION_SUMMARY.md](INTEGRATION_SUMMARY.md) - 集成总结
- [DEPLOYMENT.md](DEPLOYMENT.md) - 部署指南

---

## 🎯 使用场景

### 场景1：快速分析一个错误

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-subgraph-selection \
    --k 3
```

### 场景2：批量分析多个日志

```bash
#!/bin/bash
for log in logs/*.log; do
    python run_bug_localization.py \
        --data-dir /data/xuao/code_kg_search/linux_test/data \
        --log-file "$log" \
        --enable-subgraph-selection \
        --output "output/$(basename $log .log).json" \
        --k 5
done
```

### 场景3：深度分析（启用所有LLM功能）

```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log "mmc0: tuning execution failed: -1" \
    --enable-subgraph-selection \
    --enable-llm-detection \
    --enable-llm-log-analysis \
    --k 10
```

---

## 🤝 贡献

欢迎提交Issue和Pull Request！

---

## 📄 许可证

MIT License

---

## 📧 联系方式

如有问题或建议，请通过Issue与我们联系。

---

**最后更新**：2025-11-24
