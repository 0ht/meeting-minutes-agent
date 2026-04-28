# 🎙️ Meeting Minutes Agent

音声ファイルから AI が自動で議事録を生成するアプリケーションです。

## 概要

マイクで直接録音するか、既存の音声ファイルをアップロードするだけで、複数のAIエージェントが連携して正式な議事録を自動生成します。

```
音声ファイル
  └─► [音声解析エージェント]              … Azure Speech Fast Transcription で文字起こし（話者分離対応）
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
| 音声解析 | Azure Speech Fast Transcription API（話者分離対応、Foundry AIServices アカウント統合） |
| 言語モデル | Azure OpenAI (GPT-5.4) |
| 認証 | Managed Identity（DefaultAzureCredential） |
| ストレージ | Azure Blob Storage |
| インフラ | Terraform |

## ネットワーク構成

```
インターネット
  │
  ▼
[Streamlit Frontend]  ← 外部イングレス（パブリック）
  │  Azure Container Apps Environment（VNet統合）
  │  snet-container-apps (10.0.0.0/23)
  │  プライベートネットワーク
  ▼
[FastAPI Backend]     ← 内部イングレスのみ（インターネット非公開）
  │
  ├─► Azure AI Foundry (AIServices)
  │     ├─ Speech Fast Transcription API
  │     └─ Azure OpenAI (GPT-5.4)
  └─► Azure Blob Storage (public_network_access=false)
        └── Private Endpoint (snet-private-endpoints 10.0.2.0/24)
            └── Private DNS Zone (privatelink.blob.core.windows.net)
```

> **認証**: すべての Azure サービスへの接続は Managed Identity (DefaultAzureCredential) を使用します。API キーは不要です。

---

## ディレクトリ構成

```
.
├── backend/
│   ├── app/
│   │   ├── main.py                       # FastAPI エントリポイント
│   │   ├── config.py                     # 設定（環境変数）
│   │   ├── agents/
│   │   │   ├── speech_transcription.py   # Azure Speech Fast Transcription エージェント
│   │   │   ├── script_agent.py           # スクリプト生成エージェント
│   │   │   ├── minutes_agent.py          # 議事録作成エージェント
│   │   │   ├── terminology_agent.py      # 用語補足エージェント
│   │   │   ├── pipeline.py               # エージェントパイプライン管理
│   │   │   ├── foundry_client.py         # Foundry / Azure OpenAI クライアント共有
│   │   │   ├── terminology_tools.py      # Function Calling ループ実装
│   │   │   ├── terminology_store.py      # 用語辞書読み込み＋キャッシュ
│   │   │   └── history_store.py          # 完了ジョブの Blob 永続化
│   │   ├── models/
│   │   │   └── schemas.py                # Pydantic モデル
│   │   ├── routers/
│   │   │   ├── audio.py                  # 音声アップロード / テキスト投入 / ジョブ取得
│   │   │   └── history.py                # 履歴一覧・閲覧・ダウンロード・削除
│   │   └── data/
│   │       ├── terminology.json          # 業界・社内用語辞書
│   │       └── sample_script.txt         # サンプルスクリプト
│   ├── scripts/
│   │   ├── register_foundry_agents.py    # Foundry Agent 登録スクリプト
│   │   ├── cleanup_foundry_agents.py     # Foundry Agent 削除スクリプト
│   │   └── smoke_test_foundry.py         # Foundry 接続テスト
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
        ├── ai_services/       # Azure AI Foundry (AIServices) — OpenAI + Speech 統合
        ├── storage/           # Azure Blob Storage
        ├── networking/        # VNet + Container Apps サブネット + Private Endpoints サブネット
        ├── container_registry/# Azure Container Registry (ACR)
        └── container_apps/    # Container Apps Environment + frontend + backend
```

---

## 機能

### 議事録生成パイプライン

4 つの AI エージェントが順次処理を行い、高品質な議事録を生成します。

### エージェント詳細パネル

処理中画面・結果画面で「🔍 エージェント詳細パネル」トグルをONにすると、右側にパネルが表示され、各エージェントの入力・出力データをリアルタイムで確認できます。

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

| 変数名 | 説明 | デフォルト |
|--------|------|----------|
| `AZURE_SPEECH_ENDPOINT` | Azure AI Foundry (AIServices) エンドポイント（Speech API 用） | `""` |
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry プロジェクト エンドポイント（推奨） | `""` |
| `FOUNDRY_MODEL_DEPLOYMENT` | Foundry モデルデプロイメント名 | `gpt-5.4` |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI エンドポイント（レガシーフォールバック） | `""` |
| `AZURE_OPENAI_DEPLOYMENT` | デプロイメント名 | `gpt-5.4` |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API バージョン | `2025-04-01-preview` |
| `AZURE_STORAGE_ACCOUNT_URL` | Azure Blob Storage アカウント URL | `""` |
| `AZURE_STORAGE_CONTAINER` | 音声ファイル用コンテナ名 | `audio-files` |
| `AZURE_TERMS_CONTAINER` | 用語辞書コンテナ名 | `terms` |
| `AZURE_TERMS_BLOB` | 用語辞書 Blob 名 | `terminology.json` |
| `AZURE_HISTORY_CONTAINER` | 履歴コンテナ名 | `history` |
| `TERMINOLOGY_CACHE_TTL_SECONDS` | 用語辞書キャッシュ TTL（秒） | `300` |
| `MAX_AUDIO_SIZE_MB` | 最大音声ファイルサイズ (MB) | `100` |

> **Note:** API キーは不要です。ローカル開発では `az login` 済みの状態で `DefaultAzureCredential` が自動的にトークンを取得します。Azure 上では Managed Identity が使用されます。

フロントエンドの設定:

| 変数名 | 説明 | デフォルト |
|--------|------|----------|
| `BACKEND_URL` | バックエンドの URL（Container Apps では内部 URL が自動設定される） | `http://localhost:8000` |
| `POLL_INTERVAL_SECONDS` | ポーリング間隔（秒）（Container Apps では `2` に設定） | `3` |
| `MAX_WAIT_SECONDS` | 最大待機時間（秒） | `3600` |

### 3. Docker イメージのビルドと ACR へのプッシュ

```bash
# Terraform でインフラを構築してから実行
ACR_NAME=$(terraform -chdir=infra output -raw acr_login_server)

# ACR ビルド（ビルドはクラウド上で実行されるためローカルの Docker 不要）
az acr build --registry $ACR_NAME --image backend:latest ./backend
az acr build --registry $ACR_NAME --image frontend:latest ./frontend
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

### 5. RBAC ロール割り当て（Terraform で自動設定）

バックエンドの Managed Identity に以下のロールが自動的に割り当てられます:

| ロール | 対象リソース | 用途 |
|--------|-------------|------|
| Cognitive Services User | AI Foundry (AIServices) アカウント | 音声文字起こし API |
| Cognitive Services OpenAI User | AI Foundry (AIServices) アカウント | GPT モデル呼び出し |
| Azure AI User | AI Foundry (AIServices) アカウント | Foundry Project / Agent 操作 |
| Storage Blob Data Contributor | ストレージアカウント | 音声ファイルの保存 |

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
