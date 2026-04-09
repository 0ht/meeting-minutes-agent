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
| フロントエンド | **Python / Streamlit**（Azure Container Apps — 外部公開） |
| バックエンド | Python / FastAPI（Azure Container Apps — **プライベートネットワーク**） |
| ネットワーク | Azure VNet 統合 + 内部イングレス（フロントエンド→バックエンド間はプライベート） |
| コンテナ管理 | Azure Container Apps + Azure Container Registry (ACR) |
| 音声解析 | Azure AI Content Understanding |
| 言語モデル | Azure OpenAI (GPT-4o) |
| ストレージ | Azure Blob Storage |
| インフラ | Terraform |

## ネットワーク構成

```
インターネット
  │
  ▼
[Streamlit Frontend]  ← 外部イングレス（パブリック）
  │  Azure Container Apps Environment（VNet統合）
  │  プライベートネットワーク
  ▼
[FastAPI Backend]     ← 内部イングレスのみ（インターネット非公開）
  │
  ├─► Azure AI Content Understanding
  ├─► Azure OpenAI
  └─► Azure Blob Storage
```

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
│   ├── app.py                            # Streamlit アプリ
│   ├── requirements.txt
│   └── Dockerfile
└── infra/
    ├── providers.tf
    ├── main.tf
    ├── variables.tf
    ├── outputs.tf
    ├── terraform.tfvars.example
    └── modules/
        ├── ai_services/       # Azure OpenAI + Content Understanding
        ├── storage/           # Azure Blob Storage
        ├── networking/        # VNet + Container Apps サブネット
        ├── container_registry/# Azure Container Registry (ACR)
        └── container_apps/    # Container Apps Environment + frontend + backend
```

---

## セットアップ手順

### 前提条件

- Python 3.12+
- Azure サブスクリプション
- Terraform 1.5+
- Docker + Azure CLI

### 1. ローカル開発

**バックエンド:**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # .env を編集して Azure の接続情報を入力
uvicorn app.main:app --reload --port 8000
```

**フロントエンド:**
```bash
cd frontend
pip install -r requirements.txt
BACKEND_URL=http://localhost:8000 streamlit run app.py
```

> **Note:** Azure の認証情報を設定しない場合、各エージェントはモックデータで動作します。

### 2. 環境変数

`backend/.env.example` を参考に `.env` を作成してください。

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

フロントエンドの設定:

| 変数名 | 説明 |
|--------|------|
| `BACKEND_URL` | バックエンドの URL（Container Apps では内部 URL が自動設定される） |
| `POLL_INTERVAL_SECONDS` | ポーリング間隔（デフォルト: `2`） |

### 3. Docker イメージのビルドと ACR へのプッシュ

```bash
# Terraform でインフラを構築してから実行
ACR_NAME=$(terraform -chdir=infra output -raw acr_login_server)
az acr login --name $ACR_NAME

# バックエンド
docker build -t ${ACR_NAME}/backend:latest ./backend
docker push ${ACR_NAME}/backend:latest

# フロントエンド
docker build -t ${ACR_NAME}/frontend:latest ./frontend
docker push ${ACR_NAME}/frontend:latest
```

### 4. Terraform でのインフラ構築

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# terraform.tfvars を編集

terraform init
terraform plan
terraform apply
```

デプロイ後、`terraform output` で接続情報を確認できます:

```bash
terraform output frontend_url          # Streamlit の公開 URL
terraform output backend_internal_url  # バックエンドの内部 URL（確認用）
terraform output acr_login_server      # ACR ログインサーバー
```

---

## API リファレンス（バックエンド）

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
