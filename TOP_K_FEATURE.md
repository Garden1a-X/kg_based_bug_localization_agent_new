# Top-K路径搜索与call_line剪枝功能

## 🎯 新功能概述

本次更新引入了两个重要功能：

### 1. **Top-K路径搜索**
- 从原来只返回1条路径，改为可以返回K条（默认5条）候选路径
- 每条路径都包含完整的调用链、间接调用信息和得分
- 路径按得分排序，得分计算考虑：
  - 路径长度（越短越好）
  - 间接调用数量（越少越好）
  - 调用行号（平均行号越小越好，优先选择调用发生得更早的路径）

### 2. **call_line排序优化**
- 利用CALLS关系中新增的`call_line`字段（调用发生的行号）
- 用于路径排序：优先选择调用发生得更早的路径
- **注意**：不用于剪枝，因为调用链是跨函数的（如 D:50 -> B:10 -> A）
  - D的第50行调用B，B的第10行调用A
  - 这两个行号属于不同函数，不能直接比较进行剪枝
  - call_line主要用于在多条路径中排序，优先推荐调用更早的路径

### 3. **增大搜索深度**
- 将默认最大深度从20增加到30
- 由于使用MMC子图，性能不是问题，可以搜索更长的调用链

## 📊 数据格式

### CALLS关系新增字段

```json
{
  "head": "7",
  "tail": "6",
  "type": "CALLS",
  "call_line": 202,           // 新增：调用发生的行号
  "resolution_type": "function",
  "visibility_checked": true
}
```

### Top-K路径返回格式

```python
{
  'success': True,
  'path_count': 3,  # 找到的路径数量
  'paths': [
    {
      'path': ['func1', 'func2', ...],       # 调用路径
      'edges': ['direct', {...}, ...],       # 边类型
      'call_lines': [100, 205, None, ...],  # 每条边的调用行号
      'breaks': [...],                       # 间接调用断点信息
      'score': 985,                          # 路径得分
      'length': 16,                          # 路径长度
      'indirect_count': 4,                   # 间接调用数量
      'method': 'top_k_search',
      'success': True
    },
    # ... 更多路径
  ],
  'best_path': {...}  # 得分最高的路径（paths[0]）
}
```

## 🚀 使用方法

### 方式1：使用协调器（推荐）

```python
from coordinator.master_coordinator import MasterCoordinator

# 创建协调器
coordinator = MasterCoordinator(
    data_dir="/data/xuao/code_kg_search/linux_test/data/mmc"
)

# Top-K搜索（自动推断起止点）
result = coordinator.process_top_k(
    error_log,
    k=5  # 返回最多5条路径
)

# Top-K搜索（指定起止点）
result = coordinator.process_top_k_with_specific_functions(
    error_log,
    start_func='dw_mci_pltfm_probe',
    end_func='dw_mci_execute_tuning',
    k=5
)

# Top-K搜索（error_line参数已废弃，仅保留用于兼容性）
result = coordinator.process_top_k_with_specific_functions(
    error_log,
    start_func='dw_mci_pltfm_probe',
    end_func='dw_mci_execute_tuning',
    k=5,
    error_line=None  # 已不再用于剪枝，仅保留用于API兼容性
)

coordinator.close()
```

### 方式2：直接使用KG接口

```python
from data.kg_interface import KnowledgeGraphInterface

kg = KnowledgeGraphInterface(data_dir="...")

# Top-K路径搜索
paths = kg.find_top_k_call_paths_with_indirect(
    start='dw_mci_pltfm_probe',
    end='dw_mci_execute_tuning',
    max_depth=30,
    k=5,
    error_line=None,  # 已废弃：保留用于兼容性，不再用于剪枝
    debug=True
)

for path in paths:
    print(f"路径长度: {path['length']}")
    print(f"得分: {path['score']}")
    print(f"路径: {' -> '.join(path['path'])}")

kg.close()
```

### 方式3：使用Chain Tracer Agent

