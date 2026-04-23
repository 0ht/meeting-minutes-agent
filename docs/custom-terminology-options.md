# 社内用語のカスタマイズ — 実装オプション

会議議事録エージェントで「社内用語・業界用語」を扱うための選択肢のまとめ。

---

## 全体像（3 段階のユースケース）

| 段階 | 課題 | 該当 Azure 機能 |
|---|---|---|
| **① 文字起こし** | 音声認識の誤変換（「えむしーぴー」→ MCP 等） | Azure Speech: Phrase List / Custom Speech |
| **② スクリプト・議事録生成** | 表記ゆれ統一、正式名称化 | LLM プロンプトに用語マッピング注入 |
| **③ 議事録への注釈** | 用語に定義を付与 | LLM + 自前データストア（Language サービス単体では不可） |

---

## ① 文字起こし時のカスタマイズ

### 1-A. Phrase List（推奨・最小コスト）

- Speech Fast Transcription のリクエストに用語リストを渡すだけ。
- 学習・デプロイ不要。コストはゼロ（Speech 課金内）。
- 件数目安: 数百件まで。
- 効果: カタカナ/英略語/人名・固有名詞の認識率改善。
- 実装箇所: `backend/app/agents/speech_transcription.py` の `definition` に `phraseList` キーを追加。

```python
definition = {
    "locales": ["ja-JP"],
    "diarization": {"maxSpeakers": 10},
    "phraseList": ["Microsoft Foundry", "MCP", "AIP", "Copilot", ...],
}
```

### 1-B. Custom Speech（高精度・運用コスト大）

- 社内録音 + 正解テキストでモデルを学習。
- 必要データ: 数十時間（最低 1〜2 時間でも可）。
- コスト: 学習＋エンドポイント月額（数百 USD〜）。
- Phrase List で精度不足の場合のみ検討。

---

## ② スクリプト・議事録生成時のカスタマイズ

### 2-A. LLM プロンプトに用語マッピング注入（推奨）

- `script_agent.py` / `minutes_agent.py` のシステムプロンプトに「変換ルール」を埋め込む。
- 文字起こしの誤りを事後修正できる多重防御。
- マッピングは Blob/CQA から取得して動的注入。

```text
【社内用語マッピング】（必ずこの正式表記を使用）
- えむしーぴー / MCP → "MCP (Model Context Protocol)"
- えーあいぴー / AIP → "Azure Information Protection (AIP)"
```

### 2-B. Azure Translator + Custom Glossary（多言語のみ）

- 日↔英など翻訳が伴う場合のみ有効。
- 用語強制翻訳を TSV/XLF 形式で管理。
- 本プロジェクト（日本語→日本語）では不要。

---

## ③ 議事録への注釈用 — 用語データストアの選択肢

### 3-A. Blob Storage（小規模・MVP 推奨）

| 項目 | 内容 |
|---|---|
| 用語規模 | 〜数百件 |
| 編集 UX | Storage Explorer / Excel / Git |
| 検索 | 全件ロード→ LLM 照合 or 部分一致 |
| コスト | ◎ ほぼゼロ |
| 実装難易度 | ★ 既存コードの差し替えのみ |

### 3-B. Azure AI Search + Synonym Map（中〜大規模・本命）

| 項目 | 内容 |
|---|---|
| 用語規模 | 数千〜数十万件 |
| 編集 UX | ポータル / Index API |
| 検索 | BM25 + ベクター + シノニム展開（表記ゆれ吸収） |
| コスト | △ 月額数十〜数百 USD |
| 実装難易度 | ★★ |

### 3-C. Azure AI Language — Custom Question Answering（業務部門編集向け）

| 項目 | 内容 |
|---|---|
| 用語規模 | 数百〜数千件 |
| 編集 UX | ◎ Language Studio (Foundry) GUI |
| 検索 | QA ペア検索（用語 → 定義） |
| コスト | ○ Language リソース月額 |
| 特徴 | バージョン管理・テスト機能・同義語登録あり |

