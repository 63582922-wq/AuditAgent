from __future__ import annotations

from typing import Any, Dict, List

PIPELINE_STEP_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_step",
            "description": "执行一条流水线步骤（内环确定性工具）",
            "parameters": {
                "type": "object",
                "properties": {
                    "step": {
                        "type": "string",
                        "enum": [
                            "classifying",
                            "parsing",
                            "extracting",
                            "running_rules",
                            "cross_checking",
                            "adjudicating",
                            "generating_report",
                        ],
                        "description": "要执行的步骤",
                    },
                    "reason": {"type": "string", "description": "选择该步骤的理由（一句话）"},
                },
                "required": ["step", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_analysis",
            "description": "所有必要步骤已完成，结束分析",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "完成摘要"},
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_state",
            "description": "查看当前项目分析进度与中间结果摘要",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

STEP_DEPENDENCIES: Dict[str, List[str]] = {
    "classifying": [],
    "parsing": ["classifying"],
    "extracting": ["parsing"],
    "running_rules": ["extracting"],
    "cross_checking": ["running_rules"],
    "adjudicating": ["running_rules"],
    "generating_report": ["adjudicating"],
}

REQUIRED_FOR_FINISH = frozenset(
    {"classifying", "parsing", "running_rules", "adjudicating", "generating_report"}
)