```python
from agents.chain_tracer_agent import CallChainTracerAgent
from data.kg_interface import KnowledgeGraphInterface

kg = KnowledgeGraphInterface(data_dir="...")
tracer = CallChainTracerAgent(kg, llm_client=None)

# Top-K搜索
paths = tracer.execute_top_k(
    start_entity={'name': 'dw_mci_pltfm_probe', ...},
    end_entity={'name': 'dw_mci_execute_tuning', ...},
    max_depth=30,
    k=5,
    error_line=None
)

for idx, path in enumerate(paths):
    print(f"路径 #{idx+1}:")
    print(f"  长度: {path['length']}")
    print(f"  间接调用: {path['indirect_count']}")
    print(f"  得分: {path['score']}")
```

## 📝 运行示例

### 示例1：运行Top-K搜索脚本

```bash
cd examples
python run_mmc_case_topk.py
```

这个脚本会演示：
1. 自动推断起止点 + Top-5路径
2. 指定起止点 + Top-5路径
3. Top-K路径搜索（包含call_line排序）

输出会保存到 `output/` 目录：
- `mmc_case_topk_auto.json`
- `mmc_case_topk_specific.json`

### 示例2：直接测试KG接口

```bash
cd examples
python run_mmc_case_topk.py --direct
```

这会直接调用KG接口的Top-K搜索方法，并打印详细的调试信息。

### 示例3：对比单路径vs多路径

```bash
# 运行原有的单路径搜索
python examples/run_mmc_case.py

# 运行新的Top-K路径搜索
python examples/run_mmc_case_topk.py
```

## 🔧 核心实现

### 1. 数据层 (kg_interface.py)

新增方法：
- `_build_call_graph_with_lines()`: 构建包含行号的调用图
- `find_top_k_call_paths_with_indirect()`: Top-K路径搜索
- `_get_callees_with_lines()`: 获取被调用者及行号（用于排序，不再用于剪枝）

新增数据结构：
```python
self.call_graph_with_lines = {
    caller_id: [
        {'callee_id': '123', 'call_line': 100},
        {'callee_id': '456', 'call_line': 205},
        ...
    ],
    ...
}
```

### 2. Agent层 (chain_tracer_agent.py)

新增方法：
- `execute_top_k()`: 追踪Top-K条调用链
- 默认`max_depth`从20增加到30

### 3. 协调器层 (master_coordinator.py)

新增方法：
- `process_top_k()`: 处理错误日志，返回Top-K路径
- `process_top_k_with_specific_functions()`: 指定起止点，返回Top-K路径
- `_display_multiple_chains()`: 显示多条调用链（包含call_line信息）
- `_generate_multi_path_report()`: 生成多路径分析报告
- `_display_multi_path_summary()`: 显示多路径总结

## 📊 性能对比

### 搜索空间

**Top-K搜索：**
- 探索所有可能的调用关系，找到K条最优路径
- 搜索空间：O(branching_factor ^ depth)
- call_line用于路径排序，不影响搜索空间大小

**路径排序：**
- 考虑路径长度、间接调用数量和平均调用行号
- 优先返回更短、间接调用更少、调用发生更早的路径

### 子图性能

使用MMC子图的优势：
- 完整图谱：~120秒加载 + 查询
- MMC子图：<1秒加载 + 查询
- **性能提升：120x** ⚡

即使搜索多条路径，在子图上仍然很快！

## 🎯 典型应用场景

### 场景1：多路径候选

```python
# 找出所有可能的调用链，让用户选择最可能的一条
result = coordinator.process_top_k(error_log, k=5)

print(f"找到 {result['path_count']} 条可能的调用链:")
for idx, path in enumerate(result['paths']):
    print(f"{idx+1}. 长度={path['length']}, 间接调用={path['indirect_count']}")
    # 用户可以根据实际情况选择最合理的路径
```

### 场景2：调用行号排序

```python
# call_line信息会自动用于路径排序
# 优先返回调用发生得更早的路径
result = coordinator.process_top_k_with_specific_functions(
    error_log,
    start_func='dw_mci_pltfm_probe',
    end_func='dw_mci_execute_tuning',
    k=5
)

# 查看每条路径的调用行号信息
for idx, path in enumerate(result['paths']):
    print(f"路径 #{idx+1}: 平均调用行号={path.get('avg_call_line', 0):.1f}")
```

### 场景3：路径比较

