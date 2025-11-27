"""
子图选择器
基于错误日志或函数名，使用LLM推断应该使用哪个子图
"""
import os
import json
from typing import List, Dict, Optional
from pathlib import Path
from loguru import logger


class SubgraphSelector:
    """子图选择器 - 使用LLM分析日志/函数名选择合适的子图"""

    def __init__(self, llm_client, base_data_dir: str, subgraph_metadata: Optional[Dict] = None):
        """
        初始化子图选择器

        Args:
            llm_client: LLM客户端实例
            base_data_dir: 基础数据目录（例如 /data/xuao/code_kg_search/linux_test/data）
            subgraph_metadata: 子图元数据（可选）
                格式: {
                    'mmc': {
                        'name': 'MMC/SD Card Subsystem',
                        'description': '...',
                        'keywords': ['mmc', 'sd', 'sdio'],
                        'common_functions': ['mmc_alloc_host', 'mmc_rescan']
                    }
                }
        """
        self.llm_client = llm_client
        self.base_data_dir = Path(base_data_dir)
        self.subgraph_metadata = subgraph_metadata or {}

        # 自动发现可用的子图
        self.available_subgraphs = self._discover_subgraphs()

        logger.info(f"子图选择器初始化完成，发现 {len(self.available_subgraphs)} 个子图")

    def _discover_subgraphs(self) -> List[str]:
        """
        自动发现可用的子图

        扫描 base_data_dir，找到所有子目录作为候选子图

        Returns:
            子图名称列表
        """
        subgraphs = []

        if not self.base_data_dir.exists():
            logger.warning(f"数据目录不存在: {self.base_data_dir}")
            return subgraphs

        # 遍历所有子目录
        for item in self.base_data_dir.iterdir():
            if item.is_dir():
                # 检查是否包含 entity.json 或 relation.json
                has_entity = (item / 'entity.json').exists()
                has_relation = (item / 'relation.json').exists()

                if has_entity or has_relation:
                    subgraphs.append(item.name)

        return sorted(subgraphs)

    def select_by_log(
        self,
        log_text: str,
        top_k: int = 3,
        fallback_to_all: bool = True
    ) -> List[str]:
        """
        基于错误日志选择子图

        Args:
            log_text: 错误日志文本
            top_k: 返回前k个最相关的子图
            fallback_to_all: 如果LLM失败，是否返回所有子图

        Returns:
            推荐的子图名称列表
        """
        if not self.available_subgraphs:
            logger.warning("没有可用的子图")
            return []

        # 如果没有LLM客户端或不可用，使用关键字匹配
        if not self.llm_client or not self.llm_client.is_available():
            logger.warning("LLM不可用，使用关键字匹配")
            return self._select_by_keywords(log_text, top_k)

        try:
            # 构建LLM提示词
            prompt = self._build_log_analysis_prompt(log_text)

            # 调用LLM
            response = self.llm_client.complete(
                prompt=prompt,
                system_prompt="You are an expert in Linux kernel driver analysis.",
                temperature=0.3,
                max_tokens=500,
                timeout=60
            )

            if not response:
                raise Exception("LLM返回空响应")

            # 解析LLM响应
            selected_subgraphs = self._parse_llm_response(response, top_k)

            if selected_subgraphs:
                logger.info(f"LLM选择的子图: {selected_subgraphs}")
                return selected_subgraphs

            # 如果LLM没有返回有效结果
            if fallback_to_all:
                logger.warning("LLM未返回有效子图，使用所有子图")
                return self.available_subgraphs[:top_k]
            else:
                return []

        except Exception as e:
            logger.error(f"LLM子图选择失败: {e}")
            if fallback_to_all:
                logger.warning("LLM失败，使用所有子图")
                return self.available_subgraphs[:top_k]
            else:
                return []

    def select_by_functions(
        self,
        function_names: List[str],
        top_k: int = 3,
        fallback_to_all: bool = True
    ) -> List[str]:
        """
        基于函数名选择子图

        Args:
            function_names: 函数名列表（如起点、终点、中间关键函数）
            top_k: 返回前k个最相关的子图
            fallback_to_all: 如果LLM失败，是否返回所有子图

        Returns:
            推荐的子图名称列表
        """
        if not self.available_subgraphs:
            logger.warning("没有可用的子图")
            return []

        # 如果没有LLM客户端或不可用，使用关键字匹配
        if not self.llm_client or not self.llm_client.is_available():
            logger.warning("LLM不可用，使用关键字匹配")
            return self._select_by_keywords(' '.join(function_names), top_k)

        try:
            # 构建LLM提示词
            prompt = self._build_function_analysis_prompt(function_names)

            # 调用LLM
            response = self.llm_client.complete(
                prompt=prompt,
                system_prompt="You are an expert in Linux kernel driver analysis.",
                temperature=0.3,
                max_tokens=500,
                timeout=60
            )

            if not response:
                raise Exception("LLM返回空响应")

            # 解析LLM响应
            selected_subgraphs = self._parse_llm_response(response, top_k)

            if selected_subgraphs:
                logger.info(f"LLM选择的子图: {selected_subgraphs}")
                return selected_subgraphs

            # 如果LLM没有返回有效结果
            if fallback_to_all:
                logger.warning("LLM未返回有效子图，使用所有子图")
                return self.available_subgraphs[:top_k]
            else:
                return []

        except Exception as e:
            logger.error(f"LLM子图选择失败: {e}")
            if fallback_to_all:
                logger.warning("LLM失败，使用所有子图")
                return self.available_subgraphs[:top_k]
            else:
                return []

    def _select_by_keywords(self, text: str, top_k: int) -> List[str]:
        """
        基于关键字匹配选择子图（fallback方法）

        Args:
            text: 要匹配的文本
            top_k: 返回数量

        Returns:
            匹配的子图列表
        """
        text_lower = text.lower()
        matches = []

        for subgraph in self.available_subgraphs:
            # 检查子图名称是否在文本中
            if subgraph.lower() in text_lower:
                matches.append((subgraph, 10))  # 直接匹配，高分

            # 检查元数据中的关键字
            elif subgraph in self.subgraph_metadata:
                metadata = self.subgraph_metadata[subgraph]
                keywords = metadata.get('keywords', [])
                match_count = sum(1 for kw in keywords if kw.lower() in text_lower)
                if match_count > 0:
                    matches.append((subgraph, match_count))

        # 排序并返回top_k
        matches.sort(key=lambda x: x[1], reverse=True)
        selected = [subgraph for subgraph, _ in matches[:top_k]]

        # 如果没有匹配，返回前top_k个子图
        if not selected:
            selected = self.available_subgraphs[:top_k]

        return selected

    def _build_log_analysis_prompt(self, log_text: str) -> str:
        """构建日志分析的LLM提示词"""
        # 构建子图描述
        subgraph_descriptions = []
        for subgraph in self.available_subgraphs:
            if subgraph in self.subgraph_metadata:
                metadata = self.subgraph_metadata[subgraph]
                desc = f"- **{subgraph}**: {metadata.get('description', 'Linux driver subsystem')}"
                if metadata.get('keywords'):
                    desc += f" (关键词: {', '.join(metadata['keywords'])})"
            else:
                desc = f"- **{subgraph}**: Linux driver subsystem"
            subgraph_descriptions.append(desc)

        prompt = f"""分析以下Linux内核错误日志，判断它属于哪个驱动子系统。

## 错误日志
```
{log_text.strip()}
```

## 可用的子图（驱动子系统）
{chr(10).join(subgraph_descriptions)}

## 任务
根据日志内容（错误消息、函数名、设备类型等），选择最相关的1-3个子图。

## 输出格式
返回JSON格式（不要其他说明）：
```json
{{
  "selected_subgraphs": ["subgraph1", "subgraph2"],
  "reasoning": "简短的推理说明"
}}
```

注意：
- selected_subgraphs必须是上述列表中的名称
- 按相关度从高到低排序
- 只返回最相关的1-3个
"""
        return prompt

    def _build_function_analysis_prompt(self, function_names: List[str]) -> str:
        """构建函数分析的LLM提示词"""
        # 构建子图描述
        subgraph_descriptions = []
        for subgraph in self.available_subgraphs:
            if subgraph in self.subgraph_metadata:
                metadata = self.subgraph_metadata[subgraph]
                desc = f"- **{subgraph}**: {metadata.get('description', 'Linux driver subsystem')}"
                if metadata.get('common_functions'):
                    desc += f" (常见函数: {', '.join(metadata['common_functions'][:3])})"
            else:
                desc = f"- **{subgraph}**: Linux driver subsystem"
            subgraph_descriptions.append(desc)

        prompt = f"""分析以下Linux内核函数名，判断它们属于哪个驱动子系统。

## 函数列表
{chr(10).join(f"- {func}" for func in function_names)}

## 可用的子图（驱动子系统）
{chr(10).join(subgraph_descriptions)}

## 任务
根据函数名的前缀、命名模式、功能特征，选择最相关的1-3个子图。

## 输出格式
返回JSON格式（不要其他说明）：
```json
{{
  "selected_subgraphs": ["subgraph1", "subgraph2"],
  "reasoning": "简短的推理说明"
}}
```

注意：
- selected_subgraphs必须是上述列表中的名称
- 按相关度从高到低排序
- 只返回最相关的1-3个
- Linux内核函数通常以子系统名为前缀（如 mmc_*, dw_mci_*）
"""
        return prompt

    def _parse_llm_response(self, response: str, max_count: int) -> List[str]:
        """
        解析LLM响应

        Args:
            response: LLM返回的文本
            max_count: 最多返回的子图数量

        Returns:
            子图名称列表
        """
        try:
            # 提取JSON
            content = response.strip()
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()

            result = json.loads(content)

            # 获取选中的子图
            selected = result.get('selected_subgraphs', [])

            # 验证子图是否在可用列表中
            valid_subgraphs = [
                sg for sg in selected
                if sg in self.available_subgraphs
            ]

            # 限制数量
            return valid_subgraphs[:max_count]

        except Exception as e:
            logger.error(f"解析LLM响应失败: {e}")
            logger.debug(f"原始响应: {response}")
            return []

    def get_subgraph_path(self, subgraph_name: str) -> Optional[Path]:
        """
        获取子图数据路径

        Args:
            subgraph_name: 子图名称

        Returns:
            子图数据目录路径，不存在返回None
        """
        if subgraph_name not in self.available_subgraphs:
            return None

        subgraph_path = self.base_data_dir / subgraph_name
        if subgraph_path.exists():
            return subgraph_path
        else:
            return None
