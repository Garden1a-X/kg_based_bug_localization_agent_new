#!/usr/bin/env python3
"""
LLM 连通性测试脚本
用法: python test_llm.py --backend openai --base-url http://... --api-key xxx --model gpt-4o-mini
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ioctl_fops_mapper'))


def parse_args():
    p = argparse.ArgumentParser(description="测试 LLM 连通性")
    p.add_argument("--backend", default="openai", choices=["openai", "ollama", "local"])
    p.add_argument("--base-url", default=None, help="OpenAI-compatible base_url")
    p.add_argument("--api-key",  default="EMPTY")
    p.add_argument("--model",    default="gpt-4o-mini")
    p.add_argument("--host",     default="http://localhost:11434", help="Ollama host")
    return p.parse_args()


def main():
    args = parse_args()

    from llm.llm_client import LLMClient

    print(f"后端: {args.backend}")
    print(f"模型: {args.model}")

    if args.backend == "openai":
        if not args.base_url:
            print("[ERROR] openai 后端需要 --base-url")
            sys.exit(1)
        print(f"URL:  {args.base_url}")
        print(f"Key:  {args.api_key[:4]}{'*'*(len(args.api_key)-4) if len(args.api_key)>4 else ''}")
        client = LLMClient(backend="openai", base_url=args.base_url,
                           api_key=args.api_key, model=args.model)
    elif args.backend == "ollama":
        print(f"Host: {args.host}")
        client = LLMClient(backend="ollama", host=args.host, model=args.model)
    else:
        print(f"URL:  {args.base_url or 'http://localhost:8000'}")
        client = LLMClient(backend="local",
                           server_url=args.base_url or "http://localhost:8000",
                           model=args.model)

    print()
    if not client.is_available():
        print("[FAIL] LLM 客户端初始化失败")
        sys.exit(1)

    print("[OK] 客户端初始化成功，发送测试请求...")
    response = client.complete(
        prompt="请用一句话介绍 Linux 内核的 ioctl 机制。",
        system_prompt="你是 Linux 内核专家。",
        max_tokens=100,
        timeout=30,
    )

    if response:
        print(f"\n[OK] LLM 响应成功：\n{response}")
    else:
        print("\n[FAIL] 没有收到响应")
        sys.exit(1)


if __name__ == "__main__":
    main()
