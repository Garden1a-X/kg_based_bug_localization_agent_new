from agents.log_parser_agent import LogParserAgent


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


def test_precise_fail_message_matches_do_not_merge_text_extracted_functions():
    parser = LogParserAgent(enable_llm=False, kg_interface=FakeKG())

    result = parser.parse_log(
        "first failure\n"
        "second failure while waiting for call completion\n"
    )

    assert result["functions"] == ["first_error_func", "second_error_func"]
    assert result["key_functions"] == ["first_error_func", "second_error_func"]
    assert "call" not in result["functions"]
    assert result["inferred_error_point"] == "first_error_func"
    assert result["inferred_entry"] is None
    assert result["need_more_info"] is False
    assert result["fallback_mode"] is False
