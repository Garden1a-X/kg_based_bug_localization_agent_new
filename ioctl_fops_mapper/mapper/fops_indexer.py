"""
FileOpsIndexer：建立 file_operations.unlocked_ioctl handler 的索引

两层 fallback：
  Layer 1 — KG 查询：通过 ASSIGNED_TO 关系找 unlocked_ioctl handler
  Layer 2 — 源码扫描：regex 扫 .c 文件中的 .unlocked_ioctl = xxx 赋值
"""
import os
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from loguru import logger


# 匹配 .unlocked_ioctl = func_name 或 .compat_ioctl = func_name
_IOCTL_FIELD_RE = re.compile(
    r'\.(unlocked_ioctl|compat_ioctl)\s*=\s*(\w+)'
)

# 往上查找 file_operations 变量定义
# 如：static const struct file_operations foo_fops = {
_FOPS_VAR_RE = re.compile(
    r'\bstruct\s+file_operations\b[^=]*=\s*\{?'
    r'|'
    r'\bconst\s+struct\s+file_operations\b'
)
_FOPS_VAR_NAME_RE = re.compile(
    r'(?:static\s+)?(?:const\s+)?struct\s+file_operations\s+(\w+)\s*[=;{]'
)

# 跳过的目录
_SKIP_DIRS = {'.git', 'Documentation', 'scripts', '__pycache__'}


@dataclass
class FopsEntry:
    """一个 file_operations 的 ioctl handler 条目"""
    handler_func: str       # .unlocked_ioctl = xxx 中的 xxx
    field_name: str         # "unlocked_ioctl" 或 "compat_ioctl"
    fops_var: str           # file_operations 变量名（如 foo_fops），可能为 "<unknown>"
    source_file: str        # 来源文件（相对路径或 KG 路径）
    line_no: int            # 赋值所在行号（0 表示未知）
    driver_hint: str        # 从路径推断的驱动模块名（如 "mmc"）
    source: str             # "kg" 或 "source_scan"

    def to_dict(self) -> dict:
        return {
            "handler_func": self.handler_func,
            "field_name": self.field_name,
            "fops_var": self.fops_var,
            "source_file": self.source_file,
            "line_no": self.line_no,
            "driver_hint": self.driver_hint,
            "source": self.source,
        }


