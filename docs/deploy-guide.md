# Meeting Minutes Agent — デプロイ手順

> **最終更新日**: 2026-05-12

---

## 1. 前提条件

- [Azure Developer CLI (azd)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) — `azd version` で確認
- Azure CLI (`az`) — `az version` で確認
- `az login` 済みの状態
- Python 3.12+（ローカル開発時のみ）

> Terraform・Docker はローカルへの個別インストール不要です。azd が Terraform の実行を内部で行い、コンテナイメージは ACR リモートビルド（`az acr build`）で構築されます。

---

## 2. azd によるデプロイ（推奨）

### 2.1 初回デプロイ（インフラ構築 + アプリデプロイ）

```bash
# リポジトリのルートで実行
azd up
```

このコマンド 1 つで以下が順次実行されます:

| フェーズ | 実行内容 |
|---------|---------|
| `azd provision` | Terraform でインフラを構築（VNet / Storage / ACR / AI Services / Container Apps 等） |
| → `preprovision` フック | Container Apps の存在チェック（初回は false → プレースホルダーイメージで作成） |
| → `postprovision` フック | Container Apps に MI ベースの ACR レジストリを設定 (`az containerapp registry set`) |
| `azd deploy` | Backend / Frontend の Docker イメージを ACR リモートビルド＆Container Apps にデプロイ |
| → `predeploy` フック | ACR のパブリックアクセスを一時的に有効化（`az acr build` がデータプレーンに必要なため） |
| → `postdeploy` フック | ACR のパブリックアクセスを再度無効化（Private Endpoint のみに復元） |

初回実行時、azd が環境名やサブスクリプション・リージョンを対話的に質問します。`terraform.tfvars` は azd が自動的に読み込みます。

### 2.2 アプリケーションのみ更新

コード変更後、インフラ変更なしでアプリだけ再デプロイ:

```bash
azd deploy
```

> Backend のみ、Frontend のみ更新する場合:
> ```bash
> azd deploy --service backend
> azd deploy --service frontend
> ```

### 2.3 インフラのみ更新

`infra/` 配下の Terraform を変更した場合:

```bash
azd provision
```

### 2.4 デプロイ後の確認

```bash
azd env get-values                     # 環境変数一覧
azd env get-value frontend_url         # Streamlit の公開 URL
azd env get-value backend_internal_url # バックエンドの内部 URL
```

### 2.5 Foundry エージェント登録（必須・手動）

> **⚠️ `azd up` には含まれません。** 初回デプロイ後に必ず手動で実行してください。
> Foundry Prompt Agent は Terraform / azd のスコープ外（Foundry データプレーン API）で管理されるため、自動化されていません。

`azd up` 完了後、Foundry Prompt Agent を登録します:

```bash
# azd env から Foundry エンドポイントを取得して設定
export FOUNDRY_PROJECT_ENDPOINT=$(azd env get-value foundry_project_endpoint 2>/dev/null)
python backend/scripts/register_foundry_agents.py
```

冪等（`create_version` による upsert）。instructions やツール定義を変更した場合に再実行してください。

### 2.6 用語辞書のアップロード

```bash
az storage blob upload \
  --account-name $(azd env get-value storage_account_name 2>/dev/null) \
  --container-name terms \
  --name terminology.json \
  --file backend/app/data/terminology.json \
  --auth-mode login
```

キャッシュ TTL（デフォルト 5 分）後に自動反映。

### 2.7 環境の削除

```bash
azd down --purge    # 全リソースを削除（soft-delete も完全削除）
```

---

## 3. ローカル開発

### 3.1 バックエンド

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # .env を編集して Azure の接続情報を入力
uvicorn app.main:app --reload --port 8000
```

### 3.2 フロントエンド

```bash
cd frontend
pip install -r requirements.txt
BACKEND_URL=http://localhost:8000 streamlit run app.py
```

> **Note:** Azure の認証情報を設定しない場合、各エージェントはモックデータで動作します。ローカル開発では `az login` 済みの状態で `DefaultAzureCredential` が自動的にトークンを取得します。

---

## 4. 環境変数リファレンス

### 4.1 バックエンド

`backend/.env.example` を参考に `.env` を作成してください。Azure 環境では Terraform が Container Apps の環境変数を自動設定するため、手動設定は不要です。

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
| `SPEECH_POLL_TIMEOUT_SECONDS` | Speech API ポーリングタイムアウト | `1800` |
| `SPEECH_POLL_INTERVAL_SECONDS` | Speech API ポーリング間隔 | `10` |

### 4.2 フロントエンド

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `BACKEND_URL` | バックエンド API の URL | `http://localhost:8000` |
| `POLL_INTERVAL_SECONDS` | ポーリング間隔（秒） | `3` |
| `MAX_WAIT_SECONDS` | 最大待機時間（秒） | `3600` |

