#!/usr/bin/env python3
"""
快速探查 KG 内容，重点看 greybus ioctl 相关的实体和关系。
用法：python inspect_kg.py
"""
import json
import sys
from collections import Counter

ENTITY_FILE = "/data/xuao/code_kg/data/linux/entity.json"
RELATION_FILE = "/data/xuao/code_kg/data/linux/relation.jsonl"
KEYWORD = "greybus"  # 也可以改成 fw_mgmt / ioctl 等


def load_entities(path):
    with open(path, "r") as f:
        data = json.load(f)
    # 支持 {id: {...}} 或 [{...}, ...] 两种格式
    if isinstance(data, dict):
        return data
    elif isinstance(data, list):
        return {str(i): e for i, e in enumerate(data)}
    else:
        raise ValueError(f"未知 entity.json 格式: {type(data)}")


def main():
    print("=" * 60)
    print("1. entity.json 结构探查")
    print("=" * 60)
    entities = load_entities(ENTITY_FILE)
    print(f"总实体数: {len(entities)}")

    # 打印前 3 条看字段
    sample_keys = list(entities.keys())[:3]
    for k in sample_keys:
        print(f"  样例 [{k}]: {json.dumps(entities[k], ensure_ascii=False)[:300]}")

    # 统计实体类型
    type_counter = Counter()
    for e in entities.values():
        t = e.get("type") or e.get("entity_type") or e.get("kind") or "unknown"
        type_counter[t] += 1
    print("\n实体类型分布（Top 10）:")
    for t, c in type_counter.most_common(10):
        print(f"  {t}: {c}")

    # 搜索 greybus 相关实体
    print(f"\n关键词 '{KEYWORD}' 相关实体（最多20条）:")
    count = 0
    greybus_ids = set()
    for eid, e in entities.items():
        text = json.dumps(e, ensure_ascii=False).lower()
        if KEYWORD in text:
            greybus_ids.add(eid)
            if count < 20:
                print(f"  [{eid}] {json.dumps(e, ensure_ascii=False)[:200]}")
            count += 1
    print(f"  ... 共 {count} 条")

    # 搜索 fw_mgmt 相关
    print(f"\n关键词 'fw_mgmt' 相关实体（最多10条）:")
    fw_ids = set()
    count = 0
    for eid, e in entities.items():
        text = json.dumps(e, ensure_ascii=False).lower()
        if "fw_mgmt" in text or "fw-mgmt" in text:
            fw_ids.add(eid)
            if count < 10:
                print(f"  [{eid}] {json.dumps(e, ensure_ascii=False)[:300]}")
            count += 1
    print(f"  ... 共 {count} 条")

    print("\n" + "=" * 60)
    print("2. relation.jsonl 结构探查")
    print("=" * 60)
    rel_types = Counter()
    total_rels = 0
    sample_rels = []
    greybus_rels = []

    with open(RELATION_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rel = json.loads(line)
            total_rels += 1
            rtype = rel.get("relation") or rel.get("type") or rel.get("rel") or "unknown"
            rel_types[rtype] += 1
            if len(sample_rels) < 3:
                sample_rels.append(rel)
            if KEYWORD in json.dumps(rel, ensure_ascii=False).lower() and len(greybus_rels) < 10:
                greybus_rels.append(rel)

    print(f"总关系数: {total_rels}")
    print("\n关系类型分布（Top 15）:")
    for t, c in rel_types.most_common(15):
        print(f"  {t}: {c}")

    print("\n样例关系（前3条）:")
    for r in sample_rels:
        print(f"  {json.dumps(r, ensure_ascii=False)[:300]}")

    print(f"\n'{KEYWORD}' 相关关系（最多10条）:")
    for r in greybus_rels:
        print(f"  {json.dumps(r, ensure_ascii=False)[:300]}")

    # 检查 ioctl 相关关系
    print("\n'ioctl' 相关关系（最多10条）:")
    count = 0
    with open(RELATION_FILE, "r") as f:
        for line in f:
            if "ioctl" in line.lower():
                print(f"  {line.strip()[:300]}")
                count += 1
                if count >= 10:
                    break
    if count == 0:
        print("  (无)")

    print("\n探查完成。")


if __name__ == "__main__":
    main()