class FileOpsIndexer:
    """
    建立 file_operations → unlocked_ioctl handler 的索引。

    用法：
        indexer = FileOpsIndexer(linux_src_dir="/path/to/linux", kg=kg_interface)
        entries = indexer.build()
        # 返回 List[FopsEntry]

        # 或者按 handler 函数名快速查找
        candidates = indexer.find_by_driver_hint("mmc")
    """

    def __init__(
        self,
        linux_src_dir: str,
        kg=None,              # KnowledgeGraphInterface 实例（可选）
        max_files: int = 0,   # 0 = 不限制
    ):
        self.linux_src_dir = os.path.abspath(linux_src_dir) if linux_src_dir else ""
        self.kg = kg
        self.max_files = max_files
        self._entries: List[FopsEntry] = []
        self._built = False

    def build(self) -> List[FopsEntry]:
        """
        构建索引，返回所有 FopsEntry。
        先尝试 KG，再 fallback 到源码扫描。
        """
        entries: List[FopsEntry] = []

        # Layer 1: KG 查询
        if self.kg is not None:
            kg_entries = self._build_from_kg()
            logger.info(f"KG 查询得到 {len(kg_entries)} 条 ioctl handler 记录")
            entries.extend(kg_entries)

        # Layer 2: 源码扫描（无论 KG 是否有结果，都补充扫一遍）
        if self.linux_src_dir and os.path.isdir(self.linux_src_dir):
            src_entries = self._build_from_source()
            # 去重：跳过 KG 已经有的 handler
            existing_handlers = {e.handler_func for e in entries}
            new_src = [e for e in src_entries if e.handler_func not in existing_handlers]
            logger.info(
                f"源码扫描得到 {len(src_entries)} 条记录，"
                f"其中 {len(new_src)} 条为 KG 未覆盖的新条目"
            )
            entries.extend(new_src)
        elif not entries:
            logger.warning("KG 无数据且未提供 linux_src_dir，索引为空")

        self._entries = entries
        self._built = True
        logger.info(f"FileOpsIndexer 构建完成，共 {len(entries)} 条 ioctl handler 记录")
        return entries

    def get_entries(self) -> List[FopsEntry]:
        """返回已构建的索引（如未构建则先构建）"""
        if not self._built:
            self.build()
        return self._entries

    def find_by_driver_hint(self, driver_hint: str) -> List[FopsEntry]:
        """按驱动提示（driver_hint）过滤条目"""
        hint_lower = driver_hint.lower()
        return [
            e for e in self.get_entries()
            if hint_lower in e.driver_hint.lower()
            or hint_lower in e.source_file.lower()
            or hint_lower in e.handler_func.lower()
            or hint_lower in e.fops_var.lower()
        ]

    def find_by_handler(self, handler_func: str) -> Optional[FopsEntry]:
        """按 handler 函数名精确查找"""
        for e in self.get_entries():
            if e.handler_func == handler_func:
                return e
        return None

    def to_list_of_dicts(self) -> List[Dict[str, Any]]:
        """将所有条目转为 dict 列表（供 LLM 使用）"""
        return [e.to_dict() for e in self.get_entries()]

    # ========== 内部实现 ==========

    def _build_from_kg(self) -> List[FopsEntry]:
        """Layer 1：从 KG 的 ASSIGNED_TO 关系中提取 fops → ioctl handler 映射"""
        entries = []
        try:
            mappings = self.kg.query_fops_ioctl_handlers()
        except Exception as e:
            logger.warning(f"KG query_fops_ioctl_handlers 失败: {e}")
            return entries

        for m in mappings:
            handler = m.get("handler_func", "")
            if not handler:
                continue
            source_file = m.get("source_file", "")
            driver_hint = self._infer_driver_hint(source_file, handler)
            entries.append(FopsEntry(
                handler_func=handler,
                field_name=m.get("field_name", "unlocked_ioctl"),
                fops_var=m.get("fops_var", "<unknown>"),
                source_file=source_file,
                line_no=0,
                driver_hint=driver_hint,
                source="kg",
            ))

        return entries

    def _kg_get_func_info(self, func_name: str) -> Optional[dict]:
        """从 KG 中获取函数信息"""
        try:
            return self.kg.find_function(func_name)
        except Exception:
            return None

    def _build_from_source(self) -> List[FopsEntry]:
        """Layer 2：扫描源码，找 .unlocked_ioctl = xxx 赋值"""
        entries = []
        files_scanned = 0

        for dirpath, dirnames, filenames in os.walk(self.linux_src_dir):
            dirnames[:] = [
                d for d in dirnames
                if d not in _SKIP_DIRS and not d.startswith('.')
            ]

            for fname in filenames:
                if not fname.endswith('.c'):
                    continue

                if self.max_files > 0 and files_scanned >= self.max_files:
                    return entries

                abs_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(abs_path, self.linux_src_dir)

                found = self._scan_file_for_fops(abs_path, rel_path)
                entries.extend(found)
                files_scanned += 1

        logger.info(f"源码扫描：扫描了 {files_scanned} 个 .c 文件")
        return entries

    def _scan_file_for_fops(self, abs_path: str, rel_path: str) -> List[FopsEntry]:
        """扫描单个 .c 文件，找所有 .unlocked_ioctl = xxx"""
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            logger.debug(f"读取文件失败 {abs_path}: {e}")
            return []

        entries = []
        driver_hint = self._infer_driver_hint(rel_path, "")

        for i, line in enumerate(lines):
            m = _IOCTL_FIELD_RE.search(line)
            if not m:
                continue

            field_name = m.group(1)   # unlocked_ioctl / compat_ioctl
            handler_func = m.group(2)
            line_no = i + 1

            # 往上查 file_operations 变量名
            fops_var = self._find_fops_var(lines, i)

            entries.append(FopsEntry(
                handler_func=handler_func,
                field_name=field_name,
                fops_var=fops_var,
                source_file=rel_path,
                line_no=line_no,
                driver_hint=driver_hint,
                source="source_scan",
            ))

        return entries

    def _find_fops_var(self, lines: List[str], ioctl_assign_idx: int) -> str:
        """
        从 .unlocked_ioctl = xxx 赋值行往上扫，找包含该赋值的
        file_operations 结构体变量名。

        Linux 代码通常是：
            static const struct file_operations foo_fops = {
                ...
                .unlocked_ioctl = foo_ioctl,
                ...
            };
        """
        # 往上最多扫 100 行
        search_start = max(0, ioctl_assign_idx - 100)
        brace_depth = 0

        for i in range(ioctl_assign_idx, search_start - 1, -1):
            stripped = lines[i].strip()

            # 粗略追踪大括号（往上走，} 加深度，{ 减深度）
            brace_depth += stripped.count('}') - stripped.count('{')

            if brace_depth > 0:
                # 出了当前大括号层，这行可能是结构体初始化开头
                m = _FOPS_VAR_NAME_RE.search(lines[i])
                if m:
                    return m.group(1)

        return "<unknown>"

    @staticmethod
    def _infer_driver_hint(file_path: str, func_name: str) -> str:
        """
        从文件路径或函数名推断驱动模块名。
        例如：drivers/mmc/host/dw_mmc.c → "mmc"
        """
        if not file_path:
            return ""

        # 统一路径分隔符
        path = file_path.replace('\\', '/')

        # 从路径 drivers/xxx/ 推断
        m = re.search(r'drivers/([^/]+)', path)
        if m:
            return m.group(1)

        # 从文件名推断（去掉数字和常见后缀）
        basename = os.path.basename(path).replace('.c', '').replace('.h', '')
        return basename