### 3-D. Azure AI Language — Entity Linking（一般用語のみ）

- 抽出したエンティティを **Wikipedia URL に自動リンク**。
- 社内用語は対象外。一般 IT 用語の補足に有効。
- ハイブリッド構成（社内用語は 3-A〜3-C、一般用語は Entity Linking）が現実的。

### 3-E. SharePoint / OneDrive Excel + Graph API

| 項目 | 内容 |
|---|---|
| 用語規模 | 〜数千件 |
| 編集 UX | ◎ 業務部門が Excel で編集 |
| コスト | ◎ 既存ライセンスで対応可 |
| 注意 | Graph API 連携の認証実装が必要 |

### 3-F. Cosmos DB / PostgreSQL + pgvector

- 既存 RDB/NoSQL を使う場合の選択肢。本プロジェクトでは過剰。

---

## Azure AI Language で「用語辞書 → 注釈」を直接実現できない理由

公式ドキュメント (https://learn.microsoft.com/azure/ai-services/language-service/overview) より:

- Core: PII / Language Detection / **Custom NER** / Prebuilt NER / Text Analytics for Health
- Legacy: CLU / Custom Text Classification / Entity Linking / Key Phrase / **Question Answering** / Sentiment / Summarization

→ **「カスタム用語辞書を参照して定義を付与する」専用機能はない**。
最も近いのが Custom Question Answering（QA ペアで用語管理）。

---

## 注釈の表現方法（議事録の見た目）

| 方式 | 例 |
|---|---|
| **脚注番号** | `MCP[¹] を用いて...` ＋ 末尾に定義 |
| **インライン補足**（推奨） | `MCP（Model Context Protocol：AI とデータソースの標準接続規約）を用いて...` |
| **末尾の用語集セクション** | 現行実装 |

---

## 推奨ロードマップ

| フェーズ | 内容 | 想定工数 |
|---|---|---|
| **Phase 0** | Phrase List をハードコードで `speech_transcription.py` に追加 | 1 時間 |
| **Phase 1** | Blob 化（`terminology.json` を Blob から取得） + Script/Minutes prompt に用語マッピング注入 + 注釈方式をインライン補足に変更 | 半日〜1 日 |
| **Phase 2 (オプション)** | Custom Question Answering 連携（業務部門に編集 UI を提供） | 2〜3 日 |
| **Phase 3 (将来)** | AI Search ＋ Synonym Map に移行（用語数 1,000 超） | 3〜5 日 |
| **Phase 4 (必要時)** | Custom Speech モデル構築 | 数週間 |

---

## 判断フローチャート

```
用語数は？
├─ 〜100、開発者管理で OK
│    └─ Blob Storage + LLM (Phase 1)
├─ 100〜数千、業務部門が編集したい
│    └─ Custom Question Answering (Phase 2)
└─ 数千〜、表記ゆれ多数
     └─ Azure AI Search + Synonym Map (Phase 3)

文字起こし誤変換が多い？
├─ Yes (まず) → Phrase List (Phase 0)
└─ Phrase List で改善せず → Custom Speech (Phase 4)

多言語化する？
└─ Yes → Translator + Custom Glossary
```

---

## 単一ソース化の推奨

Phase 1 以降は Blob 上の `terminology.json` を **Single Source of Truth** にし、
以下 3 用途すべてで同じデータを参照するのが運用上最も簡潔:

1. Phrase List（文字起こし精度向上）
2. LLM プロンプトの用語マッピング（表記統一）
3. 用語注釈（議事録への定義付与）

```jsonc
{
  "phrase_list": ["MCP", "Azure Information Protection", "Copilot", ...],
  "term_mappings": [
    {
      "variants": ["えむしーぴー", "MCP"],
      "canonical": "MCP",
      "definition": "Model Context Protocol。AI とデータソース接続の標準規約",
      "category": "tech"
    }
  ]
}
```
