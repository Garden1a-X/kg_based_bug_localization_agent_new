"""
IoctlMapperAgent（新版）：
  - call site 来源（二选一）：
      1. 源码扫描（推荐）：扫描 linux_src_dir 下 ``= ioctl(`` 赋值调用形式
      2. KG 查询（兜底）：来自 CALLS 边（tail.name=='ioctl'）
  - handler 候选来自 KG 的 ASSIGNED_TO 边（tail 含 ioctl）
  - LLM 主导选择；无法解析则标 unresolved
"""
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
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

    def __init__(self, kg, llm_client, linux_src_dir: str = ""):
        """
        Args:
            kg:            KnowledgeGraphInterface 实例（必须）
            llm_client:    LLMClient 实例（必须）
            linux_src_dir: Linux 源码根目录（提供时用源码扫描找调用点，否则用 KG）
        """
        self.kg            = kg
        self.llm           = llm_client
        self.linux_src_dir = linux_src_dir

        # 源码扫描模式下：构建 KG 文件路径 → 函数行范围 索引
        # 用于扫描到 ioctl 调用后，回 KG 查 caller_id / caller_name
        self._kg_file_func_index: Dict[str, List[Dict]] = {}
        if linux_src_dir:
            self._build_kg_file_index()

    # ──────────────────────────────────────────────────────────────
    # KG 文件→函数 索引（源码扫描模式专用）
    # ──────────────────────────────────────────────────────────────

    def _kg_path_to_rel(self, kg_path: str) -> str:
        """
        把 KG 中存储的绝对路径转换为相对于 linux_src_dir 的相对路径。

        转换步骤：
        1. 调用 kg._remap_path() 应用 --path-mapping 规则，把 KG 路径换成本机路径
        2. 去掉 linux_src_dir 前缀，得到相对路径（如 drivers/mmc/host/sdhci.c）

        兜底：步骤 2 失败时回退到 _to_relative_path() 的 marker 匹配。
        """
        local = self.kg._remap_path(kg_path).replace('\\', '/')
        src_dir = os.path.abspath(self.linux_src_dir).replace('\\', '/').rstrip('/')
        if local.startswith(src_dir + '/'):
            return local[len(src_dir) + 1:]
        # 兜底：用硬编码 marker（兼容没有传 path-mapping 的情况）
        return self._to_relative_path(kg_path)

    def _build_kg_file_index(self) -> None:
        """
        遍历 KG 所有 FUNCTION 实体，按相对路径建立
        { rel_path: [{id, name, start_line, end_line}, ...] } 索引。
        源码扫描找到 ioctl 调用后，用此索引反查 caller_id / caller_name。
        """
        for eid, entity in self.kg.entity_by_id.items():
            if entity.get('type') != 'FUNCTION':
                continue
            src = entity.get('source_file', '')
            if not src:
                continue
            rel = self._kg_path_to_rel(src)
            self._kg_file_func_index.setdefault(rel, []).append({
                'id':         eid,
                'name':       entity.get('name', ''),
                'start_line': entity.get('start_line'),
                'end_line':   entity.get('end_line'),
            })
        logger.debug(f"KG 文件→函数索引构建完成：{len(self._kg_file_func_index)} 个文件")

    def _lookup_caller_in_kg(self, file_rel_path: str, ioctl_line: int) -> Optional[Dict]:
        """
        在 KG 中找包含给定行号的函数实体（start_line <= line <= end_line）。
        返回 {id, name, start_line, end_line}，未找到返回 None。
        """
        for func in self._kg_file_func_index.get(file_rel_path, []):
            s, e = func.get('start_line'), func.get('end_line')
            if s and e and s <= ioctl_line <= e:
                return func
        return None

    # ──────────────────────────────────────────────────────────────
    # 公共入口
    # ──────────────────────────────────────────────────────────────

    def run(self, max_sites: int = 0, path_prefix: str = "") -> Dict[str, Any]:
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
        logger.info("=== IoctlMapperAgent 开始运行 ===")

        # Step 1: 获取 ioctl() 调用点
        if self.linux_src_dir:
            # 源码扫描：只找 "= ioctl(" 赋值形式，更精准
            from mapper.scanner import IoctlCallScanner
            logger.info(f"Step 1: 扫描源码 {self.linux_src_dir} 查找 '= ioctl(' 调用点...")
            scanner = IoctlCallScanner(self.linux_src_dir)
            subdirs = [path_prefix.lstrip('/')] if path_prefix else None
            raw_sites = scanner.scan(subdirs=subdirs)
            call_sites = [s.to_call_site_dict() for s in raw_sites]
            logger.info(f"  扫描找到 {len(call_sites)} 个调用点")

            # 用 KG 反查 caller_id / caller_name（比正则字符串匹配更准确）
            kg_hit = 0
            for site in call_sites:
                line = site.get('call_line')
                if not line:
                    continue
                kg_info = self._lookup_caller_in_kg(site['caller_file'], line)
                if kg_info:
                    site['caller_id']    = kg_info['id']
                    site['caller_name']  = kg_info['name']
                    site['caller_start'] = kg_info['start_line']
                    site['caller_end']   = kg_info['end_line']
                    kg_hit += 1
            logger.info(f"  KG 反查 caller：{kg_hit}/{len(call_sites)} 个命中")
        else:
            # 兜底：从 KG 查询
            logger.info("Step 1: 从 KG 查询 ioctl() 调用点...")
            call_sites = self.kg.query_ioctl_call_sites()
            logger.info(f"  找到 {len(call_sites)} 个调用点")

            if path_prefix:
                prefix = path_prefix.replace('\\', '/')
                call_sites = [
                    s for s in call_sites
                    if prefix in s.get('caller_file', '').replace('\\', '/')
                ]
                logger.info(f"  过滤 '{prefix}' 后调用点: {len(call_sites)} 个")

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

            mapping, fail_info = self._resolve(site, all_handlers)
            if mapping:
                mappings.append(mapping)
            else:
                unresolved.append({"call_site": site, **fail_info})

        logger.info(f"=== 完成：{len(mappings)} 成功 / {len(unresolved)} 未解析 ===")
        return self._make_result(mappings, unresolved, len(call_sites))

    # ──────────────────────────────────────────────────────────────
    # 核心解析
    # ──────────────────────────────────────────────────────────────

    def _resolve(
        self,
        site: Dict[str, Any],
        all_handlers: List[Dict[str, Any]],
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        对单个调用点进行解析。

        流程：
        1. 读取调用函数源码（KG 给 source_file + start/end_line，文件读取）
        2. 按目录接近度过滤候选 handler（≤ MAX_CANDIDATES 个）
        3. LLM 从候选中选一个
        4. 验证选中的 handler 在 KG 里有对应实体（handler_id）

        Returns:
            (mapping_dict, {})                         — 成功
            (None, {"reason": ..., ...})               — 失败，reason 字段说明原因：
                "no_source"       无法读取调用点源码
                "no_candidates"   KG 里找不到任何候选 handler
                "llm_error"       LLM 调用本身失败（网络/超时/解析错误）
                "llm_no_match"    LLM 明确返回 selected_index=-1（附 llm_reasoning）
                "llm_bad_index"   LLM 返回了越界下标
        """
        caller_name = site.get('caller_name', '')
        caller_file = site.get('caller_file', '')
        call_line   = site.get('call_line')

        # 1. 获取调用点源码上下文
        context_lines = site.get('_context_lines')
        if context_lines is not None:
            caller_source = '\n'.join(context_lines)
        else:
            caller_source = self.kg.read_entity_source(
                {"source_file": caller_file,
                 "start_line":  site.get('caller_start'),
                 "end_line":    site.get('caller_end')}
            )
        if not caller_source:
            logger.debug(f"无法读取源码: {caller_file} "
                         f"[{site.get('caller_start')}-{site.get('caller_end')}]")
            return None, {"reason": "no_source"}

        # 2. 过滤候选（按目录接近度取 top-N）
        candidates = self._filter_candidates(site, all_handlers)
        if not candidates:
            logger.debug(f"无候选 handler: {caller_name} @ {caller_file}")
            return None, {"reason": "no_candidates"}

        # 3. LLM 选 handler
        llm_result = self.llm.resolve_ioctl_handler(
            caller_source=caller_source,
            call_line=call_line,
            caller_file=caller_file,
            candidates=candidates,
        )
        if not llm_result:
            return None, {"reason": "llm_error"}

        idx = llm_result.get("selected_index", -1)
        if idx < 0:
            return None, {
                "reason":          "llm_no_match",
                "llm_confidence":  llm_result.get("confidence"),
                "llm_reasoning":   llm_result.get("reasoning", ""),
            }
        if idx >= len(candidates):
            return None, {
                "reason":     "llm_bad_index",
                "llm_index":  idx,
                "num_candidates": len(candidates),
            }

        chosen = candidates[idx]

        # 4. 在 KG 里找 handler 的实体 ID
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
        }, {}

    @staticmethod
    def _to_relative_path(path: str) -> str:
        """
        将 KG 存储的绝对路径转换为 Linux 源码根目录下的相对路径。
        例如：/mnt/afs/.../linux-5.10/drivers/atm/eni.c → drivers/atm/eni.c
        找不到已知 linux 根标记时返回原始路径。
        """
        p = path.replace('\\', '/')
        for marker in ('linux-5.10/', 'linux_data/', 'linux/'):
            idx = p.find(marker)
            if idx >= 0:
                return p[idx + len(marker):]
        return p

    def _filter_candidates(
        self,
        site: Dict[str, Any],
        all_handlers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        按与调用点的目录接近度对候选排序，取前 MAX_CANDIDATES 个。
        用路径公共前缀深度作为分数。
        caller_file 可能是绝对路径，需先归一化为相对路径再比较。
        """
        rel_caller = self._to_relative_path(site.get('caller_file', ''))
        site_parts = rel_caller.split('/')

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
