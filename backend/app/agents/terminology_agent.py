"""Terminology Agent — enriches meeting minutes with industry/company term definitions.

Uses the shared ``lookup_terminology`` Function Calling tool (see
``terminology_tools``) to ask the LLM to identify terms in the minutes and
fetch canonical names + definitions from the Blob-backed dictionary
(``terminology_store``). This implements options 2-A + 3-A from
``docs/custom-terminology-options.md``.

Falls back to substring matching against the local dictionary copy when no
LLM endpoint is configured.
"""
from __future__ import annotations

import json
import logging

from app.agents.foundry_client import get_agents_client
from app.agents import terminology_store
from app.agents.terminology_tools import run_foundry_agent
from app.config import get_settings
from app.models.schemas import MinutesResult, TerminologyEnhancedResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたは会議議事録の用語集を作成するアシスタントです。

【手順】
1. 議事録 (Markdown) を読み、専門用語・業界用語・社内用語・略語の候補を抽出する。
2. `lookup_terminology` ツールを呼び出し、候補の正式表記 (canonical) と
   定義 (definition) を取得する。
   - 1 度のツール呼び出しで複数語を渡してよい（最大 50 件、最大 3 回まで）。
   - ツールが返した語のみを用語集に採用すること（辞書に存在しない語は載せない）。
3. 議事録末尾に「## 用語集」セクションを追加し、ツールが返した
   {canonical, definition} を表形式で並べる。

必ず以下の JSON 形式で出力してください。マークダウンコードブロックは不要です：
{
  "markdown": "用語集を追加した完全な議事録（Markdown形式）",
  "glossary": [
    {"term": "canonical 表記", "definition": "ツールが返した定義"}
  ]
}

用語集セクションの形式：
## 用語集
| 用語 | 定義 |
|------|------|
| ...  | ...  |
"""


class TerminologyAgent:
    """Enriches minutes with terminology definitions via the lookup_terminology tool."""

    def __init__(self) -> None:
        self.settings = get_settings()

    # ── public interface ──────────────────────────────────────────────────────

    async def enhance(self, minutes: MinutesResult) -> TerminologyEnhancedResult:
        """Add a glossary to *minutes* based on identified terminology."""
        if get_agents_client() is None:
            logger.warning(
                "Foundry project not configured — using rule-based terminology."
            )
            return await self._rule_based_enhance(minutes)

        # Pre-warm the dictionary cache so the sync tool's first call is instant.
        await terminology_store.get_terminology()

        user_message = f"【議事録】\n{minutes.raw_markdown}"

        raw = await run_foundry_agent(
            agent_key="terminology",
            name="meeting-terminology-agent",
            instructions=SYSTEM_PROMPT,
            user_message=user_message,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw or "{}")
        return TerminologyEnhancedResult(
            markdown=data.get("markdown", minutes.raw_markdown),
            glossary=data.get("glossary", []),
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _rule_based_enhance(self, minutes: MinutesResult) -> TerminologyEnhancedResult:
        """Substring matching against the dictionary when no LLM is available."""
        data = await terminology_store.get_terminology()
        text = minutes.raw_markdown

        found: list[dict] = []
        seen: set[str] = set()
        for mapping in data.get("term_mappings", []):
            canonical = mapping["canonical"]
            if canonical in seen:
                continue
            candidates = [canonical] + list(mapping.get("variants", []))
            if any(c and c in text for c in candidates):
                found.append({"term": canonical, "definition": mapping["definition"]})
                seen.add(canonical)

        glossary_md = ""
        if found:
            rows = "\n".join(
                f"| {item['term']} | {item['definition']} |" for item in found
            )
            glossary_md = f"\n## 用語集\n| 用語 | 定義 |\n|------|------|\n{rows}\n"

        return TerminologyEnhancedResult(
            markdown=minutes.raw_markdown + glossary_md,
            glossary=found,
        )