```python
result = coordinator.process_top_k(error_log, k=5)

# 比较不同路径
for idx, path in enumerate(result['paths']):
    print(f"\n路径 #{idx+1}:")
    print(f"  路径: {' -> '.join(path['path'])}")
    print(f"  call_lines: {path['call_lines']}")
    # 可以看到每条调用发生在哪一行
```

## 🔍 路径得分计算

```python
score = 1000 - path_length - indirect_count * 10 - avg_call_line / 100
```

- 基础分：1000
- 每增加1个节点：扣1分
- 每增加1个间接调用：扣10分
- 平均调用行号：除以100后扣分（影响较小）

示例：
- 路径A：长度15，无间接调用，平均行号100 → 得分 985 - 1.0 = 984
- 路径B：长度16，4个间接调用，平均行号50 → 得分 944 - 0.5 = 943.5
- 路径C：长度12，2个间接调用，平均行号200 → 得分 968 - 2.0 = 966

**排序：A > C > B**

**权重说明：**
- 路径长度权重：1（最基础）
- 间接调用权重：10（非常重要，间接调用代表不确定性）
- 调用行号权重：0.01（次要，用于相同条件下的精细排序）

## 🆕 兼容性

### 向后兼容

原有的API仍然可用：
- `coordinator.process()` - 返回单条路径
- `coordinator.process_with_specific_functions()` - 返回单条路径
- `chain_tracer.execute()` - 返回单条路径

### 新增API

新API不影响原有功能：
- `coordinator.process_top_k()` - 返回多条路径
- `coordinator.process_top_k_with_specific_functions()` - 返回多条路径
- `chain_tracer.execute_top_k()` - 返回多条路径

## 📚 相关文件

### 修改的文件

1. `data/kg_interface.py`
   - 新增 `call_graph_with_lines` 数据结构
   - 新增 `find_top_k_call_paths_with_indirect()` 方法
   - 新增 `_get_callees_with_lines()` 方法

2. `agents/chain_tracer_agent.py`
   - 默认 `max_depth` 从 20 增加到 30
   - 新增 `execute_top_k()` 方法

3. `coordinator/master_coordinator.py`
   - 新增 `process_top_k()` 方法
   - 新增 `process_top_k_with_specific_functions()` 方法
   - 新增多路径显示和报告生成方法

### 新增的文件

1. `examples/run_mmc_case_topk.py`
   - Top-K路径搜索示例脚本

2. `TOP_K_FEATURE.md`
   - 本文档

## ⚠️ 注意事项

### 1. call_line字段

确保你的知识图谱数据中的CALLS关系包含`call_line`字段：
```json
{
  "head": "123",
  "tail": "456",
  "type": "CALLS",
  "call_line": 100  // 必须有这个字段
}
```

如果某些CALLS关系没有`call_line`，算法仍然可以工作，只是这些边在排序时不会考虑行号信息。

### 2. error_line参数（已废弃）

`error_line`参数已不再用于剪枝：
- 保留此参数仅为了API兼容性
- 建议传入`None`或省略此参数
- call_line信息会自动用于路径排序，无需手动指定

### 3. k值选择

- k=1：等同于原来的单路径搜索
- k=3-5：适合大多数场景
- k=10+：可能会很慢，且很多路径不太合理

### 4. 搜索深度

- 默认max_depth=30
- 如果使用完整图谱，建议不要超过25
- 如果使用子图，可以尝试更大的值（如50）

## 🔬 测试建议

运行测试前，请确保：

1. 数据目录存在：
   ```bash
   ls /data/xuao/code_kg_search/linux_test/data/mmc/
   ```

2. 数据包含call_line：
   ```bash
   # 检查relations.json是否包含call_line字段
   head -20 /data/xuao/code_kg_search/linux_test/data/mmc/relations.json
   ```

3. 运行测试：
   ```bash
   # 完整流程测试
   python examples/run_mmc_case_topk.py

   # 直接KG接口测试
   python examples/run_mmc_case_topk.py --direct
   ```

## 📞 反馈

如果遇到问题或有改进建议，请在运行后反馈：
- 是否成功找到多条路径？
- call_line排序是否有效（调用更早的路径是否得分更高）？
- 搜索性能如何（速度）？
- 路径得分排序是否合理？
- 权重系数（路径长度:间接调用:调用行号 = 1:10:0.01）是否需要调整？
