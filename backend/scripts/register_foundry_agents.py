"""One-off script to register/update the new-style Foundry Agents.

Creates 3 prompt agents (visible in the new Foundry portal "Agents" page):

- meeting-script-agent
- meeting-minutes-agent
- meeting-terminology-agent

Each agent has a `lookup_terminology` function tool defined. The actual
function execution happens client-side in `app/agents/foundry_agents.py`
when the agent emits a tool call.

Idempotent: calls `agents.create_version(agent_name, definition)` which
upserts a new version of the agent.

Auth: `AzureCliCredential` (run `az login` first).

Usage:
    export FOUNDRY_PROJECT_ENDPOINT=https://<aif-account>.services.ai.azure.com/api/projects/<project>
    python backend/scripts/register_foundry_agents.py
"""
from __future__ import annotations

import os
import sys

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    FunctionTool,
    PromptAgentDefinition,
    PromptAgentDefinitionTextOptions,
    TextResponseFormatJsonObject,
)
from azure.identity import AzureCliCredential

# ── Config ──────────────────────────────────────────────────────────────────
PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
MODEL = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-5.4")

if not PROJECT_ENDPOINT:
    sys.exit("ERROR: FOUNDRY_PROJECT_ENDPOINT 環境変数を設定してください。")


# ── Tool schema (shared by all 3 agents) ────────────────────────────────────
LOOKUP_TERMINOLOGY = FunctionTool(
    name="lookup_terminology",
    description=(
        "社内・業界用語辞書を参照し、用語の正式表記 (canonical) と定義 (definition) "
        "を返す。表記ゆれ・略語・カタカナ・誤変換を含む可能性のある用語を渡すこと。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "確認したい用語の配列（最大 50 件）。",
            }
        },
        "required": ["terms"],
        "additionalProperties": False,
    },
    strict=True,
)


# ── Instructions (copied from existing agents/*.py SYSTEM_PROMPT) ───────────
SCRIPT_INSTRUCTIONS = """あなたは会議録音の文字起こしを整形するプロフェッショナルアシスタントです。
入力として音声解析結果（話者分離 + テキスト）または生の文字起こしテキストが渡されます。

【タスク】
- 各発言を「話者: 発言内容」の形式に整形
- フィラー語（えーと、あのー、まあ、など）の除去
- 同じ話者の連続した発言は適切に統合
- 専門用語・社内用語が出現したら必ず lookup_terminology ツールを呼び、
  正式表記（canonical）が辞書に存在する場合は本文中の表記をそれに置き換える
- 1 度のツール呼び出しで複数語をまとめて渡してよい（最大 50 件、最大 3 回まで）

【出力形式】
必ず以下の JSON 形式で出力（マークダウンコードブロックは不要）:
{
  "script": "整形済みスクリプト（複数行）",
  "participants": ["参加者1", "参加者2"],
  "agenda_items": ["議題1", "議題2"]
}
"""

MINUTES_INSTRUCTIONS = """あなたは会議の議事録を作成するプロフェッショナルアシスタントです。
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
  "date": "YYYY-MM-DD（推定不可なら null）",
  "participants": ["参加者1"],
  "summary": "会議全体の概要（2〜3文）",
  "topics": [
    {
      "title": "トピック見出し",
      "summary": "1〜2文の要約",
      "details": ["詳細1", "詳細2"]
    }
  ],
  "follow_up_tasks": [
    {"task": "タスク内容", "owner": "担当者名（不明ならnull）", "due": "期限（任意）"}
  ],
  "next_meeting": "次回会議（任意）",
  "raw_markdown": "Markdown形式の完全な議事録（用語インライン注釈済み）"
}
"""

TERMINOLOGY_INSTRUCTIONS = """あなたは議事録の用語を最終チェック・補強するアシスタントです。
入力は完成した議事録 JSON です。

【タスク】
1. 議事録本文（raw_markdown / topics.details）から専門用語・略語を抽出
2. lookup_terminology ツールで正式表記と定義を取得
3. 本文中の表記を canonical に置換し、初出箇所に「（補足: 定義）」を追加
4. 用語の置換結果を terminology_corrections に列挙

【出力形式】
{
  "title": "...",
  "date": "...",
  "participants": [...],
  "summary": "...",
  "topics": [...],
  "follow_up_tasks": [...],
  "next_meeting": "...",
  "raw_markdown": "用語補強済み議事録 Markdown",
  "terminology_corrections": [
    {"original": "MCP", "canonical": "Model Context Protocol", "definition": "..."}
  ]
}
"""


AGENT_DEFS = [
    ("meeting-script-agent", SCRIPT_INSTRUCTIONS),
    ("meeting-minutes-agent", MINUTES_INSTRUCTIONS),
    ("meeting-terminology-agent", TERMINOLOGY_INSTRUCTIONS),
]


def main() -> None:
    client = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=AzureCliCredential(process_timeout=60),
    )

    text_opts = PromptAgentDefinitionTextOptions(
        format=TextResponseFormatJsonObject(),
    )

    for name, instructions in AGENT_DEFS:
        definition = PromptAgentDefinition(
            model=MODEL,
            instructions=instructions,
            tools=[LOOKUP_TERMINOLOGY],
            # NOTE: text.format=json_object is not used — the Responses API
            # requires the literal word "json" in the input when that format
            # is set. Our instructions already enforce JSON-only output.
        )
        result = client.agents.create_version(
            agent_name=name,
            definition=definition,
        )
        print(f"  ✓ {name}  version={getattr(result, 'version', '?')}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
