from app.services.agent.llm_client import parse_llm_json


def test_parse_llm_json_plain():
    data = parse_llm_json('{"steps":["classify"],"reasoning":"ok"}')
    assert data["steps"] == ["classify"]


def test_parse_llm_json_markdown_with_preamble():
    text = (
        "我已充分了解所有文件。以下为最终分析计划。\n"
        '```json\n{"steps":["classify","parse"],"focus_areas":["签到"]}\n```'
    )
    data = parse_llm_json(text)
    assert data["steps"][:2] == ["classify", "parse"]
    assert data["focus_areas"] == ["签到"]


def test_parse_llm_json_embedded_in_prose():
    text = '说明文字 {"steps":["report"], "reasoning":"done"} 结束'
    data = parse_llm_json(text)
    assert data["steps"] == ["report"]
