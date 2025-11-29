#!/usr/bin/env python3
"""
测试日志匹配功能
用于调试日志解析和FAIL_MESSAGE匹配过程
"""
import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from data.kg_interface import KnowledgeGraphInterface
from agents.log_parser_agent import LogParserAgent
from llm import LLMClient
from utils.logger import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def print_fail_messages(fail_messages):
    """打印所有FAIL_MESSAGE实体"""
    console.print("\n[bold cyan]═══ FAIL_MESSAGE 实体列表 ═══[/bold cyan]")

    if not fail_messages:
        console.print("[yellow]没有找到FAIL_MESSAGE实体[/yellow]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim")
    table.add_column("函数", style="cyan")
    table.add_column("消息模式", style="green")
    table.add_column("源文件", style="blue")

    for msg_id, msg in list(fail_messages.items())[:20]:  # 只显示前20个
        table.add_row(
            str(msg.get('id', '')),
            str(msg.get('scope', '')),
            str(msg.get('name', ''))[:60] + "..." if len(str(msg.get('name', ''))) > 60 else str(msg.get('name', '')),
            str(msg.get('source_file', ''))
        )

    console.print(table)
    console.print(f"\n[dim]总共 {len(fail_messages)} 个 FAIL_MESSAGE 实体（显示前20个）[/dim]")


def print_matching_details(log_lines, fail_messages, log_parser):
    """打印每一行日志的匹配详情"""
    console.print("\n[bold cyan]═══ 日志匹配详情 ═══[/bold cyan]")

    for idx, line in enumerate(log_lines, 1):
        line = line.strip()
        if not line:
            continue

        console.print(f"\n[bold yellow]行 {idx}:[/bold yellow] [dim]{line[:100]}...[/dim]" if len(line) > 100 else f"\n[bold yellow]行 {idx}:[/bold yellow] {line}")

        # 调用匹配函数
        matches = log_parser._match_log_line_to_fail_message(line, fail_messages)

        if matches:
            console.print(f"  [green]✓ 找到 {len(matches)} 个匹配[/green]")
            for rank, (msg_id, msg, matched_text, similarity) in enumerate(matches[:3], 1):  # 只显示前3个
                console.print(f"    [{rank}] 相似度: {similarity:.2f}")
                console.print(f"        函数: {msg.get('scope', 'N/A')}")
                console.print(f"        匹配文本: {matched_text[:80]}..." if len(matched_text) > 80 else f"        匹配文本: {matched_text}")
                console.print(f"        消息模式: {msg.get('name', 'N/A')[:80]}...")
        else:
            console.print("  [red]✗ 无匹配[/red]")


def main():
    parser = argparse.ArgumentParser(description='测试日志匹配功能')
    parser.add_argument('--data-dir', required=True, help='知识图谱数据目录')
    parser.add_argument('--log-file', required=True, help='错误日志文件路径')
    parser.add_argument('--enable-llm', action='store_true', help='启用LLM辅助分析')
    parser.add_argument('--show-all-messages', action='store_true', help='显示所有FAIL_MESSAGE')
    parser.add_argument('--show-matching-details', action='store_true', help='显示每行匹配详情')

    args = parser.parse_args()

    # 读取日志文件
    log_file_path = Path(args.log_file)
    if not log_file_path.exists():
        console.print(f"[red]错误: 日志文件不存在: {args.log_file}[/red]")
        return

    with open(log_file_path, 'r', encoding='utf-8') as f:
        log_text = f.read()

    console.print(Panel(f"[bold]日志文件:[/bold] {args.log_file}\n[bold]数据目录:[/bold] {args.data_dir}",
                       title="测试配置", border_style="blue"))

    # 创建LLM客户端（如果需要）
    llm_client = None
    if args.enable_llm:
        console.print("\n[cyan]创建LLM客户端...[/cyan]")
        llm_client = LLMClient(
            backend='openai',
            model='gpt-4o-mini',
            base_url='http://10.12.208.86:8502',
            api_key=''
        )
        if llm_client.is_available():
            console.print(f"[green]✓ LLM客户端初始化成功[/green]")
        else:
            console.print("[yellow]⚠ LLM客户端不可用，将禁用LLM功能[/yellow]")
            llm_client = None

    # 加载知识图谱
    console.print("\n[cyan]加载知识图谱...[/cyan]")
    kg = KnowledgeGraphInterface(
        args.data_dir,
        enable_llm_detection=False,
        llm_client=llm_client
    )
    console.print(f"[green]✓ 知识图谱加载完成[/green]")
    console.print(f"  - 实体总数: {len(kg.entity_by_id)}")

    # 创建LogParser
    console.print("\n[cyan]创建LogParser...[/cyan]")
    log_parser = LogParserAgent(
        enable_llm=args.enable_llm and llm_client is not None,
        llm_client=llm_client,
        kg_interface=kg
    )
    console.print(f"[green]✓ LogParser创建完成[/green]")

    # 手动提取FAIL_MESSAGE（复制log_parser内部逻辑）
    console.print("\n[cyan]提取FAIL_MESSAGE实体...[/cyan]")
    fail_messages = {}
    for entity_id, entity in kg.entity_by_id.items():
        if entity.get('type') == 'FAIL_MESSAGE':
            fail_messages[entity_id] = {
                'id': entity.get('id'),
                'name': entity.get('name'),
                'type': entity.get('type'),
                'scope': entity.get('scope'),
                'source_file': entity.get('source_file'),
                'start_line': entity.get('start_line')
            }

    console.print(f"[green]✓ 找到 {len(fail_messages)} 个 FAIL_MESSAGE 实体[/green]")

    # 显示FAIL_MESSAGE实体
    if args.show_all_messages or len(fail_messages) <= 20:
        print_fail_messages(fail_messages)

    # 显示匹配详情
    if args.show_matching_details:
        log_lines = log_text.split('\n')
        print_matching_details(log_lines, fail_messages, log_parser)

    # 执行完整的日志解析
    console.print("\n[bold cyan]═══ 执行日志解析 ═══[/bold cyan]")
    result = log_parser.parse(log_text)

    # 显示解析结果
    console.print("\n[bold green]解析结果:[/bold green]")
    console.print(f"  推断入口: {result.get('inferred_entry', 'N/A')}")
    console.print(f"  推断错误点: {result.get('inferred_error_point', 'N/A')}")
    console.print(f"  关键函数: {result.get('key_functions', [])}")
    console.print(f"  匹配行数: {len(result.get('line_matches', []))}")
    console.print(f"  涉及函数数: {len(result.get('all_functions', []))}")

    # 显示匹配的行
    if result.get('line_matches'):
        console.print("\n[bold cyan]匹配的日志行:[/bold cyan]")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("行号", style="dim", width=6)
        table.add_column("函数", style="cyan", width=30)
        table.add_column("日志内容", style="green")

        for match in result['line_matches'][:10]:  # 只显示前10行
            table.add_row(
                str(match.get('line_number', '')),
                str(match.get('function', ''))[:28],
                str(match.get('matched_text', ''))[:60] + "..." if len(str(match.get('matched_text', ''))) > 60 else str(match.get('matched_text', ''))
            )

        console.print(table)
        if len(result['line_matches']) > 10:
            console.print(f"[dim]（显示前10行，共 {len(result['line_matches'])} 行）[/dim]")


if __name__ == '__main__':
    main()
