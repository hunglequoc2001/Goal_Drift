import json

from bcm_validity.features import compute_features
from bcm_validity.parsers import (author_nebius_actions, author_swe_smith_actions,
                                  canonical_command, role_aware_nebius, role_aware_swe_smith)

PLAIN = json.dumps([
    {"role": "system", "content": "You can run bash"},
    {"role": "user", "content": "<pr_description>fix it</pr_description>"},
    {"role": "assistant", "content": "Look.\n<function=bash>\n<parameter=command>grep -r foo /testbed</parameter>\n</function>"},
    {"role": "user", "content": "OBSERVATION:\nTraceback (most recent call last)"},
    {"role": "assistant", "content": "<function=str_replace_editor>\n<parameter=command>view</parameter>\n<parameter=path>/testbed/a.py</parameter>\n</function>"},
    {"role": "user", "content": "OBSERVATION:\nok"},
    {"role": "assistant", "content": "<function=submit>\n</function>"},
])
STRUCT = json.dumps([
    {"role": "system", "content": "sys", "message_type": "system_prompt"},
    {"role": "user", "content": "task", "message_type": "observation"},
    {"role": "assistant", "content": "thinking", "message_type": "action", "action": "grep -r foo /testbed",
     "tool_calls": [{"function": {"name": "bash", "arguments": "{\"command\": \"grep -r foo /testbed\"}"}}]},
    {"role": "tool", "content": "OBSERVATION:\nTraceback", "message_type": "observation"},
    {"role": "assistant", "content": "done", "message_type": "action", "action": "submit",
     "tool_calls": [{"function": {"name": "submit", "arguments": "{}"}}]},
])
NEB = [
    {"role": "system", "system_prompt": "SETTING", "text": None},
    {"role": "user", "system_prompt": None, "text": "ISSUE"},
    {"role": "ai", "system_prompt": None, "text": "Let's look.\n```\nopen a.py\n```"},
    {"role": "user", "system_prompt": None, "text": "TypeError: bad"},
    {"role": "ai", "system_prompt": None, "text": "Done.\n```\nsubmit\n```"},
]


def test_author_smith_plain_is_empty():
    assert author_swe_smith_actions(PLAIN) == []


def test_author_smith_structured_takes_thought_text():
    assert author_swe_smith_actions(STRUCT) == ["thinking", "done"]


def test_author_nebius_keeps_every_message():
    assert author_nebius_actions(NEB) == ["SETTING", "ISSUE", "Let's look.\n```\nopen a.py\n```",
                                          "TypeError: bad", "Done.\n```\nsubmit\n```"]


def test_role_aware_formats_agree():
    sp, op, fp = role_aware_swe_smith(PLAIN)
    ss, os_, fs = role_aware_swe_smith(STRUCT)
    assert (fp, fs) == ("plain", "structured")
    assert sp == ["grep -r foo /testbed", "str_replace_editor view /testbed/a.py", "submit"]
    assert ss == ["grep -r foo /testbed", "submit"]
    assert "Traceback" in op[0] and "Traceback" in os_[0]


def test_role_aware_nebius():
    s, o, _ = role_aware_nebius(NEB)
    assert s == ["open a.py", "submit"] and o == ["TypeError: bad", ""]
    f = compute_features(s, o)
    assert f["total_steps"] == 2 and f["error_flag_count"] == 0.5


def test_canonical_command():
    assert canonical_command("bash", {"command": " ls "}) == "ls"
    assert canonical_command("str_replace_editor", {"command": "view", "path": "/a"}) == "str_replace_editor view /a"
