"""Terminology Agent — enriches meeting minutes with industry/company term definitions.

Loads a terminology JSON file, identifies terms present in the minutes,
and appends a glossary section. Uses Azure OpenAI to intelligently select
and explain terms in context.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import AsyncAzureOpenAI

from app.config import get_settings
from app.models.schemas import MinutesResult, TerminologyEnhancedResult

logger = logging.getLogger(__name__)

_TERMINOLOGY_PATH = Path(__file__).parent.parent / "data" / "terminology.json"

SYSTEM_PROMPT = """あなたは会議議事録を補足するアシスタントです。
提供された議事録と用語集をもとに：

1. 議事録に登場する専門用語・業界用語・社内用語を特定する
2. 議事録の末尾に「用語集」セクションを追加する
3. 識別した用語のリストをJSONで返す

必ず以下の JSON 形式で出力してください。マークダウンコードブロックは不要です：
{
  "markdown": "用語集を追加した完全な議事録（Markdown形式）",
  "glossary": [
    {"term": "用語", "definition": "定義・説明"}
  ]
}

用語集セクションの形式：
## 用語集
| 用語 | 定義 |
|------|------|
| ...  | ...  |
"""


class TerminologyAgent:
    """Enriches minutes with terminology definitions from a reference database."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._terminology = self._load_terminology()

    # ── public interface ──────────────────────────────────────────────────────

    async def enhance(self, minutes: MinutesResult) -> TerminologyEnhancedResult:
        """Add a glossary to *minutes* based on identified terminology."""
        if not self.settings.azure_openai_endpoint or not self.settings.azure_openai_key:
            logger.warning(
                "Azure OpenAI credentials not configured — using rule-based terminology."
            )
            return self._rule_based_enhance(minutes)

        client = AsyncAzureOpenAI(
            azure_endpoint=self.settings.azure_openai_endpoint,
            api_key=self.settings.azure_openai_key,
            api_version=self.settings.azure_openai_api_version,
        )

        terminology_text = json.dumps(self._terminology, ensure_ascii=False, indent=2)
        user_message = (
            f"【用語辞書】\n{terminology_text}\n\n"
            f"【議事録】\n{minutes.raw_markdown}"
        )

        response = await client.chat.completions.create(
            model=self.settings.azure_openai_deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        return TerminologyEnhancedResult(
            markdown=data.get("markdown", minutes.raw_markdown),
            glossary=data.get("glossary", []),
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _rule_based_enhance(self, minutes: MinutesResult) -> TerminologyEnhancedResult:
        """Simple keyword matching when OpenAI is unavailable."""
        all_terms: dict[str, str] = {}
        for category in self._terminology.values():
            all_terms.update(category)

        found: list[dict] = []
        text = minutes.raw_markdown
        for term, definition in all_terms.items():
            if term in text:
                found.append({"term": term, "definition": definition})

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

    @staticmethod
    def _load_terminology() -> dict:
        try:
            with _TERMINOLOGY_PATH.open(encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("terminology.json not found — terminology agent will have no data.")
            return {}
