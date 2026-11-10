"""
llm.py - the ONE place agents talk to a language model.

In simple words:
    A node says "I am the writer, here is my prompt file and my inputs" and gets
    back either a typed object (structured output) or text. This file decides:
      - WHICH model (from agent/config.yaml -> models.profiles.<profile>.nodes)
      - the fallback model if the first one fails (cheap nodes)
      - timeouts and retries
      - how many tokens were used and what that cost (for budgets and reports)

    Prompts live in agent/prompts/<name>.md (never inside Python code).

Fake mode (GIGBID_FAKE_LLM=1) returns canned answers so tests and CI run without
an API key or network. Real runs always use the real model.
"""

import os
import re
from pathlib import Path
from string import Template

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agent.settings import CONFIG

PROMPTS = Path(__file__).resolve().parent / "prompts"
MCFG = CONFIG["models"]


def profile() -> dict:
    return MCFG["profiles"][os.getenv("MODEL_PROFILE", MCFG["profile"])]


def model_for(node: str) -> str:
    return profile()["nodes"][node]


def load_prompt(name: str) -> tuple[str, str]:
    """Return (version, template text) of agent/prompts/<name>.md. First line: 'version: X'."""
    raw = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    m = re.match(r"<!--\s*version:\s*(\S+)\s*-->\s*\n", raw)
    return (m.group(1) if m else "0"), raw[m.end():] if m else raw


def render(name: str, /, **vars) -> str:
    _, text = load_prompt(name)
    return Template(text).safe_substitute(**{k: v for k, v in vars.items()})


def _chat(model: str) -> ChatOpenAI:
    p = profile()
    return ChatOpenAI(model=model, base_url=p["base_url"], api_key=os.getenv(p["api_key_env"], "missing"),
                      timeout=MCFG["timeout_seconds"], max_retries=2, temperature=0.3, **p.get("extra", {}))


def cost_usd(model: str, usage: dict) -> float:
    pin, pout = MCFG["prices"].get(model, [0, 0])
    return (usage.get("input_tokens", 0) * pin + usage.get("output_tokens", 0) * pout) / 1_000_000


def _usage(msg, model: str, node: str) -> dict:
    u = getattr(msg, "usage_metadata", None) or {}
    usage = {"node": node, "model": model, "input_tokens": u.get("input_tokens", 0),
             "output_tokens": u.get("output_tokens", 0)}
    usage["cost_usd"] = cost_usd(model, usage)
    return usage


async def structured(node: str, prompt: str, schema: type[BaseModel], /, **vars) -> tuple[BaseModel, dict]:
    """Ask the node's model for an object matching `schema`. Returns (object, usage)."""
    text = render(prompt, **vars)
    if os.getenv("GIGBID_FAKE_LLM") == "1":
        from agent.fake_llm import fake_structured

        return fake_structured(prompt, schema, vars), {"node": node, "model": "fake", "input_tokens": 0,
                                                       "output_tokens": 0, "cost_usd": 0.0}
    models = [model_for(node), profile()["fallback"]]
    last = None
    for model in dict.fromkeys(models):                       # primary, then fallback (if different)
        try:
            r = await _chat(model).with_structured_output(schema, method="json_schema", include_raw=True).ainvoke(text)
            if r["parsed"] is None:
                raise ValueError(f"model returned unparseable output: {r.get('parsing_error')}")
            return r["parsed"], _usage(r["raw"], model, node)
        except Exception as e:  # noqa: BLE001  (any provider error -> try the fallback)
            last = e
    raise RuntimeError(f"{node}: all models failed: {type(last).__name__}: {last}")


async def text(node: str, prompt: str, /, **vars) -> tuple[str, dict]:
    """Ask the node's model for plain text. Returns (text, usage)."""
    t = render(prompt, **vars)
    if os.getenv("GIGBID_FAKE_LLM") == "1":
        from agent.fake_llm import fake_text

        return fake_text(prompt, vars), {"node": node, "model": "fake", "input_tokens": 0,
                                         "output_tokens": 0, "cost_usd": 0.0}
    last = None
    for model in dict.fromkeys([model_for(node), profile()["fallback"]]):
        try:
            msg = await _chat(model).ainvoke(t)
            return msg.content.strip(), _usage(msg, model, node)
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"{node}: all models failed: {type(last).__name__}: {last}")
