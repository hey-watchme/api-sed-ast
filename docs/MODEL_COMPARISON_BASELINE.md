# SEDモデル比較ベースライン（AST現行）

最終更新: 2026-03-09  
対象リポジトリ: `/Users/kaya.matsumoto/projects/watchme/api/behavior-analysis/feature-extractor-v2`

## 1. 目的

本ドキュメントは、SEDモデルを順次差し替えて比較するためのベースラインです。  
方針は以下の通りです。

- DB保存形式は固定（`spot_features.behavior_extractor_result`）
- APIフローは固定（`/async-process` 経由）
- 差し替えるのはモデルバックエンドのみ

---

## 2. 現行ASTの状態（Baseline A0）

### 2.1 モデル仕様

| 項目 | 値 |
|---|---|
| Backend ID | `ast_hf` |
| モデルID | `MIT/ast-finetuned-audioset-10-10-0.4593` |
| モデル種別 | AST (Audio Spectrogram Transformer) |
| 学習データ | AudioSetベース（527ラベル） |
| 入力サンプリングレート | 16kHz |
| 推論時ラベルフィルタ | デフォルト無効（raw出力、必要時のみ環境変数で有効化） |
| API version | `3.0.0` |

実装参照:

- [main_supabase.py](/Users/kaya.matsumoto/projects/watchme/api/behavior-analysis/feature-extractor-v2/main_supabase.py)
- [model_backends/ast_hf_backend.py](/Users/kaya.matsumoto/projects/watchme/api/behavior-analysis/feature-extractor-v2/model_backends/ast_hf_backend.py)
- [event_filter_config.py](/Users/kaya.matsumoto/projects/watchme/api/behavior-analysis/feature-extractor-v2/event_filter_config.py)

### 2.2 現行推論パラメータ（APIデフォルト）

| 項目 | 値 |
|---|---|
| `threshold` | `0.1` |
| `top_k` | `5` |
| `segment_duration` | `5.0s` |
| `overlap` | `0.2` |

備考: `/async-process` のバックグラウンド処理は上記デフォルトで動作。

### 2.2.1 推論パラメータ変更履歴

| 日付 | segment_duration | overlap | hop | 30秒音声の推論回数 | 変更理由・結果 |
|------|-----------------|---------|-----|-----------------|--------------|
| 〜2026-03-08 | 2.0s | 0.5 | 1.0s | 約29回 | 初期設定。短いイベント検出の高感度を優先 |
| **2026-03-09** | **5.0s** | **0.2** | **4.0s** | **約7回** | パフォーマンス改善。検出精度はほぼ変わらず、レスポンスが大幅に改善。overlap 0.2（実時間1秒重複）で境界イベントもカバー |

### 2.3 DB保存契約（固定）

| 項目 | 値 |
|---|---|
| 保存先テーブル | `spot_features` |
| 主要カラム | `device_id`, `recorded_at`, `local_date`, `local_time`, `behavior_extractor_result` |
| ステータス管理 | `behavior_status` (`processing` / `completed` / `failed`) |
| 出力形式 | `[{ "time": <sec>, "events": [{ "label": "...", "score": ... }] }]` |

---

## 3. EC2リソース占有（AST実測スナップショット）

計測時刻: 2026-03-06 01:11 JST（EC2出力: 2026-03-05 16:11 UTC）

注意: このセクションは当時の実測スナップショットであり、再開時点の現況確認は AWS MCP または AWS CLI で再確認すること。

### 3.1 インスタンス全体

| 項目 | 値 |
|---|---|
| インスタンスタイプ | `t4g.small`（2 vCPU / 2GB RAM / 30GB gp3） |
| メモリ全体 | 1.8GiB |
| メモリ使用 | 1.0GiB（free 96Mi, cache 932Mi, available 827Mi） |
| Swap | 2.0GiB中 1.1GiB使用 |
| ルートディスク | 29GB中 17GB使用（58%） |

### 3.2 ASTコンテナ単体（`behavior-analysis-feature-extractor`）

| 項目 | 値 |
|---|---|
| 稼働メモリ（アイドル時） | 180.2MiB / 1.797GiB（9.80%） |
| CPU（アイドル時） | 0.12% |
| コンテナサイズ | 346MB（virtual 2.56GB） |
| Dockerイメージサイズ | 2.21GB |
| コンテナ内HFキャッシュ | 331MB (`/root/.cache/huggingface`) |

### 3.3 Docker全体（参考）

| 項目 | 値 |
|---|---|
| Images合計 | 5.229GB |
| Containers合計 | 349.5MB |
| ASTイメージ比率 | 約42%（2.21GB / 5.229GB） |

---

## 4. 精度・有用性 比較項目（これから埋める）

### 4.1 ターゲットイベント

- 咳（Cough）
- くしゃみ（Sneeze）
- ドア系（Door / Knock等）
- 食器系（Dishes / Cutlery等）
- その他日常物音

### 4.2 評価軸