---

## 5. Terraform 変数リファレンス

`infra/terraform.tfvars` で設定。`azd up` / `azd provision` 実行時に自動的に読み込まれます。

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
| `acr_sku` | `Premium` | ACR SKU（Premium は Private Endpoint 必須） |
| `backend_cpu` / `backend_memory` | `0.5` / `1Gi` | Backend リソース割り当て |
| `frontend_cpu` / `frontend_memory` | `0.5` / `1Gi` | Frontend リソース割り当て |
| `tag_environment` | `dev` | リソースタグ値 |

---

## 6. RBAC ロール割り当て

Terraform で自動設定される。手動で確認する場合:

| ロール | 対象リソース | 用途 |
|--------|-------------|------|
| `Storage Blob Data Contributor` | Storage Account | 音声・用語辞書・履歴の読み書き |
| `Cognitive Services User` | AI Foundry Account | Speech Fast / Batch Transcription |
| `Cognitive Services OpenAI User` | AI Foundry Account | GPT モデル呼び出し |
| `Azure AI User` | AI Foundry Account | Foundry Project / Agent 操作 |
| `AcrPull` | Container Registry | Backend / Frontend のイメージプル |
| `Storage Blob Data Reader` | Storage Account | AI Services MI — Batch Transcription が音声を読み取り |

---

## 7. 環境別デプロイ

azd 環境を切り替えて staging / prod を立てる:

```bash
# staging 環境を作成
azd env new staging
azd env set AZURE_ENV_NAME staging
# infra/terraform.tfvars の environment = "staging" に変更（または -var-file で指定）
azd up
```

### 環境差分パラメーター

| パラメーター | dev | staging | prod |
|-------------|-----|---------|------|
| `acr_sku` | `Premium` | `Premium` | `Premium` |
| `storage_replication_type` | `LRS` | `LRS` | `ZRS` / `GRS` 推奨 |
| `openai_deployment_capacity` | `30` | 用途に応じて | 用途に応じて |

---

## 付録 A. azd を使わない手動デプロイ

azd を使わず Terraform + CLI で個別に操作する場合の手順です。

### A.1 Terraform によるインフラ構築

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# terraform.tfvars を編集

terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

### A.2 ACR レジストリの設定

Terraform 完了後、Container Apps に MI ベースの ACR レジストリを設定:

```bash
az containerapp registry set \
  --name ca-backend-mtgminutes-dev \
  --resource-group rg-meeting-minutes-agent \
  --server acrmtgminutesdev.azurecr.io \
  --identity system

az containerapp registry set \
  --name ca-frontend-mtgminutes-dev \
  --resource-group rg-meeting-minutes-agent \
  --server acrmtgminutesdev.azurecr.io \
  --identity system
```

### A.3 コンテナイメージのビルド & プッシュ

ACR は `public_network_access_enabled = false` のため、ビルド前に一時的にパブリックアクセスを有効化する必要があります:

```bash
# パブリックアクセスを一時有効化
az acr update --name acrmtgminutesdev --public-network-enabled true

# ACR リモートビルド
az acr build --registry acrmtgminutesdev --image meeting-minutes-backend:v1.0 ./backend
az acr build --registry acrmtgminutesdev --image meeting-minutes-frontend:v1.0 ./frontend

# パブリックアクセスを無効化（復元）
az acr update --name acrmtgminutesdev --public-network-enabled false
```

### A.4 Container Apps のイメージ更新

```bash
az containerapp update \
  --name ca-backend-mtgminutes-dev \
  --resource-group rg-meeting-minutes-agent \
  --image acrmtgminutesdev.azurecr.io/meeting-minutes-backend:v1.0

az containerapp update \
  --name ca-frontend-mtgminutes-dev \
  --resource-group rg-meeting-minutes-agent \
  --image acrmtgminutesdev.azurecr.io/meeting-minutes-frontend:v1.0
```

> **注意**: CLI で直接変更した場合は Terraform の `ignore_changes` によりドリフトは発生しませんが、一貫性のため `azd deploy` の利用を推奨します。
