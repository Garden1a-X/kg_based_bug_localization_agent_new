"""
日志工具模块
统一的日志记录和美化输出
"""
import sys
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from pathlib import Path


# 创建Rich Console实例
console = Console()


def setup_logger(log_file: str = "logs/agent.log", log_level: str = "INFO"):
    """
    配置loguru日志
    
    Args:
        log_file: 日志文件路径
        log_level: 日志级别
    """
    # 创建日志目录
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    
    # 移除默认handler
    logger.remove()
    
    # 添加控制台输出（带颜色）
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True
    )
    
    # 添加文件输出
    logger.add(
        log_file,
        rotation="100 MB",
        retention="10 days",
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )
    
    return logger


def print_success(message: str):
    """打印成功消息"""
    console.print(f"[green]✓[/green] {message}")


def print_warning(message: str):
    """打印警告消息"""
    console.print(f"[yellow]⚠[/yellow] {message}")


def print_error(message: str):
    """打印错误消息"""
    console.print(f"[red]✗[/red] {message}")


def print_info(message: str):
    """打印信息消息"""
    console.print(f"[blue]ℹ[/blue] {message}")


def print_panel(title: str, content: str, style: str = "blue"):
    """打印面板"""
    console.print(Panel(content, title=title, border_style=style))


def print_code(code: str, language: str = "python"):
    """打印代码高亮"""
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    console.print(syntax)


def print_header(text: str):
    """打印标题"""
    console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
    console.print(f"[bold cyan]{text.center(60)}[/bold cyan]")
    console.print(f"[bold cyan]{'='*60}[/bold cyan]\n")


def print_step(step_num: int, total: int, message: str):
    """打印步骤信息"""
    console.print(f"[bold magenta]步骤 {step_num}/{total}:[/bold magenta] {message}")


# 初始化logger（可在main中重新配置）
logger = setup_logger()
