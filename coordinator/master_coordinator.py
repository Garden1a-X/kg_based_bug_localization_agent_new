"""
主协调器
协调所有Agent完成Bug定位任务
"""
from typing import Dict, Optional, List
from pathlib import Path
from data.kg_interface import KnowledgeGraphInterface
from agents.log_parser_agent import LogParserAgent
from agents.entity_locator_agent import EntityLocatorAgent
from agents.chain_tracer_agent import CallChainTracerAgent
from llm import LLMClient
from utils.subgraph_selector import SubgraphSelector
from config.subgraph_metadata import SUBGRAPH_METADATA
from config.entry_points import get_candidate_entries_for_subgraph, suggest_entry_by_platform
from utils.logger import logger, print_header, print_step, print_success, print_error, print_panel
from rich.console import Console
from rich.table import Table

console = Console()


class MasterCoordinator:
    """主协调器"""

    def __init__(
        self,
        data_dir: str = None,
        llm_client: Optional[LLMClient] = None,
        enable_llm_detection: bool = False,
        enable_llm_log_analysis: bool = False,
        enable_subgraph_selection: bool = False,
        llm_config: Optional[Dict] = None
    ):
        """
        初始化协调器

        Args:
            data_dir: 数据文件目录
            llm_client: LLM客户端（可选，如果不提供则根据配置自动创建）
            enable_llm_detection: 是否启用LLM辅助间接调用检测（运行时）
            enable_llm_log_analysis: 是否启用LLM辅助日志分析
            enable_subgraph_selection: 是否启用子图自动选择
            llm_config: LLM配置（如果需要自动创建LLM客户端）
                例如: {'backend': 'openai', 'model': 'gpt-4o-mini', 'base_url': '...'}
        """
        logger.info("初始化主协调器...")

        # 保存配置
        self.base_data_dir = data_dir
        self.enable_subgraph_selection = enable_subgraph_selection

        # 如果需要LLM但没有提供客户端，则创建统一的LLM客户端
        if (enable_llm_detection or enable_llm_log_analysis or enable_subgraph_selection) and llm_client is None:
            if llm_config is None:
                # 使用默认配置
                llm_config = {
                    'backend': 'openai',
                    'model': 'gpt-4o-mini',
                    'base_url': 'http://10.12.208.86:8502',
                    'api_key': ''
                }

            logger.info("创建统一的LLM客户端...")
            llm_client = LLMClient(**llm_config)

            if llm_client.is_available():
                logger.success(f"LLM客户端初始化成功: {llm_client.get_backend_info()}")
            else:
                logger.warning("LLM客户端初始化失败，将禁用LLM功能")
                llm_client = None

        self.llm_client = llm_client

        # 如果启用子图选择，创建SubgraphSelector
        self.subgraph_selector = None
        if enable_subgraph_selection:
            self.subgraph_selector = SubgraphSelector(
                llm_client=llm_client,
                base_data_dir=data_dir,
                subgraph_metadata=SUBGRAPH_METADATA
            )
            logger.info(f"子图选择器已启用，发现 {len(self.subgraph_selector.available_subgraphs)} 个子图")

        # 创建知识图谱接口（传入LLM客户端）
        # 注意：如果启用子图选择，这里可能会在process时重新初始化
        self.kg = KnowledgeGraphInterface(
            data_dir,
            enable_llm_detection=enable_llm_detection,
            llm_client=llm_client
        )

        # 注意：不再需要LLM预处理，因为图谱中已经包含了间接调用结构（CALLS + ASSIGNED_TO）
        # LLM只在运行时用于分析delayed work的间接调用（_detect_async_call）

        # 创建各个Agent（传入LLM客户端和KG接口）
        self.log_parser = LogParserAgent(
            enable_llm=enable_llm_log_analysis,
            llm_client=llm_client,
            kg_interface=self.kg
        )
        self.entity_locator = EntityLocatorAgent(self.kg)
        self.chain_tracer = CallChainTracerAgent(self.kg, llm_client)

        # 保存enable_llm_detection以便重新初始化时使用
        self.enable_llm_detection = enable_llm_detection

        logger.success("协调器初始化完成")
    
    def process(self, log_text: str, subgraph_override: Optional[str] = None) -> Dict:
        """
        处理错误日志，进行bug定位

        Args:
            log_text: 错误日志文本
            subgraph_override: 手动指定子图（可选），如果提供则跳过自动选择

        Returns:
            分析结果
        """
        print_header("Bug定位分析流程")

        # 第0步（可选）：子图选择
        selected_subgraph = None
        if self.enable_subgraph_selection and self.subgraph_selector:
            if subgraph_override:
                # 手动指定子图
                selected_subgraph = subgraph_override
                logger.info(f"使用手动指定的子图: {selected_subgraph}")

                # 获取子图路径并重新加载KG
                subgraph_path = self.subgraph_selector.get_subgraph_path(selected_subgraph)
                if subgraph_path:
                    logger.info(f"使用子图数据: {subgraph_path}")

                    # 重新初始化知识图谱接口，使用选中的子图
                    self.kg = KnowledgeGraphInterface(
                        str(subgraph_path),
                        enable_llm_detection=self.enable_llm_detection,
                        llm_client=self.llm_client
                    )

                    # 重新初始化依赖KG的Agent
                    self.entity_locator = EntityLocatorAgent(self.kg)
                    self.chain_tracer = CallChainTracerAgent(self.kg, self.llm_client)
                    self.log_parser = LogParserAgent(
                        enable_llm=self.enable_llm_log_analysis,
                        llm_client=self.llm_client,
                        kg_interface=self.kg
                    )

                    # DEBUG: 打印切换后的状态
                    logger.info(f"[DEBUG] 切换子图后: self.kg 实例 ID = {id(self.kg)}")
                    logger.info(f"[DEBUG] 切换子图后: self.log_parser.kg 实例 ID = {id(self.log_parser.kg)}")
                    logger.info(f"[DEBUG] 切换子图后: self.kg.entity_by_id 有 {len(self.kg.entity_by_id)} 个实体")

                    print_success(f"已切换到子图: {selected_subgraph}")
                else:
                    logger.warning(f"子图路径不存在: {selected_subgraph}，使用默认图谱")
            else:
                # 自动选择子图
                print_step(1, 5, "选择相关子图")
                selected_subgraphs = self.subgraph_selector.select_by_log(log_text, top_k=1)

                if selected_subgraphs:
                    selected_subgraph = selected_subgraphs[0]
                    logger.info(f"LLM选择的子图: {selected_subgraph}")

                    # 获取子图路径
                    subgraph_path = self.subgraph_selector.get_subgraph_path(selected_subgraph)
                    if subgraph_path:
                        logger.info(f"使用子图数据: {subgraph_path}")

                        # 重新初始化知识图谱接口，使用选中的子图
                        self.kg = KnowledgeGraphInterface(
                            str(subgraph_path),
                            enable_llm_detection=self.enable_llm_detection,
                            llm_client=self.llm_client
                        )

                        # 重新初始化依赖KG的Agent
                        self.entity_locator = EntityLocatorAgent(self.kg)
                        self.chain_tracer = CallChainTracerAgent(self.kg, self.llm_client)
                        self.log_parser = LogParserAgent(
                            enable_llm=self.enable_llm_log_analysis,
                            llm_client=self.llm_client,
                            kg_interface=self.kg
                        )

                        # DEBUG: 打印切换后的状态
                        logger.info(f"[DEBUG] 切换子图后: self.kg 实例 ID = {id(self.kg)}")
                        logger.info(f"[DEBUG] 切换子图后: self.log_parser.kg 实例 ID = {id(self.log_parser.kg)}")
                        logger.info(f"[DEBUG] 切换子图后: self.kg.entity_by_id 有 {len(self.kg.entity_by_id)} 个实体")

                        print_success(f"已切换到子图: {selected_subgraph}")
                    else:
                        logger.warning(f"子图路径不存在: {selected_subgraph}，使用默认图谱")
                else:
                    logger.warning("未选择到子图，使用默认图谱")

        # 调整步骤编号（如果启用了子图选择）
        step_offset = 1 if (self.enable_subgraph_selection and not subgraph_override) else 0
        total_steps = 5 if step_offset else 4

        # 第1步：日志解析
        print_step(1 + step_offset, total_steps, "解析错误日志")
        # 使用增强的日志解析（支持 FAIL_MESSAGE 匹配）
        parsed_log = self.log_parser.parse_log(log_text)
        self._display_parsed_log(parsed_log)

        # 第2步：实体定位
        print_step(2 + step_offset, total_steps, "在图谱中定位实体")
        entities = self.entity_locator.execute(parsed_log)
        self._display_entities(entities)
        
        # 检查是否找到起点和终点
        if not entities['start_entity'] or not entities['end_entity']:
            print_error("无法定位起点或终点，分析终止")
            return {
                'success': False,
                'parsed_log': parsed_log,
                'entities': entities,
                'error': '无法定位起点或终点'
            }
        
        # 第3步：调用链追踪
        print_step(3 + step_offset, total_steps, "追踪调用链")
        chain_result = self.chain_tracer.execute(
            entities['start_entity'],
            entities['end_entity']
        )
        self._display_chain(chain_result)

        # 第4步：生成报告
        print_step(4 + step_offset, total_steps, "生成分析报告")
        report = self._generate_report(parsed_log, entities, chain_result)
        
        print_success("分析完成！")
        
        return report
    
    def process_with_specific_functions(self, log_text: str, 
                                       start_func: str, end_func: str) -> Dict:
        """
        处理错误日志，使用指定的起点和终点
        
        Args:
            log_text: 错误日志文本
            start_func: 起点函数名
            end_func: 终点函数名
            
        Returns:
            分析结果
        """
        print_header("Bug定位分析流程（指定起止点）")
        
        # 第1步：日志解析
        print_step(1, 3, "解析错误日志")
        parsed_log = self.log_parser.execute(log_text)
        
        # 第2步：定位指定函数
        print_step(2, 3, "定位指定函数")
        entities = self.entity_locator.locate_specific(start_func, end_func)
        self._display_entities(entities)
        
        if not entities['start_entity'] or not entities['end_entity']:
            print_error("无法定位指定的起点或终点")
            return {
                'success': False,
                'error': '无法定位指定函数'
            }
        
        # 第3步：调用链追踪
        print_step(3, 3, "追踪调用链")
        chain_result = self.chain_tracer.execute(
            entities['start_entity'],
            entities['end_entity']
        )
        self._display_chain(chain_result)
        
        # 生成报告
        report = self._generate_report(parsed_log, entities, chain_result)
        print_success("分析完成！")
        
        return report
    
    def _generate_report(self, parsed_log: Dict, entities: Dict, 
                        chain_result: Dict) -> Dict:
        """生成分析报告"""
        report = {
            'success': chain_result.get('success', False),
            'parsed_log': parsed_log,
            'entities': entities,
            'chain': {
                'path': chain_result['path'],
                'length': len(chain_result['path']),
                'breaks': chain_result['breaks'],
                'stats': chain_result['stats']
            }
        }
        
        # 显示报告
        self._display_report(report)
        
        return report
    
    def _display_parsed_log(self, parsed: Dict):
        """显示日志解析结果"""
        table = Table(title="日志解析结果")
        table.add_column("项目", style="cyan")
        table.add_column("内容", style="green")

        table.add_row("错误消息", str(parsed.get('error_messages', [])))
        table.add_row("错误码", str(parsed.get('error_codes', [])))

        # 只显示一次函数列表（优先显示 functions，如果 key_functions 与之不同才显示）
        functions = parsed.get('functions', [])
        key_functions = parsed.get('key_functions', [])

        if functions:
            table.add_row("涉及函数", ", ".join(functions))

        # 只有在 key_functions 存在且与 functions 不同时才显示
        if key_functions and key_functions != functions:
            table.add_row("关键函数", ", ".join(key_functions))

        # 显示推断入口和置信度
        if 'inferred_entry' in parsed and parsed['inferred_entry']:
            entry_display = parsed['inferred_entry']
            confidence = parsed.get('entry_confidence', 0.0)
            if confidence > 0:
                confidence_str = f"{confidence:.1%}"
                # 根据置信度使用不同颜色
                if confidence >= 0.6:
                    entry_display = f"{entry_display} [green](置信度: {confidence_str})[/green]"
                else:
                    entry_display = f"{entry_display} [yellow](置信度: {confidence_str}, 降级模式)[/yellow]"
            table.add_row("推断入口", entry_display)

        if 'inferred_error_point' in parsed:
            table.add_row("推断错误点", parsed['inferred_error_point'])

        console.print(table)
        console.print()
    
    def _display_entities(self, entities: Dict):
        """显示实体定位结果"""
        table = Table(title="实体定位结果")
        table.add_column("实体", style="cyan")
        table.add_column("函数名", style="green")
        table.add_column("文件", style="yellow")
        
        if entities.get('start_entity'):
            table.add_row("起点", 
                         entities['start_entity']['name'],
                         entities['start_entity'].get('file', 'N/A'))
        
        if entities.get('end_entity'):
            table.add_row("终点",
                         entities['end_entity']['name'],
                         entities['end_entity'].get('file', 'N/A'))
        
        console.print(table)
        console.print()
    
    def _display_chain(self, chain_result: Dict):
        """显示调用链结果"""
        path = chain_result['path']
        breaks = chain_result['breaks']
        stats = chain_result['stats']
        
        # 显示路径
        console.print("[bold cyan]调用路径:[/bold cyan]")
        for i, func in enumerate(path):
            # 检查是否是断点修复的位置
            is_bridge = any(b['position'] == i-1 and b['fixed'] 
                          for b in breaks)
            
            if is_bridge:
                console.print(f"  {i}. [yellow]{func}[/yellow] (桥接)")
            else:
                console.print(f"  {i}. {func}")
        console.print()
        
        # 显示断点统计
        if stats['total_breaks'] > 0:
            console.print("[bold cyan]断点修复统计:[/bold cyan]")
            console.print(f"  总断点数: {stats['total_breaks']}")
            console.print(f"  规则修复: {stats['fixed_by_rules']}")
            console.print(f"  LLM源码分析修复: {stats.get('fixed_by_source_analysis', 0)} ✨")
            console.print(f"  LLM推理修复: {stats['fixed_by_llm']}")
            console.print(f"  未修复: {stats['unfixed']}")
            console.print()
        
        # 显示断点详情
        if breaks:
            table = Table(title="断点详情")
            table.add_column("位置", style="cyan")
            table.add_column("从", style="green")
            table.add_column("到", style="green")
            table.add_column("状态", style="yellow")
            table.add_column("方法", style="magenta")
            
            for b in breaks:
                status = "✓ 已修复" if b['fixed'] else "✗ 未修复"
                method = b.get('method', 'N/A')
                
                table.add_row(
                    str(b['position']),
                    b['from'],
                    b['to'],
                    status,
                    method
                )
            
            console.print(table)
            console.print()
    
    def _display_report(self, report: Dict):
        """显示最终报告"""
        success = report['success']
        chain = report['chain']
        stats = chain['stats']

        # 计算已修复数量
        fixed_count = (stats['fixed_by_rules'] +
                      stats.get('fixed_by_source_analysis', 0) +
                      stats['fixed_by_llm'])

        # 创建总结面板
        summary = f"""
状态: {'✓ 成功' if success else '✗ 部分成功'}
调用链长度: {chain['length']}
总断点数: {stats['total_breaks']}
已修复: {fixed_count}
  - 规则修复: {stats['fixed_by_rules']}
  - LLM源码分析: {stats.get('fixed_by_source_analysis', 0)} ✨
  - LLM推理: {stats['fixed_by_llm']}
未修复: {stats['unfixed']}
        """

        print_panel("分析总结", summary.strip(),
                   style="green" if success else "yellow")
    
    def close(self):
        """关闭协调器"""
        self.kg.close()
        logger.info("协调器已关闭")

    def process_top_k(
        self,
        log_text: str,
        k: int = 5,
        error_line: int = None,
        subgraph_override: Optional[str] = None,
        user_context: Optional[Dict] = None,
        user_start_func: Optional[str] = None,
        user_end_func: Optional[str] = None
    ) -> Dict:
        """
        处理错误日志，返回Top-K条调用链

        支持三种模式：
        1. 纯自动模式：只提供日志，自动推断起止点
        2. 混合模式：提供日志 + 用户指定起止点，日志解析结果作为关键节点
        3. 手动模式：只提供起止点（使用 process_top_k_with_specific_functions）

        Args:
            log_text: 错误日志文本
            k: 返回路径数量上限
            error_line: 已废弃（保留用于兼容性，不再用于剪枝）
            subgraph_override: 手动指定子图（可选），如果提供则跳过自动选择
            user_context: 用户提供的上下文信息（可选），用于辅助入口选择
            user_start_func: 用户指定的起点函数（可选），如果提供则覆盖日志推断结果
            user_end_func: 用户指定的终点函数（可选），如果提供则覆盖日志推断结果

        Returns:
            包含多条路径的分析结果
        """
        print_header(f"Bug定位分析流程 (Top-{k}路径)")

        # 第0步（可选）：子图选择
        selected_subgraph = None
        step_offset = 0
        if self.enable_subgraph_selection and self.subgraph_selector:
            if subgraph_override:
                # 手动指定子图
                selected_subgraph = subgraph_override
                logger.info(f"使用手动指定的子图: {selected_subgraph}")

                # 获取子图路径并重新加载KG
                subgraph_path = self.subgraph_selector.get_subgraph_path(selected_subgraph)
                if subgraph_path:
                    logger.info(f"使用子图数据: {subgraph_path}")

                    # 重新初始化知识图谱接口，使用选中的子图
                    self.kg = KnowledgeGraphInterface(
                        str(subgraph_path),
                        enable_llm_detection=self.enable_llm_detection,
                        llm_client=self.llm_client
                    )

                    # 重新初始化依赖KG的Agent
                    self.entity_locator = EntityLocatorAgent(self.kg)
                    self.chain_tracer = CallChainTracerAgent(self.kg, self.llm_client)
                    self.log_parser = LogParserAgent(
                        enable_llm=self.enable_llm_log_analysis,
                        llm_client=self.llm_client,
                        kg_interface=self.kg
                    )

                    # DEBUG: 打印切换后的状态
                    logger.info(f"[DEBUG] 切换子图后: self.kg 实例 ID = {id(self.kg)}")
                    logger.info(f"[DEBUG] 切换子图后: self.log_parser.kg 实例 ID = {id(self.log_parser.kg)}")
                    logger.info(f"[DEBUG] 切换子图后: self.kg.entity_by_id 有 {len(self.kg.entity_by_id)} 个实体")

                    print_success(f"已切换到子图: {selected_subgraph}")
                else:
                    logger.warning(f"子图路径不存在: {selected_subgraph}，使用默认图谱")
            else:
                # 自动选择子图
                step_offset = 1
                print_step(1, 5, "选择相关子图")
                selected_subgraphs = self.subgraph_selector.select_by_log(log_text, top_k=1)

                if selected_subgraphs:
                    selected_subgraph = selected_subgraphs[0]
                    logger.info(f"LLM选择的子图: {selected_subgraph}")

                    # 获取子图路径
                    subgraph_path = self.subgraph_selector.get_subgraph_path(selected_subgraph)
                    if subgraph_path:
                        logger.info(f"使用子图数据: {subgraph_path}")

                        # 重新初始化知识图谱接口，使用选中的子图
                        self.kg = KnowledgeGraphInterface(
                            str(subgraph_path),
                            enable_llm_detection=self.enable_llm_detection,
                            llm_client=self.llm_client
                        )

                        # 重新初始化依赖KG的Agent
                        self.entity_locator = EntityLocatorAgent(self.kg)
                        self.chain_tracer = CallChainTracerAgent(self.kg, self.llm_client)
                        self.log_parser = LogParserAgent(
                            enable_llm=self.enable_llm_log_analysis,
                            llm_client=self.llm_client,
                            kg_interface=self.kg
                        )

                        # DEBUG: 打印切换后的状态
                        logger.info(f"[DEBUG] 切换子图后: self.kg 实例 ID = {id(self.kg)}")
                        logger.info(f"[DEBUG] 切换子图后: self.log_parser.kg 实例 ID = {id(self.log_parser.kg)}")
                        logger.info(f"[DEBUG] 切换子图后: self.kg.entity_by_id 有 {len(self.kg.entity_by_id)} 个实体")

                        print_success(f"已切换到子图: {selected_subgraph}")
                    else:
                        logger.warning(f"子图路径不存在: {selected_subgraph}，使用默认图谱")
                else:
                    logger.warning("未选择到子图，使用默认图谱")

        total_steps = 4 + step_offset

        # 第1步：日志解析
        print_step(1 + step_offset, total_steps, "解析错误日志")

        # 获取候选入口函数（如果已选择子图）
        candidate_entries = None
        if selected_subgraph:
            entry_config = get_candidate_entries_for_subgraph(selected_subgraph)
            # 合并 ko_init 和 sdk_api
            candidate_entries = entry_config.get('ko_init', []) + entry_config.get('sdk_api', [])
            logger.info(f"为子图 '{selected_subgraph}' 加载了 {len(candidate_entries)} 个候选入口")

        # 使用增强的日志解析（支持 FAIL_MESSAGE 匹配 + LLM 入口选择）
        parsed_log = self.log_parser.parse_log(
            log_text,
            candidate_entries=candidate_entries,
            user_context=user_context
        )

        self._display_parsed_log(parsed_log)

        # 检查是否需要更多信息（降级模式）
        if parsed_log.get('need_more_info'):
            console.print("\n[yellow]⚠️  需要更多信息才能确定完整调用链入口[/yellow]")
            if parsed_log.get('fallback_mode'):
                console.print(f"[dim]已启用降级模式：使用日志函数 '{parsed_log.get('inferred_entry')}' 作为起点[/dim]")
            if parsed_log.get('suggestions'):
                console.print("\n[cyan]💡 建议提供以下信息之一：[/cyan]")
                for suggestion in parsed_log['suggestions'][:3]:
                    console.print(f"   • {suggestion}")
            console.print()

        # 混合模式：如果用户提供了起止点，将日志解析结果作为关键节点
        if user_start_func or user_end_func:
            console.print("\n[cyan]🔄 混合模式：使用用户指定的起止点[/cyan]")

            # 收集日志解析出的函数作为关键节点
            intermediate_funcs_from_log = []

            if user_start_func:
                # 用户指定了起点，将日志推断的起点作为关键节点
                if parsed_log.get('inferred_entry') and parsed_log['inferred_entry'] != user_start_func:
                    intermediate_funcs_from_log.append(parsed_log['inferred_entry'])
                    console.print(f"   • 起点: [bold]{user_start_func}[/bold] (用户指定)")
                    console.print(f"   • 日志推断的起点 '{parsed_log['inferred_entry']}' 作为关键节点")
                else:
                    console.print(f"   • 起点: [bold]{user_start_func}[/bold] (用户指定)")
                parsed_log['inferred_entry'] = user_start_func

            if user_end_func:
                # 用户指定了终点，将日志推断的终点作为关键节点
                if parsed_log.get('inferred_error_point') and parsed_log['inferred_error_point'] != user_end_func:
                    intermediate_funcs_from_log.append(parsed_log['inferred_error_point'])
                    console.print(f"   • 终点: [bold]{user_end_func}[/bold] (用户指定)")
                    console.print(f"   • 日志推断的终点 '{parsed_log['inferred_error_point']}' 作为关键节点")
                else:
                    console.print(f"   • 终点: [bold]{user_end_func}[/bold] (用户指定)")
                parsed_log['inferred_error_point'] = user_end_func

            # 标记为混合模式
            parsed_log['mode'] = 'hybrid'
            parsed_log['user_provided_start'] = user_start_func
            parsed_log['user_provided_end'] = user_end_func
            parsed_log['intermediate_from_log'] = intermediate_funcs_from_log

            if intermediate_funcs_from_log:
                console.print(f"   • 关键节点: {', '.join(intermediate_funcs_from_log)}")
            console.print()

        # 第2步：实体定位
        print_step(2 + step_offset, total_steps, "在图谱中定位实体")
        entities = self.entity_locator.execute(parsed_log)
        self._display_entities(entities)

        # 检查是否找到起点和终点
        if not entities['start_entity'] or not entities['end_entity']:
            print_error("无法定位起点或终点，分析终止")
            return {
                'success': False,
                'parsed_log': parsed_log,
                'entities': entities,
                'error': '无法定位起点或终点'
            }

        # 第3步：追踪Top-K条调用链
        print_step(3 + step_offset, total_steps, "追踪Top-K条调用链")
        paths = self.chain_tracer.execute_top_k(
            entities['start_entity'],
            entities['end_entity'],
            intermediate_entities=entities.get('intermediate_entities', []),
            k=k,
            error_line=error_line
        )
        self._display_multiple_chains(paths)

        # 第4步：生成报告
        print_step(4 + step_offset, total_steps, "生成分析报告")
        report = self._generate_multi_path_report(parsed_log, entities, paths)

        print_success(f"分析完成！找到 {len(paths)} 条路径")

        return report

    def process_top_k_with_specific_functions(
        self,
        log_text: str,
        start_func: str,
        end_func: str,
        intermediate_funcs: list = None,
        k: int = 5,
        error_line: int = None,
        subgraph_override: Optional[str] = None,
        user_context: Optional[Dict] = None
    ) -> Dict:
        """
        使用指定的起点、终点和中间节点，返回Top-K条调用链

        Args:
            log_text: 错误日志文本（可选，仅用于报告）
            start_func: 起点函数名
            end_func: 终点函数名
            intermediate_funcs: 中间节点函数名列表（可选）
            k: 返回路径数量上限
            error_line: 已废弃（保留用于兼容性，不再用于剪枝）
            subgraph_override: 手动指定子图（可选），如果提供则跳过自动选择
            user_context: 用户提供的上下文信息（可选），保留用于接口一致性

        Returns:
            包含多条路径的分析结果
        """
        print_header(f"Bug定位分析流程（指定起止点，Top-{k}路径）")

        # 第0步（可选）：子图选择
        selected_subgraph = None
        step_offset = 0
        if self.enable_subgraph_selection and self.subgraph_selector:
            if subgraph_override:
                # 手动指定子图
                selected_subgraph = subgraph_override
                logger.info(f"使用手动指定的子图: {selected_subgraph}")

                # 获取子图路径并重新加载KG
                subgraph_path = self.subgraph_selector.get_subgraph_path(selected_subgraph)
                if subgraph_path:
                    logger.info(f"使用子图数据: {subgraph_path}")

                    # 重新初始化知识图谱接口，使用选中的子图
                    self.kg = KnowledgeGraphInterface(
                        str(subgraph_path),
                        enable_llm_detection=self.enable_llm_detection,
                        llm_client=self.llm_client
                    )

                    # 重新初始化依赖KG的Agent
                    self.entity_locator = EntityLocatorAgent(self.kg)
                    self.chain_tracer = CallChainTracerAgent(self.kg, self.llm_client)
                    self.log_parser = LogParserAgent(
                        enable_llm=self.enable_llm_log_analysis,
                        llm_client=self.llm_client,
                        kg_interface=self.kg
                    )

                    # DEBUG: 打印切换后的状态
                    logger.info(f"[DEBUG] 切换子图后: self.kg 实例 ID = {id(self.kg)}")
                    logger.info(f"[DEBUG] 切换子图后: self.log_parser.kg 实例 ID = {id(self.log_parser.kg)}")
                    logger.info(f"[DEBUG] 切换子图后: self.kg.entity_by_id 有 {len(self.kg.entity_by_id)} 个实体")

                    print_success(f"已切换到子图: {selected_subgraph}")
                else:
                    logger.warning(f"子图路径不存在: {selected_subgraph}，使用默认图谱")
            else:
                # 对于指定函数的情况，可以基于函数名选择子图
                step_offset = 1
                print_step(1, 4, "选择相关子图（基于函数名）")
                function_names = [start_func, end_func]
                if intermediate_funcs:
                    function_names.extend(intermediate_funcs)

                selected_subgraphs = self.subgraph_selector.select_by_functions(function_names, top_k=1)

                if selected_subgraphs:
                    selected_subgraph = selected_subgraphs[0]
                    logger.info(f"LLM选择的子图: {selected_subgraph}")

                    # 获取子图路径
                    subgraph_path = self.subgraph_selector.get_subgraph_path(selected_subgraph)
                    if subgraph_path:
                        logger.info(f"使用子图数据: {subgraph_path}")

                        # 重新初始化知识图谱接口，使用选中的子图
                        self.kg = KnowledgeGraphInterface(
                            str(subgraph_path),
                            enable_llm_detection=self.enable_llm_detection,
                            llm_client=self.llm_client
                        )

                        # 重新初始化依赖KG的Agent
                        self.entity_locator = EntityLocatorAgent(self.kg)
                        self.chain_tracer = CallChainTracerAgent(self.kg, self.llm_client)
                        self.log_parser = LogParserAgent(
                            enable_llm=self.enable_llm_log_analysis,
                            llm_client=self.llm_client,
                            kg_interface=self.kg
                        )

                        # DEBUG: 打印切换后的状态
                        logger.info(f"[DEBUG] 切换子图后: self.kg 实例 ID = {id(self.kg)}")
                        logger.info(f"[DEBUG] 切换子图后: self.log_parser.kg 实例 ID = {id(self.log_parser.kg)}")
                        logger.info(f"[DEBUG] 切换子图后: self.kg.entity_by_id 有 {len(self.kg.entity_by_id)} 个实体")

                        print_success(f"已切换到子图: {selected_subgraph}")
                    else:
                        logger.warning(f"子图路径不存在: {selected_subgraph}，使用默认图谱")
                else:
                    logger.warning("未选择到子图，使用默认图谱")

        total_steps = 3 + step_offset

        # 第1步：日志解析（仅用于报告）
        print_step(1 + step_offset, total_steps, "解析错误日志")
        parsed_log = self.log_parser.execute(log_text)

        # 第2步：定位指定函数
        print_step(2 + step_offset, total_steps, "定位指定函数")
        entities = self.entity_locator.locate_specific(
            start_func,
            end_func,
            intermediate_names=intermediate_funcs
        )
        self._display_entities(entities)

        if not entities['start_entity'] or not entities['end_entity']:
            print_error("无法定位指定的起点或终点")
            return {
                'success': False,
                'error': '无法定位指定函数'
            }

        # 第3步：追踪Top-K条调用链
        print_step(3 + step_offset, total_steps, "追踪Top-K条调用链")
        paths = self.chain_tracer.execute_top_k(
            entities['start_entity'],
            entities['end_entity'],
            intermediate_entities=entities.get('intermediate_entities', []),
            k=k,
            error_line=error_line
        )
        self._display_multiple_chains(paths)

        # 生成报告
        report = self._generate_multi_path_report(parsed_log, entities, paths)
        print_success(f"分析完成！找到 {len(paths)} 条路径")

        return report

    def _display_multiple_chains(self, paths: list):
        """显示多条调用链"""
        if not paths:
            console.print("[yellow]未找到路径[/yellow]")
            return

        console.print(f"[bold cyan]找到 {len(paths)} 条路径:[/bold cyan]\n")

        for idx, path_result in enumerate(paths):
            path = path_result['path']
            breaks = path_result['breaks']
            score = path_result.get('score', 0)
            indirect_count = path_result.get('indirect_count', 0)
            avg_call_line = path_result.get('avg_call_line', 0)
            matched_key_functions = path_result.get('matched_key_functions', [])
            missed_key_functions = path_result.get('missed_key_functions', [])

            # 构建关键函数集合（用于快速查找）
            key_function_set = set(matched_key_functions + missed_key_functions)

            # 路径标题（包含关键函数覆盖率）
            title = f"[bold green]路径 #{idx+1}[/bold green] " \
                   f"(长度={len(path)}, 间接调用={indirect_count}, " \
                   f"平均行号={avg_call_line:.1f}, 得分={score:.2f}"
            if key_function_set:
                coverage = len(matched_key_functions) / len(key_function_set) * 100
                title += f", 关键函数覆盖率={coverage:.0f}%"
            title += ")"
            console.print(title)

            # 显示路径
            for i, func in enumerate(path):
                # 检查是否是断点修复的位置
                is_bridge = any(b['position'] == i-1 and b['fixed']
                              for b in breaks)

                # 检查是否是关键函数
                is_key_function = func in key_function_set

                # 显示 call_line 信息
                call_line_info = ""
                if 'call_lines' in path_result and i > 0:
                    call_line = path_result['call_lines'][i-1]
                    if call_line:
                        call_line_info = f" [dim](line {call_line})[/dim]"

                if is_bridge:
                    # 找到桥接类型
                    bridge_type = "桥接"
                    for b in breaks:
                        if b['position'] == i-1 and b['fixed']:
                            bridge_info = b.get('bridge', {})
                            bridge_type = bridge_info.get('bridge_type', '桥接')
                            break
                    # 间接调用用黄色，如果同时是关键函数也标注
                    if is_key_function:
                        console.print(f"  {i}. [yellow]{func}[/yellow] ({bridge_type}) [cyan]✓关键函数[/cyan]{call_line_info}")
                    else:
                        console.print(f"  {i}. [yellow]{func}[/yellow] ({bridge_type}){call_line_info}")
                else:
                    # 关键函数用青色高亮
                    if is_key_function:
                        console.print(f"  {i}. [cyan]{func} ✓[/cyan]{call_line_info}")
                    else:
                        console.print(f"  {i}. {func}{call_line_info}")

            # 显示未经过的关键函数
            if missed_key_functions:
                console.print(f"  [dim]⚠ 未经过的关键函数: {', '.join(missed_key_functions)}[/dim]")

            console.print()

    def _generate_multi_path_report(self, parsed_log: Dict, entities: Dict,
                                    paths: list) -> Dict:
        """生成多路径分析报告"""
        if not paths:
            return {
                'success': False,
                'parsed_log': parsed_log,
                'entities': entities,
                'paths': [],
                'error': '未找到路径'
            }

        report = {
            'success': True,
            'parsed_log': parsed_log,
            'entities': entities,
            'paths': paths,
            'path_count': len(paths),
            'best_path': paths[0] if paths else None  # 得分最高的路径
        }

        # 显示总结
        self._display_multi_path_summary(report)

        return report

    def _display_multi_path_summary(self, report: Dict):
        """显示多路径总结"""
        paths = report['paths']
        if not paths:
            return

        # 统计信息
        total_paths = len(paths)
        min_length = min(len(p['path']) for p in paths)
        max_length = max(len(p['path']) for p in paths)
        avg_length = sum(len(p['path']) for p in paths) / total_paths

        min_indirect = min(p.get('indirect_count', 0) for p in paths)
        max_indirect = max(p.get('indirect_count', 0) for p in paths)

        summary = f"""
找到路径数: {total_paths}
路径长度: {min_length} - {max_length} (平均 {avg_length:.1f})
间接调用: {min_indirect} - {max_indirect}
最佳路径: 路径 #1 (得分={paths[0].get('score', 0)})
        """

        print_panel("多路径分析总结", summary.strip(), style="green")
