"""
IoctlMapperAgent（新版）：
  - call site 来自 KG 的 CALLS 边（tail.name=='ioctl'），确保调用方在图谱里
  - handler 候选来自 KG 的 ASSIGNED_TO 边（tail 含 ioctl），确保处理方在图谱里
  - LLM 主导选择，KG 提供代码上下文和候选列表
  - 无启发式 fallback；无法解析则标 unresolved
"""
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from loguru import logger


class IoctlMapperAgent:
    """
    用法：
        kg  = KnowledgeGraphInterface(kg_data_dir, path_mappings={...})
        llm = LLMClient(backend='openai', ...)

        agent = IoctlMapperAgent(kg=kg, llm_client=llm)
        result = agent.run()
        agent.save_result(result, "output/ioctl_mappings.json")
    """

    # LLM 候选列表上限（避免超 token）
    MAX_CANDIDATES = 20

    def __init__(self, kg, llm_client):
        """
        Args:
            kg:         KnowledgeGraphInterface 实例（必须）
            llm_client: LLMClient 实例（必须）
        """
        self.kg  = kg
        self.llm = llm_client

    # ──────────────────────────────────────────────────────────────
    # 公共入口
    # ──────────────────────────────────────────────────────────────

    def run(self, max_sites: int = 0) -> Dict[str, Any]:
        """
        执行完整映射流程。

        Args:
            max_sites: 限制处理条数（0 = 不限，用于测试）

        Returns:
            {
                "generated_at": "...",
                "stats": {...},
                "mappings": [...],
                "unresolved": [...],
            }
        """
        logger.info("=== IoctlMapperAgent 开始运行（KG-first + LLM-driven）===")

        # Step 1: 从 KG 获取 ioctl() 调用点（头在图谱里）
        logger.info("Step 1: 从 KG 查询 ioctl() 调用点...")
        call_sites = self.kg.query_ioctl_call_sites()
        logger.info(f"  找到 {len(call_sites)} 个调用点")

        if max_sites > 0:
            call_sites = call_sites[:max_sites]
            logger.info(f"  限制处理前 {max_sites} 个")

        if not call_sites:
            logger.warning("未找到任何调用点，退出")
            return self._make_result([], [], 0)

        # Step 2: 从 KG 获取全量 fops→ioctl handler 映射（尾在图谱里）
        logger.info("Step 2: 从 KG 查询 fops → ioctl handler 映射...")
        all_handlers = self.kg.query_fops_ioctl_handlers()
        logger.info(f"  找到 {len(all_handlers)} 个 handler 候选")

        # Step 3: 对每个调用点进行 LLM 解析
        logger.info("Step 3: LLM 解析调用点...")
        mappings   = []
        unresolved = []

        for idx, site in enumerate(call_sites):
            if (idx + 1) % 50 == 0:
                logger.info(f"  进度: {idx + 1}/{len(call_sites)}")

            mapping = self._resolve(site, all_handlers)
            if mapping:
                mappings.append(mapping)
            else:
                unresolved.append({"call_site": site, "reason": "llm_no_match"})

        logger.info(f"=== 完成：{len(mappings)} 成功 / {len(unresolved)} 未解析 ===")
        return self._make_result(mappings, unresolved, len(call_sites))

    # ──────────────────────────────────────────────────────────────
    # 核心解析
    # ──────────────────────────────────────────────────────────────

    def _resolve(
        self,
        site: Dict[str, Any],
        all_handlers: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        对单个调用点进行解析。

        流程：
        1. 读取调用函数源码（KG 给 source_file + start/end_line，文件读取）
        2. 按目录接近度过滤候选 handler（≤ MAX_CANDIDATES 个）
        3. LLM 从候选中选一个
        4. 验证选中的 handler 在 KG 里有对应实体（handler_id）
        """
        caller_name = site.get('caller_name', '')
        caller_file = site.get('caller_file', '')
        call_line   = site.get('call_line')

        # 1. 读调用函数源码
        caller_source = self.kg.read_entity_source(
            {"source_file": caller_file,
             "start_line":  site.get('caller_start'),
             "end_line":    site.get('caller_end')}
        )
        if not caller_source:
            logger.debug(f"无法读取源码: {caller_file} "
                         f"[{site.get('caller_start')}-{site.get('caller_end')}]")
            return None

        # 2. 过滤候选（按目录接近度取 top-N）
        candidates = self._filter_candidates(site, all_handlers)
        if not candidates:
            logger.debug(f"无候选 handler: {caller_name} @ {caller_file}")
            return None

        # 3. LLM 选 handler
        llm_result = self.llm.resolve_ioctl_handler(
            caller_source=caller_source,
            call_line=call_line,
            caller_file=caller_file,
            candidates=candidates,
        )
        if not llm_result:
            return None

        idx = llm_result.get("selected_index", -1)
        if idx < 0 or idx >= len(candidates):
            return None

        chosen = candidates[idx]

        # 4. 在 KG 里找 handler 的实体 ID（尾在图谱里）
        handler_id = self._find_handler_id(chosen.get("handler_func", ""),
                                           chosen.get("source_file", ""))

        return {
            "call_site": {
                "caller_id":   site.get("caller_id"),
                "caller_name": caller_name,
                "caller_file": caller_file,
                "call_line":   call_line,
            },
            "resolution": {
                "handler_id":   handler_id,
                "handler_func": chosen.get("handler_func", ""),
                "fops_var":     chosen.get("fops_var", ""),
                "handler_file": chosen.get("source_file", ""),
                "driver_dir":   chosen.get("driver_dir", ""),
            },
            "both_in_kg": handler_id is not None,
            "confidence": round(llm_result.get("confidence", 0) / 10.0, 2),
            "reasoning":  llm_result.get("reasoning", ""),
        }

    def _filter_candidates(
        self,
        site: Dict[str, Any],
        all_handlers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        按与调用点的目录接近度对候选排序，取前 MAX_CANDIDATES 个。
        用路径公共前缀深度作为分数。
        """
        site_parts = site.get('caller_file', '').replace('\\', '/').split('/')

        def depth(handler: Dict) -> int:
            h_parts = handler.get('source_file', '').replace('\\', '/').split('/')
            d = 0
            for a, b in zip(site_parts, h_parts):
                if a == b:
                    d += 1
                else:
                    break
            return d

        scored = sorted(all_handlers, key=depth, reverse=True)
        return scored[:self.MAX_CANDIDATES]

    def _find_handler_id(self, handler_func: str, source_file: str) -> Optional[str]:
        """
        在 KG 中找 handler 函数的实体 ID。
        优先匹配同名 + 同文件，其次只匹配名字。
        """
        if not handler_func:
            return None

        ids = self.kg.func_name_to_ids.get(handler_func, [])
        if not ids:
            return None

        # 有多个同名函数时，优先选 source_file 匹配的
        if source_file and len(ids) > 1:
            norm = source_file.replace('\\', '/')
            for eid in ids:
                entity = self.kg.entity_by_id.get(eid, {})
                if entity.get('source_file', '').replace('\\', '/').endswith(
                        norm.split('/')[-1]):
                    return eid

        return ids[0]

    # ──────────────────────────────────────────────────────────────
    # 输出
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _make_result(
        mappings: List[Dict],
        unresolved: List[Dict],
        total: int,
    ) -> Dict[str, Any]:
        return {
            "generated_at": datetime.now().isoformat(),
            "stats": {
                "total_call_sites": total,
                "mapped":           len(mappings),
                "unresolved":       len(unresolved),
                "both_in_kg":       sum(1 for m in mappings if m.get("both_in_kg")),
                "coverage":         round(len(mappings) / total, 3) if total > 0 else 0,
            },
            "mappings":   mappings,
            "unresolved": unresolved,
        }

    @staticmethod
    def save_result(result: Dict[str, Any], output_path: str) -> None:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"映射结果已保存到: {output_path}")
