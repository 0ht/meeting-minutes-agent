# Meeting Minutes Agent — デプロイ手順

> **最終更新日**: 2026-05-11

---

## 1. 前提条件

- Python 3.12+
- Azure サブスクリプション
- Terraform 1.5+
- Docker（ローカルビルド時）または Azure CLI（ACR ビルド時）
- `az login` 済みの状態

---

## 2. クイックスタート（ローカル開発）

### 2.1 バックエンド

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # .env を編集して Azure の接続情報を入力
uvicorn app.main:app --reload --port 8000
```

### 2.2 フロントエンド

```bash
cd frontend
pip install -r requirements.txt
BACKEND_URL=http://localhost:8000 streamlit run app.py
```

> **Note:** Azure の認証情報を設定しない場合、各エージェントはモックデータで動作します。ローカル開発では `az login` 済みの状態で `DefaultAzureCredential` が自動的にトークンを取得します。

---

## 3. 環境変数

### 3.1 バックエンド

`backend/.env.example` を参考に `.env` を作成してください。

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `AZURE_SPEECH_ENDPOINT` | Azure AI Foundry (AIServices) エンドポイント（Speech API 用） | `""` |
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry プロジェクト エンドポイント（推奨） | `""` |
| `FOUNDRY_MODEL_DEPLOYMENT` | Foundry モデルデプロイメント名 | `gpt-5.4` |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI エンドポイント（レガシーフォールバック） | `""` |
| `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI デプロイメント名 | `gpt-5.4` |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API バージョン | `2025-04-01-preview` |
| `AZURE_STORAGE_ACCOUNT_URL` | Blob Storage アカウント URL | `""` |
| `AZURE_STORAGE_CONTAINER` | 音声ファイル用コンテナ名 | `audio-files` |
| `AZURE_TERMS_CONTAINER` | 用語辞書コンテナ名 | `terms` |
| `AZURE_TERMS_BLOB` | 用語辞書 Blob 名 | `terminology.json` |
| `AZURE_HISTORY_CONTAINER` | 履歴コンテナ名 | `history` |
| `TERMINOLOGY_CACHE_TTL_SECONDS` | 用語辞書キャッシュ TTL（秒） | `300` |
| `MAX_AUDIO_SIZE_MB` | 最大音声ファイルサイズ (MB) | `100` |
| `SPEECH_POLL_TIMEOUT_SECONDS` | Speech API ポーリングタイムアウト | `300` |
| `SPEECH_POLL_INTERVAL_SECONDS` | Speech API ポーリング間隔 | `5` |

### 3.2 フロントエンド

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `BACKEND_URL` | バックエンド API の URL | `http://localhost:8000` |
| `POLL_INTERVAL_SECONDS` | ポーリング間隔（秒） | `3` |
| `MAX_WAIT_SECONDS` | 最大待機時間（秒） | `3600` |

---

## 4. Terraform によるインフラ構築

### 4.1 初期セットアップ

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# terraform.tfvars を編集（リソースグループ名、リージョン等）

terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

### 4.2 Terraform 変数

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `resource_group_name` | `rg-meeting-minutes-agent` | リソースグループ名 |
| `location` | `japaneast` | Azure リージョン |
| `environment` | `dev` | デプロイ環境 (dev/staging/prod) |
| `app_name` | `mtgminutes` | リソース名ベース |
| `openai_sku` | `S0` | Azure OpenAI SKU |
| `openai_model_name` | `gpt-5.4` | GPT モデル名 |
| `openai_model_version` | `2026-03-05` | GPT モデルバージョン |
| `openai_deployment_capacity` | `30` | TPM 容量 (千単位) |
| `storage_account_tier` | `Standard` | ストレージティア |
| `storage_replication_type` | `LRS` | レプリケーション種別 |
| `vnet_address_space` | `10.0.0.0/16` | VNet CIDR |
| `container_apps_subnet_cidr` | `10.0.0.0/23` | CA サブネット CIDR |
| `acr_sku` | `Basic` | ACR SKU |
| `backend_cpu` / `backend_memory` | `0.5` / `1Gi` | Backend リソース割り当て |
| `frontend_cpu` / `frontend_memory` | `0.5` / `1Gi` | Frontend リソース割り当て |
| `backend_image_tag` / `frontend_image_tag` | `latest` | イメージタグ |
| `tag_environment` | `dev` | リソースタグ値 |

