"""Throughput probe: N concurrent chat completions of fixed length against a vLLM server."""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

base, name = sys.argv[1:3]
c = OpenAI(base_url=base, api_key="EMPTY")
prompt = [{"role": "user", "content": "Write a long, detailed Python tutorial about decorators. " * 20}]


def one(i):
    t = time.time()
    r = c.chat.completions.create(model=name, messages=prompt, max_tokens=1024, temperature=0.7, seed=i,
                                  extra_body={"ignore_eos": True})
    return r.usage.completion_tokens, r.usage.prompt_tokens, time.time() - t


res = {}
for conc in [1, 8, 32]:
    t = time.time()
    with ThreadPoolExecutor(conc) as ex:
        out = list(ex.map(one, range(conc)))
    wall = time.time() - t
    res[conc] = dict(out_tokens=sum(o[0] for o in out), wall_s=round(wall, 1),
                     out_tok_per_s=round(sum(o[0] for o in out) / wall, 1))
print(json.dumps(res))
