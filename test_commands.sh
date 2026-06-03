#!/bin/bash
# 测试命令集合

echo "========================================="
echo "测试 1: 主程序 - 无用户上下文"
echo "========================================="
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log-file /data/xuao/code_kg_search/kg_based_bug_localization_agent/error.log \
    --enable-subgraph-selection \
    --enable-llm-log-analysis \
    --k 5

echo ""
echo "========================================="
echo "测试 2: 主程序 - 提供用户上下文（RK3288）"
echo "========================================="
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --log-file /data/xuao/code_kg_search/kg_based_bug_localization_agent/error.log \
    --enable-subgraph-selection \
    --enable-llm-log-analysis \
    --user-context contexts/rk3288.yaml \
    --k 5

echo ""
echo "========================================="
echo "测试 3: 主程序 - 手动指定起止点（无需用户上下文）"
echo "========================================="
python run_bug_localization.py \
    --data-dir /data/xuao/code_kg_search/linux_test/data \
    --enable-subgraph-selection \
    --start-function dw_mci_rockchip_probe \
    --end-function dw_mci_execute_tuning \
    --k 5

echo ""
echo "========================================="
echo "测试 4: LLM 入口选择调试脚本 - 无用户上下文"
echo "========================================="
python test_llm_entry_selection.py \
    --log-file /data/xuao/code_kg_search/kg_based_bug_localization_agent/error.log \
    --subgraph mmc

echo ""
echo "========================================="
echo "测试 5: LLM 入口选择调试脚本 - 提供用户上下文"
echo "========================================="
python test_llm_entry_selection.py \
    --log-file /data/xuao/code_kg_search/kg_based_bug_localization_agent/error.log \
    --user-context contexts/rk3288.yaml \
    --subgraph mmc

echo ""
echo "========================================="
echo "测试 6: 示例程序 - 标准模式（子图自动选择 + LLM入口选择）"
echo "========================================="
python examples/run_mmc_case_topk.py

echo ""
echo "========================================="
echo "测试 7: 示例程序 - 日志匹配模式（无用户上下文）"
echo "========================================="
python examples/run_mmc_case_topk.py --log-match

echo ""
echo "========================================="
echo "测试 8: 示例程序 - 日志匹配模式（提供用户上下文）"
echo "========================================="
python examples/run_mmc_case_topk.py --mode log-match --user-context contexts/rk3288.yaml

echo ""
echo "所有测试完成！"
