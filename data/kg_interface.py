"""
知识图谱接口模块
从JSON文件读取知识图谱数据
"""
import json
import os
from typing import Dict, List, Optional, Any, Tuple
from loguru import logger
from pathlib import Path

# ============================================================
# TODO: 等图谱修复后删除这个导入
# ============================================================
# Mock 数据已移除 - 现在完全依赖图谱数据


class KnowledgeGraphInterface:
    """知识图谱接口 - 基于JSON文件"""

    def __init__(self, data_dir: str = None, enable_llm_detection: bool = False, llm_client=None, path_mappings: dict = None):
        """
        初始化知识图谱接口

        Args:
            data_dir: 数据文件所在目录
            enable_llm_detection: 是否启用LLM辅助间接调用检测（运行时）
            llm_client: LLM客户端实例（可选）
            path_mappings: 路径映射字典，用于将图谱中的路径映射到当前环境
                          例如: {"E:\\cpppro\\clang_kg\\linux": "/data/xuao/code_kg/data/linux_data"}
        """
        if data_dir is None:
            data_dir = os.getenv('KG_DATA_DIR', '/data/xuao/code_kg_search/linux_test/data')

        self.data_dir = Path(data_dir)
        self.enable_llm_detection = enable_llm_detection
        self.llm_client = llm_client  # 统一的LLM客户端

        # 路径映射配置
        self.path_mappings = path_mappings or {}
        if self.path_mappings:
            logger.info(f"  ✓ 配置路径映射: {len(self.path_mappings)} 个")
            for old_path, new_path in self.path_mappings.items():
                logger.info(f"    {old_path} -> {new_path}")

        # 缓存数据
        self.entities = {}  # {entity_type: {name: entity}}
        self.relations = {}  # {rel_type: [relations]}
        self.entity_by_id = {}  # {id: entity} - 用于通过id快速查找

        # 声明-实现映射
        self.decl_to_impl = {}  # {decl_id: impl_id}
        self.impl_to_decl = {}  # {impl_id: [decl_ids]}

        # 函数名到所有ID的映射（支持同名函数）
        self.func_name_to_ids = {}  # {func_name: [id1, id2, ...]}

        # 调用关系图（包含行号信息）
        # {caller_id: [(callee_id, call_line), ...]}
        self.call_graph_with_lines = {}

        # LLM间接调用检测缓存（函数指针）
        # {func_name: [(target_func, bridge_info), ...]}
        self.llm_indirect_call_cache = {}

        # 异步调用检测相关
        self.async_functions = set()  # 异步函数集合（基于关键字/配置识别）
        self.async_call_cache = {}    # 异步调用缓存 {(caller, callee): [(target, bridge_info), ...]}

        # 加载所有数据
        self._load_all_data()

        # 初始化已知的异步函数（即使不启用LLM也需要）
        self._init_known_async_functions()

        logger.info(f"已加载知识图谱: {data_dir}")
    
    def _load_all_data(self):
        """加载所有JSON文件"""
        logger.info("正在加载数据...")

        # 检查是否使用合并格式（entity.json + relation.json）
        entity_file = self.data_dir / 'entity.json'
        relation_file = self.data_dir / 'relation.json'

        if entity_file.exists() and relation_file.exists():
            logger.info("检测到合并格式数据文件")
            self._load_merged_format(entity_file, relation_file)
        else:
            logger.info("使用分散格式数据文件")
            self._load_separated_format()

    def _load_merged_format(self, entity_file: Path, relation_file: Path):
        """加载合并格式的数据（entity.json + relation.json）"""
        # 加载实体
        logger.info(f"加载实体文件: {entity_file.name}")
        with open(entity_file, 'r', encoding='utf-8') as f:
            entities_data = json.load(f)

        # 解析实体数据结构
        if isinstance(entities_data, dict):
            # 字典格式：按类型分组
            for entity_type, entity_list in entities_data.items():
                if isinstance(entity_list, list):
                    self.entities[entity_type] = {}
                    for item in entity_list:
                        if isinstance(item, dict) and 'name' in item:
                            # 标准化ID为字符串（确保类型一致性）
                            if 'id' in item:
                                item['id'] = str(item['id'])
                            self.entities[entity_type][item['name']] = item
                            # 同时建立 id 映射
                            if 'id' in item:
                                self.entity_by_id[item['id']] = item
                    logger.info(f"  ✓ 加载 {entity_type}: {len(self.entities[entity_type])} 个")
        elif isinstance(entities_data, list):
            # 列表格式：根据 type 字段分组（你的格式）
            for entity in entities_data:
                if isinstance(entity, dict) and 'name' in entity:
                    # 标准化ID为字符串（确保类型一致性）
                    if 'id' in entity:
                        entity['id'] = str(entity['id'])
                    entity_type = entity.get('type', entity.get('entity_type', 'Unknown'))
                    if entity_type not in self.entities:
                        self.entities[entity_type] = {}
                    self.entities[entity_type][entity['name']] = entity
                    # 同时建立 id 映射
                    if 'id' in entity:
                        self.entity_by_id[entity['id']] = entity

            for entity_type, entities in self.entities.items():
                logger.info(f"  ✓ 加载 {entity_type}: {len(entities)} 个")

        # 建立声明-实现映射（针对函数）
        if 'FUNCTION' in self.entities:
            self._build_decl_impl_mapping()
            self._build_func_name_mapping()

        # 加载关系
        logger.info(f"加载关系文件: {relation_file.name}")
        with open(relation_file, 'r', encoding='utf-8') as f:
            relations_data = json.load(f)

        # 解析关系数据结构
        if isinstance(relations_data, dict):
            # 字典格式：按类型分组
            for rel_type, rel_list in relations_data.items():
                if isinstance(rel_list, list):
                    # 标准化关系中的ID为字符串
                    for rel in rel_list:
                        if 'head' in rel:
                            rel['head'] = str(rel['head'])
                        if 'tail' in rel:
                            rel['tail'] = str(rel['tail'])
                    self.relations[rel_type] = rel_list
                    logger.info(f"  ✓ 加载 {rel_type}: {len(rel_list)} 个")
        elif isinstance(relations_data, list):
            # 列表格式：根据 type 字段分组
            for relation in relations_data:
                if isinstance(relation, dict):
                    # 标准化关系中的ID为字符串
                    if 'head' in relation:
                        relation['head'] = str(relation['head'])
                    if 'tail' in relation:
                        relation['tail'] = str(relation['tail'])
                    rel_type = relation.get('type', relation.get('relation_type', 'UNKNOWN'))
                    if rel_type not in self.relations:
                        self.relations[rel_type] = []
                    self.relations[rel_type].append(relation)

            for rel_type, relations in self.relations.items():
                logger.info(f"  ✓ 加载 {rel_type}: {len(relations)} 个")

        # 构建包含行号的调用图
        self._build_call_graph_with_lines()

    def _build_decl_impl_mapping(self):
        """建立函数声明-实现映射"""
        from collections import defaultdict

        func_by_name = defaultdict(lambda: {'decls': [], 'impls': []})

        # 按名称分组，区分声明和实现
        # 注意：必须遍历entity_by_id而不是entities['FUNCTION']
        # 因为entities['FUNCTION']按名称索引，同名函数会被覆盖
        for entity_id, entity in self.entity_by_id.items():
            if entity.get('type') != 'FUNCTION':
                continue

            func_name = entity.get('name')
            func_id = entity.get('id')
            is_decl = entity.get('is_declaration', False)

            if not func_name or not func_id:
                continue

            if is_decl:
                func_by_name[func_name]['decls'].append(func_id)
            else:
                func_by_name[func_name]['impls'].append(func_id)

        # 建立映射关系
        mapping_count = 0
        for func_name, ids in func_by_name.items():
            decls = ids['decls']
            impls = ids['impls']

            # 如果有实现，将所有声明映射到第一个实现
            if impls:
                impl_id = impls[0]
                for decl_id in decls:
                    self.decl_to_impl[decl_id] = impl_id
                    if impl_id not in self.impl_to_decl:
                        self.impl_to_decl[impl_id] = []
                    self.impl_to_decl[impl_id].append(decl_id)
                    mapping_count += 1

        if mapping_count > 0:
            logger.info(f"  ✓ 建立声明→实现映射: {mapping_count} 对")

    def _build_func_name_mapping(self):
        """建立函数名到所有ID的映射（支持同名函数）"""
        # 遍历所有函数实体，按名称建立ID列表
        for entity_id, entity in self.entity_by_id.items():
            if entity.get('type') == 'FUNCTION':
                func_name = entity.get('name')
                if func_name:
                    if func_name not in self.func_name_to_ids:
                        self.func_name_to_ids[func_name] = []
                    self.func_name_to_ids[func_name].append(entity_id)

        # 统计有多个ID的函数
        multi_id_count = sum(1 for ids in self.func_name_to_ids.values() if len(ids) > 1)
        if multi_id_count > 0:
            logger.info(f"  ✓ 建立函数名→ID映射: {len(self.func_name_to_ids)} 个函数, {multi_id_count} 个有多个ID")

    def _build_call_graph_with_lines(self):
        """构建包含行号信息的调用图"""
        if 'CALLS' not in self.relations:
            return

        for rel in self.relations['CALLS']:
            caller_id = rel.get('head')
            callee_id = rel.get('tail')
            call_line = rel.get('call_line')

            if not caller_id or not callee_id:
                continue

            if caller_id not in self.call_graph_with_lines:
                self.call_graph_with_lines[caller_id] = []

            self.call_graph_with_lines[caller_id].append({
                'callee_id': callee_id,
                'call_line': call_line
            })

        logger.info(f"  ✓ 构建调用图（含行号）: {len(self.call_graph_with_lines)} 个调用者")

    def _init_known_async_functions(self):
        """
        初始化已知的异步函数列表（即使不启用LLM也需要）

        包括：
        1. 从配置文件读取（如果存在）
        2. 从图谱中通过关键字识别
        3. 使用默认列表（fallback）
        """
        # 1. 尝试从配置文件读取
        config_file = Path(__file__).parent.parent / 'config' / 'indirect_call_detection.yaml'

        if config_file.exists():
            try:
                import yaml
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)

                async_config = config.get('async_call_detection', {})
                known_funcs = async_config.get('known_async_functions', [])
                keywords = async_config.get('keywords', [])

                # 添加显式配置的异步函数
                self.async_functions.update(known_funcs)

                # 基于关键字扫描图谱中的函数
                if keywords and 'FUNCTION' in self.entities:
                    for func_name in self.entities['FUNCTION'].keys():
                        func_name_lower = func_name.lower()
                        if any(kw in func_name_lower for kw in keywords):
                            self.async_functions.add(func_name)

                if self.async_functions:
                    logger.info(f"  ✓ 初始化异步函数: {len(self.async_functions)} 个")

            except Exception as e:
                logger.warning(f"加载异步函数配置失败: {e}")

        # 2. 使用默认列表（fallback）
        if not self.async_functions:
            # 即使没有配置文件，也初始化一些已知的异步调度函数
            default_async_functions = [
                'mmc_schedule_delayed_work',
                'schedule_work',
                'schedule_delayed_work',
                'queue_work',
                'queue_delayed_work'
            ]
            self.async_functions.update(default_async_functions)
            logger.info(f"  ✓ 使用默认异步函数列表: {len(self.async_functions)} 个")

    def normalize_id(self, func_id):
        """
        标准化为实现ID

        Args:
            func_id: 函数ID（可能是声明或实现）

        Returns:
            实现ID
        """
        return self.decl_to_impl.get(func_id, func_id)

    def get_equivalent_ids(self, func_id):
        """
        获取等价ID集合（包括声明和实现）

        Args:
            func_id: 函数ID

        Returns:
            等价ID集合
        """
        equivalent = {func_id}

        # 如果是声明，添加对应的实现
        if func_id in self.decl_to_impl:
            equivalent.add(self.decl_to_impl[func_id])

        # 如果是实现，添加所有对应的声明
        if func_id in self.impl_to_decl:
            equivalent.update(self.impl_to_decl[func_id])

        return equivalent

    def _load_separated_format(self):
        """加载分散格式的数据（多个独立文件）"""
        # 加载实体
        entity_files = {
            'Function': 'entity_function.json',
            'Struct': 'entity_struct.json',
            'Variable': 'entity_variable.json',
            'Field': 'entity_field.json',
            'File': 'entity_file.json',
        }

        for entity_type, filename in entity_files.items():
            filepath = self.data_dir / filename
            if filepath.exists():
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 如果是字典，转为列表
                    if isinstance(data, dict):
                        data = list(data.values())
                    # 标准化ID为字符串
                    for item in data:
                        if 'id' in item:
                            item['id'] = str(item['id'])
                    self.entities[entity_type] = {
                        item['name']: item for item in data if 'name' in item
                    }
                    # 建立 id 映射
                    for item in data:
                        if 'id' in item:
                            self.entity_by_id[item['id']] = item
                logger.info(f"✓ 加载 {entity_type}: {len(self.entities[entity_type])} 个")

        # 加载关系
        relation_files = {
            'CALLS': 'relation_calls.json',
            'CONTAINS': 'relation_contains.json',
            'TYPE_OF': 'relation_typeof.json',
            'ASSIGNED_TO': 'relation_assignedto.json',
            'HAS_MEMBERS': 'relation_has_members.json',
            'RETURNS': 'relation_returns.json',
            'HAS_PARAMETERS': 'relation_has_parameters.json',
            'HAS_VARIABLES': 'relation_has_variables.json',
            'INCLUDES': 'relation_includes.json',
            'ioctl_call': 'relation_ioctl_call.json',
        }

        for rel_type, filename in relation_files.items():
            filepath = self.data_dir / filename
            if filepath.exists():
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data = list(data.values())
                    # 标准化关系中的ID为字符串
                    for rel in data:
                        if 'head' in rel:
                            rel['head'] = str(rel['head'])
                        if 'tail' in rel:
                            rel['tail'] = str(rel['tail'])
                    self.relations[rel_type] = data
                logger.info(f"✓ 加载 {rel_type}: {len(self.relations[rel_type])} 个")

        # 建立声明-实现映射和函数名映射（针对函数）
        if 'FUNCTION' in self.entities:
            self._build_decl_impl_mapping()
            self._build_func_name_mapping()

        # 构建包含行号的调用图
        self._build_call_graph_with_lines()

    def close(self):
        """关闭连接"""
        logger.info("知识图谱接口关闭")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    # ============ 基础查询方法 ============
    
    def query(self, cypher: str, **params) -> List[Dict]:
        """
        模拟Cypher查询（简化版本）
        注意：这是简化实现，不支持复杂的Cypher语法
        """
        # JSON版本不需要Cypher，直接返回空
        logger.warning("JSON模式不支持直接Cypher查询，请使用专用方法")
        return []
    
    def entity_exists(self, entity_type: str, name: str) -> bool:
        """
        检查实体是否存在
        
        Args:
            entity_type: 实体类型（Function, Struct, Variable等）
            name: 实体名称
            
        Returns:
            是否存在
        """
        if entity_type not in self.entities:
            return False
        return name in self.entities[entity_type]
    
    # ============ 函数相关查询 ============
    
    def find_function(self, func_name: str) -> Optional[Dict]:
        """
        查找函数实体

        Args:
            func_name: 函数名

        Returns:
            函数实体信息，如果不存在返回None
        """
        if 'FUNCTION' not in self.entities:
            return None

        entity = self.entities['FUNCTION'].get(func_name)
        if entity and 'file' not in entity and 'source_file' in entity:
            # 添加 file 字段作为 source_file 的别名，保持向后兼容
            entity = entity.copy()
            entity['file'] = entity['source_file']

        return entity
    
    def find_functions_by_pattern(self, pattern: str) -> List[Dict]:
        """
        模糊查找函数

        Args:
            pattern: 函数名模式

        Returns:
            匹配的函数列表
        """
        if 'FUNCTION' not in self.entities:
            return []

        results = []
        for name, func in self.entities['FUNCTION'].items():
            if pattern.lower() in name.lower():
                # 添加 file 字段
                func_copy = func.copy()
                if 'file' not in func_copy and 'source_file' in func_copy:
                    func_copy['file'] = func_copy['source_file']
                results.append(func_copy)
                if len(results) >= 10:  # 限制返回数量
                    break

        return results
    
    def get_function_code(self, func_name: str) -> Optional[str]:
        """
        获取函数代码
        
        Args:
            func_name: 函数名
            
        Returns:
            函数代码字符串
        """
        func = self.find_function(func_name)
        if not func:
            return None
        
        return func.get('code') or func.get('body')
    
    # ============ 调用关系查询 ============
    
    def has_direct_call(self, caller: str, callee: str) -> bool:
        """
        检查两个函数之间是否有直接CALLS关系

        Args:
            caller: 调用者函数名
            callee: 被调用者函数名

        Returns:
            是否存在直接调用关系
        """
        if 'CALLS' not in self.relations:
            return False

        # 先获取两个函数的实体（带id）
        caller_entity = self.find_function(caller)
        callee_entity = self.find_function(callee)

        if not caller_entity or not callee_entity:
            return False

        caller_id = caller_entity.get('id')
        callee_id = callee_entity.get('id')

        if not caller_id or not callee_id:
            return False

        for rel in self.relations['CALLS']:
            # 关系中使用 head/tail 字段，存储的是 id
            head = rel.get('head')
            tail = rel.get('tail')

            if head == caller_id and tail == callee_id:
                return True

        return False
    
    def find_call_path(self, start: str, end: str, max_depth: int = 10) -> Optional[List[str]]:
        """
        查找两个函数之间的调用路径（BFS搜索）

        Args:
            start: 起始函数名
            end: 目标函数名
            max_depth: 最大搜索深度

        Returns:
            调用路径（函数名列表），如果不存在返回None
        """
        if 'CALLS' not in self.relations:
            return None

        # 获取起点和终点的实体（带id）
        start_entity = self.find_function(start)
        end_entity = self.find_function(end)

        if not start_entity or not end_entity:
            return None

        start_id = start_entity.get('id')
        end_id = end_entity.get('id')

        if not start_id or not end_id:
            return None

        # 构建邻接表（使用id）
        graph = {}
        for rel in self.relations['CALLS']:
            head = rel.get('head')  # caller id
            tail = rel.get('tail')  # callee id

            if head and tail:
                if head not in graph:
                    graph[head] = []
                graph[head].append(tail)

        # BFS搜索（使用id）
        from collections import deque

        queue = deque([(start_id, [start_id])])
        visited = {start_id}

        while queue:
            current_id, path_ids = queue.popleft()

            if len(path_ids) > max_depth:
                continue

            if current_id == end_id:
                # 将id路径转换为名字路径
                path_names = []
                for entity_id in path_ids:
                    entity = self.entity_by_id.get(entity_id)
                    if entity:
                        path_names.append(entity['name'])
                return path_names

            if current_id in graph:
                for neighbor_id in graph[current_id]:
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        queue.append((neighbor_id, path_ids + [neighbor_id]))

        return None

    def _find_indirect_callees(self, func_name: str) -> List[tuple]:
        """
        查找函数的间接调用目标

        注意：此方法已废弃。间接调用现在直接从图谱的 CALLS 关系获取（在 _get_callees_with_lines 中）。
        保留此方法仅用于向后兼容，但应该使用新的 find_top_k_call_paths_with_indirect 方法。

        Args:
            func_name: 函数名

        Returns:
            间接调用列表，每项为 (目标函数名, 桥接信息)
        """
        # 不再使用LLM预处理缓存，因为图谱中已经包含间接调用关系
        # if self.enable_llm_detection and func_name in self.llm_indirect_call_cache:
        #     llm_callees = self.llm_indirect_call_cache[func_name]
        #     if llm_callees:
        #         logger.debug(f"函数 {func_name} 使用LLM检测结果: {len(llm_callees)} 个间接调用")
        #         return llm_callees

        # 没有找到间接调用
        return []

    def _detect_async_call(self, caller_name: str, callee_name: str) -> List[tuple]:
        """
        检测异步调用关系

        流程：
        1. 检查缓存
        2. LLM分析 caller 的源码，提取调用 callee 时的参数字段
        3. 查询 ASSIGNED_TO
        4. 缓存结果

        Args:
            caller_name: 调用者函数名（如 _mmc_detect_change）
            callee_name: 被调用者函数名（如 mmc_schedule_delayed_work）

        Returns:
            [(async_target, bridge_info), ...]
        """
        logger.info(f"🔍 检测到异步调用: {caller_name} -> {callee_name}")

        # 1. 检查缓存
        cache_key = (caller_name, callee_name)
        if cache_key in self.async_call_cache:
            cached_targets = self.async_call_cache[cache_key]
            logger.info(f"  ✓ 使用缓存结果: 找到 {len(cached_targets)} 个异步目标")
            for target_name, _ in cached_targets:
                logger.info(f"    → {target_name}")
            return cached_targets

        # 2. 获取 caller 的源码
        logger.info(f"  📖 读取 {caller_name} 的源码...")
        caller_source = self._get_function_source(caller_name)
        if not caller_source:
            logger.warning(f"  ✗ 无法获取源码，跳过异步调用检测")
            self.async_call_cache[cache_key] = []
            return []

        logger.info(f"  ✓ 源码读取成功 (长度: {len(caller_source)} 字符)")

        # 3. LLM提取参数字段名（如果启用LLM）
        field_name = None
        if self.enable_llm_detection:
            logger.info(f"  🤖 使用 LLM 分析源码，提取参数字段名...")
            field_name = self._llm_extract_async_parameter(caller_name, callee_name, caller_source)
            if field_name:
                logger.info(f"  ✓ LLM 提取成功: 字段名 = '{field_name}'")

        # 4. 如果 LLM 未提取到字段名，尝试使用常见模式
        if not field_name:
            logger.info(f"  🔎 使用正则表达式提取参数字段名...")
            # 尝试从源码中用简单正则提取
            import re
            # 匹配模式：schedule_*(&xxx->field) 或 schedule_*(&field)
            match = re.search(rf'{re.escape(callee_name)}\s*\(\s*&\w*->(\w+)', caller_source)
            if match:
                field_name = match.group(1)
                logger.info(f"  ✓ 正则提取成功: 字段名 = '{field_name}' (模式: &xxx->{field_name})")
            else:
                # 尝试匹配 schedule_*(&field)
                match = re.search(rf'{re.escape(callee_name)}\s*\(\s*&(\w+)', caller_source)
                if match:
                    field_name = match.group(1)
                    logger.info(f"  ✓ 正则提取成功: 字段名 = '{field_name}' (模式: &{field_name})")
                else:
                    logger.warning(f"  ✗ 正则提取失败，未找到参数字段")

        # 5. 如果还是没有，尝试 Mock 数据
        async_targets = []
        if field_name:
            logger.info(f"  🔗 查询 MOUNTED_TO/ASSIGNED_TO 关系: 字段名 = '{field_name}'")
            async_targets = self._query_assigned_to_for_async(field_name)

            if async_targets:
                logger.info(f"  ✓ 找到 {len(async_targets)} 个异步目标函数:")
                for target_name, bridge_info in async_targets:
                    logger.info(f"    → {target_name} (method={bridge_info.get('method', 'unknown')})")
            else:
                logger.warning(f"  ✗ 未找到异步目标函数")
        else:
            logger.warning(f"  ✗ 未提取到字段名，无法查询异步目标")

        # 6. 缓存结果
        self.async_call_cache[cache_key] = async_targets
        return async_targets

    def _remap_path(self, path: str) -> str:
        """
        应用路径映射，将图谱中的路径转换为当前环境的路径

        Args:
            path: 原始路径

        Returns:
            重映射后的路径
        """
        if not self.path_mappings:
            return path

        # 尝试每个映射规则
        for old_prefix, new_prefix in self.path_mappings.items():
            # 处理 Windows 路径分隔符
            normalized_path = path.replace('\\', '/')
            normalized_old = old_prefix.replace('\\', '/')

            if normalized_path.startswith(normalized_old):
                # 替换前缀
                relative_part = normalized_path[len(normalized_old):]
                remapped = new_prefix + relative_part
                logger.debug(f"路径映射: {path} -> {remapped}")
                return remapped

        return path

    def _get_function_source(self, func_name: str) -> Optional[str]:
        """
        获取函数源代码

        Args:
            func_name: 函数名

        Returns:
            函数源代码，失败返回None
        """
        # 获取所有同名函数ID
        all_func_ids = self.func_name_to_ids.get(func_name, [])
        if not all_func_ids:
            return None

        # 优先选择实现（非声明）
        func_entity = None
        for func_id in all_func_ids:
            entity = self.entity_by_id.get(func_id)
            if not entity:
                continue

            is_decl = entity.get('is_declaration', False)
            if not is_decl:
                func_entity = entity
                break

        # 如果没有实现，使用第一个
        if not func_entity and all_func_ids:
            func_entity = self.entity_by_id.get(all_func_ids[0])

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
                # 应用路径映射
                remapped_file = self._remap_path(source_file)

                try:
                    with open(remapped_file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        source_code = ''.join(lines[start_line-1:end_line])
                except Exception as e:
                    logger.debug(f"读取源文件失败 ({remapped_file}): {e}")
                    return None

        return source_code

    def _llm_extract_async_parameter(self, caller_name: str, callee_name: str, caller_source: str) -> Optional[str]:
        """
        LLM分析调用者源码，提取work字段名

        Args:
            caller_name: 调用者函数名
            callee_name: 被调用者函数名
            caller_source: 调用者源代码

        Returns:
            字段名（如 'detect'），如果未找到则返回 None
        """
        # 使用统一的LLM客户端
        if not self.llm_client or not self.llm_client.is_available():
            logger.debug("LLM客户端不可用，无法提取异步参数")
            return None

        try:
            field_name = self.llm_client.extract_async_parameter(
                caller_name, callee_name, caller_source
            )
            return field_name

        except Exception as e:
            logger.error(f"LLM提取参数失败: {e}")
            return None

    def _query_assigned_to_for_async(self, field_name: str) -> List[tuple]:
        """
        查询哪些函数被赋值给指定字段（异步调用）

        处理同名实体问题：
        1. 找到所有名为 field_name 的 FIELD 实体
        2. 查询 ASSIGNED_TO 关系（head=field_id, tail=function_id）
        3. 返回 target 函数列表

        Args:
            field_name: 字段名

        Returns:
            [(target_func, bridge_info), ...]
        """
        logger.info(f"    🔍 查找字段 '{field_name}' 的 FIELD 实体...")

        # 先尝试图谱查询
        # 1. 找到所有名为 field_name 的 FIELD 实体
        field_ids = []

        # 方法1：从 entities['FIELD'] 中查询（如果有的话）
        field_entities = self.entities.get('FIELD', {})
        if field_entities:
            # entities['FIELD'] 是 {name: entity} 的字典
            # 但可能有同名字段，所以需要遍历
            for name, entity in field_entities.items():
                if name == field_name:
                    field_id = entity.get('id')
                    if field_id:
                        field_ids.append(field_id)

        # 方法2：如果方法1没找到，遍历 entity_by_id（处理同名情况）
        if not field_ids:
            for entity_id, entity in self.entity_by_id.items():
                # 检查是否是 FIELD 类型
                entity_type = entity.get('type') or entity.get('entity_type') or entity.get('kind')
                entity_name = entity.get('name')

                if entity_type == 'FIELD' and entity_name == field_name:
                    field_ids.append(entity_id)

        if not field_ids:
            logger.warning(f"    ✗ 未找到名为 '{field_name}' 的 FIELD 实体")
            return []
        else:
            logger.info(f"    ✓ 找到 {len(field_ids)} 个名为 '{field_name}' 的 FIELD 实体")
            for fid in field_ids[:3]:  # 最多显示3个
                logger.info(f"      - Field ID: {fid}")

        # 2. 构建 field_id 集合用于快速查询
        field_id_set = set(field_ids)

        # 3. 查询 ASSIGNED_TO 和 MOUNTED_TO 关系
        logger.info(f"    🔗 查询 MOUNTED_TO/ASSIGNED_TO 关系...")
        field_to_func_relations = []
        assigned_to_relations = self.relations.get('ASSIGNED_TO', [])
        mounted_to_relations = self.relations.get('MOUNTED_TO', [])
        field_to_func_relations.extend(assigned_to_relations)
        field_to_func_relations.extend(mounted_to_relations)

        logger.info(f"    📊 图谱中共有 {len(assigned_to_relations)} 条 ASSIGNED_TO 关系")
        logger.info(f"    📊 图谱中共有 {len(mounted_to_relations)} 条 MOUNTED_TO 关系")

        target_function_ids = []
        matched_relations = []

        for rel in field_to_func_relations:
            head_id = rel.get('head')
            tail_id = rel.get('tail')

            # ASSIGNED_TO/MOUNTED_TO: head=FIELD_ID, tail=FUNCTION_ID
            if head_id in field_id_set:
                target_function_ids.append(tail_id)
                rel_type = rel.get('type', 'ASSIGNED_TO')
                matched_relations.append((rel_type, head_id, tail_id))

        if not target_function_ids:
            logger.warning(f"    ✗ 未找到字段 '{field_name}' 的 MOUNTED_TO/ASSIGNED_TO 关系")
            return []
        else:
            logger.info(f"    ✓ 找到 {len(target_function_ids)} 个匹配的关系:")
            for rel_type, head_id, tail_id in matched_relations[:5]:  # 最多显示5个
                logger.info(f"      - {rel_type}: {head_id} → {tail_id}")

        # 4. 获取目标函数名
        logger.info(f"    📝 解析目标函数名...")
        targets = []
        for func_id in target_function_ids:
            func_entity = self.entity_by_id.get(func_id)
            if func_entity:
                target_func_name = func_entity.get('name')
                targets.append((
                    target_func_name,
                    {
                        'bridge_type': 'async',
                        'bridge_entity': field_name,
                        'init_func': 'INIT_DELAYED_WORK',
                        'method': 'llm_analysis'
                    }
                ))
                logger.info(f"      - 函数 ID {func_id} → {target_func_name}")

        if targets:
            target_names = [t[0] for t in targets]
            logger.info(f"    ✅ 成功找到 {len(targets)} 个异步目标函数: {target_names}")

        return targets

    def preprocess_llm_indirect_calls(self, config_file: str = None):
        """
        预处理：使用LLM检测配置中指定的函数的间接调用
        同时识别异步函数列表

        Args:
            config_file: 配置文件路径（YAML格式）
                        如果为None，使用默认配置文件
        """
        if not self.enable_llm_detection:
            logger.warning("LLM检测未启用，跳过预处理")
            return

        # 加载配置
        if config_file is None:
            config_file = Path(__file__).parent.parent / 'config' / 'indirect_call_detection.yaml'

        if not Path(config_file).exists():
            logger.warning(f"配置文件不存在: {config_file}")
            return

        import yaml
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # ========== 1. 函数指针检测（已有） ==========
        func_names = config.get('functions_need_llm_detection', [])
        if func_names:
            logger.info(f"开始预处理 {len(func_names)} 个函数的间接调用...")

            # 导入LLM检测器
            from utils.llm_indirect_call_detector import preprocess_indirect_calls

            # 批量检测
            self.llm_indirect_call_cache = preprocess_indirect_calls(
                kg_interface=self,
                func_names=func_names
            )

            logger.info(f"函数指针检测完成！缓存了 {sum(len(v) for v in self.llm_indirect_call_cache.values())} 条间接调用关系")

        # ========== 2. 异步函数识别（新增） ==========
        async_config = config.get('async_call_detection', {})
        keywords = async_config.get('keywords', [])
        known_funcs = async_config.get('known_async_functions', [])

        # 添加显式配置的异步函数
        self.async_functions = set(known_funcs)

        # 基于关键字扫描图谱中的所有函数
        if keywords:
            logger.info(f"扫描图谱中匹配异步关键字的函数...")
            keyword_matched = 0
            for func_name in self.entities.get('FUNCTION', {}).keys():
                func_name_lower = func_name.lower()
                if any(kw in func_name_lower for kw in keywords):
                    self.async_functions.add(func_name)
                    keyword_matched += 1

            logger.info(f"异步函数识别完成！共识别 {len(self.async_functions)} 个异步函数")
            logger.info(f"  - 显式配置: {len(known_funcs)} 个")
            logger.info(f"  - 关键字匹配: {keyword_matched} 个")

    def find_call_path_with_indirect(self, start: str, end: str, max_depth: int = 10, debug: bool = False) -> Optional[Dict]:
        """
        查找调用路径（支持间接调用）

        Args:
            start: 起始函数名
            end: 目标函数名
            max_depth: 最大搜索深度
            debug: 是否输出调试信息

        Returns:
            包含路径和边类型信息的字典，如果不存在返回None
            {
                'path': [函数名列表],
                'edges': [边类型列表], # 'direct' 或 {'type': 'indirect', 'bridge': ...}
            }
        """
        if debug:
            print(f"\n{'='*80}")
            print(f"🔍 开始扩展BFS搜索")
            print(f"{'='*80}")
            print(f"起点: {start}")
            print(f"终点: {end}")
            print(f"最大深度: {max_depth}")

        # 获取起点和终点的实体
        start_entity = self.find_function(start)
        end_entity = self.find_function(end)

        if not start_entity or not end_entity:
            if debug:
                print(f"❌ 起点或终点不存在!")
                print(f"   起点存在: {start_entity is not None}")
                print(f"   终点存在: {end_entity is not None}")
            return None

        start_id = start_entity.get('id')
        end_id = end_entity.get('id')

        if not start_id or not end_id:
            if debug:
                print(f"❌ 起点或终点没有ID!")
                print(f"   start_id: {start_id}")
                print(f"   end_id: {end_id}")
            return None

        # 标准化为实现ID
        orig_start_id = start_id
        orig_end_id = end_id
        start_id = self.normalize_id(start_id)
        end_id = self.normalize_id(end_id)

        if debug:
            print(f"\n📌 ID信息:")
            print(f"   起点ID: {orig_start_id} -> {start_id}")
            print(f"   终点ID: {orig_end_id} -> {end_id}")

        # 获取终点的等价ID集合
        end_equivalent_ids = self.get_equivalent_ids(end_id)
        if debug:
            print(f"   终点等价ID: {end_equivalent_ids}")
            print()

        # BFS搜索（支持间接调用）
        from collections import deque

        queue = deque([(start_id, [start_id], [])])  # (当前id, 路径ids, 边类型)
        visited = {start_id}

        nodes_explored = 0
        max_queue_size = 0

        while queue:
            nodes_explored += 1
            max_queue_size = max(max_queue_size, len(queue))

            current_id, path_ids, edge_types = queue.popleft()

            if len(path_ids) > max_depth:
                continue

            # 检查是否到达终点（使用等价ID集合）
            if current_id in end_equivalent_ids:
                # 将id路径转换为名字路径
                path_names = []
                for entity_id in path_ids:
                    entity = self.entity_by_id.get(entity_id)
                    if entity:
                        path_names.append(entity['name'])

                if debug:
                    print(f"\n{'='*80}")
                    print(f"✅ 找到路径！")
                    print(f"{'='*80}")
                    print(f"📊 搜索统计:")
                    print(f"   总探索节点: {nodes_explored}")
                    print(f"   最大队列大小: {max_queue_size}")
                    print(f"   路径长度: {len(path_names)}")
                    print(f"{'='*80}\n")

                return {
                    'path': path_names,
                    'edges': edge_types
                }

            current_entity = self.entity_by_id.get(current_id)
            if not current_entity:
                continue

            current_name = current_entity['name']

            if debug and nodes_explored <= 20:  # 只输出前20个节点
                print(f"🔎 节点 #{nodes_explored}: {current_name} (深度 {len(path_ids)})")

            # 1. 获取直接调用的邻居
            direct_callees = self.get_callees(current_name, debug=(debug and nodes_explored <= 5))

            if debug and nodes_explored <= 20:
                print(f"   ├─ 直接调用: {len(direct_callees)} 个")

            for callee_name in direct_callees:
                callee_entity = self.find_function(callee_name)
                if not callee_entity:
                    continue

                callee_id = callee_entity.get('id')
                if not callee_id:
                    continue

                # 标准化ID
                callee_id = self.normalize_id(callee_id)
                if callee_id and callee_id not in visited:
                    visited.add(callee_id)
                    queue.append((
                        callee_id,
                        path_ids + [callee_id],
                        edge_types + ['direct']
                    ))

            # 2. 获取间接调用的邻居
            indirect_callees = self._find_indirect_callees(current_name)

            if debug and nodes_explored <= 20:
                print(f"   └─ 间接调用: {len(indirect_callees)} 个")
                if indirect_callees:
                    for callee_name, bridge_info in indirect_callees:
                        print(f"      ➜ {callee_name} ({bridge_info.get('bridge_type', 'unknown')})")

            for callee_name, bridge_info in indirect_callees:
                callee_entity = self.find_function(callee_name)
                if not callee_entity:
                    continue

                callee_id = callee_entity.get('id')
                if not callee_id:
                    continue

                # 标准化ID
                callee_id = self.normalize_id(callee_id)
                if callee_id and callee_id not in visited:
                    visited.add(callee_id)
                    queue.append((
                        callee_id,
                        path_ids + [callee_id],
                        edge_types + [{'type': 'indirect', 'bridge': bridge_info}]
                    ))

        # 搜索失败
        if debug:
            print(f"\n{'='*80}")
            print(f"❌ 搜索失败，未找到路径")
            print(f"{'='*80}")
            print(f"📊 搜索统计:")
            print(f"   总探索节点: {nodes_explored}")
            print(f"   最大队列大小: {max_queue_size}")
            print(f"   访问节点总数: {len(visited)}")
            print(f"{'='*80}\n")

        return None

    def find_top_k_call_paths_with_indirect(
        self,
        start: str,
        end: str,
        max_depth: int = 30,
        k: int = 5,
        error_line: Optional[int] = None,
        debug: bool = False
    ) -> List[Dict]:
        """
        查找Top-K条调用路径（支持间接调用和call_line排序）

        Args:
            start: 起始函数名
            end: 目标函数名
            max_depth: 最大搜索深度
            k: 返回路径数量上限
            error_line: 已废弃（保留用于兼容性，不再用于剪枝）
            debug: 是否输出调试信息

        Returns:
            路径列表，每个路径包含 path, edges, score, avg_call_line 等信息
            路径按得分排序，得分考虑了路径长度、间接调用数量和平均调用行号
        """
        if debug:
            print(f"\n{'='*80}")
            print(f"🔍 开始Top-{k}路径搜索")
            print(f"{'='*80}")
            print(f"起点: {start}")
            print(f"终点: {end}")
            print(f"最大深度: {max_depth}")
            if error_line:
                print(f"注意: error_line参数已废弃 (传入值: {error_line})")

        # 获取终点的实体
        end_entity = self.find_function(end)
        if not end_entity:
            if debug:
                print(f"❌ 终点不存在!")
            return []

        end_id = end_entity.get('id')
        if not end_id:
            if debug:
                print(f"❌ 终点没有ID!")
            return []

        # 标准化终点为实现ID
        end_id = self.normalize_id(end_id)
        # 获取终点的等价ID集合
        end_equivalent_ids = self.get_equivalent_ids(end_id)

        # 获取起点函数的所有ID（支持多个实现）
        all_start_ids = self.func_name_to_ids.get(start, [])
        if not all_start_ids:
            if debug:
                print(f"❌ 起点不存在!")
            return []

        # 过滤出所有实现（非声明）
        start_impl_ids = []
        for func_id in all_start_ids:
            entity = self.entity_by_id.get(func_id)
            if entity and not entity.get('is_declaration', False):
                start_impl_ids.append(func_id)

        # 如果没有实现，使用所有ID（包括声明）
        if not start_impl_ids:
            start_impl_ids = all_start_ids

        # 标准化为实现ID
        start_impl_ids = [self.normalize_id(sid) for sid in start_impl_ids]

        if debug:
            print(f"\n📌 ID信息:")
            print(f"   起点函数名: {start}")
            print(f"   起点实现数量: {len(start_impl_ids)}")
            print(f"   起点IDs: {start_impl_ids}")
            print(f"   终点ID: {end_id}")
            print(f"   终点等价ID: {end_equivalent_ids}")

        # 对每个起点实现分别执行BFS搜索
        from collections import deque

        all_found_paths = []
        total_nodes_explored = 0
        total_max_queue_size = 0

        for start_idx, start_id in enumerate(start_impl_ids):
            if debug and len(start_impl_ids) > 1:
                start_entity = self.entity_by_id.get(start_id)
                start_info = f"{start_entity.get('name')}@{start_entity.get('source_file', 'unknown')}" if start_entity else str(start_id)
                print(f"\n🔄 BFS #{start_idx + 1}/{len(start_impl_ids)}: 起点 = {start_info}")

            # 队列元素：(当前id, 路径ids, 边类型, call_lines, 是否是间接调用目标)
            # is_indirect_target=True 表示该节点是通过间接调用到达的，后续只查找直接调用
            queue = deque([(start_id, [start_id], [], [], False)])
            # 改变visited的记录方式：记录 (node_id, path_length) 以支持找到多条路径
            visited_at_depth = {}  # {node_id: min_depth}

            found_paths = []
            nodes_explored = 0
            max_queue_size = 0

            while queue and len(found_paths) < k:
                nodes_explored += 1
                max_queue_size = max(max_queue_size, len(queue))

                current_id, path_ids, edge_types, call_lines, is_indirect_target = queue.popleft()
                current_depth = len(path_ids)

                if current_depth > max_depth:
                    continue

                # 检查是否到达终点
                if current_id in end_equivalent_ids:
                    # 将id路径转换为名字路径
                    path_names = []
                    for entity_id in path_ids:
                        entity = self.entity_by_id.get(entity_id)
                        if entity:
                            path_names.append(entity['name'])

                    # 计算路径得分
                    # 1. 越短越好（每个节点扣1分）
                    # 2. 间接调用越少越好（每个间接调用扣10分）
                    # 3. 调用发生得越早越好（call_line越小越好）
                    indirect_count = sum(1 for e in edge_types if isinstance(e, dict))

                    # 计算平均调用行号（忽略None值）
                    valid_call_lines = [cl for cl in call_lines if cl is not None]
                    avg_call_line = sum(valid_call_lines) / len(valid_call_lines) if valid_call_lines else 0

                    # 得分计算：基础分1000 - 路径长度 - 间接调用惩罚 - 调用行号惩罚
                    # 调用行号惩罚：平均行号除以100（让行号的影响小于间接调用）
                    score = 1000 - current_depth - indirect_count * 10 - avg_call_line / 100

                    found_paths.append({
                        'path': path_names,
                        'path_ids': path_ids,  # 添加 ID 列表，用于准确定位实体
                        'edges': edge_types,
                        'call_lines': call_lines,
                        'score': score,
                        'length': current_depth,
                        'indirect_count': indirect_count,
                        'avg_call_line': avg_call_line
                    })

                    if debug:
                        print(f"✅ 找到路径 #{len(found_paths)}: 长度={current_depth}, 间接调用={indirect_count}")

                    continue

                # 检查是否应该继续探索（允许多次访问但控制深度）
                if current_id in visited_at_depth:
                    if current_depth >= visited_at_depth[current_id] + 3:  # 允许深度差3以内的重复访问
                        continue
                visited_at_depth[current_id] = min(
                    visited_at_depth.get(current_id, float('inf')),
                    current_depth
                )

                current_entity = self.entity_by_id.get(current_id)
                if not current_entity:
                    continue

                current_name = current_entity['name']

                # 1. 获取调用的邻居（带行号）
                # 如果当前节点是间接调用的目标，只查找直接调用（allow_indirect=False）
                # 这样可以避免间接调用的递归爆炸
                allow_indirect_calls = not is_indirect_target
                callees = self._get_callees_with_lines(current_id, error_line, allow_indirect=allow_indirect_calls)

                for callee_name, callee_line, is_from_indirect in callees:
                    callee_entity = self.find_function(callee_name)
                    if not callee_entity:
                        continue

                    callee_id = callee_entity.get('id')
                    if not callee_id:
                        continue

                    callee_id = self.normalize_id(callee_id)
                    if not callee_id or callee_id in path_ids:  # 避免环路
                        continue

                    # 确定边的类型
                    if is_from_indirect:
                        edge_type = {'type': 'indirect', 'bridge': {'bridge_type': 'function_pointer'}}
                    else:
                        edge_type = 'direct'

                    # 添加到队列
                    # 如果是通过间接调用找到的函数，标记 is_indirect_target=True
                    # 这样该函数后续只会查找直接调用，避免递归爆炸
                    queue.append((
                        callee_id,
                        path_ids + [callee_id],
                        edge_types + [edge_type],
                        call_lines + [callee_line],
                        is_from_indirect  # 继承间接调用标记
                    ))

                    # 检查是否是异步调用函数（只在直接调用时检查）
                    if not is_from_indirect and callee_name in self.async_functions:
                        if debug:
                            print(f"  ⚡ 触发异步调用检测: {current_name} -> {callee_name}")

                        # 检测异步调用关系
                        async_targets = self._detect_async_call(current_name, callee_name)

                        if debug and async_targets:
                            print(f"  ✅ 找到 {len(async_targets)} 个异步目标，添加到搜索队列")

                        for async_target_name, bridge_info in async_targets:
                            async_target_entity = self.find_function(async_target_name)
                            if not async_target_entity:
                                if debug:
                                    print(f"    ⚠️  异步目标 {async_target_name} 未在图谱中找到，跳过")
                                continue

                            async_target_id = async_target_entity.get('id')
                            if not async_target_id:
                                continue

                            async_target_id = self.normalize_id(async_target_id)
                            # 注意：async_target 可能已经在 path 中（避免环路）
                            # 但 callee 一定不在 path 中（因为上面检查过了）
                            if not async_target_id or async_target_id in path_ids + [callee_id]:
                                if debug:
                                    print(f"    ⚠️  异步目标 {async_target_name} 已在路径中或无效，跳过")
                                continue

                            if debug:
                                print(f"    ➕ 添加异步路径: {current_name} -> {callee_name} --[async]--> {async_target_name}")
                                print(f"       桥接信息: {bridge_info.get('bridge_entity')} ({bridge_info.get('method')})")

                            # 添加异步调用边：current → callee → async_target
                            # 路径包含两个节点：callee 和 async_target
                            # 包含两条边：direct 和 async
                            # 异步调用的目标函数也标记为 is_indirect_target=True（避免继续递归）
                            queue.append((
                                async_target_id,
                                path_ids + [callee_id, async_target_id],
                                edge_types + ['direct', {'type': 'async', 'bridge': bridge_info}],
                                call_lines + [callee_line, None],  # 异步调用没有call_line
                                True  # 异步调用的目标也是间接目标，后续只查找直接调用
                            ))

            # 收集当前起点的所有路径
            all_found_paths.extend(found_paths)
            total_nodes_explored += nodes_explored
            total_max_queue_size = max(total_max_queue_size, max_queue_size)

            if debug and len(start_impl_ids) > 1:
                if found_paths:
                    print(f"   ✅ 从该起点找到 {len(found_paths)} 条路径")
                else:
                    print(f"   ❌ 从该起点未找到路径")

        # 合并所有起点的路径，按得分排序
        all_found_paths.sort(key=lambda x: x['score'], reverse=True)

        if debug:
            print(f"\n{'='*80}")
            if all_found_paths:
                print(f"✅ 总共找到 {len(all_found_paths)} 条路径")
            else:
                print(f"❌ 未找到路径")
            print(f"{'='*80}")
            print(f"📊 搜索统计:")
            print(f"   起点实现数量: {len(start_impl_ids)}")
            print(f"   总探索节点: {total_nodes_explored}")
            print(f"   最大队列大小: {total_max_queue_size}")
            print(f"{'='*80}\n")

        return all_found_paths[:k]

    def query_assigned_to_by_field_name(self, field_name: str) -> List[str]:
        """
        根据字段名查询 ASSIGNED_TO 关系，返回所有赋值目标函数

        处理流程：
        1. 遍历 entity_by_id，找到所有名为 field_name 的 FIELD 实体
        2. 查询这些 FIELD 的 ASSIGNED_TO 关系
        3. 返回所有目标函数名列表

        Args:
            field_name: 字段名（如 "execute_tuning"）

        Returns:
            函数名列表（可能为空）
        """
        # 1. 找到所有名为 field_name 的 FIELD 实体
        field_ids = []

        for entity_id, entity in self.entity_by_id.items():
            entity_type = entity.get('type')
            entity_name = entity.get('name')

            if entity_type == 'FIELD' and entity_name == field_name:
                field_ids.append(entity_id)

        if not field_ids:
            logger.debug(f"未找到名为 {field_name} 的 FIELD 实体")
            return []

        logger.debug(f"找到 {len(field_ids)} 个名为 {field_name} 的 FIELD 实体")

        # 2. 查询 ASSIGNED_TO 和 MOUNTED_TO 关系
        field_id_set = set(field_ids)
        target_function_names = []

        field_to_func_relations = []
        field_to_func_relations.extend(self.relations.get('ASSIGNED_TO', []))
        field_to_func_relations.extend(self.relations.get('MOUNTED_TO', []))

        for rel in field_to_func_relations:
            head_id = rel.get('head')
            tail_id = rel.get('tail')

            # ASSIGNED_TO/MOUNTED_TO: head=FIELD_ID, tail=FUNCTION_ID
            if head_id in field_id_set:
                # 获取目标函数名
                target_entity = self.entity_by_id.get(tail_id)
                if target_entity and target_entity.get('type') == 'FUNCTION':
                    target_name = target_entity.get('name')
                    if target_name:
                        target_function_names.append(target_name)
                        rel_type = rel.get('type', 'ASSIGNED_TO')
                        logger.debug(f"  匹配到 {rel_type}: {field_name} -> {target_name}")

        if target_function_names:
            logger.debug(f"✓ 字段 '{field_name}' 的 ASSIGNED_TO/MOUNTED_TO 目标: {target_function_names}")
        else:
            logger.debug(f"未找到字段 '{field_name}' 的 ASSIGNED_TO/MOUNTED_TO 关系")

        return list(set(target_function_names))  # 去重

    def _get_callees_with_lines(self, func_id: str, error_line: Optional[int] = None, allow_indirect: bool = True) -> List[Tuple[str, Optional[int], bool]]:
        """
        获取函数的被调用者及其调用行号（支持间接调用）

        Args:
            func_id: 函数ID
            error_line: 保留参数（为了兼容性），但不再用于剪枝
                       因为调用链是跨函数的，不同函数的行号不能直接比较
            allow_indirect: 是否允许查找间接调用（默认 True）
                           设为 False 时，只返回直接调用，用于避免间接调用的递归查询

        Returns:
            [(callee_name, call_line, is_from_indirect), ...] 的列表
            - callee_name: 被调用函数名
            - call_line: 调用行号（用于路径排序）
            - is_from_indirect: 是否是通过间接调用找到的（True 表示间接调用）

        注意：
            - 对于直接调用：is_from_indirect=False
            - 对于间接调用（函数指针）：查询 ASSIGNED_TO 关系，is_from_indirect=True
            - 如果 allow_indirect=False，跳过间接调用的查询
        """
        result = []

        # 获取等价ID
        equivalent_ids = self.get_equivalent_ids(func_id)

        # 遍历 CALLS 关系（而不是预构建的 call_graph_with_lines）
        # 因为我们需要检查 call_type 和 target_type
        if 'CALLS' not in self.relations:
            return []

        for rel in self.relations['CALLS']:
            head_id = rel.get('head')
            tail_id = rel.get('tail')

            # 检查是否是当前函数的调用
            if head_id not in equivalent_ids:
                continue

            call_line = rel.get('call_line')
            call_type = rel.get('call_type', 'direct')  # 默认是直接调用
            target_type = rel.get('target_type', 'FUNCTION')  # 默认目标是函数

            # ========== 直接调用 ==========
            if call_type == 'direct' or target_type == 'FUNCTION':
                # 标准化tail_id并查找名字
                callee_id_normalized = self.normalize_id(tail_id)
                callee_entity = self.entity_by_id.get(callee_id_normalized)

                if callee_entity and 'name' in callee_entity:
                    result.append((callee_entity['name'], call_line, False))  # False 表示直接调用

            # ========== 间接调用（函数指针） ==========
            elif call_type == 'indirect' and target_type == 'FIELD':
                # 如果不允许间接调用，跳过
                if not allow_indirect:
                    # 提前获取 field_path 用于日志
                    _field_path = rel.get('field_path', [])
                    _field_name = _field_path[-1] if _field_path else 'unknown'
                    logger.debug(f"跳过间接调用（allow_indirect=False）: {_field_name}")
                    continue

                # tail 指向 FIELD 实体
                field_entity = self.entity_by_id.get(tail_id)

                if not field_entity:
                    logger.warning(f"间接调用的 FIELD 实体不存在: {tail_id}")
                    continue

                # 获取字段名：优先使用 field_path 的最后一个元素
                field_path = rel.get('field_path', [])
                if field_path:
                    field_name = field_path[-1]  # 使用路径的最后一个元素
                else:
                    field_name = field_entity.get('name')  # fallback 到实体名称

                if not field_name:
                    logger.warning(f"无法获取字段名: field_entity={field_entity}")
                    continue

                logger.debug(f"检测到间接调用: field_name={field_name}, field_path={field_path}")

                # 查询 ASSIGNED_TO 关系
                candidate_functions = self.query_assigned_to_by_field_name(field_name)

                if candidate_functions:
                    # 将所有候选函数加入结果（过度近似策略）
                    for candidate_name in candidate_functions:
                        result.append((candidate_name, call_line, True))  # True 表示间接调用
                else:
                    # 如果图谱中没有找到，fallback 到 Mock 数据
                    logger.debug(f"图谱中未找到字段 '{field_name}' 的 ASSIGNED_TO，尝试 Mock 数据")
                    # TODO: 这里可以添加 Mock fallback 逻辑

        # 遍历 ioctl_call 关系（直接调用，格式简单，只有 head/tail）
        for rel in self.relations.get('ioctl_call', []):
            head_id = rel.get('head')
            tail_id = rel.get('tail')

            if head_id not in equivalent_ids:
                continue

            callee_id_normalized = self.normalize_id(tail_id)
            callee_entity = self.entity_by_id.get(callee_id_normalized)

            if callee_entity and 'name' in callee_entity:
                result.append((callee_entity['name'], None, False))  # ioctl_call 没有 call_line

        return result

    def find_reachable_from_start(self, start: str, max_depth: int = 10) -> Dict[str, List[str]]:
        """
        从起点出发，找到所有可达的函数及其路径

        Args:
            start: 起始函数名
            max_depth: 最大搜索深度

        Returns:
            {函数名: 到达该函数的路径}
        """
        start_entity = self.find_function(start)
        if not start_entity:
            return {}

        start_id = start_entity.get('id')
        if not start_id:
            return {}

        from collections import deque

        reachable = {start: [start]}
        queue = deque([(start_id, [start_id])])
        visited = {start_id}

        while queue:
            current_id, path_ids = queue.popleft()

            if len(path_ids) > max_depth:
                continue

            current_entity = self.entity_by_id.get(current_id)
            if not current_entity:
                continue

            current_name = current_entity['name']

            # 获取直接调用
            for callee_name in self.get_callees(current_name):
                callee_entity = self.find_function(callee_name)
                if not callee_entity:
                    continue

                callee_id = callee_entity.get('id')
                if callee_id and callee_id not in visited:
                    visited.add(callee_id)
                    new_path_ids = path_ids + [callee_id]
                    queue.append((callee_id, new_path_ids))

                    # 转换为名字路径
                    path_names = [self.entity_by_id[eid]['name'] for eid in new_path_ids if eid in self.entity_by_id]
                    reachable[callee_name] = path_names

        return reachable

    def find_reachable_to_end(self, end: str, max_depth: int = 10) -> Dict[str, List[str]]:
        """
        反向搜索：找到所有能到达终点的函数及其路径

        Args:
            end: 目标函数名
            max_depth: 最大搜索深度

        Returns:
            {函数名: 从该函数到终点的路径}
        """
        end_entity = self.find_function(end)
        if not end_entity:
            return {}

        end_id = end_entity.get('id')
        if not end_id:
            return {}

        from collections import deque

        reachable = {end: [end]}
        queue = deque([(end_id, [end_id])])
        visited = {end_id}

        while queue:
            current_id, path_ids = queue.popleft()

            if len(path_ids) > max_depth:
                continue

            current_entity = self.entity_by_id.get(current_id)
            if not current_entity:
                continue

            current_name = current_entity['name']

            # 获取调用者（反向）
            for caller_name in self.get_callers(current_name):
                caller_entity = self.find_function(caller_name)
                if not caller_entity:
                    continue

                caller_id = caller_entity.get('id')
                if caller_id and caller_id not in visited:
                    visited.add(caller_id)
                    new_path_ids = [caller_id] + path_ids
                    queue.append((caller_id, new_path_ids))

                    # 转换为名字路径
                    path_names = [self.entity_by_id[eid]['name'] for eid in new_path_ids if eid in self.entity_by_id]
                    reachable[caller_name] = path_names

        return reachable

    def get_all_paths(self, start: str, end: str, max_depth: int = 10, limit: int = 5) -> List[List[str]]:
        """
        获取所有可能的调用路径（DFS搜索）
        
        Args:
            start: 起始函数
            end: 目标函数
            max_depth: 最大深度
            limit: 最多返回路径数
            
        Returns:
            路径列表
        """
        if 'CALLS' not in self.relations:
            return []
        
        # 构建邻接表
        graph = {}
        for rel in self.relations['CALLS']:
            src = rel.get('source') or rel.get('from') or rel.get('caller')
            tgt = rel.get('target') or rel.get('to') or rel.get('callee')
            
            if src not in graph:
                graph[src] = []
            graph[src].append(tgt)
        
        # DFS查找所有路径
        all_paths = []
        
        def dfs(current, path, visited):
            if len(all_paths) >= limit:
                return
            
            if len(path) > max_depth:
                return
            
            if current == end:
                all_paths.append(path[:])
                return
            
            if current in graph:
                for neighbor in graph[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        path.append(neighbor)
                        dfs(neighbor, path, visited)
                        path.pop()
                        visited.remove(neighbor)
        
        dfs(start, [start], {start})
        
        return all_paths
    
    def get_callers(self, func_name: str) -> List[str]:
        """
        获取调用某函数的所有函数

        Args:
            func_name: 函数名

        Returns:
            调用者函数名列表
        """
        if 'CALLS' not in self.relations:
            return []

        # 获取该函数名的所有ID（包括声明和实现）
        all_func_ids = self.func_name_to_ids.get(func_name, [])

        if not all_func_ids:
            return []

        # 收集所有等价ID（同名函数的所有ID + 声明-实现映射）
        equivalent_ids = set()
        for func_id in all_func_ids:
            equivalent_ids.add(func_id)
            # 加上声明-实现映射的等价ID
            equivalent_ids.update(self.get_equivalent_ids(func_id))

        callers = []
        for rel in self.relations['CALLS']:
            head = rel.get('head')  # caller id
            tail = rel.get('tail')  # callee id

            # 检查 tail 是否是当前函数的等价ID之一
            if tail in equivalent_ids:
                # 标准化 head 并查找名字
                head_normalized = self.normalize_id(head)
                caller_entity = self.entity_by_id.get(head_normalized)
                if caller_entity and 'name' in caller_entity:
                    callers.append(caller_entity['name'])

        return list(set(callers))

    def get_callees(self, func_name: str, debug: bool = False) -> List[str]:
        """
        获取某函数调用的所有函数

        Args:
            func_name: 函数名
            debug: 是否输出调试信息

        Returns:
            被调用函数名列表
        """
        if 'CALLS' not in self.relations:
            return []

        # 获取该函数名的所有ID（包括声明和实现）
        all_func_ids = self.func_name_to_ids.get(func_name, [])

        if not all_func_ids:
            return []

        # 收集所有等价ID（同名函数的所有ID + 声明-实现映射）
        equivalent_ids = set()
        for func_id in all_func_ids:
            equivalent_ids.add(func_id)
            # 加上声明-实现映射的等价ID
            equivalent_ids.update(self.get_equivalent_ids(func_id))

        if debug:
            print(f"      [get_callees] {func_name}")
            print(f"         该名称的所有ID: {all_func_ids}")
            print(f"         等价ID集合: {equivalent_ids}")

        callees = []
        matched_count = 0
        for rel in self.relations['CALLS']:
            head = rel.get('head')  # caller id
            tail = rel.get('tail')  # callee id

            # 检查 head 是否是当前函数的等价ID之一
            if head in equivalent_ids:
                matched_count += 1
                # 标准化 tail 并查找名字
                tail_normalized = self.normalize_id(tail)
                callee_entity = self.entity_by_id.get(tail_normalized)
                if callee_entity and 'name' in callee_entity:
                    callees.append(callee_entity['name'])
                    if debug and matched_count <= 3:
                        print(f"         ✓ 找到调用: {callee_entity['name']}")

        if debug:
            print(f"         匹配的关系数: {matched_count}")
            print(f"         被调用函数: {len(callees)} 个")

        return list(set(callees))
    
    # ============ 断点修复相关查询 ============
    
    def check_async_pattern(self, node_a: str, node_b: str) -> Optional[Dict]:
        """
        检查异步调用模式（work_struct）

        Args:
            node_a: 起始函数
            node_b: 目标函数

        Returns:
            桥接信息，如果不存在返回None
        """
        # 首先尝试从真实图谱中查找
        # 查找 work_struct.func 指向 node_b 的关系
        field_to_func_relations = []
        field_to_func_relations.extend(self.relations.get('ASSIGNED_TO', []))
        field_to_func_relations.extend(self.relations.get('MOUNTED_TO', []))

        if field_to_func_relations:
            for rel in field_to_func_relations:
                src = rel.get('source') or rel.get('from')
                tgt = rel.get('target') or rel.get('to')

                # 检查是否是 work_struct 的 func 字段指向目标函数
                if tgt == node_b and 'func' in str(src).lower():
                    return {
                        'bridge_type': 'async',
                        'bridge_entity': 'work_struct.func',
                        'init_func': 'INIT_WORK/INIT_DELAYED_WORK'
                    }

        # 没有找到异步调用桥接
        return None
    
    def check_function_pointer_pattern(self, node_a: str, node_b: str) -> Optional[Dict]:
        """
        检查函数指针调用模式（ops表）

        Args:
            node_a: 起始函数
            node_b: 目标函数

        Returns:
            桥接信息，如果不存在返回None
        """
        # 首先尝试从真实图谱中查找
        # 查找 ops 相关的赋值
        field_to_func_relations = []
        field_to_func_relations.extend(self.relations.get('ASSIGNED_TO', []))
        field_to_func_relations.extend(self.relations.get('MOUNTED_TO', []))

        if field_to_func_relations:
            for rel in field_to_func_relations:
                src = rel.get('source') or rel.get('from')
                tgt = rel.get('target') or rel.get('to')

                # 检查是否是 ops 表字段指向目标函数
                if tgt == node_b and 'ops' in str(src).lower():
                    return {
                        'bridge_type': 'function_pointer',
                        'bridge_entity': src,
                        'ops_var': src
                    }

        # 没有找到函数指针桥接
        return None
    
    # ============ 上下文查询 ============
    
    def get_function_context(self, func_name: str) -> Dict[str, Any]:
        """
        获取函数的完整上下文信息
        
        Args:
            func_name: 函数名
            
        Returns:
            包含函数所有相关信息的字典
        """
        func_info = self.find_function(func_name)
        if not func_info:
            return {}
        
        return {
            'info': func_info,
            'code': self.get_function_code(func_name),
            'callers': self.get_callers(func_name),
            'callees': self.get_callees(func_name),
            'variables': self.get_function_variables(func_name),
            'related_structs': self.get_related_structs(func_name)
        }
    
    def get_function_variables(self, func_name: str) -> List[Dict]:
        """获取函数中使用的变量"""
        if 'CONTAINS' not in self.relations:
            return []
        
        variables = []
        for rel in self.relations['CONTAINS']:
            src = rel.get('source') or rel.get('from')
            tgt = rel.get('target') or rel.get('to')
            
            if src == func_name and 'Variable' in self.entities:
                var_info = self.entities['Variable'].get(tgt)
                if var_info:
                    variables.append(var_info)
        
        return variables
    
    def get_related_structs(self, func_name: str) -> List[str]:
        """获取函数相关的结构体"""
        variables = self.get_function_variables(func_name)
        
        if 'TYPE_OF' not in self.relations:
            return []
        
        struct_names = set()
        for var in variables:
            var_name = var.get('name')
            for rel in self.relations['TYPE_OF']:
                src = rel.get('source') or rel.get('from')
                tgt = rel.get('target') or rel.get('to')
                
                if src == var_name:
                    struct_names.add(tgt)
        
        return list(struct_names)
    
    # ============ LLM辅助定位需要的方法 ============

    def fuzzy_search_functions(self, keywords: List[str], max_results: int = 50) -> List[Dict]:
        """
        根据关键词模糊搜索函数

        Args:
            keywords: 关键词列表（如 ["tuning", "init", "mmc"]）
            max_results: 最多返回多少个结果

        Returns:
            匹配的函数列表 [{"name": "func", "source_file": "...", "score": 2}, ...]
            按匹配分数排序（分数=匹配的关键词数量）
        """
        if 'FUNCTION' not in self.entities:
            return []

        matches = []

        # 遍历所有函数
        for func_name, func_entity in self.entities['FUNCTION'].items():
            # 计算匹配分数：看有多少个关键词出现在函数名中
            score = 0
            func_name_lower = func_name.lower()

            for keyword in keywords:
                if keyword.lower() in func_name_lower:
                    score += 1

            # 如果至少匹配一个关键词，加入结果
            if score > 0:
                result = {
                    "name": func_name,
                    "score": score,
                    "id": func_entity.get('id')
                }
                # 添加source_file信息（如果有）
                if 'source_file' in func_entity:
                    result['source_file'] = func_entity['source_file']

                matches.append(result)

        # 按分数排序（分数高的在前）
        matches.sort(key=lambda x: x['score'], reverse=True)

        return matches[:max_results]

    def get_function_ids(self, func_name: str) -> List[str]:
        """
        获取函数名对应的所有ID（支持同名函数）

        Args:
            func_name: 函数名

        Returns:
            函数ID列表
        """
        return self.func_name_to_ids.get(func_name, [])

    def get_function_info(self, func_id: str) -> Optional[Dict]:
        """
        通过ID获取函数信息

        Args:
            func_id: 函数ID

        Returns:
            函数实体信息，如果不存在返回None
        """
        entity = self.entity_by_id.get(str(func_id))
        if entity and entity.get('type') == 'FUNCTION':
            return entity
        return None

    def get_function_name(self, func_id: str) -> Optional[str]:
        """
        通过ID获取函数名

        Args:
            func_id: 函数ID

        Returns:
            函数名，如果不存在返回None
        """
        entity = self.entity_by_id.get(str(func_id))
        if entity:
            return entity.get('name')
        return None

    # ============ 统计信息 ============

    def get_call_frequency(self, func_name: str) -> int:
        """获取函数被调用的次数"""
        return len(self.get_callers(func_name))
    
    def get_database_stats(self) -> Dict[str, int]:
        """获取图谱统计信息"""
        stats = {}
        
        # 统计实体
        for entity_type, entities in self.entities.items():
            stats[entity_type] = len(entities)
        
        # 统计关系
        for rel_type, relations in self.relations.items():
            stats[rel_type] = len(relations)
        
        return stats


# 便捷函数：创建知识图谱接口
def create_kg_interface(data_dir: str = None) -> KnowledgeGraphInterface:
    """
    创建知识图谱接口实例

    Args:
        data_dir: 数据文件目录，如果为None则从环境变量读取

    Returns:
        KnowledgeGraphInterface实例
    """
    return KnowledgeGraphInterface(data_dir)
