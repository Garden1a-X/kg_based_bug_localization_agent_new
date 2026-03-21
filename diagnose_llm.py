#!/usr/bin/env python3
"""
LLM 连通性诊断脚本 - 逐层排查问题
用法: python diagnose_llm.py --base-url http://10.12.208.86:8502 --api-key kw-xxx --model gpt-4o-mini
"""
import argparse
import socket
import sys
from urllib.parse import urlparse


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--api-key",  default="EMPTY")
    p.add_argument("--model",    default="gpt-4o-mini")
    return p.parse_args()


def step1_tcp(host, port):
    print(f"\n[步骤1] TCP 连通性测试 {host}:{port} ...")
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        print(f"  OK  能连通")
        return True
    except Exception as e:
        print(f"  FAIL  无法连接: {e}")
        print("  => 检查: IP/端口是否正确、防火墙、VPN、机器是否运行")
        return False


def step2_http(base_url, api_key):
    import requests
    print(f"\n[步骤2] HTTP 基础请求 GET {base_url} ...")
    try:
        r = requests.get(base_url, timeout=5,
                         headers={"Authorization": f"Bearer {api_key}"})
        print(f"  状态码: {r.status_code}")
        print(f"  响应体: {r.text[:300]}")
        return True
    except Exception as e:
        print(f"  FAIL  {e}")
        return False


def step3_models(base_url, api_key):
    import requests
    # 规范化 base_url
    urls_to_try = []
    if not base_url.rstrip("/").endswith("/v1"):
        urls_to_try.append(base_url.rstrip("/") + "/v1/models")
    urls_to_try.append(base_url.rstrip("/") + "/models")

    print(f"\n[步骤3] 获取模型列表 ...")
    for url in urls_to_try:
        print(f"  GET {url}")
        try:
            r = requests.get(url, timeout=10,
                             headers={"Authorization": f"Bearer {api_key}",
                                      "Content-Type": "application/json"})
            print(f"  状态码: {r.status_code}")
            print(f"  响应: {r.text[:500]}")
        except Exception as e:
            print(f"  ERROR: {e}")


def step4_chat(base_url, api_key, model):
    import requests, json
    # 尝试两种路径
    urls_to_try = []
    if not base_url.rstrip("/").endswith("/v1"):
        urls_to_try.append(base_url.rstrip("/") + "/v1/chat/completions")
    urls_to_try.append(base_url.rstrip("/") + "/chat/completions")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 20,
    }

    print(f"\n[步骤4] Chat Completion 测试 ...")
    for url in urls_to_try:
        print(f"  POST {url}")
        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=30,
            )
            print(f"  状态码: {r.status_code}")
            print(f"  响应: {r.text[:600]}")
            if r.status_code == 200:
                data = r.json()
                content = data["choices"][0]["message"]["content"]
                print(f"\n  [OK] 模型回复: {content}")
                return True
        except Exception as e:
            print(f"  ERROR: {e}")
    return False


def step5_openai_sdk(base_url, api_key, model):
    print(f"\n[步骤5] openai SDK 测试 ...")
    # 自动补 /v1
    sdk_url = base_url.rstrip("/")
    if not sdk_url.endswith("/v1"):
        sdk_url_v1 = sdk_url + "/v1"
    else:
        sdk_url_v1 = sdk_url

    for url in [sdk_url_v1, sdk_url]:
        print(f"  base_url={url}")
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=url)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=20,
                timeout=30,
            )
            print(f"  [OK] 回复: {resp.choices[0].message.content}")
            print(f"\n  => 在代码里请用 base_url='{url}'")
            return url
        except Exception as e:
            print(f"  FAIL: {e}")
    return None


def main():
    args = parse_args()
    parsed = urlparse(args.base_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    print("=" * 60)
    print(f"诊断目标: {args.base_url}")
    print(f"模型:     {args.model}")
    print("=" * 60)

    if not step1_tcp(host, port):
        print("\n=> TCP 不通，后续步骤跳过")
        sys.exit(1)

    step2_http(args.base_url, args.api_key)
    step3_models(args.base_url, args.api_key)
    ok = step4_chat(args.base_url, args.api_key, args.model)
    if not ok:
        step5_openai_sdk(args.base_url, args.api_key, args.model)


if __name__ == "__main__":
    main()