| カテゴリ | 指標 |
|---|---|
| 精度 | Precision / Recall / F1（イベント別） |
| 実用性 | 誤検知の少なさ、見逃しの少なさ、運用しやすさ |
| 性能 | 1ファイル処理時間、CPU%、メモリ使用量ピーク |
| コスト | 追加イメージ容量、EC2負荷、ECR増分 |
| 実装難易度 | 導入工数、依存ライブラリ、保守性 |

---

## 5. モデル比較テーブル（追記用）

| ID | モデル名 | 学習/チューニング | 対象クラス数 | 推論速度 | メモリ占有 | イメージ増分 | 咳F1 | くしゃみF1 | 物音F1 | 総評 |
|---|---|---|---:|---|---|---|---:|---:|---:|---|
| A0 | AST `MIT/ast-finetuned-audioset-10-10-0.4593` | AudioSet fine-tuned | 527 | 未計測（実運用中） | 180.2MiB idle | 基準（2.21GB image） | 未計測 | 未計測 | 未計測 | Baseline |
| B1 |  |  |  |  |  |  |  |  |  |  |
| B2 |  |  |  |  |  |  |  |  |  |  |
| B3 |  |  |  |  |  |  |  |  |  |  |

---

## 6. 比較実行ログ（追記用）

| Run ID | 日時 | モデル | テスト音源セット | パラメータ | 主な結果 | 備考 |
|---|---|---|---|---|---|---|
| R001 | 2026-03-09 | AST (A0) | 本番録音 | `threshold=0.1, top_k=5, segment=5s, overlap=0.2` | 精度ほぼ変わらず、レスポンス大幅改善 | 旧設定(2s/0.5)からの変更後確認 |

---

## 7. 実行コマンドメモ（運用）

### ASTコンテナ実測（EC2）

```bash
docker stats --no-stream behavior-analysis-feature-extractor
docker ps --size --filter name=behavior-analysis-feature-extractor
docker images | grep watchme-behavior-analysis-feature-extractor
docker exec behavior-analysis-feature-extractor sh -lc 'du -sh /root/.cache/huggingface'
```

### API実行（本番フロー）

```bash
curl -X POST "https://api.hey-watch.me/behavior-analysis/features/async-process" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "files/<device_id>/<YYYY-MM-DD>/<HH-MM>/audio.wav",
    "device_id": "<uuid>",
    "recorded_at": "<UTC timestamp>"
  }'
```

---

## 8. MCP導入時のセッション再開メモ（重要）

AWS MCP導入後は、Codexセッション再起動で一時的に会話が切断される想定。  
再開時はこの手順でコンテキストを復元する。

### 8.1 再開時に最初に確認するファイル

1. 本比較ドキュメント  
   [MODEL_COMPARISON_BASELINE.md](/Users/kaya.matsumoto/projects/watchme/api/behavior-analysis/feature-extractor-v2/docs/MODEL_COMPARISON_BASELINE.md)
2. SED本体実装  
   [main_supabase.py](/Users/kaya.matsumoto/projects/watchme/api/behavior-analysis/feature-extractor-v2/main_supabase.py)
3. モデル切替バックエンド  
   [model_backends/factory.py](/Users/kaya.matsumoto/projects/watchme/api/behavior-analysis/feature-extractor-v2/model_backends/factory.py)
4. IAM/CLI運用方針  
   [TECHNICAL_REFERENCE.md](/Users/kaya.matsumoto/projects/watchme/server-configs/docs/TECHNICAL_REFERENCE.md:27)

### 8.2 現在の前提（再開時点）

- Baselineは `A0 = AST (MIT/ast-finetuned-audioset-10-10-0.4593)`
- DB保存形式は固定（`spot_features.behavior_extractor_result`）
- モデル切替は `SED_MODEL_BACKEND` / `SED_MODEL_NAME` で行う
- EC2管理系CLIは `--profile admin` を使う（`default` は一部操作不可）

### 8.3 再開後の最初の実行コマンド

```bash
# 作業ディレクトリ
cd /Users/kaya.matsumoto/projects/watchme/api/behavior-analysis/feature-extractor-v2

# 変更状況確認
git status --short

# AWSプロファイル確認（admin優先）
aws sts get-caller-identity --profile admin

# defaultも確認したい場合のみ
aws sts get-caller-identity
```

### 8.4 次の作業開始ポイント

- まずASTベースライン計測を実施（同一音源セット）
- その後、追加モデルを `model_backends/` に1つずつ実装
- 各モデルの結果を本ドキュメントの比較表（Section 5）へ追記

### 8.5 AWS MCP設定（導入済み）

- Codex設定ファイル: `/Users/kaya.matsumoto/.codex/config.toml`
  - `[mcp_servers.aws]`
  - `command = "/Users/kaya.matsumoto/.codex/bin/start-aws-mcp.sh"`
- 起動ラッパー: `/Users/kaya.matsumoto/.codex/bin/start-aws-mcp.sh`
  - 既定プロファイル: `admin`
  - 既定リージョン: `ap-southeast-2`
  - 上書き環境変数: `AWS_MCP_PROFILE`, `AWS_MCP_REGION`
