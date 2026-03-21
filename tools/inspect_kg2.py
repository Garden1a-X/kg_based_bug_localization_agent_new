#!/usr/bin/env python3
"""
深度探查 KG 中 greybus fw-mgmt ioctl 链路。
验证：FW_MGMT_IOC_* 宏 → 哪些函数引用它 → 是否能找到 ioctl handler
用法：python inspect_kg2.py
"""
import json
from collections import defaultdict

ENTITY_FILE = "/data/xuao/code_kg/data/linux/entity.json"
RELATION_FILE = "/data/xuao/code_kg/data/linux/relation.jsonl"


def load_entities(path):
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return {str(i): e for i, e in enumerate(data)}
    return data


print("加载实体...")
entities = load_entities(ENTITY_FILE)
# 建立 name → id 的反向索引（只针对 greybus staging 相关）
name_to_ids = defaultdict(list)
greybus_staging_ids = set()
fw_mgmt_ioctl_ids = set()

for eid, e in entities.items():
    src = e.get("source_file", "")
    name = e.get("name", "")
    if "staging/greybus" in src or "greybus/staging" in src:
        greybus_staging_ids.add(eid)
        name_to_ids[name].append(eid)
    if "fw_mgmt" in name.lower() or "FW_MGMT" in name:
        fw_mgmt_ioctl_ids.add(eid)

print(f"greybus staging 实体数: {len(greybus_staging_ids)}")
print(f"含 fw_mgmt 的实体数: {len(fw_mgmt_ioctl_ids)}")

# 打印 greybus staging 中名字含 ioctl 的函数
print("\n--- greybus staging 中含 'ioctl' 的函数 ---")
for eid in greybus_staging_ids:
    e = entities[eid]
    if "ioctl" in e.get("name", "").lower() and e.get("type") == "FUNCTION":
        print(f"  [{eid}] {e['name']} @ {e.get('source_file','').split('linux-5.10/')[-1]}:{e.get('start_line')}")

# 打印 FW_MGMT_IOC_* 宏实体
print("\n--- FW_MGMT_IOC_* 相关实体 ---")
for eid, e in entities.items():
    name = e.get("name", "")
    if "FW_MGMT_IOC" in name:
        print(f"  [{eid}] type={e.get('type')} name={name} @ {e.get('source_file','').split('linux-5.10/')[-1]}:{e.get('start_line')}")

# 打印 CAP_IOC_* 宏实体（对比）
print("\n--- CAP_IOC_* 相关实体 ---")
for eid, e in entities.items():
    name = e.get("name", "")
    if "CAP_IOC" in name:
        print(f"  [{eid}] type={e.get('type')} name={name} @ {e.get('source_file','').split('linux-5.10/')[-1]}:{e.get('start_line')}")

# 收集 fw_mgmt 和 cap_ioctl 相关实体 ID
target_names = {}
for eid, e in entities.items():
    name = e.get("name", "")
    if "FW_MGMT_IOC" in name or "CAP_IOC" in name or "cap_ioctl" in name or "fw_mgmt_ioctl" in name:
        target_names[eid] = name

print(f"\n目标实体共 {len(target_names)} 个")
target_ids = set(target_names.keys())

# 扫描关系，找涉及这些实体的关系
print("\n加载关系（只关注目标实体）...")
rel_count = 0
found_rels = []
with open(RELATION_FILE) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        rel = json.loads(line)
        h, t = str(rel["head"]), str(rel["tail"])
        if h in target_ids or t in target_ids:
            found_rels.append(rel)
            rel_count += 1

print(f"涉及目标实体的关系: {rel_count} 条")

# 按关系类型分组展示
by_type = defaultdict(list)
for r in found_rels:
    by_type[r["type"]].append(r)

for rtype, rels in by_type.items():
    print(f"\n  关系类型 {rtype} ({len(rels)} 条，展示前10):")
    for r in rels[:10]:
        h_name = entities.get(str(r["head"]), {}).get("name", "?")
        t_name = entities.get(str(r["tail"]), {}).get("name", "?")
        h_file = entities.get(str(r["head"]), {}).get("source_file", "").split("linux-5.10/")[-1]
        t_file = entities.get(str(r["tail"]), {}).get("source_file", "").split("linux-5.10/")[-1]
        print(f"    [{r['head']}]{h_name}({h_file}) --{rtype}--> [{r['tail']}]{t_name}({t_file})")

print("\n探查完成。")
