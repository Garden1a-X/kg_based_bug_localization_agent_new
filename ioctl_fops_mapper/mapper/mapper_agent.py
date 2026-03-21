"""
IoctlMapperAgent：协调 scanner、fops_indexer 和 LLM，
将每个 ioctl() 调用点映射到对应的 file_operations 实例。
"""
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from loguru import logger

from .scanner import IoctlCallScanner, IoctlCallSite
from .fops_indexer import FileOpsIndexer, FopsEntry


class IoctlMapperAgent:
    """
    主 Agent：将 ioctl() 调用点映射到 file_operations 结构体实例

    用法：
        from data.kg_interface import KnowledgeGraphInterface
        from llm.llm_client import LLMClient

        kg = KnowledgeGraphInterface(kg_data_dir)
        llm = LLMClient(backend='openai', base_url='...', model='...')

        agent = IoctlMapperAgent(
            linux_src_dir="/path/to/linux",
            kg=kg,
            llm_client=llm,
        )
        result = agent.run()
        agent.save_result(result, "output/ioctl_mappings.json")
    """

    def __init__(
        self,
        linux_src_dir: str,
        kg=None,
        llm_client=None,
        context_radius: int = 30,
        max_files: int = 0,
        scan_subdirs: Optional[List[str]] = None,
    ):
        """
        Args:
            linux_src_dir: Linux 源码根目录
            kg: KnowledgeGraphInterface 实例（可选）
            llm_client: LLMClient 实例（可选，无 LLM 时跳过 LLM 分析）
            context_radius: ioctl 调用点前后各取多少行上下文
            max_files: 限制扫描文件数量（0 = 不限，测试用）
            scan_subdirs: 只扫指定子目录（None = 全量）
        """
        self.linux_src_dir = linux_src_dir
        self.kg = kg
        self.llm = llm_client
        self.context_radius = context_radius
        self.max_files = max_files
        self.scan_subdirs = scan_subdirs

        self.scanner = IoctlCallScanner(
            linux_src_dir=linux_src_dir,
            context_radius=context_radius,
            max_files=max_files,
        )
        self.indexer = FileOpsIndexer(
            linux_src_dir=linux_src_dir,
            kg=kg,
            max_files=max_files,
        )

    def run(self) -> Dict[str, Any]:
        """
        执行完整映射流程。

        Returns:
            {
                "generated_at": "...",
                "stats": {...},
                "mappings": [...],
                "unresolved": [...],
            }
        """
        logger.info("=== IoctlMapperAgent 开始运行 ===")

        # Step 1: 扫描 ioctl() 调用点
        logger.info("Step 1: 扫描 ioctl() 调用点...")
        call_sites = self.scanner.scan(subdirs=self.scan_subdirs)
        logger.info(f"找到 {len(call_sites)} 个 ioctl() 调用点")

        if not call_sites:
            logger.warning("未找到任何 ioctl() 调用点，退出")
            return self._make_result([], [], len(call_sites))

        # Step 2: 构建 fops 索引
        logger.info("Step 2: 构建 file_operations handler 索引...")
        fops_entries = self.indexer.build()
        logger.info(f"索引包含 {len(fops_entries)} 条 ioctl handler 记录")

        # Step 3: 对每个调用点进行映射
        logger.info("Step 3: 映射调用点...")
        mappings = []
        unresolved = []

        for idx, site in enumerate(call_sites):
            if (idx + 1) % 100 == 0:
                logger.info(f"  处理进度: {idx + 1}/{len(call_sites)}")

            mapping = self._resolve_call_site(site, fops_entries)
            if mapping:
                mappings.append(mapping)
            else:
                unresolved.append({
                    "call_site": site.to_dict(),
                    "reason": "no_match_found",
                })

        logger.info(
            f"=== 映射完成：{len(mappings)} 成功，{len(unresolved)} 未解析 ==="
        )
        return self._make_result(mappings, unresolved, len(call_sites))

    # ========== 内部方法 ==========

    def _resolve_call_site(
        self,
        site: IoctlCallSite,
        fops_entries: List[FopsEntry],
    ) -> Optional[Dict[str, Any]]:
        """
        对单个 ioctl() 调用点进行映射。

        策略：
        1. 无 LLM 时：纯基于调用者函数名 / 文件路径做关键词匹配
        2. 有 LLM 时：先用 LLM 分析上下文获取 driver_module，再做精确匹配
        """
        if not fops_entries:
            return None

        context_str = self.scanner.get_context_string(site)

        if self.llm and self.llm.is_available():
            return self._resolve_with_llm(site, fops_entries, context_str)
        else:
            return self._resolve_heuristic(site, fops_entries)

    def _resolve_with_llm(
        self,
        site: IoctlCallSite,
        fops_entries: List[FopsEntry],
        context_str: str,
    ) -> Optional[Dict[str, Any]]:
        """使用 LLM 分析上下文，再从索引中匹配最佳候选"""

        # Step A: LLM 分析调用点上下文
        analysis = self.llm.analyze_ioctl_context(
            code_context=context_str,
            file_path=site.file_path,
            line_no=site.line_no,
        )

        if not analysis:
            logger.debug(f"LLM 分析失败，fallback 到启发式: {site.file_path}:{site.line_no}")
            return self._resolve_heuristic(site, fops_entries)

        driver_module = analysis.get("driver_module") or ""
        confidence_raw = analysis.get("confidence", 0)
        if isinstance(confidence_raw, str):
            try:
                confidence_raw = float(confidence_raw)
            except ValueError:
                confidence_raw = 0

        # Step B: 根据 driver_module 筛选候选列表
        if driver_module:
            candidates = self.indexer.find_by_driver_hint(driver_module)
        else:
            candidates = fops_entries

        if not candidates:
            candidates = fops_entries  # fallback 到全量

        # 候选太多时截断（避免超出 LLM token 限制）
        MAX_CANDIDATES = 20
        if len(candidates) > MAX_CANDIDATES:
            # 优先保留与文件路径更相似的
            candidates = self._rank_candidates(site, candidates)[:MAX_CANDIDATES]

        # Step C: LLM 从候选列表中选最佳
        candidates_dicts = [e.to_dict() for e in candidates]
        matched = self.llm.match_fops_candidate(
            ioctl_analysis=analysis,
            fops_candidates=candidates_dicts,
            code_context=context_str,
        )

        if matched:
            return {
                "call_site": site.to_dict(),
                "resolution": {
                    "fops_variable": matched.get("fops_var", "<unknown>"),
                    "unlocked_ioctl_handler": matched.get("handler_func", ""),
                    "field_name": matched.get("field_name", "unlocked_ioctl"),
                    "fops_source_file": matched.get("source_file", ""),
                    "driver_module": matched.get("driver_hint", driver_module),
                },
                "confidence": round(matched.get("match_confidence", 0) / 10.0, 2),
                "method": "llm+kg" if matched.get("source") == "kg" else "llm+source_scan",
                "llm_analysis": {
                    "device_path": analysis.get("device_path"),
                    "driver_module": driver_module,
                    "fd_source": analysis.get("fd_source"),
                    "llm_confidence": confidence_raw,
                },
                "reasoning": matched.get("match_reasoning", ""),
            }

        # LLM 匹配失败，fallback 到启发式
        return self._resolve_heuristic(site, fops_entries)

    def _resolve_heuristic(
        self,
        site: IoctlCallSite,
        fops_entries: List[FopsEntry],
    ) -> Optional[Dict[str, Any]]:
        """
        无 LLM 时的启发式匹配：
        - 基于调用点文件路径与 fops 来源文件路径的相似度
        - 基于调用者函数名与 handler 函数名的前缀匹配
        """
        if not fops_entries:
            return None

        ranked = self._rank_candidates(site, fops_entries)
        if not ranked:
            return None

        best = ranked[0]
        score = self._similarity_score(site, best)

        # 相似度过低则认为无法匹配
        if score < 0.1:
            return None

        return {
            "call_site": site.to_dict(),
            "resolution": {
                "fops_variable": best.fops_var,
                "unlocked_ioctl_handler": best.handler_func,
                "field_name": best.field_name,
                "fops_source_file": best.source_file,
                "driver_module": best.driver_hint,
            },
            "confidence": round(min(score, 1.0), 2),
            "method": "heuristic",
            "reasoning": f"基于文件路径/函数名相似度匹配（score={score:.2f}）",
        }

    def _rank_candidates(
        self,
        site: IoctlCallSite,
        candidates: List[FopsEntry],
    ) -> List[FopsEntry]:
        """按相似度对候选排序（高分在前）"""
        scored = [(self._similarity_score(site, e), e) for e in candidates]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored]

    def _similarity_score(self, site: IoctlCallSite, entry: FopsEntry) -> float:
        """
        简单的相似度计算：
        - 文件路径共同前缀越长，分数越高
        - 调用者函数名与 handler 函数名有公共前缀，加分
        - driver_hint 出现在 site 路径中，加分
        """
        score = 0.0

        # 路径相似度（共同路径组成部分）
        site_parts = set(site.file_path.replace('\\', '/').split('/'))
        entry_parts = set(entry.source_file.replace('\\', '/').split('/'))
        common = site_parts & entry_parts
        if site_parts:
            score += len(common) / max(len(site_parts), 1) * 0.6

        # driver_hint 出现在调用点路径
        if entry.driver_hint and entry.driver_hint.lower() in site.file_path.lower():
            score += 0.3

        # 函数名前缀匹配
        caller = site.caller_func.lower()
        handler = entry.handler_func.lower()
        if caller != "<unknown>" and handler:
            prefix_len = self._common_prefix_len(caller, handler)
            if prefix_len > 3:
                score += min(prefix_len / max(len(caller), len(handler)), 1.0) * 0.1

        return score

    @staticmethod
    def _common_prefix_len(a: str, b: str) -> int:
        length = 0
        for ca, cb in zip(a, b):
            if ca == cb:
                length += 1
            else:
                break
        return length

    @staticmethod
    def _make_result(
        mappings: List[Dict],
        unresolved: List[Dict],
        total_sites: int,
    ) -> Dict[str, Any]:
        return {
            "generated_at": datetime.now().isoformat(),
            "stats": {
                "total_call_sites": total_sites,
                "mapped": len(mappings),
                "unresolved": len(unresolved),
                "coverage": round(len(mappings) / total_sites, 3) if total_sites > 0 else 0,
            },
            "mappings": mappings,
            "unresolved": unresolved,
        }

    @staticmethod
    def save_result(result: Dict[str, Any], output_path: str) -> None:
        """将映射结果写入 JSON 文件"""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"映射结果已保存到: {output_path}")
