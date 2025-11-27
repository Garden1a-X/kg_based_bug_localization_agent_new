#!/usr/bin/env python3
"""
测试入口点选择功能

测试场景：
1. 有候选入口 + LLM 能确定 → 高置信度
2. 有候选入口 + LLM 不确定 → 低置信度，降级模式
3. 无候选入口 + LLM 推断 → 中等置信度
4. LLM 不可用 → 降级到日志函数
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.entry_points import (
    get_candidate_entries_for_subgraph,
    get_all_entry_points,
    suggest_entry_by_platform,
    ENTRY_POINT_SETS
)
from agents.log_parser_agent import LogParserAgent
from llm import LLMClient
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def test_config_loading():
    """测试配置文件加载"""
    console.print("\n[bold cyan]测试1: 配置文件加载[/bold cyan]")

    # 测试获取 MMC 子图的候选入口
    mmc_entries = get_candidate_entries_for_subgraph('mmc')
    console.print(f"✓ MMC 子图候选入口数量: {len(mmc_entries.get('ko_init', []))}")
    console.print(f"  示例: {mmc_entries.get('ko_init', [])[:3]}")

    # 测试获取所有入口
    all_entries = get_all_entry_points()
    console.print(f"✓ 所有子系统入口总数: {len(all_entries)}")

    # 测试平台建议
    suggested = suggest_entry_by_platform('rk3288')
    console.print(f"✓ RK3288 平台建议入口: {suggested}")


def test_log_parsing_with_candidates():
    """测试带候选入口的日志解析"""
    console.print("\n[bold cyan]测试2: 日志解析（带候选入口）[/bold cyan]")

    # 创建 LLM 客户端（使用默认配置）
    llm_client = LLMClient(
        backend='openai',
        model='gpt-4o-mini',
        base_url='http://10.12.208.86:8502',
        api_key=''
    )

    if not llm_client.is_available():
        console.print("[yellow]⚠️ LLM 不可用，跳过此测试[/yellow]")
        return

    # 创建日志解析器
    log_parser = LogParserAgent(enable_llm=True, llm_client=llm_client)

    # 测试日志
    test_log = """
ALL phases bad!
mmc0: tuning execution failed: -1
mmc0: error -1 whilst initialising MMC card
"""

    # 获取候选入口
    mmc_config = get_candidate_entries_for_subgraph('mmc')
    candidates = mmc_config.get('ko_init', [])

    console.print(f"候选入口数量: {len(candidates)}")
    console.print(f"候选列表: {candidates[:5]}...")

    # 解析日志
    console.print("\n[dim]正在调用 LLM 分析...[/dim]")
    result = log_parser.parse_log(
        test_log,
        candidate_entries=candidates
    )

    # 显示结果
    table = Table(title="日志解析结果")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")

    table.add_row("推断入口", result.get('inferred_entry', 'N/A'))
    table.add_row("入口置信度", f"{result.get('entry_confidence', 0):.1%}")
    table.add_row("推断错误点", result.get('inferred_error_point', 'N/A'))
    table.add_row("需要更多信息", str(result.get('need_more_info', False)))
    table.add_row("降级模式", str(result.get('fallback_mode', False)))

    console.print(table)

    # 显示LLM推理
    if result.get('llm_reasoning'):
        console.print("\n[cyan]LLM 推理过程:[/cyan]")
        for i, reason in enumerate(result['llm_reasoning'], 1):
            console.print(f"  {i}. {reason}")

    # 显示建议
    if result.get('suggestions'):
        console.print("\n[yellow]建议提供的信息:[/yellow]")
        for suggestion in result['suggestions']:
            console.print(f"  • {suggestion}")


def test_log_parsing_with_user_context():
    """测试带用户上下文的日志解析"""
    console.print("\n[bold cyan]测试3: 日志解析（带用户上下文）[/bold cyan]")

    llm_client = LLMClient(
        backend='openai',
        model='gpt-4o-mini',
        base_url='http://10.12.208.86:8502',
        api_key=''
    )

    if not llm_client.is_available():
        console.print("[yellow]⚠️ LLM 不可用，跳过此测试[/yellow]")
        return

    log_parser = LogParserAgent(enable_llm=True, llm_client=llm_client)

    test_log = """
mmc0: tuning execution failed: -1
mmc0: error -1 whilst initialising MMC card
"""

    # 提供用户上下文
    user_context = {
        'platform': 'RK3288',
        'driver_hint': 'Designware MMC controller'
    }

    mmc_config = get_candidate_entries_for_subgraph('mmc')
    candidates = mmc_config.get('ko_init', [])

    console.print(f"用户上下文: {user_context}")
    console.print(f"候选入口数量: {len(candidates)}")

    console.print("\n[dim]正在调用 LLM 分析...[/dim]")
    result = log_parser.parse_log(
        test_log,
        candidate_entries=candidates,
        user_context=user_context
    )

    console.print(f"\n✓ 推断入口: [green]{result.get('inferred_entry')}[/green]")
    console.print(f"✓ 置信度: [green]{result.get('entry_confidence', 0):.1%}[/green]")
    console.print(f"✓ 需要更多信息: {result.get('need_more_info', False)}")


def test_fallback_mode():
    """测试降级模式（LLM 不可用）"""
    console.print("\n[bold cyan]测试4: 降级模式（LLM 不可用）[/bold cyan]")

    # 创建不启用 LLM 的解析器
    log_parser = LogParserAgent(enable_llm=False, llm_client=None)

    test_log = """
mmc0: tuning execution failed: -1
mmc0: error -1 whilst initialising MMC card
"""

    result = log_parser.parse_log(test_log)

    console.print(f"✓ 推断入口: [yellow]{result.get('inferred_entry')}[/yellow]")
    console.print(f"✓ 置信度: [yellow]{result.get('entry_confidence', 0):.1%}[/yellow]")
    console.print(f"✓ 降级模式: {result.get('fallback_mode', False)}")
    console.print(f"✓ 涉及函数: {result.get('functions', [])}")

    if result.get('suggestions'):
        console.print("\n建议:")
        for suggestion in result['suggestions'][:2]:
            console.print(f"  • {suggestion}")


def main():
    """运行所有测试"""
    console.print(Panel.fit(
        "[bold]入口点选择功能测试[/bold]\n"
        "测试配置加载、LLM 分析、降级模式等功能",
        border_style="cyan"
    ))

    try:
        # 测试1: 配置加载
        test_config_loading()

        # 测试2: 带候选入口的日志解析
        test_log_parsing_with_candidates()

        # 测试3: 带用户上下文的日志解析
        test_log_parsing_with_user_context()

        # 测试4: 降级模式
        test_fallback_mode()

        console.print("\n[bold green]✓ 所有测试完成[/bold green]")

    except Exception as e:
        console.print(f"\n[bold red]✗ 测试失败: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
