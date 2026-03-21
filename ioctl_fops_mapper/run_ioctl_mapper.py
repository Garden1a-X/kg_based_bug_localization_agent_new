#!/usr/bin/env python3
"""
run_ioctl_mapper.py — ioctl 调用映射入口

调用点查找方式（二选一，KG 始终用于 handler 候选和 LLM 上下文）：
  --linux-src 指定源码目录：扫描源文件，找 '= ioctl(' 赋值调用（推荐）
  不指定 --linux-src：从 KG 的 CALLS 边查找（兜底）

用法示例：

  # 推荐：遍历源码找调用点
  python run_ioctl_mapper.py \\
      --kg-data-dir /data/xuao/code_kg/data/linux \\
      --linux-src /data/xuao/code_kg/data/linux_data \\
      --path-prefix tools/testing \\
      --llm-backend openai \\
      --llm-base-url http://10.x.x.x:8502 \\
      --llm-model gpt-4o-mini \\
      --output output/ioctl_mappings.json

  # 兜底：从 KG CALLS 边找调用点
  python run_ioctl_mapper.py \\
      --kg-data-dir /data/xuao/code_kg/data/linux \\
      --path-mapping /mnt/afs/liyuekeng/workspace/data/linux-5.10:/data/xuao/code_kg/data/linux_data \\
      --llm-backend ollama --llm-model qwen3:4b \\
      --max-sites 20 \\
      --output output/test.json
"""

import argparse
import os
import sys
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def parse_args():
    parser = argparse.ArgumentParser(
        description="ioctl 调用映射（KG-first + LLM-driven）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # KG（必须）
    parser.add_argument("--kg-data-dir", required=True,
                        help="KG 数据目录（含 entity.json / relation.json）")
    parser.add_argument("--path-mapping", default=None,
                        help="KG 路径 → 本机路径，格式：旧前缀:新前缀，"
                             "多个用逗号分隔，例如 /mnt/afs/...:/data/xuao/...")

    # LLM（必须）
    parser.add_argument("--llm-backend", required=True,
                        choices=["openai", "ollama", "local"])
    parser.add_argument("--llm-base-url", default=None,
                        help="OpenAI 兼容接口 base_url")
    parser.add_argument("--llm-api-key", default="EMPTY")
    parser.add_argument("--llm-model", default="gpt-4o-mini")
    parser.add_argument("--llm-host", default="http://localhost:11434",
                        help="Ollama host")

    parser.add_argument("--linux-src", default=None,
                        help="Linux 源码根目录；提供时遍历源文件找 '= ioctl(' 调用点，否则从 KG CALLS 边查找")
    parser.add_argument("--path-prefix", default=None,
                        help="只处理此路径前缀下的调用点，如 tools/testing")

    # 运行控制
    parser.add_argument("--max-sites", type=int, default=0,
                        help="最多处理多少个调用点（0=不限，测试用）")
    parser.add_argument("--output", default="output/ioctl_mappings.json")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    return parser.parse_args()


def parse_path_mapping(mapping_str: str) -> dict:
    """解析 'old1:new1,old2:new2' 格式的路径映射"""
    if not mapping_str:
        return {}
    result = {}
    for pair in mapping_str.split(','):
        pair = pair.strip()
        # 用 ':/' 作分隔符，兼容 Linux 绝对路径（不含 Windows 驱动器号）
        sep_idx = pair.find(':/')
        if sep_idx > 0:
            old = pair[:sep_idx]
            new = pair[sep_idx + 1:]
            result[old] = new
    return result


def setup_logging(level: str):
    logger.remove()
    logger.add(sys.stderr, level=level, format="{time:HH:mm:ss} | {level} | {message}")


def load_kg(kg_data_dir: str, path_mappings: dict):
    from data.kg_interface import KnowledgeGraphInterface
    logger.info(f"加载 KG: {kg_data_dir}")
    kg = KnowledgeGraphInterface(kg_data_dir, path_mappings=path_mappings)
    logger.info("KG 加载成功")
    return kg


def load_llm(args):
    from llm.llm_client import LLMClient
    if args.llm_backend == "openai":
        if not args.llm_base_url:
            logger.error("--llm-backend openai 需要 --llm-base-url")
            sys.exit(1)
        client = LLMClient(backend="openai", base_url=args.llm_base_url,
                           api_key=args.llm_api_key, model=args.llm_model)
    elif args.llm_backend == "ollama":
        client = LLMClient(backend="ollama", host=args.llm_host, model=args.llm_model)
    else:
        client = LLMClient(backend="local",
                           server_url=args.llm_base_url or "http://localhost:8000",
                           model=args.llm_model)

    if not client.is_available():
        logger.error("LLM 不可用，退出")
        sys.exit(1)
    logger.info(f"LLM 初始化成功: {client.get_backend_info()}")
    return client


def main():
    args = parse_args()
    setup_logging(args.log_level)

    path_mappings = parse_path_mapping(args.path_mapping)
    if path_mappings:
        logger.info(f"路径映射: {path_mappings}")

    kg  = load_kg(args.kg_data_dir, path_mappings)
    llm = load_llm(args)

    from mapper.mapper_agent import IoctlMapperAgent
    agent  = IoctlMapperAgent(kg=kg, llm_client=llm, linux_src_dir=args.linux_src or "")
    result = agent.run(max_sites=args.max_sites, path_prefix=args.path_prefix or "")

    stats = result["stats"]
    logger.info(
        f"结果: 总调用点={stats['total_call_sites']}  "
        f"已映射={stats['mapped']}  "
        f"头尾均在KG={stats['both_in_kg']}  "
        f"未解析={stats['unresolved']}  "
        f"覆盖率={stats['coverage']:.1%}"
    )

    agent.save_result(result, args.output)
    logger.info("完成")


if __name__ == "__main__":
    main()
