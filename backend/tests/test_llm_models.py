import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import StreamThoughtSplitter, parse_openai_model_ids, pick_listed_model, split_thinking_from_answer


def test_parse_openai_model_ids_from_llama_cpp_payload():
    payload = {
        "object": "list",
        "data": [
            {"id": "gemma-4-e4b-it-q4_k_m.gguf", "object": "model"},
            {"id": "qwen2.5-7b-instruct", "object": "model"},
        ],
    }
    assert parse_openai_model_ids(payload) == [
        "gemma-4-e4b-it-q4_k_m.gguf",
        "qwen2.5-7b-instruct",
    ]


def test_parse_openai_model_ids_ignores_junk():
    assert parse_openai_model_ids({"data": [1, {"id": "ok"}, ""]}) == ["ok"]
    assert parse_openai_model_ids(None) == []


def test_pick_listed_model_prefers_env_when_present():
    models = ["qwen2.5-7b-instruct", "llama-3"]
    assert pick_listed_model(models, "llama-3") == "llama-3"
    assert pick_listed_model(models, "gemma") == "qwen2.5-7b-instruct"
    assert pick_listed_model([], "gemma") is None


def test_split_thinking_from_answer_react():
    thought, answer = split_thinking_from_answer(
        "Thought: I should call the tool.\nAction: analyze_weibull\nFinal Answer: B10 is 149 h."
    )
    assert "I should call the tool" in thought
    assert answer == "B10 is 149 h."


def test_split_thinking_from_answer_think_tags():
    thought, answer = split_thinking_from_answer("<think>plan the fit</think>\nB10 is 149 h.")
    assert thought == "plan the fit"
    assert "B10 is 149 h." in answer


def test_split_does_not_swallow_reliability_markdown():
    md = (
        "## Results\n\n"
        "Observation: $\\beta > 1$ indicates wear-out.\n\n"
        "| $\\beta$ | $\\eta$ |\n| --- | --- |\n| 2.1 | 400 |\n\n"
        "Action: replace the bearing at B10."
    )
    thought, answer = split_thinking_from_answer(md)
    assert thought == ""
    assert "wear-out" in answer
    assert "| 2.1 | 400 |" in answer
    assert "Action: replace" in answer


def test_stream_splitter_routes_react_then_answer():
    splitter = StreamThoughtSplitter()
    kinds = []
    for chunk in ["Thought: use the tool\n", "Final Answer: ", "B10 is 149 h."]:
        kinds.extend(splitter.feed(chunk))
    kinds.extend(splitter.flush())
    thought = "".join(text for kind, text in kinds if kind == "thought")
    answer = "".join(text for kind, text in kinds if kind == "token")
    assert "use the tool" in thought
    assert "B10 is 149 h." in answer
    assert "Thought:" not in answer
