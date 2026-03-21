#!/usr/bin/env python3
"""
test_quick.py — ioctl_fops_mapper 快速诊断脚本

逐步输出每阶段结果，方便定位问题。

用法示例：
  python test_quick.py \
      --kg-data-dir /data/xuao/code_kg/data/linux \
      --path-mapping /mnt/afs/.../linux-5.10:/data/xuao/code_kg/data/linux_data \
      --llm-backend openai \
      --llm-base-url http://10.x.x.x:8502 \
      --llm-model gpt-4o-mini \
      --max-sites 5
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger


def parse_args():
    p = argparse.ArgumentParser(description="ioctl_fops_mapper 快速诊断")
    p.add_argument("--kg-data-dir", required=True)
    p.add_argument("--path-mapping", default=None,
                   help="旧前缀:新前缀，多个用逗号分隔")
    p.add_argument("--check-path", default=None,
                   help="只检查路径映射，不加载 KG（传一个 KG 原始路径验证映射是否正确）")
    p.add_argument("--llm-backend", required=True,
                   choices=["openai", "ollama", "local"])
    p.add_argument("--llm-base-url", default=None)
    p.add_argument("--llm-api-key", default="EMPTY")
    p.add_argument("--llm-model", default="gpt-4o-mini")
    p.add_argument("--llm-host", default="http://localhost:11434")
    p.add_argument("--max-sites", type=int, default=5,
                   help="测试处理的调用点数量（默认 5）")
    p.add_argument("--path-prefix", default=None,
                   help="只处理 caller_file 包含此前缀的调用点，如 /drivers/（默认不过滤）")
    p.add_argument("--linux-src", default=None,
                   help="Linux 源码根目录；提供时用源码扫描 '= ioctl(' 找调用点，否则用 KG 查询")
    return p.parse_args()


def parse_path_mapping(s):
    if not s:
        return {}
    result = {}
    for pair in s.split(','):
        pair = pair.strip()
        # 用 ':/' 作分隔符，兼容 Linux 绝对路径（不含 Windows 驱动器号）
        sep_idx = pair.find(':/')
        if sep_idx > 0:
            result[pair[:sep_idx]] = pair[sep_idx + 1:]
    return result


def sep(title=""):
    print("\n" + "=" * 60)
    if title:
        print(f"  {title}")
        print("=" * 60)


def main():
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")

    args = parse_args()
    path_mappings = parse_path_mapping(args.path_mapping)

    # ── 路径映射快速检查（--check-path 时只跑这一步）─────────────
    sep("路径映射诊断")
    print(f"  原始参数: {args.path_mapping}")
    print(f"  解析结果: {path_mappings}")
    if path_mappings:
        for old, new in path_mappings.items():
            print(f"  映射规则: '{old}'  →  '{new}'")
            if os.path.isdir(new):
                print(f"           目标目录存在 ✓")
            else:
                print(f"           目标目录不存在 ✗  ({new})")
    else:
        print("  ✗ 路径映射解析为空！检查 --path-mapping 格式是否为 /旧前缀:/新前缀")

    if args.check_path:
        test_path = args.check_path
        remapped = test_path
        for old, new in path_mappings.items():
            if test_path.startswith(old):
                remapped = new + test_path[len(old):]
                break
        print(f"\n  测试路径: {test_path}")
        print(f"  重映射后: {remapped}")
        print(f"  文件存在: {'✓' if os.path.isfile(remapped) else '✗'}")
        print()
        return  # 只检查路径，不继续

    # ── Step 0: LLM 连通性 ──────────────────────────────────────
    sep("Step 0: LLM 连通性检查")
    from llm.llm_client import LLMClient
    if args.llm_backend == "openai":
        llm = LLMClient(backend="openai", base_url=args.llm_base_url,
                        api_key=args.llm_api_key, model=args.llm_model)
    elif args.llm_backend == "ollama":
        llm = LLMClient(backend="ollama", host=args.llm_host, model=args.llm_model)
    else:
        llm = LLMClient(backend="local",
                        server_url=args.llm_base_url or "http://localhost:8000",
                        model=args.llm_model)

    if not llm.is_available():
        print("✗ LLM 不可用，退出")
        sys.exit(1)

    ping = llm.complete("回复 OK", max_tokens=10, timeout=30)
    if ping:
        print(f"✓ LLM 可用，回复: {ping.strip()[:80]}")
    else:
        print("✗ LLM 无响应，退出")
        sys.exit(1)

    # ── Step 1: 加载 KG ─────────────────────────────────────────
    sep("Step 1: 加载 KG")
    from data.kg_interface import KnowledgeGraphInterface
    kg = KnowledgeGraphInterface(args.kg_data_dir, path_mappings=path_mappings)
    print(f"✓ KG 加载完成")
    print(f"  实体总数: {len(kg.entity_by_id)}")
    print(f"  函数名索引: {len(kg.func_name_to_ids)} 个函数")
    print(f"  关系类型: {list(kg.relations.keys())}")

    # ── Step 2: 获取 ioctl 调用点 ────────────────────────────────
    if args.linux_src:
        sep("Step 2: 扫描源码查找 '= ioctl(' 调用点")
        from mapper.scanner import IoctlCallScanner
        scanner = IoctlCallScanner(args.linux_src)
        subdirs = [args.path_prefix.lstrip('/')] if args.path_prefix else None
        if subdirs:
            print(f"  扫描子目录: {subdirs}")
        raw_sites = scanner.scan(subdirs=subdirs)
        call_sites = [s.to_call_site_dict() for s in raw_sites]
        print(f"✓ 扫描找到 {len(call_sites)} 个 '= ioctl(' 调用点")
        if not call_sites:
            print("✗ 无调用点，检查 --linux-src 路径和 --path-prefix 是否正确")
            sys.exit(1)
    else:
        sep("Step 2: 查询 ioctl() 调用点（从 KG CALLS 边）")
        call_sites = kg.query_ioctl_call_sites()
        print(f"✓ 共找到 {len(call_sites)} 个调用点")
        if not call_sites:
            print("✗ 无调用点，检查 KG 是否包含 CALLS 关系且 tail.name=='ioctl'")
            sys.exit(1)
        if args.path_prefix:
            prefix = args.path_prefix.replace('\\', '/')
            call_sites = [
                s for s in call_sites
                if prefix in s.get('caller_file', '').replace('\\', '/')
            ]
            print(f"  → 过滤 '{prefix}': {len(call_sites)} 个")

    sample = call_sites[:3]
    print(f"\n  前 {len(sample)} 个样例:")
    for i, s in enumerate(sample):
        print(f"  [{i}] {s['caller_name']}  @ {s['caller_file']}:{s.get('call_line','?')}")

    sites_to_process = call_sites[:args.max_sites]
    print(f"  → 本次处理前 {len(sites_to_process)} 个")

    # ── Step 3: 查询 fops handler 候选 ──────────────────────────
    sep("Step 3: 查询 fops → ioctl handler 候选")
    all_handlers = kg.query_fops_ioctl_handlers()
    print(f"✓ 共找到 {len(all_handlers)} 个 fops → ioctl handler 映射")

    if not all_handlers:
        print("✗ 无候选，检查 KG 是否包含 ASSIGNED_TO 关系且 handler 名含 'ioctl'")
        sys.exit(1)

    print(f"\n  全部 fops 列表（{len(all_handlers)} 条）:")
    for h in all_handlers:
        print(f"    [{h['driver_dir']}]  {h['fops_var']}.unlocked_ioctl = {h['handler_func']}")

    # ── Step 4: 逐条解析（带详细输出）───────────────────────────
    sep(f"Step 4: LLM 解析（处理 {len(sites_to_process)} 个调用点）")
    from mapper.mapper_agent import IoctlMapperAgent
    agent = IoctlMapperAgent(kg=kg, llm_client=llm, linux_src_dir=args.linux_src or "")

    ok, fail, unresolvable = 0, 0, 0
    for idx, site in enumerate(sites_to_process):
        caller = site['caller_name']
        print(f"\n  [{idx+1}/{len(sites_to_process)}] {caller} @ {site['caller_file']}:{site.get('call_line','?')}")

        # 读源码（scanner 已预置 _context_lines；否则通过 KG 读文件）
        context_lines = site.get('_context_lines')
        if context_lines is not None:
            src = '\n'.join(context_lines)
        else:
            src = kg.read_entity_source({
                "source_file": site['caller_file'],
                "start_line":  site['caller_start'],
                "end_line":    site['caller_end'],
            })
        if not src:
            print(f"    ✗ 无法读取源码（路径映射是否正确？）")
            fail += 1
            continue
        print(f"    ✓ 源码读取成功（{src.count(chr(10))} 行）")

        # 过滤候选
        candidates = agent._filter_candidates(site, all_handlers)
        print(f"    候选 handler 数: {len(candidates)}")
        if candidates:
            print(f"    top-3 候选: {[c['handler_func'] for c in candidates[:3]]}")

        # LLM 选择
        llm_result = llm.resolve_ioctl_handler(
            caller_source=src,
            call_line=site.get('call_line'),
            caller_file=site['caller_file'],
            candidates=candidates,
        )

        if llm_result is None:
            print(f"    ✗ LLM 返回 None")
            fail += 1
            continue

        sel_idx = llm_result.get("selected_index", -1)
        conf = llm_result.get("confidence", 0)
        reason = llm_result.get("reasoning", "")

        if sel_idx == -1:
            # LLM 合法地判断无法静态确定（如动态分发、PHY层转发等）
            print(f"    ○ 无法静态确定（动态分发）")
            print(f"      reasoning: {reason}")
            unresolvable += 1
            continue

        if sel_idx < 0 or sel_idx >= len(candidates):
            print(f"    ✗ LLM 返回非法下标 (selected_index={sel_idx})")
            fail += 1
            continue

        chosen = candidates[sel_idx]
        print(f"    ✓ 选中: {chosen['handler_func']}  (confidence={conf}/10)")
        print(f"      fops_var: {chosen['fops_var']}")
        print(f"      handler_file: {chosen['source_file']}")
        print(f"      reasoning: {reason}")
        ok += 1

    # ── 汇总 ────────────────────────────────────────────────────
    sep("汇总")
    print(f"  处理: {len(sites_to_process)}  成功: {ok}  动态分发: {unresolvable}  失败: {fail}")
    print(f"  解析率: {ok / len(sites_to_process):.0%}" if sites_to_process else "")
    print(f"\n  KG 总调用点: {total}  handler 候选: {len(all_handlers)}")
    print()


if __name__ == "__main__":
    main()
