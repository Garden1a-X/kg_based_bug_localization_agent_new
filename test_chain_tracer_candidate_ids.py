from agents.chain_tracer_agent import CallChainTracerAgent


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
