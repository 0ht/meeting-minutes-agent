"""Minutes Agent — creates structured meeting minutes from the clean script.

Uses Azure OpenAI (GPT-4o) to produce:
- Title and date
- Participant list
- Executive summary
- Key decisions
- Action items (with owner and due date)
- Next meeting date
- Full markdown document
"""
from __future__ import annotations

import json
import logging
from datetime import date

from openai import AsyncAzureOpenAI

from app.config import get_settings
from app.models.schemas import MinutesResult, ScriptResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたは会議の議事録を作成するプロフェッショナルアシスタントです。
提供された会議スクリプトをもとに、正式な議事録を作成してください。

必ず以下の JSON 形式で出力してください。マークダウンコードブロックは不要です：
{
  "title": "会議タイトル",
  "date": "YYYY-MM-DD（スクリプトから推定できない場合はnull）",
  "participants": ["参加者1", "参加者2"],
  "summary": "会議全体の要約（3〜5文）",
  "decisions": ["決定事項1", "決定事項2"],
  "action_items": [
    {"owner": "担当者名", "task": "タスク内容", "due": "期限（任意）"}
  ],
  "next_meeting": "次回会議の日程（任意）",
  "raw_markdown": "Markdown形式の完全な議事録"
}

raw_markdown は以下の構造にしてください：
# [会議タイトル]
**日時：** [日付]  
**参加者：** [参加者]

## 概要
[要約]

## 決定事項
- [決定事項リスト]

## アクションアイテム
| 担当者 | タスク | 期限 |
|--------|--------|------|
| ...    | ...    | ...  |

## 次回会議
[次回会議情報]
"""


class MinutesAgent:
    """Creates structured meeting minutes from the clean script."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(self, script: ScriptResult) -> MinutesResult:
        """Generate meeting minutes from *script*."""
        if not self.settings.azure_openai_endpoint or not self.settings.azure_openai_key:
            logger.warning("Azure OpenAI credentials not configured — returning mock minutes.")
            return self._mock_result(script)

        client = AsyncAzureOpenAI(
            azure_endpoint=self.settings.azure_openai_endpoint,
            api_key=self.settings.azure_openai_key,
            api_version=self.settings.azure_openai_api_version,
        )

        user_message = (
            f"【参加者】{', '.join(script.participants)}\n"
            f"【議題】{', '.join(script.agenda_items)}\n\n"
            f"【会議スクリプト】\n{script.script}"
        )

        response = await client.chat.completions.create(
            model=self.settings.azure_openai_deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        return MinutesResult(
            title=data.get("title", "会議議事録"),
            date=data.get("date"),
            participants=data.get("participants", script.participants),
            summary=data.get("summary", ""),
            decisions=data.get("decisions", []),
            action_items=data.get("action_items", []),
            next_meeting=data.get("next_meeting"),
            raw_markdown=data.get("raw_markdown", ""),
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _mock_result(script: ScriptResult) -> MinutesResult:
        today = date.today().isoformat()
        markdown = f"""# 新製品ロードマップ検討会議
**日時：** {today}
**参加者：** {', '.join(script.participants)}

## 概要
本日の会議では、新製品のロードマップとQ3の売上目標について議論しました。AIを活用した自動要約機能の開発状況と今後のスケジュールを確認しました。

## 決定事項
- AI自動要約機能を来月末にリリースする
- テストは2週間後から開始する
- 次回会議を来月15日に設定する

## アクションアイテム
| 担当者 | タスク | 期限 |
|--------|--------|------|
| 田中 | AI自動要約機能の開発完了 | 来月末 |
| 田中 | テスト環境の準備 | 2週間後 |
| 司会 | 次回会議の案内送付 | 今週中 |

## 次回会議
来月15日（詳細は別途案内）
"""
        return MinutesResult(
            title="新製品ロードマップ検討会議",
            date=today,
            participants=script.participants,
            summary=(
                "本日の会議では、新製品のロードマップとQ3の売上目標について議論しました。"
                "AIを活用した自動要約機能の開発状況と今後のスケジュールを確認しました。"
                "来月末のリリースに向けてテストを2週間後から開始することが決定しました。"
            ),
            decisions=[
                "AI自動要約機能を来月末にリリースする",
                "テストは2週間後から開始する",
                "次回会議を来月15日に設定する",
            ],
            action_items=[
                {"owner": "田中", "task": "AI自動要約機能の開発完了", "due": "来月末"},
                {"owner": "田中", "task": "テスト環境の準備", "due": "2週間後"},
                {"owner": "司会", "task": "次回会議の案内送付", "due": "今週中"},
            ],
            next_meeting="来月15日",
            raw_markdown=markdown,
        )
