# 🎙️ Meeting Minutes Agent

音声ファイルから AI が自動で議事録を生成するアプリケーションです。

## 概要

マイクで直接録音するか、既存の音声ファイルをアップロードするだけで、4 つの AI エージェントが連携して正式な議事録を自動生成します。

```
音声ファイル
  └─► 音声解析 → スクリプト生成 → 議事録作成 → 用語補足
```

**主要技術:** Python (FastAPI / Streamlit) · Azure Container Apps · Azure AI Foundry (Speech + OpenAI) · Terraform

## クイックスタート

```bash
# バックエンド
cd backend && pip install -r requirements.txt
cp .env.example .env  # Azure 接続情報を設定
uvicorn app.main:app --reload --port 8000

# フロントエンド
cd frontend && pip install -r requirements.txt
BACKEND_URL=http://localhost:8000 streamlit run app.py
```

> Azure 認証情報を設定しない場合はモックデータで動作します。

## ドキュメント

詳細は [docs/](docs/README.md) を参照してください。

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
- **Response:** `202 Accepted` — `{ "job_id": "...", "status": "pending" }`

### POST `/api/v1/audio/transcript`

文字起こし済みテキストから議事録生成を開始します。

- **Content-Type:** `application/json`
- **Body:** `{ "transcript": "...", "speakers": ["話者A", "話者B"], "language": "ja" }`
- **Response:** `202 Accepted` — `{ "job_id": "...", "status": "pending" }`

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

### 履歴エンドポイント

| メソッド | パス | 説明 |
|----------|------|------|
| `GET` | `/api/v1/history` | 議事録履歴一覧（新しい順） |
| `GET` | `/api/v1/history/{job_id}` | 保存済み議事録の詳細 |
| `GET` | `/api/v1/history/{job_id}/input` | 入力ファイルのダウンロード |
| `DELETE` | `/api/v1/history/{job_id}` | 履歴削除 (`204 No Content`) |

### ヘルスチェック

- `GET /health` → `{ "status": "ok" }`

---

## 用語辞書のカスタマイズ

`backend/app/data/terminology.json`（ローカル）または Azure Blob Storage の `terms/terminology.json` を編集することで、業界・社内用語を追加できます。

```json
{
  "phrase_list": ["MCP", "Azure OpenAI"],
  "term_mappings": [
    {
      "variants": ["えむしーぴー", "エムシーピー", "MCP"],
      "canonical": "MCP",
      "definition": "Model Context Protocol。AI とデータソース/ツールを接続するプロトコル。",
      "category": "tech"
    }
  ]
}
```

Blob Storage 上の辞書が優先され、取得できない場合はローカルファイルにフォールバックします。キャッシュ TTL（デフォルト 300 秒）後に自動で再取得されます。

詳細な実装オプションの比較は [`docs/custom-terminology-options.md`](docs/custom-terminology-options.md) を参照してください。

---

## 本番利用に向けた注意点

> **本リポジトリはデモ・PoC 用途で構築されています。** 本番環境で運用する場合は [`docs/poc-vs-production.md`](docs/poc-vs-production.md) を参照してください。
>
> 主な差分: 認証なし / CORS 全開放 / インメモリジョブストア / LRS ストレージ / CI/CD なし — 詳細なチェックリストと段階的移行アプローチを記載しています。

---

## ドキュメント

| ドキュメント | 説明 |
|-------------|------|
| [`docs/requirement.md`](docs/requirement.md) | 要件定義（システム構成図 / 機能要件 / 非機能要件） |
| [`docs/architecture.md`](docs/architecture.md) | アーキテクチャ詳細（コンポーネント / 通信経路 / セキュリティ） |
| [`docs/deploy-guide.md`](docs/deploy-guide.md) | デプロイ手順（クイックスタート / Terraform / ACR） |
| [`docs/operations.md`](docs/operations.md) | 運用ガイド（監視 / トラブルシュート / 更新） |
| [`docs/cost-estimate.md`](docs/cost-estimate.md) | 月額コスト見積もり（リソース別 / 最適化ヒント） |
| [`docs/poc-vs-production.md`](docs/poc-vs-production.md) | PoC 前提と本番ベストプラクティスの差分 |
| [`docs/custom-terminology-options.md`](docs/custom-terminology-options.md) | 社内用語カスタマイズの実装オプション比較 |
| [`docs/architecture.drawio`](docs/architecture.drawio) | アーキテクチャ構成図（draw.io 形式） |

---

## ライセンス

MIT
