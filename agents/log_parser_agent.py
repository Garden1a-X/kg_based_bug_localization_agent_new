"""
日志解析Agent
从错误日志中提取结构化信息
"""
import re
from typing import Dict, List
from agents.base_agent import BaseAgent
from data.mock_indirect_calls import MOCK_FAIL_MESSAGES, _extract_message_pattern


class LogParserAgent(BaseAgent):
    """日志解析Agent - 基于FAIL_MESSAGE实体匹配"""

    def __init__(self, enable_llm: bool = False, llm_client=None):
        super().__init__("LogParser")
        self.enable_llm = enable_llm
        self.llm_client = llm_client  # 统一的LLM客户端

        # 定义常见的错误模式（保留用于fallback）
        self.error_patterns = {
            'error_message': r'(error|Error|ERROR)[:\s]+(.+?)(?:\n|$)',
            'error_code': r'error[:\s]+(-?\d+)',
            'function_name': r'([a-zA-Z_][a-zA-Z0-9_]+)\s*\(',
            'file_path': r'([/\w]+\.c)',
            'line_number': r':(\d+):',
        }

    def execute(self, log_text: str) -> Dict:
        """
        解析日志文本

        Args:
            log_text: 原始日志文本

        Returns:
            结构化的日志信息
        """
        self.log_start("解析错误日志")

        result = {
            'raw_log': log_text,
            'error_messages': self._extract_error_messages(log_text),
            'error_codes': self._extract_error_codes(log_text),
            'functions': self._extract_functions(log_text),
            'files': self._extract_files(log_text),
            'lines': self._extract_line_numbers(log_text)
        }

        self.log_success(f"提取到 {len(result['error_messages'])} 个错误消息")
        self.log_info(f"涉及函数: {result['functions']}")

        return result
    
    def _extract_error_messages(self, log_text: str) -> List[str]:
        """提取错误消息"""
        messages = []
        
        # 模式1: "error: xxx"
        pattern1 = re.findall(r'error[:\s]+(.+?)(?:\n|$)', log_text, re.IGNORECASE)
        messages.extend(pattern1)
        
        # 模式2: "failed: xxx"  
        pattern2 = re.findall(r'failed[:\s]+(.+?)(?:\n|$)', log_text, re.IGNORECASE)
        messages.extend(pattern2)
        
        # 模式3: "xxx whilst xxx"
        pattern3 = re.findall(r'(.+?whilst.+?)(?:\n|$)', log_text)
        messages.extend(pattern3)
        
        return list(set(messages))  # 去重
    
    def _extract_error_codes(self, log_text: str) -> List[int]:
        """提取错误码"""
        codes = re.findall(r'[-]?\d+', log_text)
        return [int(c) for c in codes if c.startswith('-') or int(c) > 0]
    
    def _extract_functions(self, log_text: str) -> List[str]:
        """提取函数名"""
        # 匹配 C 函数名模式
        functions = re.findall(r'([a-zA-Z_][a-zA-Z0-9_]+)\s*\(', log_text)
        return list(set(functions))
    
    def _extract_files(self, log_text: str) -> List[str]:
        """提取文件路径"""
        files = re.findall(r'([/\w]+\.c)', log_text)
        return list(set(files))
    
    def _extract_line_numbers(self, log_text: str) -> List[int]:
        """提取行号"""
        lines = re.findall(r':(\d+):', log_text)
        return [int(l) for l in lines]

    def _match_log_line_to_fail_message(self, log_line: str, fail_messages: dict) -> list:
        """
        尝试将一行日志匹配到FAIL_MESSAGE实体

        Args:
            log_line: 单行日志文本
            fail_messages: FAIL_MESSAGE实体字典

        Returns:
            匹配到的消息列表 [(msg_id, msg_data, matched_text, similarity), ...]
        """
        matches = []

        for msg_id, msg_data in fail_messages.items():
            # 从name字段提取匹配模式
            pattern = _extract_message_pattern(msg_data.get('name', ''))
            if not pattern:
                continue

            # 尝试匹配
            match_obj = re.search(pattern, log_line, re.IGNORECASE)
            if match_obj:
                matched_text = match_obj.group(0)

                # 计算相似度（匹配长度占日志行的比例）
                similarity = len(matched_text) / len(log_line.strip()) if log_line.strip() else 0

                matches.append((msg_id, msg_data, matched_text, similarity))

        # 按相似度排序（从高到低）
        matches.sort(key=lambda x: x[3], reverse=True)

        return matches

    def _analyze_log_by_lines(self, log_text: str) -> dict:
        """
        逐行分析日志，匹配FAIL_MESSAGE

        Args:
            log_text: 完整日志文本

        Returns:
            分析结果
        """
        lines = [line.strip() for line in log_text.strip().split('\n') if line.strip()]

        result = {
            'total_lines': len(lines),
            'line_matches': [],
            'all_functions': []
        }

        for idx, line in enumerate(lines, 1):
            matches = self._match_log_line_to_fail_message(line, MOCK_FAIL_MESSAGES)

            if matches:
                # 取最佳匹配（相似度最高）
                best_msg_id, best_msg, matched_text, similarity = matches[0]
                func_name = best_msg.get('scope')

                # 记录所有候选函数（用于LLM分析）
                candidates = []
                for msg_id, msg, txt, sim in matches:
                    candidates.append({
                        'function': msg.get('scope'),
                        'message_id': msg_id,
                        'source_file': msg.get('source_file'),
                        'start_line': msg.get('start_line'),
                        'similarity': sim,
                        'matched_text': txt
                    })

                result['line_matches'].append({
                    'line_number': idx,
                    'log_line': line,
                    'matched_text': matched_text,
                    'similarity': similarity,
                    'function': func_name,
                    'message_id': best_msg_id,
                    'source_file': best_msg.get('source_file'),
                    'start_line': best_msg.get('start_line'),
                    'candidates': candidates  # 所有候选函数
                })

                if func_name and func_name not in result['all_functions']:
                    result['all_functions'].append(func_name)

        return result

    def parse_mmc_log(
        self,
        log_text: str,
        candidate_entries: list = None,
        user_context: dict = None
    ) -> Dict:
        """
        专门针对MMC日志的解析（甲方案例）
        使用基于FAIL_MESSAGE实体的匹配方法

        Args:
            log_text: MMC错误日志
            candidate_entries: 候选入口函数列表（可选）
            user_context: 用户提供的上下文信息（可选）

        Returns:
            解析结果，包含推断的起点和终点、置信度等
        """
        self.log_start("解析MMC错误日志")

        # 使用新的基于FAIL_MESSAGE的匹配方法
        matching_result = self._analyze_log_by_lines(log_text)

        # 提取关键函数
        all_functions = matching_result.get('all_functions', [])
        matched_count = len(matching_result.get('line_matches', []))

        self.log_success(f"匹配到 {matched_count} 行日志")
        self.log_info(f"涉及函数: {all_functions}")

        # 构建基础结果
        result = {
            'raw_log': log_text,
            'line_matches': matching_result.get('line_matches', []),
            'functions': all_functions,  # 所有匹配到的函数
            'error_messages': self._extract_error_messages(log_text),
            'error_codes': self._extract_error_codes(log_text),
            # 初始化入口相关字段（不设置默认值）
            'inferred_entry': None,
            'entry_confidence': 0.0,
            'need_more_info': False,
            'suggestions': [],
            'llm_reasoning': []
        }

        # 推断错误点：取最底层的函数（日志的第一个匹配函数）
        if all_functions:
            result['inferred_error_point'] = all_functions[0]
        else:
            result['inferred_error_point'] = None

        # 关键函数：所有从日志匹配到的函数（包括错误点和中间点）
        result['key_functions'] = all_functions

        # 推断中间节点：除了第一个（错误点）之外的所有函数
        if len(all_functions) > 1:
            result['intermediate_functions'] = all_functions[1:]
        else:
            result['intermediate_functions'] = []

        # 如果启用了LLM，调用LLM进行增强分析
        if self.enable_llm and self.llm_client:
            llm_result = self._analyze_with_llm(
                log_text,
                matching_result,
                candidate_entries=candidate_entries,
                user_context=user_context
            )

            if llm_result and not llm_result.get('error'):
                # 使用LLM的入口推断
                if llm_result.get('start_entity'):
                    result['inferred_entry'] = llm_result['start_entity']
                    result['entry_confidence'] = llm_result.get('start_confidence', 0.5)

                # 使用LLM的终点推断
                if llm_result.get('end_entity'):
                    result['inferred_error_point'] = llm_result['end_entity']

                # 中间节点
                if llm_result.get('intermediate_entities'):
                    result['intermediate_functions'] = llm_result['intermediate_entities']

                # 其他信息
                result['need_more_info'] = llm_result.get('need_more_info', False)
                result['suggestions'] = llm_result.get('suggestions', [])
                result['llm_reasoning'] = llm_result.get('reasoning', [])
                result['llm_analysis'] = llm_result

        # 降级处理：如果LLM没有给出入口或置信度太低
        if not result['inferred_entry'] or result['entry_confidence'] < 0.6:
            # 使用日志中最上层的函数作为降级入口
            if all_functions:
                result['inferred_entry'] = all_functions[-1]  # 日志函数列表最后一个
                result['entry_confidence'] = 0.3  # 标记为低置信度
                result['need_more_info'] = True
                result['fallback_mode'] = True  # 标记为降级模式

                if not result['suggestions']:
                    result['suggestions'] = [
                        "硬件平台信息（如 RK3288, i.MX28, Renesas 等）",
                        "驱动类型提示（如 dw_mci, mxs_mmc, sdhci 等）",
                        "完整的 dmesg 日志（包含驱动加载信息）",
                        "设备树信息或内核配置"
                    ]

                self.log_warning(f"⚠️ 无法确定完整入口，使用降级模式：{result['inferred_entry']} (日志最上层函数)")
                self.log_info(f"💡 建议提供: {', '.join(result['suggestions'][:2])}")
            else:
                # 连日志函数都没有，无法分析
                result['need_more_info'] = True
                result['suggestions'] = ["无法从日志中提取函数信息，请提供更详细的错误日志"]
                self.log_error("❌ 无法从日志中提取任何函数信息")

        return result

    def _analyze_with_llm(
        self,
        log_text: str,
        matching_result: dict,
        candidate_entries: list = None,
        user_context: dict = None
    ) -> dict:
        """
        使用LLM分析日志（可选）

        Args:
            log_text: 完整日志文本
            matching_result: 模式匹配结果
            candidate_entries: 候选入口函数列表（可选）
            user_context: 用户提供的上下文信息（可选）

        Returns:
            LLM分析结果
        """
        # 使用统一的LLM客户端
        if not self.llm_client or not self.llm_client.is_available():
            self.log_info("LLM客户端不可用，跳过LLM分析")
            return {"error": "LLM not available"}

        try:
            # 使用 llm_client 的 analyze_log 方法
            llm_result = self.llm_client.analyze_log(
                log_text,
                candidate_entries=candidate_entries,
                user_context=user_context
            )

            if not llm_result:
                return {"error": "LLM返回空结果"}

            # 如果LLM没有返回某些字段，添加默认值
            if 'intermediate_entities' not in llm_result:
                llm_result['intermediate_entities'] = []
            if 'start_confidence' not in llm_result:
                llm_result['start_confidence'] = 0.5
            if 'need_more_info' not in llm_result:
                llm_result['need_more_info'] = False
            if 'suggestions' not in llm_result:
                llm_result['suggestions'] = []
            if 'reasoning' not in llm_result:
                llm_result['reasoning'] = []

            return llm_result

        except Exception as e:
            self.log_info(f"LLM分析失败: {e}")
            return {"error": str(e)}
