"""Model-free stand-in for a vLLM server, used only for infrastructure tests of the full-study runner (no GPU, no LLM).

OpenAI-compatible /v1/chat/completions. The served model name selects a scripted policy (one bash block per reply,
as the text-based mini-swe-agent config expects):
  fake-gold        apply the task's ORIGINAL gold patch (found by matching the issue text), then submit the diff
  fake-text        submit the sentence "No changes are needed; the issue is already fixed." instead of a diff
  fake-bigout      print ~3 MB to stdout once (saved-trajectory truncation), then submit
  fake-sleep       run `sleep 600` (agent wall-clock cap)
  fake-noop        submit an empty diff
Usage: python fake_llm.py <port>
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[2] / "data/swe_bench_verified/data/test-00000-of-00001.parquet"
D = pd.read_parquet(DATA)
SUBMIT = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A && git diff --cached"


def gold_for(text):
    for ps, patch in zip(D.problem_statement, D.patch):
        if ps.strip()[:400] in text:
            return patch
    return None


def policy(name, msgs):
    n_assist = sum(m["role"] == "assistant" for m in msgs)
    task = "\n".join(str(m.get("content")) for m in msgs if m["role"] == "user")
    if n_assist == 0:
        return "THOUGHT: look at the repository first.\n\n```mswea_bash_command\ncd /testbed && git status --short && ls | head\n```"
    if name == "fake-gold" and n_assist == 1:
        p = gold_for(task)
        if p:
            return f"THOUGHT: apply the fix.\n\n```mswea_bash_command\ncd /testbed && git apply <<'EOF_FAKE'\n{p}\nEOF_FAKE\n```"
    if name == "fake-bigout" and n_assist == 1:
        return "THOUGHT: produce a lot of output.\n\n```mswea_bash_command\nseq 1 400000\n```"
    if name == "fake-sleep":
        return "THOUGHT: wait.\n\n```mswea_bash_command\nsleep 600\n```"
    if name == "fake-text":
        return 'THOUGHT: the issue is already fixed.\n\n```mswea_bash_command\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && echo "No changes are needed; the issue is already fixed."\n```'
    return f"THOUGHT: done.\n\n```mswea_bash_command\ncd /testbed && {SUBMIT}\n```"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send({"object": "list", "data": [{"id": n, "object": "model"} for n in
                                               ["fake-gold", "fake-text", "fake-bigout", "fake-sleep", "fake-noop"]]})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        txt = policy(req.get("model", ""), req.get("messages", []))
        self._send({"id": "x", "object": "chat.completion", "created": 0, "model": req.get("model"),
                    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": txt}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
