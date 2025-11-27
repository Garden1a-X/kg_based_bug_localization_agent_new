#!/usr/bin/env python3
"""
基于源码分析的桥接查找器
使用LLM分析源码，找出断裂调用链之间的连接
"""

from typing import Optional, Dict, List
from loguru import logger
import json


class SourceCodeBridgeFinder:
    """源码桥接查找器 - 使用LLM分析源码找出异步/函数指针调用"""

    def __init__(self, llm_client):
        """
        初始化

        Args:
            llm_client: 统一的LLM客户端实例
        """
        self.llm_client = llm_client

    def analyze_async_connection(
        self,
        func_a_source: str,
        func_b_source: str,
        init_func_sources: Optional[List[Dict[str, str]]] = None
    ) -> Optional[Dict]:
        """
        分析两个函数之间的异步连接

        Args:
            func_a_source: 函数A的源码
            func_b_source: 函数B的源码
            init_func_sources: 可能的初始化函数源码列表
                [{"name": "func_name", "source": "source_code"}, ...]

        Returns:
            {
                "connected": True/False,
                "bridge_type": "async_work"/"function_pointer"/etc,
                "bridge_entity": "host->detect"/etc,
                "explanation": "详细解释",
                "confidence": 0.0-1.0
            }
        """
        prompt = self._build_async_analysis_prompt(
            func_a_source, func_b_source, init_func_sources
        )

        # 使用统一的LLM客户端
        if not self.llm_client or not self.llm_client.is_available():
            logger.warning("LLM客户端不可用，无法进行源码桥接分析")
            return None

        try:
            # 使用 llm_client 的 chat_completion 方法
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert in Linux kernel source code analysis, "
                               "specializing in identifying async callbacks, function pointers, "
                               "and delayed work connections."
                },
                {"role": "user", "content": prompt}
            ]

            content = self.llm_client.chat_completion(
                messages=messages,
                temperature=0.3,
                max_tokens=1000,
                timeout=180
            )

            if not content:
                return None

            # 解析JSON输出
            result = self._parse_analysis_result(content)
            return result

        except Exception as e:
            logger.error(f"LLM分析失败: {e}")
            return None

    def _build_async_analysis_prompt(
        self,
        func_a_source: str,
        func_b_source: str,
        init_func_sources: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """构建分析prompt"""

        prompt = f"""Analyze the following Linux kernel functions to determine if they are connected through async callbacks, function pointers, or delayed work mechanisms.

**Function A:**
```c
{func_a_source}
```

**Function B:**
```c
{func_b_source}
```
"""

        if init_func_sources:
            prompt += "\n**Related initialization/setup functions:**\n"
            for i, func_info in enumerate(init_func_sources, 1):
                prompt += f"\n{i}. {func_info['name']}:\n```c\n{func_info['source']}\n```\n"

        prompt += """

**Task:**
Determine if Function A eventually leads to calling Function B through:
1. Delayed work (work_struct, delayed_work)
2. Function pointer assignment (ops table, callbacks)
3. Other indirect call mechanisms

Provide your analysis in JSON format:
```json
{
  "connected": true/false,
  "bridge_type": "async_work" | "function_pointer" | "callback" | "none",
  "bridge_entity": "the variable/struct field that connects them",
  "explanation": "Detailed explanation of how they are connected",
  "confidence": 0.0-1.0
}
```

**Guidelines:**
- Look for patterns like:
  - `queue_delayed_work(..., work, ...)` where work points to Function B
  - `INIT_DELAYED_WORK(&something, function_b)`
  - `ops->callback = function_b` in initialization
  - `container_of(work, struct_type, field)` patterns
- Check if initialization functions set up the connection
- Be specific about the bridge entity (e.g., "host->detect.work")
- Only set `connected: true` if you find clear evidence
- Confidence should reflect certainty (0.0 = unsure, 1.0 = certain)
"""

        return prompt

    def _parse_analysis_result(self, content: str) -> Optional[Dict]:
        """解析LLM分析结果"""
        try:
            # 提取JSON
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            else:
                json_str = content

            result = json.loads(json_str)

            # 验证必需字段
            if "connected" not in result:
                result["connected"] = False

            return result

        except Exception as e:
            print(f"解析LLM输出失败: {e}")
            print(f"输出内容: {content}")
            return None

    def find_bridge_between_functions(
        self,
        func_a_info: Dict,
        func_b_info: Dict,
        source_reader,
        kg_interface
    ) -> Optional[Dict]:
        """
        综合查找两个函数之间的桥接

        Args:
            func_a_info: 函数A的信息 {"name": "...", "id": "...", "source_file": "...", ...}
            func_b_info: 函数B的信息
            source_reader: SourceCodeReader实例
            kg_interface: KnowledgeGraphInterface实例

        Returns:
            桥接信息或None
        """
        print(f"\n尝试通过源码分析连接: {func_a_info['name']} → {func_b_info['name']}")

        # 读取函数A和B的源码
        func_a_source = source_reader.read_function_source(
            func_a_info['source_file'],
            func_a_info['start_line'],
            func_a_info['end_line']
        )

        func_b_source = source_reader.read_function_source(
            func_b_info['source_file'],
            func_b_info['start_line'],
            func_b_info['end_line']
        )

        if not func_a_source or not func_b_source:
            print("  ❌ 无法读取源码")
            return None

        print(f"  ✓ 已读取函数源码")
        print(f"    函数A: {len(func_a_source)} 字符")
        print(f"    函数B: {len(func_b_source)} 字符")

        # TODO: 可以添加启发式规则，找相关的初始化函数
        # 例如：如果函数A涉及host->detect，就去找mmc_alloc_host
        init_func_sources = self._find_related_init_functions(
            func_a_info, func_b_info, source_reader, kg_interface
        )

        # 让LLM分析
        print(f"  → 让LLM分析源码...")
        result = self.analyze_async_connection(
            func_a_source, func_b_source, init_func_sources
        )

        if result and result.get('connected'):
            print(f"  ✅ LLM发现连接!")
            print(f"    类型: {result.get('bridge_type')}")
            print(f"    桥接: {result.get('bridge_entity')}")
            print(f"    置信度: {result.get('confidence', 0.0):.2f}")
            print(f"    解释: {result.get('explanation', '')[:100]}...")
            return {
                'bridge_type': result.get('bridge_type', 'unknown'),
                'bridge_entity': result.get('bridge_entity', ''),
                'explanation': result.get('explanation', ''),
                'confidence': result.get('confidence', 0.5)
            }
        else:
            print(f"  ❌ LLM未发现明确连接")
            if result:
                print(f"    {result.get('explanation', '')[:100]}...")
            return None

    def _find_related_init_functions(
        self,
        func_a_info: Dict,
        func_b_info: Dict,
        source_reader,
        kg_interface
    ) -> List[Dict[str, str]]:
        """
        查找可能相关的初始化函数

        启发式规则：
        - 如果函数名包含"schedule"，查找"alloc"函数
        - 如果涉及work_struct，查找INIT_WORK/INIT_DELAYED_WORK
        """
        init_sources = []

        # 简单启发式：如果是mmc相关，查找mmc_alloc_host
        func_a_name = func_a_info.get('name', '')
        if 'mmc' in func_a_name.lower() and 'schedule' in func_a_name.lower():
            # 尝试找mmc_alloc_host
            alloc_func_ids = kg_interface.get_function_ids('mmc_alloc_host')
            if alloc_func_ids:
                alloc_func_info = kg_interface.get_function_info(alloc_func_ids[0])
                if alloc_func_info:
                    alloc_source = source_reader.read_function_source(
                        alloc_func_info['source_file'],
                        alloc_func_info['start_line'],
                        alloc_func_info['end_line']
                    )
                    if alloc_source:
                        init_sources.append({
                            'name': 'mmc_alloc_host',
                            'source': alloc_source
                        })
                        print(f"  ✓ 找到相关初始化函数: mmc_alloc_host")

        return init_sources


def test_bridge_finder():
    """测试桥接查找器"""
    import sys
    from pathlib import Path

    # 添加项目根目录到路径
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    from utils.source_code_reader import SourceCodeReader
    from data.kg_interface import KnowledgeGraphInterface

    print("="*80)
    print("测试源码桥接查找器")
    print("="*80)

    # 初始化
    reader = SourceCodeReader()
    kg = KnowledgeGraphInterface(data_dir="/data/xuao/code_kg_search/linux_test/data")
    finder = SourceCodeBridgeFinder()

    # 测试：mmc_schedule_delayed_work → mmc_rescan
    print("\n测试案例: mmc_schedule_delayed_work → mmc_rescan")
    print("="*80)

    func_a_info = {
        'name': 'mmc_schedule_delayed_work',
        'source_file': 'E:\\cpppro\\clang_kg\\linux\\drivers\\mmc\\core\\core.c',
        'start_line': 63,
        'end_line': 73
    }

    func_b_info = {
        'name': 'mmc_rescan',
        'source_file': 'E:\\cpppro\\clang_kg\\linux\\drivers\\mmc\\core\\core.c',
        'start_line': 2237,
        'end_line': 2310
    }

    result = finder.find_bridge_between_functions(
        func_a_info, func_b_info, reader, kg
    )

    print("\n" + "="*80)
    print("测试结果")
    print("="*80)

    if result:
        print("✅ 找到连接!")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("❌ 未找到连接")


if __name__ == "__main__":
    test_bridge_finder()
