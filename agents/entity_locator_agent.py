"""
实体定位Agent
在知识图谱中定位错误相关的实体
"""
from typing import Dict, Optional
from agents.base_agent import BaseAgent
from data.kg_interface import KnowledgeGraphInterface


class EntityLocatorAgent(BaseAgent):
    """实体定位Agent - 图谱为主"""
    
    def __init__(self, kg: KnowledgeGraphInterface):
        super().__init__("EntityLocator")
        self.kg = kg
    
    def execute(self, parsed_log: Dict) -> Dict:
        """
        在图谱中定位实体
        
        Args:
            parsed_log: 解析后的日志信息
            
        Returns:
            定位到的实体信息
        """
        self.log_start("在图谱中定位实体")
        
        result = {
            'start_entity': None,
            'end_entity': None,
            'intermediate_entities': []
        }
        has_precise_log_matches = parsed_log.get('has_precise_log_matches', False)
        
        # 1. 定位起点（入口函数）
        if parsed_log.get('inferred_entry'):
            result['start_entity'] = self._locate_function(parsed_log['inferred_entry'])
        
        # 2. 定位终点（错误点）
        if parsed_log.get('inferred_error_point'):
            result['end_entity'] = self._locate_function(parsed_log['inferred_error_point'])
        
        # 3. 如果有关键函数，定位它们
        intermediate_func_names = []

        # 收集所有中间节点函数名（来自日志解析或用户指定）
        if 'key_functions' in parsed_log:
            intermediate_func_names.extend(parsed_log['key_functions'])

        # 混合模式：日志推断的起止点作为关键节点
        if 'intermediate_from_log' in parsed_log:
            intermediate_func_names.extend(parsed_log['intermediate_from_log'])

        # 定位所有中间节点
        if intermediate_func_names:
            key_entities = []
            for func_name in intermediate_func_names:
                entity = self._locate_function(func_name)
                if entity:
                    key_entities.append(entity)

            if key_entities:
                result['intermediate_entities'] = key_entities

                # 如果还没有终点，使用第一个关键函数（通常是最深层的）
                if not result['end_entity']:
                    result['end_entity'] = key_entities[0]
                    self.log_info(f"使用关键函数作为终点: {key_entities[0]['name']}")

        # 4. 如果还没有起点，使用默认的probe函数
        if not result['start_entity'] and not has_precise_log_matches:
            default_entry = 'dw_mci_pltfm_probe'
            self.log_info(f"尝试使用默认入口: {default_entry}")
            result['start_entity'] = self._locate_function(default_entry)

        # 5. 如果还没有推断出来，尝试从日志中的函数列表定位
        if (not result['start_entity'] or not result['end_entity']) and not has_precise_log_matches:
            result = self._locate_from_function_list(parsed_log['functions'], result)

        # 记录结果
        if result['start_entity']:
            self.log_success(f"起点: {result['start_entity']['name']}")
        else:
            self.log_warning("未找到起点函数")
        
        if result['end_entity']:
            self.log_success(f"终点: {result['end_entity']['name']}")
        else:
            self.log_warning("未找到终点函数")
        
        return result
    
    def _locate_function(self, func_name: str) -> Optional[Dict]:
        """
        精确定位函数
        
        Args:
            func_name: 函数名
            
        Returns:
            函数信息，如果不存在返回None
        """
        if not func_name:
            return None

        # 1. 精确匹配
        entity = self.kg.find_function(func_name)
        if entity:
            self.log_info(f"✓ 精确匹配: {func_name}")
            return entity
        
        # 2. 模糊匹配（处理宏展开等情况）
        self.log_warning(f"精确匹配失败，尝试模糊匹配: {func_name}")
        candidates = self.kg.find_functions_by_pattern(func_name)
        
        if candidates:
            self.log_info(f"找到 {len(candidates)} 个候选函数")
            # 返回第一个候选（后续可以用LLM排序）
            return self.kg.find_function(candidates[0]['name'])
        
        self.log_error(f"未找到函数: {func_name}")
        return None
    
    def _locate_from_function_list(self, functions: list, result: Dict) -> Dict:
        """
        从函数列表中定位起点和终点
        
        Args:
            functions: 日志中提到的函数列表
            result: 当前结果字典
            
        Returns:
            更新后的结果
        """
        # 尝试定位所有提到的函数
        located = []
        for func_name in functions:
            entity = self._locate_function(func_name)
            if entity:
                located.append(entity)
        
        if not located:
            return result

        def is_same_entity(entity_a: Optional[Dict], entity_b: Optional[Dict]) -> bool:
            if not entity_a or not entity_b:
                return False
            id_a = entity_a.get('id')
            id_b = entity_b.get('id')
            if id_a and id_b:
                return id_a == id_b
            return entity_a.get('name') == entity_b.get('name')

        def without_existing_counterpart(entities: list, counterpart: Optional[Dict]) -> list:
            if not counterpart:
                return entities
            return [entity for entity in entities if not is_same_entity(entity, counterpart)]

        # 如果没有起点，使用第一个与终点不同的函数
        if not result['start_entity'] and located:
            start_candidates = without_existing_counterpart(located, result.get('end_entity'))
            if start_candidates:
                result['start_entity'] = start_candidates[0]
                self.log_info(f"使用第一个函数作为起点: {start_candidates[0]['name']}")
        
        # 如果没有终点，使用最后一个与起点不同的函数
        if not result['end_entity'] and located:
            end_candidates = without_existing_counterpart(located, result.get('start_entity'))
            if end_candidates:
                result['end_entity'] = end_candidates[-1]
                self.log_info(f"使用最后一个函数作为终点: {end_candidates[-1]['name']}")
        
        # 中间的函数作为参考
        if len(located) > 2:
            result['intermediate_entities'] = located[1:-1]
        
        return result
    
    def locate_specific(self, start_name: str, end_name: str, intermediate_names: list = None) -> Dict:
        """
        直接定位指定的起点、终点和中间节点

        Args:
            start_name: 起点函数名
            end_name: 终点函数名
            intermediate_names: 中间节点函数名列表（可选）

        Returns:
            定位结果
        """
        self.log_start(f"定位指定函数: {start_name} -> {end_name}")

        result = {
            'start_entity': self._locate_function(start_name),
            'end_entity': self._locate_function(end_name),
            'intermediate_entities': []
        }

        # 定位中间节点
        if intermediate_names:
            key_entities = []
            for func_name in intermediate_names:
                entity = self._locate_function(func_name)
                if entity:
                    key_entities.append(entity)
                    self.log_info(f"✓ 定位到中间节点: {func_name}")

            if key_entities:
                result['intermediate_entities'] = key_entities
                self.log_success(f"定位到 {len(key_entities)} 个中间节点")

        return result
