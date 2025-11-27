# 快速部署指南

## 📦 在服务器上部署

### 第1步：上传所有文件

将以下文件复制到服务器 `/data/xuao/code_kg_search/bug_localization_agent/`:

```
bug_localization_agent/
├── setup_project.sh              # 项目结构创建脚本
├── requirements.txt              # 依赖列表
├── .env.example                  # 配置模板
├── README.md                     # 说明文档
│
├── config/
│   ├── __init__.py
│   └── settings.py               # 从 config_settings.py 改名
│
├── data/
│   ├── __init__.py
│   └── kg_interface.py           # 从 data_kg_interface.py 改名
│
├── utils/
│   ├── __init__.py
│   └── logger.py                 # 从 utils_logger.py 改名
│
├── agents/
│   ├── __init__.py
│   ├── base_agent.py             # 从 agents_base_agent.py 改名
│   ├── log_parser_agent.py       # 从 agents_log_parser_agent.py 改名
│   ├── entity_locator_agent.py   # 从 agents_entity_locator_agent.py 改名
│   └── chain_tracer_agent.py     # 从 agents_chain_tracer_agent.py 改名
│
├── coordinator/
│   ├── __init__.py
│   └── master_coordinator.py     # 从 coordinator_master_coordinator.py 改名
│
├── tests/
│   ├── __init__.py
│   └── test_connections.py       # 从 tests_test_connections.py 改名
│
└── examples/
    ├── __init__.py
    └── run_mmc_case.py           # 从 examples_run_mmc_case.py 改名
```

### 第2步：创建项目结构

```bash
cd /data/xuao/code_kg_search
bash setup_project.sh
```

或手动创建:

```bash
cd /data/xuao/code_kg_search
mkdir -p bug_localization_agent/{config,data,tools,agents,coordinator,utils,tests/test_data,examples,logs,output}
cd bug_localization_agent
touch {config,data,tools,agents,coordinator,utils,tests,examples}/__init__.py
```

### 第3步：放置代码文件

**重要**: 我生成的文件名需要改名，去掉前缀:

```bash
cd /data/xuao/code_kg_search/bug_localization_agent

# 配置文件
mv config_settings.py config/settings.py

# 数据层
mv data_kg_interface.py data/kg_interface.py

# 工具层
mv utils_logger.py utils/logger.py

# Agent层
mv agents_base_agent.py agents/base_agent.py
mv agents_log_parser_agent.py agents/log_parser_agent.py
mv agents_entity_locator_agent.py agents/entity_locator_agent.py
mv agents_chain_tracer_agent.py agents/chain_tracer_agent.py

# 协调层
mv coordinator_master_coordinator.py coordinator/master_coordinator.py

# 测试
mv tests_test_connections.py tests/test_connections.py

# 示例
mv examples_run_mmc_case.py examples/run_mmc_case.py
```

### 第4步：安装依赖

```bash
cd /data/xuao/code_kg_search/bug_localization_agent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 第5步：配置环境

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置（填入你的Neo4j信息）
vim .env
```

必须配置:
```bash
NEO4J_URI=bolt://your_neo4j_host:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

可选配置（用于LLM兜底）:
```bash
ANTHROPIC_API_KEY=your_api_key
```

### 第6步：测试连接

```bash
python tests/test_connections.py
```

预期输出:
```
===== 环境检查 =====

检查项目结构...
✓ config/ 存在
✓ data/ 存在
...

测试Neo4j连接...
✓ Neo4j连接成功
  URI: bolt://localhost:7687
  
  数据库统计（前5类实体）:
    Function: 12345
    Struct: 2345
    ...

测试Anthropic API连接...
✓ Anthropic API连接成功
  (或 ⚠ 未配置ANTHROPIC_API_KEY)

===== 检查结果 =====
✓ 项目结构
✓ Neo4j连接
✓ Anthropic API

✓ 环境配置正确，可以运行框架
```

### 第7步：运行示例

```bash
# 运行甲方MMC案例
python examples/run_mmc_case.py
```

---

## 🔧 文件重命名脚本

如果你是直接从我这里复制的文件，可以用这个脚本批量改名:

```bash
#!/bin/bash
# rename_files.sh

cd /data/xuao/code_kg_search/bug_localization_agent

# 配置
mv config_settings.py config/settings.py 2>/dev/null

# 数据层
mv data_kg_interface.py data/kg_interface.py 2>/dev/null

# 工具
mv utils_logger.py utils/logger.py 2>/dev/null

# Agent
mv agents_base_agent.py agents/base_agent.py 2>/dev/null
mv agents_log_parser_agent.py agents/log_parser_agent.py 2>/dev/null
mv agents_entity_locator_agent.py agents/entity_locator_agent.py 2>/dev/null
mv agents_chain_tracer_agent.py agents/chain_tracer_agent.py 2>/dev/null

# 协调器
mv coordinator_master_coordinator.py coordinator/master_coordinator.py 2>/dev/null

# 测试
mv tests_test_connections.py tests/test_connections.py 2>/dev/null

# 示例
mv examples_run_mmc_case.py examples/run_mmc_case.py 2>/dev/null

echo "文件重命名完成"
```

保存为 `rename_files.sh`，然后:
```bash
chmod +x rename_files.sh
bash rename_files.sh
```

---

## 📝 常见问题

### Q1: Neo4j连接失败
**A**: 检查:
1. Neo4j是否启动
2. URI、用户名、密码是否正确
3. 端口7687是否开放

### Q2: 找不到模块
**A**: 确保:
1. 所有 `__init__.py` 文件都创建了
2. 文件位置正确
3. 虚拟环境已激活

### Q3: LLM功能不可用
**A**: 这是正常的，如果没有配置 `ANTHROPIC_API_KEY`:
- 框架仍可运行
- 只是无法使用第3层LLM兜底
- 第1层（图谱）和第2层（规则）仍正常工作

### Q4: 图谱中找不到函数
**A**: 检查:
1. 函数名是否正确
2. 图谱中是否已经提取了这些代码
3. 尝试使用模糊查询

---

## 🎯 下一步

部署完成后:

1. **验证基本功能**: 运行 `python examples/run_mmc_case.py`
2. **查看输出**: 结果保存在 `output/` 目录
3. **尝试自定义案例**: 准备你自己的错误日志
4. **根据需要扩展**: 添加更多专家规则、优化提示词等

---

## 📞 需要帮助？

如果遇到问题:
1. 查看日志文件: `logs/agent.log`
2. 运行测试: `python tests/test_connections.py`
3. 检查配置: `cat .env`
