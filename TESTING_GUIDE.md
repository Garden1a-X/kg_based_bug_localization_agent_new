# 用户上下文功能测试指南

## 快速测试

### 方法 1: 运行完整测试脚本

```bash
bash test_commands.sh
```

这会依次运行所有8个测试，展示用户上下文在不同场景下的效果。

### 方法 2: 单独运行测试

选择您想测试的场景：

---

## 📋 测试场景详解

### 🔍 核心对比测试（推荐先运行这两个）

#### 测试 1: 主程序 - 无用户上下文
```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log-file /data/xuao/code_kg_search/kg_based_bug_localization_agent/error.log \
    --enable-subgraph-selection \
    --enable-llm-log-analysis \
    --k 5
```

**预期结果**：
- ⚠️ LLM 置信度较低（< 0.6）
- 📢 系统会建议提供平台/驱动信息
- 🔄 自动启用降级模式（使用日志中的函数作为起点）

---

#### 测试 2: 主程序 - 提供用户上下文（RK3288）
```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log-file /data/xuao/code_kg_search/kg_based_bug_localization_agent/error.log \
    --enable-subgraph-selection \
    --enable-llm-log-analysis \
    --user-context contexts/rk3288.yaml \
    --k 5
```

**预期结果**：
- ✅ LLM 置信度提高（>= 0.7）
- 🎯 正确识别入口函数（如 `dw_mci_rockchip_probe`）
- 📊 找到更准确的调用链路径

---

### 🎛️ 手动模式测试

#### 测试 3: 主程序 - 手动指定起止点
```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --enable-subgraph-selection \
    --start-function dw_mci_rockchip_probe \
    --end-function dw_mci_execute_tuning \
    --k 5
```

**说明**：手动模式不需要日志和用户上下文，直接搜索指定函数之间的调用链。

---

### 🐛 调试工具测试

#### 测试 4: LLM 入口选择调试 - 无用户上下文
```bash
python test_llm_entry_selection.py \
    --log-file /data/xuao/code_kg_search/kg_based_bug_localization_agent/error.log \
    --subgraph mmc
```

**用途**：查看 LLM 的原始推理过程和置信度评分。

---

#### 测试 5: LLM 入口选择调试 - 提供用户上下文
```bash
python test_llm_entry_selection.py \
    --log-file /data/xuao/code_kg_search/kg_based_bug_localization_agent/error.log \
    --user-context contexts/rk3288.yaml \
    --subgraph mmc
```

**用途**：对比提供上下文前后的推理差异。

---

### 📝 示例程序测试

#### 测试 6: 示例程序 - 标准模式
```bash
python examples/run_mmc_case_topk.py
```

**说明**：演示子图自动选择和 LLM 入口选择的集成效果。

---

#### 测试 7: 示例程序 - 日志匹配模式（无用户上下文）
```bash
python examples/run_mmc_case_topk.py --log-match
```

**说明**：使用日志匹配功能，但不提供用户上下文。

---

#### 测试 8: 示例程序 - 日志匹配模式（提供用户上下文）
```bash
python examples/run_mmc_case_topk.py --mode log-match --user-context contexts/rk3288.yaml
```

**说明**：完整流程 - 日志匹配 + 子图选择 + LLM 入口选择（带用户上下文）。

---

## 🎯 关键对比点

运行测试 1 和测试 2 后，对比以下指标：

| 指标 | 无用户上下文 | 有用户上下文 |
|------|------------|------------|
| **置信度** | < 0.6 (低) | >= 0.7 (高) |
| **入口函数** | 降级模式（日志函数） | 正确识别（probe函数） |
| **推理依据** | 仅基于日志内容 | 结合平台+驱动信息 |
| **需要更多信息** | ✅ Yes | ❌ No |

---

## 📂 可用的用户上下文文件

项目提供了以下预配置文件：

| 文件 | 平台 | 驱动 |
|------|------|------|
| `contexts/rk3288.yaml` | Rockchip RK3288 | dw_mci_rockchip |
| `contexts/kirin960.yaml` | Hisilicon Kirin 960 | dw_mci_hi3660 |
| `contexts/imx28.yaml` | NXP i.MX28 | mxs_mmc |
| `contexts/minimal_example.yaml` | 最小示例 | - |

---

## 🔧 自定义测试

### 使用自定义日志文件

```bash
python test_llm_entry_selection.py \
    --log-file /path/to/your/error.log \
    --user-context contexts/rk3288.yaml \
    --subgraph mmc
```

### 使用自定义用户上下文

1. 复制示例文件：
```bash
cp contexts/minimal_example.yaml contexts/my_platform.yaml
```

2. 编辑配置：
```yaml
platform: <您的平台>
driver_hint: <驱动类型>
```

3. 运行测试：
```bash
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log-file error.log \
    --enable-subgraph-selection \
    --enable-llm-log-analysis \
    --user-context contexts/my_platform.yaml \
    --k 5
```

---

## 🐞 调试技巧

### 查看完整的 LLM prompt

```bash
LLM_DEBUG_PROMPT=1 python test_llm_entry_selection.py \
    --log-file error.log \
    --user-context contexts/rk3288.yaml \
    --subgraph mmc

# 查看保存的 prompt
cat /tmp/llm_prompt_debug.txt
```

### 查看详细日志

```bash
# 设置日志级别为 DEBUG
export LOG_LEVEL=DEBUG

python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log-file error.log \
    --enable-subgraph-selection \
    --enable-llm-log-analysis \
    --user-context contexts/rk3288.yaml \
    --k 5
```

---

## 📊 验证成功的标准

测试成功的标志：

1. **测试 1**（无上下文）：
   - ⚠️ 置信度 < 0.6
   - 💡 提示需要更多信息
   - 🔄 使用降级模式

2. **测试 2**（有上下文）：
   - ✅ 置信度 >= 0.7
   - 🎯 入口函数正确（如 `dw_mci_rockchip_probe`）
   - 📈 找到的路径更准确

3. **测试 5**（调试工具 + 上下文）：
   - 📝 推理过程中明确引用了用户提供的平台/驱动信息
   - ✅ 输出中有 "基于用户提供的平台信息" 等说明

---

## ❓ 常见问题

### Q: 如果所有测试的置信度都很低怎么办？

A: 检查：
1. LLM 服务是否正常运行（`http://10.12.208.86:8502`）
2. 用户上下文文件格式是否正确
3. 日志文件是否存在且可读

### Q: 可以跳过某些测试吗？

A: 可以。推荐最小测试集：
- 测试 1 + 测试 2（核心对比）
- 测试 4 + 测试 5（调试验证）

### Q: 测试需要多长时间？

A:
- 单个测试：约 10-30 秒
- 完整测试脚本：约 3-5 分钟

---

## 📚 相关文档

- [USER_CONTEXT_GUIDE.md](USER_CONTEXT_GUIDE.md) - 用户上下文功能详细说明
- [ENTRY_POINT_SELECTION.md](ENTRY_POINT_SELECTION.md) - 入口选择机制
- [README.md](README.md) - 项目总体说明
