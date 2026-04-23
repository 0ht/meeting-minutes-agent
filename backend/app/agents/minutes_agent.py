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

from app.agents.foundry_client import get_agents_client
from app.agents.terminology_tools import run_foundry_agent
from app.config import get_settings
from app.models.schemas import MinutesResult, ScriptResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたは会議の議事録を作成するプロフェッショナルアシスタントです。
提供された会議スクリプトをもとに、Teams 風の構造化された議事録を作成してください。

【用語の取り扱い】
議事録に登場する専門用語・社内用語・略語については、必ず `lookup_terminology`
ツールを呼び出して正式表記 (canonical) と定義 (definition) を取得してください。
- 1 度のツール呼び出しで複数語をまとめて渡してよい（最大 50 件、最大 3 回まで）。
- ツールが定義を返した語は、初出箇所で「正式表記（補足: 定義）」のインライン注釈を
  本文 (raw_markdown / details) に付与する。例: `MCP（Model Context Protocol。AI とデータソース接続の標準規約）`。
- 同じ語が複数回出ても、注釈は初出のみで十分。
- ツールが空配列を返した語は注釈しない。

必ず以下の JSON 形式で出力してください。マークダウンコードブロックは不要です：
{
  "title": "会議タイトル",
  "date": "YYYY-MM-DD（スクリプトから推定できない場合はnull）",
  "participants": ["参加者1", "参加者2"],
  "summary": "会議全体の概要（簡潔に2〜3文）",
  "topics": [
    {
      "title": "トピックの見出し（1行・体言止め可）",
      "summary": "そのトピックで何が話されたかの簡潔な要約（1〜2文）",
      "details": [
        "議論の要点を3〜6行程度の箇条書きでまとめる",
        "誰が何を主張・説明・決定したかを含める",
        "数値・固有名詞・期日などは具体的に記載する"
      ]
    }
  ],
  "follow_up_tasks": [
    {"task": "タスク内容", "owner": "担当者名（不明ならnull）", "due": "期限（任意）"}
  ],
  "next_meeting": "次回会議の日程（任意）",
  "raw_markdown": "Markdown形式の完全な議事録（用語インライン注釈済み）"
}

ガイドライン：
- summary は冗長にせず、2〜3文で会議の目的・主要結論を端的に述べてください。
- topics には会議で扱われた主要なアジェンダを順序通り抽出してください（通常 3〜8 件）。
- details はトピックごとに 3〜6 行程度の簡潔な箇条書きで、何が話されたかが分かるようにしてください。
- 決定事項は該当トピックの details 内に記載するか、follow_up_tasks に展開してください（独立セクションは不要）。
- follow_up_tasks は Teams の「フォローアップ タスク」相当で、タスク・担当者を明記してください。

raw_markdown は以下の構造にしてください：
# [会議タイトル]
**日時：** [日付]  
**参加者：** [参加者]

## 概要
[2〜3文の簡潔な概要]

## 議事
### [トピック1のタイトル]
[トピックの要約1〜2文]
- [詳細1]
- [詳細2]
- [詳細3]

### [トピック2のタイトル]
...

## フォローアップ タスク
- **[タスク内容]** — 担当: [担当者]（期限: [期限]）
"""


class MinutesAgent:
    """Creates structured meeting minutes from the clean script."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(self, script: ScriptResult) -> MinutesResult:
        """Generate meeting minutes from *script*."""
        if get_agents_client() is None:
            logger.warning("Foundry project not configured — returning mock minutes.")
            return self._mock_result(script)

        user_message = (
            f"【参加者】{', '.join(script.participants)}\n"
            f"【議題】{', '.join(script.agenda_items)}\n\n"
            f"【会議スクリプト】\n{script.script}"
        )

        raw = await run_foundry_agent(
            agent_key="minutes",
            name="meeting-minutes-agent",
            instructions=SYSTEM_PROMPT,
            user_message=user_message,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw or "{}")
        return MinutesResult(
            title=data.get("title", "会議議事録"),
            date=data.get("date"),
            participants=data.get("participants", script.participants),
            summary=data.get("summary", ""),
            topics=data.get("topics", []),
            follow_up_tasks=data.get("follow_up_tasks", data.get("action_items", [])),
            decisions=data.get("decisions", []),
            action_items=data.get("action_items", []),
            next_meeting=data.get("next_meeting"),
            raw_markdown=data.get("raw_markdown", ""),
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _mock_result(script: ScriptResult) -> MinutesResult:
        today = date.today().isoformat()
        topics = [
            {
                "title": "新製品ロードマップの確認",
                "summary": "新製品の開発状況とリリース計画について議論した。",
                "details": [
                    "AI自動要約機能の開発が予定通り進行していることを確認",
                    "リリース時期を来月末に設定",
                    "テスト工程は2週間後から開始することで合意",
                ],
            },
            {
                "title": "Q3 売上目標と次回会議",
                "summary": "Q3 の売上目標と次回ミーティングのスケジュールを確認した。",
                "details": [
                    "Q3 売上目標は前期比 110% を目指す",
                    "次回会議を来月15日に設定",
                ],
            },
        ]
        follow_up = [
            {"task": "AI自動要約機能の開発完了", "owner": "田中", "due": "来月末"},
            {"task": "テスト環境の準備", "owner": "田中", "due": "2週間後"},
            {"task": "次回会議の案内送付", "owner": "司会", "due": "今週中"},
        ]
        topics_md = "\n\n".join(
            f"### {t['title']}\n{t['summary']}\n"
            + "\n".join(f"- {d}" for d in t["details"])
            for t in topics
        )
        tasks_md = "\n".join(
            f"- **{t['task']}** — 担当: {t['owner']}（期限: {t['due']}）"
            for t in follow_up
        )
        markdown = f"""# 新製品ロードマップ検討会議
**日時：** {today}  
**参加者：** {', '.join(script.participants)}

## 概要
新製品ロードマップと Q3 売上目標を確認し、AI自動要約機能のリリース計画を合意した。

## 議事
{topics_md}

## フォローアップ タスク
{tasks_md}
"""
        return MinutesResult(
            title="新製品ロードマップ検討会議",
            date=today,
            participants=script.participants,
            summary=(
                "新製品ロードマップと Q3 売上目標を確認し、"
                "AI自動要約機能を来月末にリリースすることで合意した。"
            ),
            topics=topics,
            follow_up_tasks=follow_up,
            decisions=[
                "AI自動要約機能を来月末にリリースする",
                "テストは2週間後から開始する",
                "次回会議を来月15日に設定する",
            ],
            action_items=follow_up,
            next_meeting="来月15日",
            raw_markdown=markdown,
        )
