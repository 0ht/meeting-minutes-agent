"""Script Agent — converts a raw transcript into a clean, structured script.

Uses Azure OpenAI (GPT-4o) to:
- Clean up filler words, overlapping speech, and transcription errors
- Identify speakers and attribute utterances
- Organize the conversation chronologically
- Identify agenda items discussed
"""
from __future__ import annotations

import json
import logging

from app.agents.foundry_client import get_agents_client
from app.agents.terminology_tools import run_foundry_agent
from app.config import get_settings
from app.models.schemas import ContentAnalysisResult, ScriptResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたは会議の文字起こしを整理するアシスタントです。
以下の生の文字起こしテキストを受け取り、次の作業を行ってください：

1. フィラーワード（えー、あのー、まあ など）を除去する
2. 発言者ごとに整理し、「発言者名：発言内容」の形式にする
3. 議題（アジェンダ項目）を特定する
4. 参加者リストを作成する
5. 専門用語・社内用語・略語・カタカナ表記・誤変換と思われる語を見つけたら、必ず
   `lookup_terminology` ツールを呼び出して正式表記 (canonical) を確認し、
   スクリプト本文の表記を canonical に統一する。
   - 1 度のツール呼び出しで複数の用語をまとめて渡してよい（最大 50 件）。
   - ツールが空配列を返した語はそのままで構わない。
   - ツール呼び出しは最大 3 回まで。

必ず以下の JSON 形式で出力してください。マークダウンコードブロックは不要です：
{
  "script": "整理した会議スクリプト（改行区切り、用語は canonical に統一済み）",
  "participants": ["参加者1", "参加者2"],
  "agenda_items": ["議題1", "議題2"]
}"""


class ScriptAgent:
    """Cleans and structures the raw transcript into a readable script."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(self, content: ContentAnalysisResult) -> ScriptResult:
        """Generate a clean script from *content*."""
        if get_agents_client() is None:
            logger.warning("Foundry project not configured — returning mock script.")
            return self._mock_result(content)

        user_message = (
            f"【既知の話者】{', '.join(content.speakers) or '不明'}\n"
            f"【議題候補】{', '.join(content.topics) or '不明'}\n\n"
            f"【生文字起こし】\n{content.raw_transcript}"
        )

        raw = await run_foundry_agent(
            agent_key="script",
            name="meeting-script-agent",
            instructions=SYSTEM_PROMPT,
            user_message=user_message,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw or "{}")
        return ScriptResult(
            script=data.get("script", ""),
            participants=data.get("participants", content.speakers),
            agenda_items=data.get("agenda_items", content.topics),
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _mock_result(content: ContentAnalysisResult) -> ScriptResult:
        script_lines = [
            "司会：本日はお集まりいただきありがとうございます。本日の議題は新製品のロードマップとQ3売上目標です。",
            "司会：田中さん、新機能についてご説明ください。",
            "田中：はい、新機能はAIを活用した自動要約機能です。来月末のリリースを目指しています。",
            "鈴木：スケジュールについて確認させてください。テストはいつ開始しますか？",
            "田中：テストは2週間後から開始する予定です。",
            "司会：ありがとうございます。次回の会議は来月15日に設定しましょう。",
        ]
        return ScriptResult(
            script="\n".join(script_lines),
            participants=content.speakers or ["司会", "田中", "鈴木"],
            agenda_items=content.topics or ["新製品ロードマップ", "Q3売上目標"],
        )
