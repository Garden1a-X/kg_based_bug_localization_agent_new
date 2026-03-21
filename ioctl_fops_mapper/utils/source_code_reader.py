#!/usr/bin/env python3
"""
源码读取工具
从知识图谱的source_file和行号信息读取函数源码
"""

import os
from typing import Optional


class SourceCodeReader:
    """源码读取器"""

    def __init__(self, linux_source_root: str = "/data/xuao/code_kg/data/linux_data"):
        """
        初始化源码读取器

        Args:
            linux_source_root: Linux内核源码根目录
        """
        self.linux_source_root = linux_source_root

    def convert_path(self, kg_path: str) -> str:
        """
        转换知识图谱中的路径为本地路径

        Args:
            kg_path: 知识图谱中的路径（Windows格式）
                    例如：E:\cpppro\clang_kg\linux\drivers\mmc\host\dw_mmc.c

        Returns:
            本地路径（Linux格式）
            例如：/data/xuao/code_kg/data/linux_data/drivers/mmc/host/dw_mmc.c
        """
        # 替换路径前缀
        # E:\cpppro\clang_kg\linux\ → /data/xuao/code_kg/data/linux_data/
        if kg_path.startswith('E:\\cpppro\\clang_kg\\linux\\'):
            relative_path = kg_path.replace('E:\\cpppro\\clang_kg\\linux\\', '')
        elif kg_path.startswith('E:/cpppro/clang_kg/linux/'):
            relative_path = kg_path.replace('E:/cpppro/clang_kg/linux/', '')
        else:
            # 尝试其他格式
            relative_path = kg_path

        # 统一路径分隔符为 /
        relative_path = relative_path.replace('\\', '/')

        # 拼接本地路径
        local_path = os.path.join(self.linux_source_root, relative_path)

        return local_path

    def read_function_source(
        self,
        source_file: str,
        start_line: int,
        end_line: int
    ) -> Optional[str]:
        """
        读取函数源码

        Args:
            source_file: 源文件路径（知识图谱格式）
            start_line: 起始行号（从1开始）
            end_line: 结束行号（从1开始）

        Returns:
            函数源码，如果读取失败返回None
        """
        # 转换路径
        local_path = self.convert_path(source_file)

        # 检查文件是否存在
        if not os.path.exists(local_path):
            print(f"警告: 文件不存在: {local_path}")
            return None

        try:
            with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # 提取指定行（行号从1开始，list索引从0开始）
            start_idx = start_line - 1
            end_idx = end_line  # end_line本身是包含的，所以不用-1

            if start_idx < 0 or end_idx > len(lines):
                print(f"警告: 行号超出范围: {start_line}-{end_line}, 文件共{len(lines)}行")
                return None

            source_code = ''.join(lines[start_idx:end_idx])
            return source_code

        except Exception as e:
            print(f"错误: 读取文件失败: {local_path}, {e}")
            return None

    def read_function_with_context(
        self,
        source_file: str,
        start_line: int,
        end_line: int,
        context_lines: int = 10
    ) -> Optional[dict]:
        """
        读取函数源码及其上下文

        Args:
            source_file: 源文件路径
            start_line: 起始行号
            end_line: 结束行号
            context_lines: 上下文行数

        Returns:
            {
                'function_source': '函数源码',
                'before_context': '函数前的上下文',
                'after_context': '函数后的上下文',
                'full_source': '完整的代码（包含上下文）'
            }
        """
        local_path = self.convert_path(source_file)

        if not os.path.exists(local_path):
            return None

        try:
            with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # 计算上下文范围
            context_start = max(0, start_line - 1 - context_lines)
            context_end = min(len(lines), end_line + context_lines)

            # 提取各部分
            before_context = ''.join(lines[context_start:start_line - 1])
            function_source = ''.join(lines[start_line - 1:end_line])
            after_context = ''.join(lines[end_line:context_end])
            full_source = ''.join(lines[context_start:context_end])

            return {
                'function_source': function_source,
                'before_context': before_context,
                'after_context': after_context,
                'full_source': full_source,
                'file_path': local_path,
                'line_range': f'{start_line}-{end_line}'
            }

        except Exception as e:
            print(f"错误: 读取文件失败: {e}")
            return None


def test_source_reader():
    """测试源码读取器"""
    print("="*80)
    print("测试源码读取器")
    print("="*80)

    reader = SourceCodeReader()

    # 测试路径转换
    test_path = r"E:\cpppro\clang_kg\linux\drivers\mmc\host\dw_mmc.c"
    converted = reader.convert_path(test_path)
    print(f"\n路径转换测试:")
    print(f"  输入: {test_path}")
    print(f"  输出: {converted}")

    # 测试读取mmc_rescan函数
    print(f"\n{'='*80}")
    print("测试读取 mmc_rescan 函数")
    print("="*80)

    source = reader.read_function_source(
        source_file="E:\\cpppro\\clang_kg\\linux\\drivers\\mmc\\core\\core.c",
        start_line=2237,
        end_line=2310
    )

    if source:
        print(f"\n✅ 成功读取源码 ({len(source)} 字符)")
        print(f"\n前200字符:")
        print(source[:200])
        print("\n...")
    else:
        print("\n❌ 读取失败")

    # 测试读取带上下文
    print(f"\n{'='*80}")
    print("测试读取 mmc_schedule_delayed_work 带上下文")
    print("="*80)

    context = reader.read_function_with_context(
        source_file="E:\\cpppro\\clang_kg\\linux\\drivers\\mmc\\core\\core.c",
        start_line=63,
        end_line=73,
        context_lines=5
    )

    if context:
        print(f"\n✅ 成功读取")
        print(f"\n文件路径: {context['file_path']}")
        print(f"行号范围: {context['line_range']}")
        print(f"\n完整代码（带上下文）:")
        print(context['full_source'])
    else:
        print("\n❌ 读取失败")


if __name__ == "__main__":
    test_source_reader()
