"""Unit tests for the Exp02 parsers (synthetic SWE-agent 1.1 histories)."""
from bcm02.parse import author_all, author_smith, role_aware, semantic_category

H = [
    {"role": "system", "content": "You are a helpful assistant", "message_type": "system_prompt"},
    {"role": "user", "content": [{"type": "text", "text": "<pr_description>fix bug</pr_description>"}], "message_type": "observation"},
    {"role": "assistant", "content": "", "thought": "", "action": "grep -rn foo /app",
     "tool_calls": [{"function": {"name": "bash", "arguments": '{"command": "grep -rn foo /app"}'}}], "message_type": "action"},
    {"role": "tool", "content": [{"type": "text", "text": "OBSERVATION:\nTraceback (most recent call last)"}], "message_type": "observation"},
    {"role": "assistant", "content": "Let me edit", "thought": "Let me edit", "action": "str_replace_editor str_replace /app/a.py --old_str x --new_str y",
     "tool_calls": "[{'function': {'name': 'str_replace_editor', 'arguments': '{\"command\": \"str_replace\", \"path\": \"/app/a.py\"}'}}]", "message_type": "action"},
    {"role": "tool", "content": "edited", "message_type": "observation"},
    {"role": "assistant", "content": "Exit due to cost limit", "action": "", "message_type": "action"},
]


def test_author_smith_drops_hidden_thoughts():
    assert author_smith(H) == ["Let me edit", "Exit due to cost limit"]


def test_author_all_includes_everything():
    assert len(author_all(H)) == 6  # system, user, tool x2, 2 non-empty assistant (empty one dropped)


def test_role_aware_steps_and_obs():
    r = role_aware(H)
    assert r["steps"] == ["grep -rn foo /app", "str_replace_editor str_replace /app/a.py --old_str x --new_str y"]
    assert "Traceback" in r["obs"][0] and r["obs"][1] == "edited"
    assert r["n_harness_msgs"] == 1 and r["n_action_msgs"] == 3 and r["tools"] == ["bash", "str_replace_editor"]


def test_semantic_categories():
    cases = {
        "grep -rn foo /app": "search", "find /app -name '*.py'": "search", "ls -la /app": "search",
        "cat /app/a.py": "view", "sed -n '1,20p' a.py": "view", "str_replace_editor view /app/a.py": "view",
        "str_replace_editor create /app/r.py --file_text 'x'": "edit", "sed -i 's/a/b/' a.py": "edit",
        "cat > /app/x.py << 'EOF'\nprint(1)\nEOF": "edit", "cd /app && python -m pytest tests/ -q": "test",
        "cd /app && go test ./lib/...": "test", "npm test -- foo": "test", "python reproduce.py": "run",
        "cd /app && node repro.js": "run", "git diff": "vcs", "pip install -e .": "install", "submit": "submit",
        "echo hello": "other",
    }
    for cmd, cat in cases.items():
        assert semantic_category(cmd) == cat, (cmd, semantic_category(cmd), cat)
