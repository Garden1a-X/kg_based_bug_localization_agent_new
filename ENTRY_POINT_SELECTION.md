# 入口点选择功能

## 概述

实现了智能入口点选择功能，支持 LLM 基于日志和候选入口自动确定调用链起点，并在无法确定时提供降级方案。

---

## 核心特性

### 1. **配置化的候选入口集合**
- 支持多个子系统的入口点配置（MMC、USB、网络等）
- 区分 KO 初始化入口（probe）和 SDK API 入口
- 支持平台到驱动的映射

### 2. **LLM 智能分析**
- 基于日志内容、候选入口列表和用户上下文进行分析
- 返回置信度评分（0.0-1.0）
- 提供推理过程说明

### 3. **降级模式**
- 当置信度低于 0.6 或 LLM 不可用时自动启用
- 使用日志中最上层的函数作为降级入口
- 提示用户需要的额外信息

### 4. **用户交互**
- 清晰显示置信度和模式状态
- 提供具体的信息补充建议
- 支持用户提供额外上下文

---

## 修改的文件

### 1. 新增文件

#### `config/entry_points.py`
候选入口点配置文件，包含：
- `ENTRY_POINT_SETS`: 各子系统的入口配置
- `PLATFORM_DRIVER_MAP`: 平台到驱动的映射
- `get_candidate_entries_for_subgraph()`: 获取子图候选入口
- `suggest_entry_by_platform()`: 基于平台建议入口

**配置的子系统**：
- MMC/SD (10+ 驱动)
- USB (10+ 驱动)
- Network
- I2C
- SPI
- PCIe
- Block
- GPU

### 2. 修改的文件

#### `llm/llm_client.py`
修改 `analyze_log()` 方法：
- **新增参数**：
  - `candidate_entries`: 候选入口列表
  - `user_context`: 用户上下文（平台、驱动提示等）
- **返回字段**：
  - `start_entity`: 推断的入口函数
  - `start_confidence`: 置信度 (0.0-1.0)
  - `reasoning`: 推理过程
  - `need_more_info`: 是否需要更多信息
  - `suggestions`: 建议提供的信息

#### `agents/log_parser_agent.py`
修改 `parse_mmc_log()` 方法：

**新增参数**：
```python
def parse_mmc_log(
    log_text: str,
    candidate_entries: list = None,
    user_context: dict = None
) -> Dict:
```

**返回字段**：
```python
{
    'inferred_entry': str,           # 推断的入口（不再硬编码）
    'entry_confidence': float,        # 置信度 0.0-1.0
    'need_more_info': bool,          # 是否需要更多信息
    'fallback_mode': bool,           # 是否为降级模式
    'suggestions': list,             # 建议提供的信息
    'llm_reasoning': list,           # LLM 推理过程
    # ... 其他原有字段
}
```

**降级逻辑**：
```python
if not result['inferred_entry'] or result['entry_confidence'] < 0.6:
    # 使用日志最上层函数作为降级入口
    result['inferred_entry'] = all_functions[-1]
    result['entry_confidence'] = 0.3
    result['fallback_mode'] = True
```

#### `coordinator/master_coordinator.py`
修改 `process_top_k()` 方法：

1. **导入配置**：
```python
from config.entry_points import get_candidate_entries_for_subgraph
```

2. **获取候选入口**：
```python
if selected_subgraph:
    entry_config = get_candidate_entries_for_subgraph(selected_subgraph)
    candidate_entries = entry_config.get('ko_init', []) + entry_config.get('sdk_api', [])
```

3. **传入候选入口**：
```python
parsed_log = self.log_parser.parse_mmc_log(
    log_text,
    candidate_entries=candidate_entries
)
```

4. **显示降级提示**：
```python
if parsed_log.get('need_more_info'):
    console.print("⚠️  需要更多信息才能确定完整调用链入口")
    if parsed_log.get('fallback_mode'):
        console.print("已启用降级模式：使用日志函数作为起点")
```

5. **修改 `_display_parsed_log()`**：
显示置信度和模式状态：
```python
if confidence >= 0.6:
    entry_display = f"{entry} (置信度: {confidence:.1%})"
else:
    entry_display = f"{entry} (置信度: {confidence:.1%}, 降级模式)"
```

### 3. 测试文件

#### `test_entry_point_selection.py`
测试脚本，包含：
- 配置文件加载测试
- 带候选入口的日志解析测试
- 带用户上下文的日志解析测试
- 降级模式测试

---

## 使用方式

### 1. 自动模式（推荐）

```python
from coordinator.master_coordinator import MasterCoordinator

coordinator = MasterCoordinator(
    data_dir='/data/xuao/code_kg_search/linux_test/data',
    enable_llm_log_analysis=True,
    enable_subgraph_selection=True,
    llm_config={
        'backend': 'openai',
        'model': 'gpt-4o-mini',
        'base_url': 'http://10.12.208.86:8502'
    }
)

# LLM 会自动从候选入口中选择
result = coordinator.process_top_k(
    log_text="mmc0: tuning execution failed: -1",
    k=5
)
```

