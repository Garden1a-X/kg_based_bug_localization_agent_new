from agents.chain_tracer_agent import CallChainTracerAgent
from data.kg_interface import KnowledgeGraphInterface


class RecordingKG:
    def __init__(self):
        self.calls = []
        self.entity_by_id = {
            "start-1": {
                "id": "start-1",
                "name": "entry",
                "type": "FUNCTION",
                "source_file": "entry.c",
                "start_line": 1,
                "end_line": 10,
            },
            "end-wrong": {
                "id": "end-wrong",
                "name": "target",
                "type": "FUNCTION",
                "source_file": "wrong.c",
                "start_line": 20,
                "end_line": 30,
            },
            "end-right": {
                "id": "end-right",
                "name": "target",
                "type": "FUNCTION",
                "source_file": "right.c",
                "start_line": 40,
                "end_line": 50,
            },
        }
        self.func_name_to_ids = {
            "entry": ["start-1"],
            "target": ["end-wrong", "end-right"],
        }

    def find_top_k_call_paths_with_indirect(self, *args, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("preferred_end_id") != "end-right":
            return []

        return [
            {
                "path": ["entry", "target"],
                "path_ids": ["start-1", "end-right"],
                "edges": ["direct"],
                "call_lines": [42],
                "score": 100,
                "length": 2,
                "avg_call_line": 42,
            }
        ]


def test_execute_top_k_uses_current_candidate_ids_for_disambiguation():
    kg = RecordingKG()
    tracer = CallChainTracerAgent(kg)

    paths = tracer.execute_top_k(
        kg.entity_by_id["start-1"],
        kg.entity_by_id["end-right"],
        k=1,
    )

    assert paths
    assert kg.calls[0]["preferred_start_id"] == "start-1"
    assert kg.calls[0]["preferred_end_id"] == "end-right"
    assert paths[0]["nodes_detailed"][1]["entities"][0]["id"] == "end-right"


def test_top_k_deduplicates_identical_paths_from_duplicate_edges():
    kg = KnowledgeGraphInterface.__new__(KnowledgeGraphInterface)
    kg.entity_by_id = {
        "start": {"id": "start", "name": "entry", "type": "FUNCTION"},
        "mid": {"id": "mid", "name": "mid", "type": "FUNCTION"},
        "end": {"id": "end", "name": "target", "type": "FUNCTION"},
    }
    kg.func_name_to_ids = {
        "entry": ["start"],
        "mid": ["mid"],
        "target": ["end"],
    }
    kg.entities = {"FUNCTION": {}}
    kg.relations = {
        "CALLS": [
            {"head": "start", "tail": "mid", "type": "CALLS", "call_line": 10},
            {"head": "start", "tail": "mid", "type": "CALLS", "call_line": 10},
            {"head": "mid", "tail": "end", "type": "CALLS", "call_line": 20},
            {"head": "mid", "tail": "end", "type": "CALLS", "call_line": 20},
        ]
    }
    kg.decl_to_impl = {}
    kg.impl_to_decl = {}
    kg.async_functions = set()
    kg.async_call_cache = {}
    kg.llm_indirect_call_cache = {}
    kg.call_graph_with_lines = {}
    kg.calls_by_head = {}
    kg.ioctl_calls_by_head = {}
    kg._callees_with_lines_cache = {}
    kg._build_call_graph_with_lines()

    paths = kg.find_top_k_call_paths_with_indirect(
        "entry",
        "target",
        max_depth=4,
        k=5,
        preferred_start_id="start",
        preferred_end_id="end",
    )

    assert len(paths) == 1
    assert paths[0]["path_ids"] == ["start", "mid", "end"]
    assert paths[0]["call_lines"] == [10, 20]


def test_bidirectional_search_stitches_long_direct_chain():
    kg = KnowledgeGraphInterface.__new__(KnowledgeGraphInterface)
    node_ids = ["a", "n1", "n2", "n3", "n4", "n5", "c"]
    kg.entity_by_id = {
        node_id: {"id": node_id, "name": node_id.upper(), "type": "FUNCTION"}
        for node_id in node_ids
    }
    kg.func_name_to_ids = {node_id.upper(): [node_id] for node_id in node_ids}
    kg.entities = {"FUNCTION": {}}
    kg.relations = {
        "CALLS": [
            {"head": src, "tail": dst, "type": "CALLS", "call_line": idx + 1}
            for idx, (src, dst) in enumerate(zip(node_ids, node_ids[1:]))
        ]
    }
    kg.decl_to_impl = {}
    kg.impl_to_decl = {}
    kg.async_functions = set()
    kg.async_call_cache = {}
    kg.llm_indirect_call_cache = {}
    kg._build_call_graph_with_lines()

    paths = kg._find_bidirectional_call_paths(
        start_impl_ids=["a"],
        end_equivalent_ids={"c"},
        max_depth=10,
        k=1,
    )

    assert len(paths) == 1
    assert paths[0]["path_ids"] == node_ids
    assert paths[0]["path"] == [node_id.upper() for node_id in node_ids]
    assert paths[0]["call_lines"] == [1, 2, 3, 4, 5, 6]
    assert paths[0]["method"] == "bidirectional_search"
