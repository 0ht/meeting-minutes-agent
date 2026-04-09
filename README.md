# 🎙️ Meeting Minutes Agent

音声ファイルから AI が自動で議事録を生成するアプリケーションです。

## 概要

マイクで直接録音するか、既存の音声ファイルをアップロードするだけで、複数のAIエージェントが連携して正式な議事録を自動生成します。

```
音声ファイル
  └─► [Content Understanding エージェント]  … 文字起こし・構造化データ抽出
        └─► [スクリプト生成エージェント]     … 読みやすい会議スクリプトを作成
              └─► [議事録作成エージェント]   … 決定事項・アクションアイテム等を整理
                    └─► [用語補足エージェント] … 業界/社内用語の用語集を付加
```

## 技術スタック

| レイヤー | 技術 |
|----------|------|
| バックエンド | Python / FastAPI |
| フロントエンド | HTML / CSS / Vanilla JS (FastAPI で静的配信) |
| 音声解析 | Azure AI Content Understanding |
| 言語モデル | Azure OpenAI (GPT-4o) |
| ストレージ | Azure Blob Storage |
| インフラ | Terraform (Azure App Service) |

---

## ディレクトリ構成

```
.
├── backend/
│   ├── app/
│   │   ├── main.py                       # FastAPI エントリポイント
│   │   ├── config.py                     # 設定（環境変数）
│   │   ├── agents/
│   │   │   ├── content_understanding.py  # Azure AI Content Understanding エージェント
│   │   │   ├── script_agent.py           # スクリプト生成エージェント
│   │   │   ├── minutes_agent.py          # 議事録作成エージェント
│   │   │   ├── terminology_agent.py      # 用語補足エージェント
│   │   │   └── pipeline.py               # エージェントパイプライン管理
│   │   ├── models/
│   │   │   └── schemas.py                # Pydantic モデル
│   │   ├── routers/
│   │   │   └── audio.py                  # API エンドポイント
│   │   └── data/
│   │       └── terminology.json          # 業界・社内用語辞書
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── frontend/
│   ├── index.html                        # メイン UI
│   ├── css/styles.css
│   └── js/app.js
└── infra/
    ├── providers.tf
    ├── main.tf
    ├── variables.tf
    ├── outputs.tf
    ├── terraform.tfvars.example
    └── modules/
        ├── ai_services/   # Azure OpenAI + Content Understanding
        ├── storage/       # Azure Blob Storage
        └── app_service/   # Azure App Service (Linux)
```

---

## セットアップ手順

### 前提条件

- Python 3.12+
- Azure サブスクリプション
- Terraform 1.5+
- Docker (コンテナデプロイの場合)

### 1. ローカル開発

```bash
cd backend
pip install -r requirements.txt

# 環境変数を設定
cp .env.example .env
# .env を編集して Azure の接続情報を入力

# サーバーを起動（フロントエンドも / で配信されます）
uvicorn app.main:app --reload --port 8000
```

ブラウザで `http://localhost:8000` を開いてください。

> **Note:** Azure の認証情報を設定しない場合、各エージェントはモックデータで動作します。

### 2. 環境変数

`.env.example` を参考に `.env` を作成してください。

| 変数名 | 説明 |
|--------|------|
| `AZURE_CU_ENDPOINT` | Azure AI Content Understanding エンドポイント |
| `AZURE_CU_KEY` | Azure AI Content Understanding APIキー |
| `AZURE_CU_ANALYZER_ID` | アナライザーID（デフォルト: `prebuilt-audioAnalyzer`） |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI エンドポイント |
| `AZURE_OPENAI_KEY` | Azure OpenAI APIキー |
| `AZURE_OPENAI_DEPLOYMENT` | デプロイメント名（デフォルト: `gpt-4o`） |
| `AZURE_STORAGE_CONNECTION_STRING` | Azure Blob Storage 接続文字列 |
| `AZURE_STORAGE_CONTAINER` | コンテナ名（デフォルト: `audio-files`） |

### 3. Terraform でのインフラ構築

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# terraform.tfvars を編集

terraform init
terraform plan
terraform apply
```

デプロイ後、`terraform output` で接続情報を確認できます。

### 4. Docker でのビルド・実行

```bash
# リポジトリルートで実行
docker build -t meeting-minutes-agent ./backend

docker run -p 8000:8000 \
  -e AZURE_CU_ENDPOINT=... \
  -e AZURE_CU_KEY=... \
  -e AZURE_OPENAI_ENDPOINT=... \
  -e AZURE_OPENAI_KEY=... \
  meeting-minutes-agent
```

---

## API リファレンス

### POST `/api/v1/audio/upload`

音声ファイルをアップロードして議事録生成ジョブを開始します。

- **Content-Type:** `multipart/form-data`
- **Body:** `file` — 音声ファイル (wav, mp3, mp4, m4a, ogg, webm, flac)
- **Response:** `{ "job_id": "...", "status": "pending" }`

### GET `/api/v1/audio/jobs/{job_id}`

ジョブのステータスと結果を取得します。

```json
{
  "job_id": "...",
  "status": "done",
  "content_analysis": { "raw_transcript": "...", "speakers": [...] },
  "script": { "script": "...", "participants": [...] },
  "minutes": { "title": "...", "summary": "...", "decisions": [...] },
  "final_minutes": { "markdown": "...", "glossary": [...] }
}
```

`status` は `pending` → `processing` → `done` / `error` と変化します。

---

## 用語辞書のカスタマイズ

`backend/app/data/terminology.json` を編集することで、業界・社内用語を追加できます。

```json
{
  "industry": {
    "用語": "定義"
  },
  "company": {
    "社内用語": "説明"
  }
}
```

---

## ライセンス

MIT