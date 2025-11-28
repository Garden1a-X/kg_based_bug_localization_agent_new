#!/usr/bin/env python3
"""
LLM辅助的间接调用检测器

用于分析函数源码，提取间接调用的字段名，并在图谱中查找目标函数
"""

from typing import List, Dict, Optional
import json
from loguru import logger


class LLMIndirectCallDetector:
    """LLM间接调用检测器"""

    def __init__(self, kg_interface, llm_client):
        """
        初始化

        Args:
            kg_interface: 知识图谱接口
            llm_client: 统一的LLM客户端实例
        """
        self.kg = kg_interface
        self.llm_client = llm_client

    def detect_indirect_callees(self, func_name: str) -> List[tuple]:
        """
        检测函数的间接调用目标

        Args:
            func_name: 函数名

        Returns:
            间接调用列表，每项为 (目标函数名, 桥接信息)
            例如: [("dw_mci_execute_tuning", {"bridge_type": "function_pointer", ...})]
        """
        try:
            # 1. 获取函数源码
            source_code = self._get_function_source(func_name)
            if not source_code:
                logger.warning(f"无法获取函数 {func_name} 的源码")
                return []

            # 2. LLM提取间接调用字段
            field_names = self._extract_field_names_with_llm(func_name, source_code)
            if not field_names:
                logger.debug(f"函数 {func_name} 未发现间接调用")
                return []

            # 3. 在图谱中查询ASSIGNED_TO关系
            indirect_callees = []
            for field_name in field_names:
                candidates = self._query_assigned_to(field_name)
                for cand in candidates:
                    indirect_callees.append((
                        cand['target_function'],
                        {
                            'bridge_type': 'function_pointer',
                            'bridge_entity': field_name,
                            'context_var_name': cand.get('context_var_name', 'N/A'),
                            'method': 'llm_analysis'
                        }
                    ))

            if indirect_callees:
                logger.info(f"函数 {func_name} 发现 {len(indirect_callees)} 个间接调用目标")

            return indirect_callees

        except Exception as e:
            logger.error(f"检测函数 {func_name} 的间接调用失败: {e}")
            return []

    def _get_function_source(self, func_name: str) -> Optional[str]:
        """
        获取函数源码

        Args:
            func_name: 函数名

        Returns:
            函数源代码，失败返回None
        """
        # 获取所有同名函数ID
        all_func_ids = self.kg.func_name_to_ids.get(func_name, [])
        if not all_func_ids:
            return None

        # 优先选择实现（非声明）
        func_entity = None
        for func_id in all_func_ids:
            entity = self.kg.entity_by_id.get(func_id)
            if not entity:
                continue

            is_decl = entity.get('is_declaration', False)
            if not is_decl:
                func_entity = entity
                break

        # 如果没有实现，使用第一个
        if not func_entity and all_func_ids:
            func_entity = self.kg.entity_by_id.get(all_func_ids[0])

        if not func_entity:
            return None

        # 尝试从实体获取源码
        source_code = func_entity.get('code') or func_entity.get('body')

        # 如果没有，从源文件读取
        if not source_code:
            source_file = func_entity.get('source_file')
            start_line = func_entity.get('start_line')
            end_line = func_entity.get('end_line')

            if source_file and start_line and end_line:
                try:
                    with open(source_file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        source_code = ''.join(lines[start_line-1:end_line])
                except Exception as e:
                    logger.warning(f"读取源文件失败: {e}")
                    return None

        return source_code

    def _extract_field_names_with_llm(self, func_name: str, source_code: str) -> List[str]:
        """
        用LLM分析源码，提取间接调用的字段名

        Args:
            func_name: 函数名
            source_code: 函数源代码

        Returns:
            字段名列表，例如 ["execute_tuning"]
        """
        # 使用统一的LLM客户端
        if not self.llm_client or not self.llm_client.is_available():
            logger.debug("LLM客户端不可用，无法提取函数指针字段")
            return []

        try:
            # 使用 llm_client 的 extract_function_pointer_fields 方法
            field_names = self.llm_client.extract_function_pointer_fields(func_name, source_code)
            return field_names if field_names else []

        except Exception as e:
            logger.error(f"LLM提取字段名失败: {e}")
            return []

        # 下面的代码已废弃，保留作为参考
        """
        prompt = self._build_extraction_prompt(source_code)

        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert in C code analysis, specializing in identifying function pointer calls."
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
                return []

            # 解析JSON
            indirect_calls = self._parse_llm_response(content)

            # 提取字段名
            field_names = [call.get('field_name') for call in indirect_calls if call.get('field_name')]

            if field_names:
                logger.debug(f"LLM为 {func_name} 提取到字段: {field_names}")

            return field_names

        except Exception as e:
            logger.error(f"LLM分析失败: {e}")
            return []

    def _build_extraction_prompt(self, source_code: str) -> str:
        """构建提取prompt"""
        prompt = f"""分析以下C函数，识别所有通过函数指针的间接调用。

函数代码：
```c
{source_code}
```

任务：
1. 找出所有形如 `ptr->field(...)` 或 `(*ptr->field)(...)` 的间接调用
2. 提取字段名（field的名字，即最后一级的字段）
3. 如果有多层嵌套（如 `host->ops->execute_tuning`），提取最后一级字段名（`execute_tuning`）

返回JSON格式：
```json
{{
  "indirect_calls": [
    {{
      "expression": "完整的调用表达式",
      "field_name": "字段名（最后一级）",
      "explanation": "简短说明（可选）"
    }}
  ]
}}
```

注意事项：
- 只关注实际的函数调用，忽略NULL检查等判断语句
- 如果有多个间接调用，全部列出
- 字段名应该是可以在图谱中查询的标识符
- 如果没有找到间接调用，返回空数组

示例：
```c
// 对于这样的代码：
if (host->ops && host->ops->execute_tuning)
    err = host->ops->execute_tuning(host, opcode);

// 应该返回：
{{
  "indirect_calls": [
    {{
      "expression": "host->ops->execute_tuning(host, opcode)",
      "field_name": "execute_tuning",
      "explanation": "Function pointer call through ops table"
    }}
  ]
}}
```
"""
        return prompt

    def _parse_llm_response(self, content: str) -> List[Dict]:
        """解析LLM响应"""
        try:
            # 提取JSON代码块
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

            data = json.loads(json_str)
            return data.get("indirect_calls", [])

        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {e}")
            return []
        except Exception as e:
            logger.warning(f"解析失败: {e}")
            return []

    def _query_assigned_to(self, field_name: str) -> List[Dict]:
        """
        根据字段名查询ASSIGNED_TO关系

        Args:
            field_name: 字段名（如 "execute_tuning"）

        Returns:
            候选函数列表
        """
        # 步骤1: 找到所有名为field_name的FIELD实体ID
        field_ids = []
        for entity_id, entity in self.kg.entity_by_id.items():
            if entity.get('type') == 'FIELD' and entity.get('name') == field_name:
                field_ids.append(entity_id)

        if not field_ids:
            return []

        # 步骤2: 在ASSIGNED_TO和MOUNTED_TO关系中查找
        field_id_set = set(field_ids)
        results = []

        field_to_func_relations = []
        field_to_func_relations.extend(self.kg.relations.get('ASSIGNED_TO', []))
        field_to_func_relations.extend(self.kg.relations.get('MOUNTED_TO', []))

        for rel in field_to_func_relations:
            head_id = rel.get('head')  # FIELD实体ID
            tail_id = rel.get('tail')  # FUNCTION实体ID

            if head_id not in field_id_set:
                continue

            if not tail_id:
                continue

            target_entity = self.kg.entity_by_id.get(tail_id)
            if not target_entity:
                continue

            target_func_name = target_entity.get('name')
            if target_func_name:
                results.append({
                    'target_function': target_func_name,
                    'field_name': field_name,
                    'context_var_id': rel.get('context_var_id', 'N/A'),
                    'context_var_name': rel.get('context_var_name', 'N/A'),
                })

        return results


def preprocess_indirect_calls(
    kg_interface,
    func_names: List[str],
    api_key: str = "",
    base_url: str = "http://10.12.208.86:8502"
) -> Dict[str, List[tuple]]:
    """
    预处理：批量检测函数的间接调用

    Args:
        kg_interface: 知识图谱接口
        func_names: 需要检测的函数名列表
        api_key: LLM API密钥
        base_url: LLM API地址

    Returns:
        {func_name: [(target_func, bridge_info), ...]}
    """
    detector = LLMIndirectCallDetector(kg_interface, api_key, base_url)
    cache = {}

    logger.info(f"开始预处理 {len(func_names)} 个函数的间接调用...")

    for func_name in func_names:
        logger.info(f"  处理函数: {func_name}")
        indirect_callees = detector.detect_indirect_callees(func_name)
        cache[func_name] = indirect_callees

        if indirect_callees:
            logger.info(f"    ✓ 找到 {len(indirect_callees)} 个间接调用目标")
        else:
            logger.info(f"    ℹ️  未发现间接调用")

    logger.info(f"预处理完成！缓存了 {sum(len(v) for v in cache.values())} 条间接调用关系")

    return cache
