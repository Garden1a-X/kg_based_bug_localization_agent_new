#!/usr/bin/env python3
"""
run_ioctl_mapper.py — 入口脚本

将 Linux 源码中的 ioctl() 调用点映射到对应的 file_operations 实例。

用法示例：

  # 最简单：只扫源码（无 KG、无 LLM）
  python run_ioctl_mapper.py \
      --linux-src /path/to/linux \
      --output output/ioctl_mappings.json

  # 使用 KG + LLM（OpenAI 兼容接口）
  python run_ioctl_mapper.py \
      --linux-src /path/to/linux \
      --kg-data-dir /path/to/kg/data \
      --llm-backend openai \
      --llm-base-url http://10.x.x.x:8502 \
      --llm-model gpt-4o-mini \
      --output output/ioctl_mappings.json

  # 使用 Ollama
  python run_ioctl_mapper.py \
      --linux-src /path/to/linux \
      --llm-backend ollama \
      --llm-host http://localhost:11434 \
      --llm-model qwen3:4b \
      --output output/ioctl_mappings.json

  # 只扫 mmc 子系统，限制 50 个文件（快速测试）
  python run_ioctl_mapper.py \
      --linux-src /path/to/linux \
      --subdirs drivers/mmc \
      --max-files 50 \
      --output output/ioctl_mmc_test.json
"""

import argparse
import os
import sys
from loguru import logger

# 保证 repo 根目录在 import 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mapper.mapper_agent import IoctlMapperAgent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 Linux 源码中的 ioctl() 调用点映射到 file_operations 实例",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # 必选 / 核心参数
    parser.add_argument(
        "--linux-src", required=True,
        help="Linux 源码根目录路径",
    )
    parser.add_argument(
        "--output", default="output/ioctl_mappings.json",
        help="输出 JSON 文件路径（默认：output/ioctl_mappings.json）",
    )

    # KG 参数（可选）
    parser.add_argument(
        "--kg-data-dir", default=None,
        help="KG 数据目录（包含 entity.json / relation.json），不提供则跳过 KG 查询",
    )

    # LLM 参数（可选）
    parser.add_argument(
        "--llm-backend", default=None, choices=["openai", "ollama", "local"],
        help="LLM 后端类型，不提供则不使用 LLM（只做启发式匹配）",
    )
    parser.add_argument(
        "--llm-base-url", default=None,
        help="OpenAI 兼容接口的 base_url",
    )
    parser.add_argument(
        "--llm-api-key", default="EMPTY",
        help="API key（默认 EMPTY，适用于本地服务）",
    )
    parser.add_argument(
        "--llm-model", default="gpt-4o-mini",
        help="LLM 模型名称（默认 gpt-4o-mini）",
    )
    parser.add_argument(
        "--llm-host", default="http://localhost:11434",
        help="Ollama host（仅 --llm-backend ollama 时使用）",
    )

    # 扫描参数
    parser.add_argument(
        "--subdirs", nargs="*", default=None,
        help="只扫指定子目录（相对于 linux-src），如 drivers/mmc drivers/usb",
    )
    parser.add_argument(
        "--max-files", type=int, default=0,
        help="最多扫描多少个文件（0 = 不限，用于测试）",
    )
    parser.add_argument(
        "--context-radius", type=int, default=30,
        help="ioctl 调用点前后各取多少行上下文（默认 30）",
    )

    # 日志
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    return parser.parse_args()


def setup_logging(level: str) -> None:
    logger.remove()
    logger.add(sys.stderr, level=level, format="{time:HH:mm:ss} | {level} | {message}")


def load_kg(kg_data_dir: str):
    """加载 KG，返回 KnowledgeGraphInterface 实例，失败返回 None"""
    if not kg_data_dir:
        return None
    try:
        from data.kg_interface import KnowledgeGraphInterface
        logger.info(f"加载 KG: {kg_data_dir}")
        kg = KnowledgeGraphInterface(kg_data_dir)
        logger.info("KG 加载成功")
        return kg
    except Exception as e:
        logger.warning(f"KG 加载失败（将跳过 KG 查询）: {e}")
        return None


def load_llm(args):
    """根据参数创建 LLMClient，失败返回 None"""
    if not args.llm_backend:
        return None
    try:
        from llm.llm_client import LLMClient
        if args.llm_backend == "openai":
            if not args.llm_base_url:
                logger.warning("--llm-backend openai 需要提供 --llm-base-url，跳过 LLM")
                return None
            client = LLMClient(
                backend="openai",
                base_url=args.llm_base_url,
                api_key=args.llm_api_key,
                model=args.llm_model,
            )
        elif args.llm_backend == "ollama":
            client = LLMClient(
                backend="ollama",
                host=args.llm_host,
                model=args.llm_model,
            )
        elif args.llm_backend == "local":
            client = LLMClient(
                backend="local",
                server_url=args.llm_base_url or "http://localhost:8000",
                model=args.llm_model,
            )
        else:
            return None

        if client.is_available():
            logger.info(f"LLM 初始化成功: {client.get_backend_info()}")
        else:
            logger.warning("LLM 初始化但不可用，将跳过 LLM 分析")
        return client
    except Exception as e:
        logger.warning(f"LLM 初始化失败（将跳过 LLM 分析）: {e}")
        return None


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    logger.info("=== ioctl → file_operations 映射器 ===")
    logger.info(f"Linux 源码目录: {args.linux_src}")
    logger.info(f"输出文件: {args.output}")

    # 检查源码目录
    if not os.path.isdir(args.linux_src):
        logger.error(f"Linux 源码目录不存在: {args.linux_src}")
        sys.exit(1)

    # 加载 KG（可选）
    kg = load_kg(args.kg_data_dir)

    # 加载 LLM（可选）
    llm = load_llm(args)

    if not kg and not llm:
        logger.info("未使用 KG 和 LLM，将仅依赖源码扫描和启发式匹配")

    # 创建并运行 Agent
    agent = IoctlMapperAgent(
        linux_src_dir=args.linux_src,
        kg=kg,
        llm_client=llm,
        context_radius=args.context_radius,
        max_files=args.max_files,
        scan_subdirs=args.subdirs,
    )

    result = agent.run()

    # 打印摘要
    stats = result.get("stats", {})
    logger.info(
        f"结果摘要: 总调用点={stats.get('total_call_sites', 0)}, "
        f"已映射={stats.get('mapped', 0)}, "
        f"未解析={stats.get('unresolved', 0)}, "
        f"覆盖率={stats.get('coverage', 0):.1%}"
    )

    # 保存结果
    agent.save_result(result, args.output)
    logger.info("完成")


if __name__ == "__main__":
    main()
