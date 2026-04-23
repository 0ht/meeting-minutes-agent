"""Microsoft Foundry **Prompt Agent** (new API) terminology lookup.

Each pipeline stage (script / minutes / terminology) is fronted by a
Foundry Prompt Agent that has the ``lookup_terminology`` Function Tool
registered in its definition. Agents are pre-created by
``backend/scripts/register_foundry_agents.py`` (run once after each
instructions/tool-schema change) and become visible in the new Foundry
portal "Agents" page.

Runtime invocation goes through the Azure OpenAI **Responses API** with
``extra_body={"agent": {"name": ..., "type": "agent_reference"}}`` so the
service uses the saved agent's instructions/model/tools. We drive the
function-call loop client-side: when the response contains
``function_call`` output items, we execute ``lookup_terminology`` locally
and submit ``function_call_output`` items via a follow-up
``responses.create`` with ``previous_response_id``.

Public surface (unchanged from the legacy Assistants implementation):

    await run_foundry_agent(
        agent_key="script",          # one of: script | minutes | terminology
        name=...,                     # ignored at runtime (baked into agent)
        instructions=...,             # ignored at runtime (baked into agent)
        user_message="...",
        response_format=...,          # ignored at runtime (baked into agent)
    ) -> str | None
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.agents import terminology_store
from app.agents.foundry_client import get_chat_client, get_chat_deployment

logger = logging.getLogger(__name__)


# ── agent_key → Foundry agent name (must match register_foundry_agents.py) ──
AGENT_NAMES: dict[str, str] = {
    "script": "meeting-script-agent",
    "minutes": "meeting-minutes-agent",
    "terminology": "meeting-terminology-agent",
}

MAX_TOOL_ROUNDS = 5  # safety cap on function-call loop iterations


# ── Tool implementation (sync — invoked from async via to_thread) ────────────


def lookup_terminology(terms: list[str]) -> str:
    """社内・業界用語辞書を参照し、用語の正式表記 (canonical) と定義 (definition) を返す。"""
    if not isinstance(terms, list):
        terms = [str(terms)]
    cleaned = [str(t) for t in terms if t]
    results = terminology_store.lookup(cleaned)
    return json.dumps({"results": results}, ensure_ascii=False)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _call_attr(item: Any, attr: str) -> Any:
    """Read *attr* from either an SDK model or a dict-shaped item."""
    if isinstance(item, dict):
        return item.get(attr)
    return getattr(item, attr, None)


def _extract_function_calls(response: Any) -> list[Any]:
    """Return the ``function_call`` output items from a Responses API result."""
    out = getattr(response, "output", None) or []
    calls = []
    for item in out:
        if _call_attr(item, "type") == "function_call":
            calls.append(item)
    return calls


def _extract_output_text(response: Any) -> str:
    """Best-effort extraction of the final assistant text."""
    text = getattr(response, "output_text", None)
    if text:
        return text

    parts: list[str] = []
    for item in getattr(response, "output", None) or []:
        if _call_attr(item, "type") != "message":
            continue
        for content in _call_attr(item, "content") or []:
            if _call_attr(content, "type") in ("output_text", "text"):
                value = _call_attr(content, "text")
                if isinstance(value, dict):
                    value = value.get("value")
                if value:
                    parts.append(value)
    return "".join(parts)


# ── Main async entrypoint ────────────────────────────────────────────────────


async def run_foundry_agent(
    *,
    agent_key: str,
    name: str | None = None,  # noqa: ARG001 (kept for backwards compat)
    instructions: str | None = None,  # noqa: ARG001 (baked into agent)
    user_message: str,
    response_format: dict[str, Any] | None = None,  # noqa: ARG001 (baked into agent)
) -> str | None:
    """Invoke a pre-registered Foundry Prompt Agent and return its final text.

    Returns ``None`` when Foundry is not configured (callers fall back to
    a mock implementation).
    """
    client = get_chat_client()
    if client is None:
        return None

    agent_name = AGENT_NAMES.get(agent_key)
    if not agent_name:
        logger.error("Unknown agent_key=%s; cannot route to Foundry agent", agent_key)
        return None

    # Warm the in-process terminology cache before the sync tool can run.
    await terminology_store.get_terminology()

    deployment = get_chat_deployment()
    agent_ref = {"agent_reference": {"name": agent_name, "type": "agent_reference"}}

    # Initial request.
    response = await client.responses.create(
        model=deployment,
        input=[{"role": "user", "content": user_message}],
        extra_body=agent_ref,
    )

    # Function-call loop.
    rounds = 0
    while rounds < MAX_TOOL_ROUNDS:
        calls = _extract_function_calls(response)
        if not calls:
            break
        rounds += 1

        tool_inputs: list[dict[str, Any]] = []
        for call in calls:
            call_id = _call_attr(call, "call_id") or _call_attr(call, "id")
            fn_name = _call_attr(call, "name")
            raw_args = _call_attr(call, "arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}

            if fn_name == "lookup_terminology":
                output = await asyncio.to_thread(
                    lookup_terminology, args.get("terms", [])
                )
            else:
                logger.warning("Unhandled tool call: %s", fn_name)
                output = json.dumps({"error": f"unknown tool {fn_name}"})

            tool_inputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output,
                }
            )

        logger.info(
            "Foundry tool round=%d agent=%s calls=%d",
            rounds,
            agent_name,
            len(calls),
        )

        response = await client.responses.create(
            model=deployment,
            input=tool_inputs,
            previous_response_id=response.id,
            extra_body=agent_ref,
        )
    else:
        if rounds >= MAX_TOOL_ROUNDS and _extract_function_calls(response):
            logger.warning(
                "Foundry agent %s exceeded MAX_TOOL_ROUNDS=%d",
                agent_name,
                MAX_TOOL_ROUNDS,
            )

    return _extract_output_text(response)
