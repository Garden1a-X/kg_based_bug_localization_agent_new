"""
IoctlCallScanner：扫描 Linux 源码目录，找出所有 ioctl() 调用点
"""
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional
from loguru import logger


# 匹配 ioctl() 调用行（避免误匹配函数定义名称，如 foo_ioctl(）
# 只匹配直接调用 ioctl(...)，不匹配函数定义
_IOCTL_CALL_RE = re.compile(r'\bioctl\s*\(')

# 匹配 C 函数定义的开头，用于往上找调用者函数名
# 例如：static int foo_bar(struct xxx *x, ...)
_FUNC_DEF_RE = re.compile(
    r'^[\w\s\*]+\s+(\w+)\s*\([^;]*$'
)

# 跳过的目录（编译产物等），只跳过顶层 Documentation，不跳过子目录中的 Documentation
_SKIP_DIRS = {'.git', 'tools/testing', 'scripts', '__pycache__'}


@dataclass
class IoctlCallSite:
    """一个 ioctl() 调用点"""
    file_path: str          # 相对于 linux_src_dir 的路径
    abs_path: str           # 绝对路径
    line_no: int            # ioctl() 所在行号（1-indexed）
    caller_func: str        # 调用 ioctl 的函数名（可能为 "<unknown>"）
    line_content: str       # ioctl() 所在行的内容（strip 后）
    context_lines: List[str] = field(default_factory=list)  # 上下文行（用于 LLM 分析）

    def to_dict(self) -> dict:
        return {
            "file": self.file_path,
            "line": self.line_no,
            "caller_func": self.caller_func,
            "line_content": self.line_content,
        }


class IoctlCallScanner:
    """
    扫描 Linux 源码目录中所有 .c / .h 文件，找出 ioctl() 调用点。

    用法：
        scanner = IoctlCallScanner("/path/to/linux")
        sites = scanner.scan()
        # 或者只扫指定子目录
        sites = scanner.scan(subdirs=["drivers/mmc", "drivers/usb"])
    """

    def __init__(
        self,
        linux_src_dir: str,
        context_radius: int = 30,
        max_files: int = 0,
    ):
        """
        Args:
            linux_src_dir: Linux 源码根目录
            context_radius: ioctl() 调用点前后各取多少行作为 LLM 上下文
            max_files: 最多扫描多少个文件（0 = 不限制，用于测试）
        """
        self.linux_src_dir = os.path.abspath(linux_src_dir)
        self.context_radius = context_radius
        self.max_files = max_files

    def scan(self, subdirs: Optional[List[str]] = None) -> List[IoctlCallSite]:
        """
        扫描源码目录，返回所有 ioctl() 调用点列表。

        Args:
            subdirs: 只扫指定子目录（相对于 linux_src_dir），None 表示全量扫描

        Returns:
            IoctlCallSite 列表
        """
        sites: List[IoctlCallSite] = []
        files_scanned = 0

        if subdirs:
            roots = [os.path.join(self.linux_src_dir, d) for d in subdirs]
        else:
            roots = [self.linux_src_dir]

        for root_dir in roots:
            if not os.path.isdir(root_dir):
                logger.warning(f"目录不存在，跳过: {root_dir}")
                continue

            for dirpath, dirnames, filenames in os.walk(root_dir):
                # 跳过不需要的目录
                # 只在 linux_src_dir 的直接子目录才跳过 Documentation（内核根目录级别的文档目录）
                is_linux_root = (dirpath == self.linux_src_dir)
                dirnames[:] = [
                    d for d in dirnames
                    if d not in _SKIP_DIRS
                    and not d.startswith('.')
                    and not (is_linux_root and d == 'Documentation')
                ]

                for fname in filenames:
                    if not (fname.endswith('.c') or fname.endswith('.h')):
                        continue

                    if self.max_files > 0 and files_scanned >= self.max_files:
                        logger.info(f"已达到文件数量上限 {self.max_files}，停止扫描")
                        return sites

                    abs_path = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(abs_path, self.linux_src_dir)

                    found = self._scan_file(abs_path, rel_path)
                    sites.extend(found)
                    files_scanned += 1

                    if files_scanned % 1000 == 0:
                        logger.info(f"已扫描 {files_scanned} 个文件，找到 {len(sites)} 个 ioctl() 调用点")

        logger.info(f"扫描完成：共扫描 {files_scanned} 个文件，找到 {len(sites)} 个 ioctl() 调用点")
        return sites

    def _scan_file(self, abs_path: str, rel_path: str) -> List[IoctlCallSite]:
        """扫描单个文件，返回其中所有 ioctl() 调用点"""
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            logger.debug(f"读取文件失败 {abs_path}: {e}")
            return []

        sites = []
        for i, line in enumerate(lines):
            if not _IOCTL_CALL_RE.search(line):
                continue

            line_no = i + 1  # 1-indexed
            caller_func = self._find_caller_func(lines, i)
            context = self._extract_context(lines, i)

            sites.append(IoctlCallSite(
                file_path=rel_path,
                abs_path=abs_path,
                line_no=line_no,
                caller_func=caller_func,
                line_content=line.strip(),
                context_lines=context,
            ))

        return sites

    def _find_caller_func(self, lines: List[str], ioctl_line_idx: int) -> str:
        """
        从 ioctl() 调用行往上扫，找到最近的函数定义名。
        返回函数名，找不到返回 "<unknown>"。
        """
        # 往上最多扫 100 行
        search_start = max(0, ioctl_line_idx - 100)
        brace_depth = 0

        for i in range(ioctl_line_idx, search_start - 1, -1):
            stripped = lines[i].strip()

            # 粗略追踪大括号深度（往上走，遇到 } 增加，遇到 { 减少）
            brace_depth += stripped.count('}') - stripped.count('{')

            # 当大括号深度 > 0 时，说明我们已经出了 ioctl 所在的函数体
            # 这行可能是函数定义
            if brace_depth > 0:
                m = _FUNC_DEF_RE.match(lines[i])
                if m:
                    return m.group(1)
                # 也尝试更宽泛的匹配：找 "word(" 形式但不是控制语句
                simple = re.match(r'^[\w\s\*]+\b(\w+)\s*\(', lines[i])
                if simple:
                    name = simple.group(1)
                    if name not in {'if', 'while', 'for', 'switch', 'do', 'return', 'sizeof'}:
                        return name

        return "<unknown>"

    def _extract_context(self, lines: List[str], center_idx: int) -> List[str]:
        """提取 ioctl() 调用点周围的代码行（用于 LLM 分析）"""
        start = max(0, center_idx - self.context_radius)
        end = min(len(lines), center_idx + self.context_radius + 1)
        return [line.rstrip('\n') for line in lines[start:end]]

    def get_context_string(self, site: IoctlCallSite) -> str:
        """将 IoctlCallSite 的 context_lines 拼成字符串（供 LLM 使用）"""
        start_line = max(1, site.line_no - self.context_radius)
        result = []
        for i, line in enumerate(site.context_lines):
            result.append(f"{start_line + i:4d}: {line}")
        return '\n'.join(result)
