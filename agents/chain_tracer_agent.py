"""
调用链追踪Agent
构建从入口到错误点的完整调用链
实现分层降级策略：
  第1层：扩展搜索（直接+间接调用）
  第2层：分段搜索+拼接
  第3层：LLM推理
  第4层：用户交互
"""
from typing import List, Optional, Dict, Tuple, Set
from agents.base_agent import BaseAgent
from data.kg_interface import KnowledgeGraphInterface
from utils.source_code_reader import SourceCodeReader
from agents.source_code_bridge_finder import SourceCodeBridgeFinder
from loguru import logger


class CallChainTracerAgent(BaseAgent):
    """调用链追踪Agent - 分层降级策略"""
    
    def __init__(self, kg: KnowledgeGraphInterface, llm_client=None):
        super().__init__("CallChainTracer")
        self.kg = kg
        self.llm = llm_client  # 可选的LLM客户端

        # 源码分析工具（用于LLM分析源码找断点连接）
        self.source_reader = SourceCodeReader()

        # 如果有 llm_client，创建 SourceCodeBridgeFinder
        if llm_client and hasattr(llm_client, 'is_available') and llm_client.is_available():
            # 直接传递 llm_client，不再提取参数
            self.bridge_finder = SourceCodeBridgeFinder(llm_client=llm_client)
        else:
            self.bridge_finder = None

        # 统计信息
        self.stats = {
            'total_breaks': 0,
            'fixed_by_rules': 0,
            'fixed_by_llm': 0,
            'fixed_by_source_analysis': 0,  # 新增：通过源码分析修复的数量
            'unfixed': 0
        }
    
    def execute(self, start_entity: Dict, end_entity: Dict,
                max_depth: int = 30) -> Dict:
        """
        追踪调用链 - 分层降级策略

        Args:
            start_entity: 起始实体
            end_entity: 目标实体
            max_depth: 最大搜索深度

        Returns:
            调用链信息
        """
        start_name = start_entity['name']
        end_name = end_entity['name']

        self.log_start(f"追踪调用链: {start_name} -> {end_name}")

        # === 第1层：扩展搜索（支持间接调用） ===
        result = self.kg.find_call_path_with_indirect(start_name, end_name, max_depth, debug=False)

        if result and result.get('path'):
            self.log_success(f"✓ 扩展搜索成功，路径长度: {len(result['path'])}")

            # 统计间接调用数量（包括函数指针和异步调用）
            edges = result.get('edges', [])
            indirect_count = sum(1 for e in edges if isinstance(e, dict))

            # 构建 breaks 信息（用于显示间接调用位置）
            breaks = []
            for i, edge in enumerate(edges):
                if isinstance(edge, dict):
                    edge_type = edge.get('type')
                    # 处理函数指针（indirect）和异步调用（async）
                    if edge_type in ['indirect', 'async']:
                        bridge_info = edge.get('bridge', {})
                        # 从bridge中获取实际的检测方法（llm_analysis或mock_data）
                        detection_method = bridge_info.get('method', 'unknown')
                        breaks.append({
                            'position': i,
                            'from': result['path'][i],
                            'to': result['path'][i + 1],
                            'fixed': True,
                            'method': detection_method,  # 使用实际的检测方法
                            'bridge': bridge_info
                        })

            # 更新统计
            self.stats['total_breaks'] = indirect_count
            self.stats['fixed_by_rules'] = indirect_count

            return {
                'path': result['path'],
                'edges': result.get('edges', []),
                'breaks': breaks,
                'method': 'extended_search',
                'stats': self.stats,
                'success': True
            }

        # === 第2层：分段搜索+拼接 ===
        self.log_warning("第1层失败，尝试第2层：分段搜索+拼接...")
        result = self._segmented_search_and_stitch(start_name, end_name, max_depth)

        if result:
            self.log_success(f"✓ 分段搜索成功，路径长度: {len(result['path'])}")
            return {
                'path': result['path'],
                'edges': result.get('edges', []),
                'breaks': result.get('breaks', []),  # 统一使用 'breaks'
                'method': 'segmented_search',
                'stats': self.stats,
                'success': True
            }

        # === 第3层：LLM推理 ===
        if self.llm:
            self.log_warning("第2层失败，尝试第3层：LLM推理...")
            result = self._llm_guided_search(start_name, end_name, max_depth)

            if result:
                self.log_success(f"✓ LLM推理成功，路径长度: {len(result['path'])}")
                return {
                    'path': result['path'],
                    'edges': result.get('edges', []),
                    'breaks': result.get('breaks', []),
                    'method': 'llm_inference',
                    'stats': self.stats,
                    'success': True
                }

        # === 第4层：需要用户交互 ===
        self.log_error("第3层失败，需要用户提供关键节点")
        return {
            'path': [],
            'edges': [],
            'breaks': [],
            'method': 'failed',
            'stats': self.stats,
            'success': False,
            'user_interaction_needed': True,
            'message': f"无法自动找到从 {start_name} 到 {end_name} 的调用路径，请提供关键中间节点"
        }
    
    def _detect_breaks(self, path: List[str]) -> List[Tuple[int, str, str]]:
        """
        检测路径中的断点
        
        Args:
            path: 函数调用路径
            
        Returns:
            断点列表，每个断点是 (位置, 函数A, 函数B) 的元组
        """
        breaks = []
        
        for i in range(len(path) - 1):
            node_a = path[i]
            node_b = path[i + 1]
            
            if not self.kg.has_direct_call(node_a, node_b):
                breaks.append((i, node_a, node_b))
                self.log_warning(f"断点 {i+1}: {node_a} -/-> {node_b}")
        
        return breaks
    
    def _fix_breaks(self, path: List[str], breaks: List[Tuple[int, str, str]]) -> Tuple[List[str], List[Dict]]:
        """
        修复所有断点
        
        Args:
            path: 原始路径
            breaks: 断点列表
            
        Returns:
            (修复后的路径, 断点修复信息列表)
        """
        fixed_path = path.copy()
        fixed_breaks = []
        
        # 按位置倒序修复（避免插入位置变化）
        for pos, node_a, node_b in reversed(breaks):
            self.log_info(f"尝试修复断点: {node_a} -> {node_b}")
            
            fix_result = self._fix_break_with_fallback(node_a, node_b)
            
            break_info = {
                'position': pos,
                'from': node_a,
                'to': node_b,
                'fixed': fix_result is not None,
                'method': fix_result[0] if fix_result else None,
                'bridge': fix_result[1] if fix_result else None
            }
            
            if fix_result:
                method, bridge = fix_result
                # 插入桥接实体到路径中
                if isinstance(bridge, str):
                    fixed_path.insert(pos + 1, bridge)
                elif isinstance(bridge, dict) and 'entity' in bridge:
                    fixed_path.insert(pos + 1, bridge['entity'])
                
                self.log_success(f"✓ 通过{method}修复成功")
            else:
                self.log_error(f"✗ 无法修复")
            
            fixed_breaks.append(break_info)
        
        # 倒序遍历，所以最后要反转
        fixed_breaks.reverse()
        
        return fixed_path, fixed_breaks
    
    def _fix_break_with_fallback(self, node_a: str, node_b: str) -> Optional[Tuple[str, any]]:
        """
        分层降级修复断点
        
        Args:
            node_a: 起始函数
            node_b: 目标函数
            
        Returns:
            (修复方法, 桥接信息) 或 None
        """
        # === 第1层：尝试专家规则 ===
        self.log_info("第1层：尝试专家规则...")
        bridge = self._try_expert_rules(node_a, node_b)
        
        if bridge:
            self.stats['fixed_by_rules'] += 1
            return ('rule', bridge)
        
        # === 第2层：LLM兜底 ===
        if self.llm:
            self.log_warning("第2层：规则失败，启用LLM推理...")
            bridge = self._llm_infer_bridge(node_a, node_b)
            
            if bridge and bridge.get('confidence', 0) > 0.6:
                self.stats['fixed_by_llm'] += 1
                return ('llm', bridge)
        
        # === 第3层：无法修复 ===
        self.log_error("第3层：无法修复此断点")
        self.stats['unfixed'] += 1
        return None
    
    def _try_expert_rules(self, node_a: str, node_b: str) -> Optional[Dict]:
        """
        尝试所有专家规则
        
        Args:
            node_a: 起始函数
            node_b: 目标函数
            
        Returns:
            桥接信息或None
        """
        # 规则1: 异步调用
        bridge = self._check_async_pattern(node_a, node_b)
        if bridge:
            return bridge
        
        # 规则2: 函数指针
        bridge = self._check_function_pointer_pattern(node_a, node_b)
        if bridge:
            return bridge
        
        # 规则3: 回调注册（待实现）
        # bridge = self._check_callback_pattern(node_a, node_b)
        # if bridge: return bridge
        
        # 规则4: 事件触发（待实现）
        # bridge = self._check_event_pattern(node_a, node_b)
        # if bridge: return bridge
        
        return None
    
    def _check_async_pattern(self, node_a: str, node_b: str) -> Optional[Dict]:
        """
        规则1: 检查异步调用模式（work_struct）

        优先使用LLM源码分析，失败后回退到Mock数据

        Args:
            node_a: 起始函数
            node_b: 目标函数

        Returns:
            桥接信息或None
        """
        # === 第1层：LLM源码分析 ===
        if self.bridge_finder:
            self.log_info(f"  → 尝试LLM源码分析: {node_a} -> {node_b}")

            # 获取函数信息
            func_a_ids = self.kg.get_function_ids(node_a)
            func_b_ids = self.kg.get_function_ids(node_b)

            if func_a_ids and func_b_ids:
                func_a_info = self.kg.get_function_info(func_a_ids[0])
                func_b_info = self.kg.get_function_info(func_b_ids[0])

                if func_a_info and func_b_info:
                    # 使用LLM分析源码
                    bridge_result = self.bridge_finder.find_bridge_between_functions(
                        func_a_info, func_b_info, self.source_reader, self.kg
                    )

                    if bridge_result:
                        self.stats['fixed_by_source_analysis'] += 1
                        self.log_success(f"✓ LLM源码分析成功: {bridge_result.get('bridge_type')}")
                        return {
                            'bridge_type': 'async',
                            'bridge_entity': bridge_result.get('bridge_entity', ''),
                            'method': 'llm_source_analysis',
                            'confidence': bridge_result.get('confidence', 0.0),
                            'explanation': bridge_result.get('explanation', '')
                        }

        # === 第2层：回退到Mock数据 ===
        self.log_info(f"  → 回退到Mock数据检查")
        result = self.kg.check_async_pattern(node_a, node_b)

        if result:
            self.log_success(f"✓ 检测到异步调用(Mock): {result.get('init_func')}")
            return result

        return None
    
    def _check_function_pointer_pattern(self, node_a: str, node_b: str) -> Optional[Dict]:
        """
        规则2: 检查函数指针调用模式（ops表）

        优先使用LLM源码分析，失败后回退到Mock数据

        Args:
            node_a: 起始函数
            node_b: 目标函数

        Returns:
            桥接信息或None
        """
        # === 第1层：LLM源码分析 ===
        if self.bridge_finder:
            self.log_info(f"  → 尝试LLM源码分析: {node_a} -> {node_b}")

            # 获取函数信息
            func_a_ids = self.kg.get_function_ids(node_a)
            func_b_ids = self.kg.get_function_ids(node_b)

            if func_a_ids and func_b_ids:
                func_a_info = self.kg.get_function_info(func_a_ids[0])
                func_b_info = self.kg.get_function_info(func_b_ids[0])

                if func_a_info and func_b_info:
                    # 使用LLM分析源码
                    bridge_result = self.bridge_finder.find_bridge_between_functions(
                        func_a_info, func_b_info, self.source_reader, self.kg
                    )

                    if bridge_result:
                        self.stats['fixed_by_source_analysis'] += 1
                        self.log_success(f"✓ LLM源码分析成功: {bridge_result.get('bridge_type')}")
                        return {
                            'bridge_type': 'function_pointer',
                            'bridge_entity': bridge_result.get('bridge_entity', ''),
                            'method': 'llm_source_analysis',
                            'confidence': bridge_result.get('confidence', 0.0),
                            'explanation': bridge_result.get('explanation', '')
                        }

        # === 第2层：回退到Mock数据 ===
        self.log_info(f"  → 回退到Mock数据检查")
        result = self.kg.check_function_pointer_pattern(node_a, node_b)

        if result:
            self.log_success(f"✓ 检测到函数指针(Mock): {result.get('struct_name')}.{result.get('field_name')}")
            return result

        return None
    
    def _segmented_search_and_stitch(
        self,
        start_name: str,
        end_name: str,
        max_depth: int
    ) -> Optional[Dict]:
        """
        分段搜索+拼接策略

        Args:
            start_name: 起始函数
            end_name: 目标函数
            max_depth: 最大深度

        Returns:
            拼接后的路径信息，失败返回None
        """
        self.log_info("  正在从起点进行正向搜索...")
        reachable_from_start = self.kg.find_reachable_from_start(start_name, max_depth // 2)

        self.log_info("  正在从终点进行反向搜索...")
        reachable_to_end = self.kg.find_reachable_to_end(end_name, max_depth // 2)

        # 找交集节点
        intersection = set(reachable_from_start.keys()) & set(reachable_to_end.keys())

        if not intersection:
            self.log_error("  ✗ 未找到可拼接的交集节点")
            return None

        self.log_info(f"  找到 {len(intersection)} 个交集节点")

        # 尝试用间接调用桥接交集节点
        for bridge_node in intersection:
            # 检查能否用间接调用连接
            path_to_bridge = reachable_from_start[bridge_node]
            path_from_bridge = reachable_to_end[bridge_node]

            # 检查 path_to_bridge 最后一个节点到 path_from_bridge 第一个节点
            if len(path_to_bridge) >= 2 and len(path_from_bridge) >= 2:
                last_before_bridge = path_to_bridge[-2] if len(path_to_bridge) > 1 else path_to_bridge[-1]
                first_after_bridge = path_from_bridge[1] if len(path_from_bridge) > 1 else path_from_bridge[0]

                # 检查是否有间接调用关系
                bridge_info = self._find_any_bridge(last_before_bridge, first_after_bridge)

                if bridge_info:
                    # 拼接路径
                    stitched_path = path_to_bridge + path_from_bridge[1:]
                    self.log_success(f"  ✓ 通过节点 {bridge_node} 成功拼接路径")

                    return {
                        'path': stitched_path,
                        'edges': [],  # TODO: 标记边类型
                        'bridges': [{'node': bridge_node, 'info': bridge_info}]
                    }

        # 如果直接拼接失败，选择最短的路径组合
        if intersection:
            shortest_node = min(
                intersection,
                key=lambda n: len(reachable_from_start[n]) + len(reachable_to_end[n])
            )

            stitched_path = (
                reachable_from_start[shortest_node] +
                reachable_to_end[shortest_node][1:]
            )

            self.log_warning(f"  使用最短路径拼接（通过节点 {shortest_node}）")
            return {
                'path': stitched_path,
                'edges': [],
                'bridges': [{'node': shortest_node, 'info': None}]
            }

        return None

    def _find_any_bridge(self, node_a: str, node_b: str) -> Optional[Dict]:
        """查找任意类型的桥接"""
        # 检查异步
        bridge = self.kg.check_async_pattern(node_a, node_b)
        if bridge:
            return bridge

        # 检查函数指针
        bridge = self.kg.check_function_pointer_pattern(node_a, node_b)
        if bridge:
            return bridge

        return None

    def _llm_guided_search(
        self,
        start_name: str,
        end_name: str,
        max_depth: int
    ) -> Optional[Dict]:
        """
        LLM引导的搜索

        Args:
            start_name: 起始函数
            end_name: 目标函数
            max_depth: 最大深度

        Returns:
            路径信息，失败返回None
        """
        if not self.llm or not self.llm.is_available():
            self.log_error("  ✗ LLM不可用")
            return None

        # 收集上下文
        context = self._collect_bridge_context(start_name, end_name)

        # 使用LLM分析关系
        code_a = context.get('code_a', '')
        code_b = context.get('code_b', '')

        result = self.llm.analyze_code_relationship(
            start_name, end_name, code_a, code_b, context
        )

        if result and result.get('confidence', 0) > 0.6:
            # LLM给出了高置信度的桥接建议
            bridge_entity = result.get('bridge_entity', 'unknown')
            self.log_success(f"  ✓ LLM推理成功: {result.get('bridge_type')} via {bridge_entity}")

            # 构造推理路径
            return {
                'path': [start_name, bridge_entity, end_name],
                'edges': [
                    {'type': 'llm_inferred', 'info': result},
                    {'type': 'llm_inferred', 'info': result}
                ]
            }

        return None

    def _llm_infer_bridge(self, node_a: str, node_b: str) -> Optional[Dict]:
        """
        LLM推理：当所有规则都失败时

        Args:
            node_a: 起始函数
            node_b: 目标函数

        Returns:
            桥接信息或None
        """
        if not self.llm or not self.llm.is_available():
            return None

        # 收集上下文
        context = self._collect_bridge_context(node_a, node_b)

        # 使用新的 OpenAI 客户端
        code_a = context.get('code_a', '')
        code_b = context.get('code_b', '')

        result = self.llm.analyze_code_relationship(
            node_a, node_b, code_a, code_b, context
        )

        if result and result.get('confidence', 0) > 0.6:
            self.log_success(f"✓ LLM推理成功: {result.get('bridge_type')}")
            return result

        return None
    
    def _collect_bridge_context(self, node_a: str, node_b: str) -> Dict:
        """收集用于LLM推理的上下文"""
        return {
            'code_a': self.kg.get_function_code(node_a) or "代码未找到",
            'code_b': self.kg.get_function_code(node_b) or "代码未找到",
            'callees_a': self.kg.get_callees(node_a),
            'callers_b': self.kg.get_callers(node_b),
            'related_structs_a': self.kg.get_related_structs(node_a),
            'related_structs_b': self.kg.get_related_structs(node_b)
        }
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self.stats.copy()

    def execute_top_k(
        self,
        start_entity: Dict,
        end_entity: Dict,
        intermediate_entities: Optional[List[Dict]] = None,
        max_depth: int = 30,
        k: int = 5,
        error_line: Optional[int] = None
    ) -> List[Dict]:
        """
        追踪Top-K条调用链

        Args:
            start_entity: 起始实体
            end_entity: 目标实体
            intermediate_entities: 中间途径点（关键函数列表），路径会尽量经过这些点
            max_depth: 最大搜索深度
            k: 返回路径数量上限
            error_line: 已废弃（保留用于兼容性，不再用于剪枝）

        Returns:
            路径列表，每个路径包含 path, edges, breaks 等信息
        """
        start_name = start_entity['name']
        end_name = end_entity['name']

        self.log_start(f"追踪Top-{k}条调用链: {start_name} -> {end_name}")
        if error_line:
            logger.warning(f"error_line参数已废弃，不再用于剪枝（传入值: {error_line}）")

        # 使用新的Top-K路径搜索
        paths = self.kg.find_top_k_call_paths_with_indirect(
            start_name,
            end_name,
            max_depth=max_depth,
            k=k,
            error_line=error_line,
            debug=False
        )

        if not paths:
            self.log_error("未找到任何路径")
            return []

        self.log_success(f"✓ 找到 {len(paths)} 条路径")

        # 提取关键函数名称（用于后续匹配）
        key_function_names = set()
        if intermediate_entities:
            key_function_names = {entity['name'] for entity in intermediate_entities}
            self.log_info(f"关键函数: {list(key_function_names)}")

        # 处理每条路径，添加breaks信息
        result_paths = []
        for idx, path_info in enumerate(paths):
            edges = path_info.get('edges', [])
            path = path_info.get('path', [])
            call_lines = path_info.get('call_lines', [])

            # 统计间接调用数量（包括函数指针和异步调用）
            indirect_count = sum(1 for e in edges if isinstance(e, dict))

            # 构建 breaks 信息（用于显示间接调用位置）
            breaks = []
            for i, edge in enumerate(edges):
                if isinstance(edge, dict):
                    edge_type = edge.get('type')
                    # 处理函数指针（indirect）和异步调用（async）
                    if edge_type in ['indirect', 'async']:
                        bridge_info = edge.get('bridge', {})
                        # 从bridge中获取实际的检测方法（llm_analysis或mock_data）
                        detection_method = bridge_info.get('method', 'unknown')
                        breaks.append({
                            'position': i,
                            'from': path[i],
                            'to': path[i + 1],
                            'fixed': True,
                            'method': detection_method,  # 使用实际的检测方法
                            'bridge': bridge_info
                        })

            # 检查路径经过了哪些关键函数
            matched_key_functions = []
            missed_key_functions = []
            if key_function_names:
                path_set = set(path)
                for key_func in key_function_names:
                    if key_func in path_set:
                        matched_key_functions.append(key_func)
                    else:
                        missed_key_functions.append(key_func)

            # 构建增强的路径信息
            enriched_info = self._build_enriched_path_info(path, edges, call_lines)

            result_paths.append({
                # 原有字段（保持向后兼容）
                'path': path,
                'edges': edges,
                'call_lines': call_lines,
                'breaks': breaks,
                'score': path_info.get('score', 0),
                'length': path_info.get('length', len(path)),
                'indirect_count': indirect_count,
                'avg_call_line': path_info.get('avg_call_line', 0),
                'matched_key_functions': matched_key_functions,
                'missed_key_functions': missed_key_functions,
                'method': 'top_k_search',
                'success': True,
                # 新增增强字段
                'nodes_detailed': enriched_info['nodes'],
                'connections': enriched_info['connections']
            })

            logger.info(f"  路径 #{idx+1}: 长度={len(path)}, 间接调用={indirect_count}, 得分={path_info.get('score', 0)}")

        # 如果有关键函数，调整得分并重新排序
        if key_function_names:
            self.log_info("根据关键函数覆盖率调整得分...")
            for path_result in result_paths:
                matched_count = len(path_result['matched_key_functions'])
                # 每匹配一个关键函数，得分+50
                score_boost = matched_count * 50
                original_score = path_result['score']
                path_result['score'] = original_score + score_boost

                if matched_count > 0:
                    coverage = matched_count / len(key_function_names) * 100
                    logger.info(f"    路径匹配 {matched_count}/{len(key_function_names)} 个关键函数 "
                              f"(覆盖率: {coverage:.1f}%), 得分: {original_score:.2f} → {path_result['score']:.2f}")

            # 按调整后的得分重新排序
            result_paths.sort(key=lambda x: x['score'], reverse=True)
            self.log_success("得分调整完成，已重新排序")

        return result_paths

    def _get_node_detailed_info(self, func_name: str) -> Dict:
        """
        获取节点的详细信息（包括同名节点处理）

        Args:
            func_name: 函数名

        Returns:
            节点详细信息字典
        """
        # 获取所有同名函数的ID
        all_ids = self.kg.func_name_to_ids.get(func_name, [])

        if not all_ids:
            return {
                'name': func_name,
                'exists': False,
                'count': 0,
                'entities': []
            }

        # 收集所有同名实体的详细信息（最多5个）
        entities_info = []
        for func_id in all_ids[:5]:  # 最多展示5个
            entity = self.kg.entity_by_id.get(func_id)
            if entity:
                entities_info.append({
                    'id': entity.get('id'),
                    'name': entity.get('name'),
                    'type': entity.get('type'),
                    'source_file': entity.get('source_file'),
                    'start_line': entity.get('start_line'),
                    'end_line': entity.get('end_line'),
                    'is_declaration': entity.get('is_declaration', False)
                })

        return {
            'name': func_name,
            'exists': True,
            'count': len(all_ids),
            'has_multiple': len(all_ids) > 1,
            'entities': entities_info,
            'note': f'在当前子图下有 {len(all_ids)} 个同名节点' if len(all_ids) > 1 else None
        }

    def _build_enriched_path_info(self, path: List[str], edges: List, call_lines: List) -> Dict:
        """
        构建增强的路径信息（包含详细节点信息和清晰的边信息）

        Args:
            path: 函数名列表
            edges: 边类型列表
            call_lines: 调用行号列表

        Returns:
            增强的路径信息
        """
        # 1. 构建节点详细信息
        nodes_detailed = []
        for func_name in path:
            node_info = self._get_node_detailed_info(func_name)
            nodes_detailed.append(node_info)

        # 2. 构建统一的边信息（节点间的连接）
        connections = []
        for i in range(len(edges)):
            from_node = path[i]
            to_node = path[i + 1]
            call_line = call_lines[i] if i < len(call_lines) else None
            edge = edges[i]

            # 统一的连接信息格式
            connection = {
                'from': from_node,
                'to': to_node,
                'call_line': call_line
            }

            # 判断边的类型
            if isinstance(edge, dict):
                edge_type = edge.get('type')
                if edge_type == 'async':
                    connection['type'] = 'async'
                    connection['bridge'] = edge.get('bridge', {})
                    connection['description'] = '异步调用'
                elif edge_type == 'indirect':
                    connection['type'] = 'indirect'
                    connection['bridge'] = edge.get('bridge', {})
                    connection['description'] = '间接调用（函数指针）'
                else:
                    connection['type'] = edge_type
                    connection['bridge'] = edge.get('bridge', {})
            else:
                # 直接调用
                connection['type'] = 'direct'
                connection['description'] = '直接调用'

            connections.append(connection)

        return {
            'nodes': nodes_detailed,
            'connections': connections
        }