### 2. 带用户上下文

```python
# 用户提供额外信息
user_context = {
    'platform': 'RK3288',
    'driver_hint': 'Designware MMC'
}

# 通过 run_with_config.py 传入
# 或直接在代码中使用（需要修改接口）
```

### 3. 查看结果

```python
if result['success']:
    print(f"入口: {result['parsed_log']['inferred_entry']}")
    print(f"置信度: {result['parsed_log']['entry_confidence']:.1%}")

    if result['parsed_log'].get('fallback_mode'):
        print("⚠️ 降级模式：仅展示部分调用链")
        print(f"建议提供: {result['parsed_log']['suggestions']}")
```

---

## 工作流程

```
┌─────────────────────────────────────────┐
│ 1. 日志输入                              │
│    "mmc0: tuning execution failed"      │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 2. 子图选择（如果启用）                   │
│    → 选择 'mmc' 子图                     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 3. 获取候选入口                          │
│    → 加载 mmc 子图的候选入口列表          │
│    [dw_mci_pltfm_probe, mxs_mmc_probe...] │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 4. LLM 分析日志                          │
│    输入：日志 + 候选入口 + 用户上下文      │
│    输出：入口 + 置信度 + 推理             │
└──────────────┬──────────────────────────┘
               │
               ├─── 置信度 >= 0.6 ────────┐
               │                          │
               │                          ▼
               │              ┌───────────────────────┐
               │              │ 5a. 正常模式           │
               │              │  使用 LLM 推断的入口   │
               │              └───────────────────────┘
               │
               └─── 置信度 < 0.6 ─────────┐
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │ 5b. 降级模式           │
                              │  使用日志最上层函数     │
                              │  提示需要更多信息       │
                              └───────────────────────┘
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │ 6. 显示建议            │
                              │  "建议提供平台信息"     │
                              └───────────────────────┘
```

---

## 关键决策

### 1. **为什么删除硬编码？**
- 原代码：`result['inferred_entry'] = 'dw_mci_pltfm_probe'`
- 问题：只适用于特定驱动，不通用
- 解决：让 LLM 基于候选列表选择，失败则降级

### 2. **为什么置信度阈值是 0.6？**
- < 0.6：信息不足，需要用户补充
- 0.6-0.8：有一定证据，可接受
- > 0.8：非常确定

### 3. **降级入口为什么是 `all_functions[-1]`？**
- `all_functions[0]`：错误点（最底层）
- `all_functions[-1]`：日志最上层函数，更接近入口方向
- 搜索 `all_functions[-1]` → `all_functions[0]` 仍有价值

### 4. **为什么不做反向搜索？**
- 异步调用无法反向追溯
- 函数指针关系是单向的
- 必须正向搜索才能处理间接调用

---

## 测试方法

### 运行测试脚本
```bash
python test_entry_point_selection.py
```

### 测试场景
1. **配置加载**：验证 30+ 个驱动入口已加载
2. **LLM 高置信度**：提供候选 + 明确日志 → 置信度 > 0.6
3. **LLM 低置信度**：模糊日志 → 置信度 < 0.6，降级
4. **LLM 不可用**：直接降级到日志函数

### 预期输出
```
测试1: 配置文件加载
✓ MMC 子图候选入口数量: 10
✓ RK3288 平台建议入口: dw_mci_pltfm_probe

测试2: 日志解析（带候选入口）
推断入口: dw_mci_pltfm_probe
入口置信度: 75%
需要更多信息: False

测试3: 日志解析（带用户上下文）
✓ 推断入口: dw_mci_pltfm_probe
✓ 置信度: 85%

测试4: 降级模式
✓ 推断入口: mmc_attach_mmc (降级)
✓ 置信度: 30%
✓ 建议: 硬件平台信息, 驱动类型提示
```

---

## 后续扩展

### 可选功能
1. **多候选尝试**：置信度低时尝试多个候选入口
2. **反向验证**：检查选定入口能否到达错误点
3. **学习优化**：记录用户反馈，优化选择策略
4. **配置热更新**：支持用户添加自定义入口

### 配置扩展
1. 添加更多子系统（文件系统、音频等）
2. 细化平台映射（更多硬件平台）
3. 支持用户自定义候选入口配置文件

---

## 总结

✅ **实现了**：
- 无硬编码的入口选择
- LLM 智能分析 + 置信度评估
- 降级模式 + 用户提示
- 配置化的候选入口管理

✅ **优势**：
- 通用性：支持多个子系统
- 可靠性：有降级保障
- 透明性：清晰的置信度和建议
- 可扩展：易于添加新驱动

✅ **用户体验**：
- 自动模式：一键分析
- 补充模式：提供上下文后重新分析
- 降级模式：即使无法确定完整链，也能提供部分信息
