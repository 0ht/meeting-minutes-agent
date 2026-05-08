"""Smoke test: invoke the registered Foundry minutes-agent via Responses API.

Usage:
    export FOUNDRY_PROJECT_ENDPOINT=https://<aif-account>.services.ai.azure.com/api/projects/<project>
    python backend/scripts/smoke_test_foundry.py
"""
import asyncio
import os
import sys

# Uses FOUNDRY_PROJECT_ENDPOINT env var (set via .env or shell).
if not os.environ.get("FOUNDRY_PROJECT_ENDPOINT"):
    sys.exit("ERROR: FOUNDRY_PROJECT_ENDPOINT 環境変数を設定してください。")
os.environ.setdefault("FOUNDRY_MODEL_DEPLOYMENT", "gpt-5.4")
os.environ.setdefault("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
# Avoid blob fetch — use local file fallback in terminology_store.
os.environ.setdefault("AZURE_TERMS_CONTAINER", "")
os.environ.setdefault("AZURE_TERMS_BLOB", "")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.terminology_tools import run_foundry_agent  # noqa: E402


async def main():
    text = await run_foundry_agent(
        agent_key="minutes",
        name="meeting-minutes-agent",
        instructions=None,
        user_message=(
            "【参加者】田中, 佐藤\n【議題】MCP導入\n\n"
            "【会議スクリプト】\n田中: 今日はMCPの導入について議論します。\n"
            "佐藤: AOAIとの連携も必要ですね。"
        ),
    )
    print("─" * 60)
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
