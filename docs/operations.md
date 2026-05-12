# Meeting Minutes Agent — 運用ガイド

> **最終更新日**: 2026-05-12

---

## 1. 監視

### 1.1 ログ

| コンポーネント | 出力先 | レベル |
|---------------|--------|--------|
| Backend | Python `logging` → Container Apps → Log Analytics Workspace | INFO |
| Frontend | Streamlit 標準出力 → Container Apps → Log Analytics Workspace | — |

- **ログ保持期間**: 30 日（`law-{app}-{env}` の `retention_in_days = 30`）

### 1.2 Log Analytics クエリ例

```kusto
// Backend のエラーログ（直近 1 時間）
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "ca-backend-mtgminutes-dev"
| where Log_s has "ERROR" or Log_s has "Exception"
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
| take 50
```

```kusto
// ジョブ完了のレイテンシ分析
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "ca-backend-mtgminutes-dev"
| where Log_s has "Pipeline completed"
| order by TimeGenerated desc
```

### 1.3 ヘルスチェック

| コンポーネント | エンドポイント | 間隔 | 失敗閾値 |
|---------------|---------------|------|---------|
| Backend | `GET /health` (port 8000) | 30 秒 | 3 回で再起動 |
| Frontend | `/_stcore/health` (port 8501) | Docker HEALTHCHECK | — |

### 1.4 スケーリング

| コンポーネント | min | max | スケーリング条件 |
|----------------|-----|-----|-----------------|
| Backend CA | 1 | 5 | Container Apps 自動スケーリング（HTTP リクエスト数） |
| Frontend CA | 1 | 3 | Container Apps 自動スケーリング（HTTP リクエスト数） |

---

## 2. トラブルシューティング

### 2.1 よくある問題

#### 「議事録生成がエラーになる」

1. Backend のログを確認:
   ```bash
   az containerapp logs show \
     --name ca-backend-mtgminutes-dev \
     --resource-group rg-meeting-minutes-agent \
     --tail 50 --type console
   ```
2. Foundry エージェントが登録されているか確認:
   ```bash
   export FOUNDRY_PROJECT_ENDPOINT=<endpoint>
   python backend/scripts/cleanup_foundry_agents.py list
   ```
3. RBAC が正しく付与されているか確認:
   ```bash
   az role assignment list \
     --scope /subscriptions/<sub>/resourceGroups/rg-meeting-minutes-agent \
     --output table
   ```

#### 「音声の文字起こしが失敗する」

- Speech API エンドポイント (`AZURE_SPEECH_ENDPOINT`) が正しいか確認
- Managed Identity に `Cognitive Services User` ロールがあるか確認
- 音声ファイルが対応形式 (wav/mp3/mp4/m4a/ogg/webm/flac) か確認
- ファイルサイズが 100MB 以下か確認
- Batch モードの場合: AI Services MI に `Storage Blob Data Reader` ロールがあるか確認（Batch API が Blob から音声を読み取るため）

#### 「Blob Storage にアクセスできない」

- Private Endpoint が正しく構成されているか確認
- `Storage Blob Data Contributor` ロールが付与されているか確認
- `shared_access_key_enabled = false` のため、SAS やキーではアクセス不可
- Container Apps が VNet 統合されているか確認

#### 「用語辞書が反映されない」

- Blob Storage の `terms/terminology.json` が正しい JSON か確認
- キャッシュ TTL（デフォルト 300 秒）を待つか、Backend を再起動
- ローカルフォールバック (`backend/app/data/terminology.json`) も確認

#### 「コンテナが起動しない」

- ACR からのイメージプルが成功しているか確認:
  ```bash
  az containerapp show \
    --name ca-backend-mtgminutes-dev \
    --resource-group rg-meeting-minutes-agent \
    --query "properties.runningStatus"
  ```
- ACR の管理者認証が有効か、または Managed Identity が `AcrPull` ロールを持っているか確認

---

## 3. 更新手順

### 3.1 アプリケーション更新

1. コード変更をコミット
2. イメージをビルド＆プッシュ:
   ```bash
   az acr build --registry acrmtgminutesdev \
     --image meeting-minutes-backend:<new-tag> ./backend
   ```
3. Container Apps を更新:
   ```bash
   # Terraform 経由（推奨）
   # terraform.tfvars の backend_image_tag を変更後:
   cd infra && terraform plan -out=tfplan && terraform apply tfplan

   # または az CLI 直接（緊急時）
   az containerapp update \
     --name ca-backend-mtgminutes-dev \
     --resource-group rg-meeting-minutes-agent \
     --image acrmtgminutesdev.azurecr.io/meeting-minutes-backend:<new-tag>
   ```

### 3.2 インフラ変更ルール

- Azure リソースの変更は **必ず Terraform (`infra/`) を編集して `terraform apply`** で行う
- `az` CLI / ポータルで直接変更しない（ドリフト発生のため）
- やむを得ず CLI で先に変更した場合は、後で Terraform 側を実態に合わせて drift 解消

### 3.3 Foundry エージェント更新

`azd deploy` 実行時に `postdeploy` フックで自動登録される。instructions やツール定義を変更した場合は `azd deploy` で反映される。

手動で再実行する場合:

```bash
export FOUNDRY_PROJECT_ENDPOINT=<endpoint>
python backend/scripts/register_foundry_agents.py
```

### 3.4 用語辞書更新

`azd deploy` 実行時に `postdeploy` フックで `backend/app/data/terminology.json` が自動アップロードされる。

手動で再実行する場合:

```bash
az storage blob upload \
  --account-name <storage-account> \
  --container-name terms \
  --name terminology.json \
  --file backend/app/data/terminology.json \
  --auth-mode login \
  --overwrite
```

キャッシュ TTL 後に自動反映（デフォルト 5 分）。

---

## 4. 既知の制約

| 項目 | 説明 |
|------|------|
| ジョブストア | インメモリ（`_jobs` dict）。プロセス再起動で処理中ジョブは消失。完了済みジョブは Blob 履歴に永続化済み |
| Speech Phrase List | Fast Transcription API は `phraseList` 未対応。用語正規化は LLM エージェントに委任 |
| 音声正規化 | pydub (ffmpeg) で 16 kHz / 16-bit / mono WAV にリサンプル。失敗時はオリジナルで送信 |
| Storage コンテナ作成 | `Storage Blob Data Contributor` ロールではコンテナ作成不可。新規コンテナは Terraform で宣言 |
| 長時間音声 | Fast Transcription タイムアウトは httpx で最大 30 分 (read=1800s)。Batch はポーリング最大 1800s |
| Batch Transcription | AIServices kind のアカウントで動作確認済み。API バージョン `2025-10-15` + `:submit` パスが必要 |