### 4.3 デプロイ後の確認

```bash
terraform output frontend_url          # Streamlit の公開 URL
terraform output backend_internal_url  # バックエンドの内部 URL（確認用）
terraform output acr_login_server      # ACR ログインサーバー
```

---

## 5. コンテナイメージのビルド

### 5.1 ACR ビルド（推奨 — ローカル Docker 不要）

```bash
ACR_NAME=$(terraform -chdir=infra output -raw acr_login_server)

az acr build --registry $ACR_NAME --image meeting-minutes-backend:v1.0 ./backend
az acr build --registry $ACR_NAME --image meeting-minutes-frontend:v1.0 ./frontend
```

### 5.2 ローカルビルド & プッシュ

```bash
ACR_SERVER=$(terraform -chdir=infra output -raw acr_login_server)
az acr login --name ${ACR_SERVER%%.*}

docker build -t $ACR_SERVER/meeting-minutes-backend:v1.0 ./backend
docker push $ACR_SERVER/meeting-minutes-backend:v1.0

docker build -t $ACR_SERVER/meeting-minutes-frontend:v1.0 ./frontend
docker push $ACR_SERVER/meeting-minutes-frontend:v1.0
```

---

## 6. イメージタグの更新（Container Apps へのデプロイ）

### 6.1 Terraform 経由

`terraform.tfvars` の `backend_image_tag` / `frontend_image_tag` を変更後:

```bash
cd infra
terraform plan -out=tfplan
terraform apply tfplan
```

### 6.2 az CLI 直接更新（緊急時のみ）

```bash
az containerapp update \
  --name ca-backend-mtgminutes-dev \
  --resource-group rg-meeting-minutes-agent \
  --image acrmtgminutesdev.azurecr.io/meeting-minutes-backend:v1.1

az containerapp update \
  --name ca-frontend-mtgminutes-dev \
  --resource-group rg-meeting-minutes-agent \
  --image acrmtgminutesdev.azurecr.io/meeting-minutes-frontend:v1.1
```

> **注意**: CLI で直接変更した場合は、後で `terraform.tfvars` を実態に合わせて drift を解消してください。

---

## 7. Foundry エージェント登録

```bash
export FOUNDRY_PROJECT_ENDPOINT=https://<aif-account>.services.ai.azure.com/api/projects/<project>
az login
python backend/scripts/register_foundry_agents.py
```

冪等（`create_version` による upsert）。instructions やツール定義を変更した場合に再実行する。

---

## 8. 用語辞書の更新

```bash
az storage blob upload \
  --account-name <storage-account> \
  --container-name terms \
  --name terminology.json \
  --file backend/app/data/terminology.json \
  --auth-mode login
```

キャッシュ TTL（デフォルト 5 分）後に自動反映。

---

## 9. RBAC ロール割り当て

Terraform で自動設定される。手動で確認する場合:

| ロール | 対象リソース | 用途 |
|--------|-------------|------|
| `Storage Blob Data Contributor` | Storage Account | 音声・用語辞書・履歴の読み書き |
| `Cognitive Services User` | AI Foundry Account | Speech Fast Transcription |
| `Cognitive Services OpenAI User` | AI Foundry Account | GPT モデル呼び出し |
| `Azure AI User` | AI Foundry Account | Foundry Project / Agent 操作 |

---

## 10. 環境別デプロイ

staging / prod を立てる場合は、別の tfvars ファイルまたは Terraform workspace を用意:

```bash
# staging 例
cp infra/terraform.tfvars.example infra/terraform-staging.tfvars
# environment = "staging" に変更

cd infra
terraform workspace new staging
terraform plan -var-file=terraform-staging.tfvars -out=tfplan
terraform apply tfplan
```

### 環境差分パラメーター

| パラメーター | dev | staging | prod |
|-------------|-----|---------|------|
| `acr_sku` | `Basic` | `Standard` 推奨 | `Premium` 推奨 |
| `storage_replication_type` | `LRS` | `LRS` | `ZRS` / `GRS` 推奨 |
| `openai_deployment_capacity` | `30` | 用途に応じて | 用途に応じて |
