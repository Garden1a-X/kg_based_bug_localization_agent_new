from agents.log_parser_agent import LogParserAgent
from agents.entity_locator_agent import EntityLocatorAgent


class FakeKG:
    def __init__(self):
        self.entity_by_id = {
            "msg-1": {
                "id": "msg-1",
                "name": 'pr_err("first failure")',
                "type": "FAIL_MESSAGE",
                "scope": "first_error_func",
                "source_file": "driver.c",
                "start_line": 10,
            },
            "msg-2": {
                "id": "msg-2",
                "name": 'pr_err("second failure")',
                "type": "FAIL_MESSAGE",
                "scope": "second_error_func",
                "source_file": "driver.c",
                "start_line": 20,
            },
        }
        self.func_name_to_ids = {
            "first_error_func": ["func-1"],
            "second_error_func": ["func-2"],
            "call": ["func-call"],
        }
        self.entities = {
            "FUNCTION": {
                "first_error_func": {
                    "id": "func-1",
                    "name": "first_error_func",
                    "type": "FUNCTION",
                },
                "second_error_func": {
                    "id": "func-2",
                    "name": "second_error_func",
                    "type": "FUNCTION",
                },
                "call": {
                    "id": "func-call",
                    "name": "call",
                    "type": "FUNCTION",
                },
            }
        }

    def find_function(self, func_name):
        return self.entities["FUNCTION"].get(func_name)

    def find_functions_by_pattern(self, pattern):
        return [
            entity
            for name, entity in self.entities["FUNCTION"].items()
            if pattern and pattern.lower() in name.lower()
        ]


def test_precise_fail_message_matches_do_not_merge_text_extracted_functions():
    parser = LogParserAgent(enable_llm=False, kg_interface=FakeKG())

    result = parser.parse_log(
        "first failure\n"
        "second failure while waiting for call completion\n"
    )

    assert result["functions"] == ["first_error_func", "second_error_func"]
    assert result["key_functions"] == ["first_error_func", "second_error_func"]
    assert result["has_precise_log_matches"] is True
    assert "call" not in result["functions"]
    assert result["inferred_error_point"] == "first_error_func"
    assert result["inferred_entry"] == "second_error_func"
    assert result["entry_confidence"] == 0.6
    assert result["need_more_info"] is False
    assert result["fallback_mode"] is False


def test_precise_fail_message_matches_do_not_backfill_start_from_log_functions():
    kg = FakeKG()
    parser = LogParserAgent(enable_llm=False, kg_interface=kg)
    parsed = parser.parse_log("first failure\nsecond failure")

    entities = EntityLocatorAgent(kg).execute(parsed)

    assert entities["start_entity"]["name"] == "second_error_func"
    assert entities["end_entity"]["name"] == "first_error_func"


def test_single_precise_fail_message_match_does_not_infer_entry():
    kg = FakeKG()
    parser = LogParserAgent(enable_llm=False, kg_interface=kg)

    result = parser.parse_log("first failure")

    assert result["functions"] == ["first_error_func"]
    assert result["inferred_error_point"] == "first_error_func"
    assert result["inferred_entry"] is None
    assert result["need_more_info"] is False
    assert result["fallback_mode"] is False
