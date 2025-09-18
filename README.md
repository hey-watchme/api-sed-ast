# AST Audio Event Detection API

Audio Spectrogram Transformer (AST) を使用した音響イベント検出APIのローカル環境プロトタイプ

## 概要

Hugging Faceで公開されている事前学習済みモデル `MIT/ast-finetuned-audioset-10-10-0.4593` を使用して、音声ファイルから音響イベント（Speech、Music、Cough、Laughterなど）を検出するWeb APIサーバーです。

## 特徴

- 🎯 **527種類の音響イベント**を検出可能（AudioSetベース）
- 🚀 **Transformerベース**の最新アーキテクチャ
- 📊 **確率スコア付き**で上位5件の予測結果を返す
- 🔧 **FastAPI**による高速なAPIサーバー

## セットアップ

### 1. 仮想環境の作成（推奨）

```bash
# 仮想環境を作成
python3 -m venv venv

# 仮想環境を有効化
source venv/bin/activate  # macOS/Linux
# または
venv\Scripts\activate     # Windows
```

### 2. 依存ライブラリのインストール

```bash
# requirements.txtからインストール
pip install -r requirements.txt
```

⚠️ **注意**: 初回起動時にモデル（約350MB）が自動ダウンロードされます。

### 3. モデルの動作確認（オプション）

```bash
# テストスクリプトを実行
python3 test_model.py
```

## サーバーの起動

```bash
# APIサーバーを起動（ポート8017で動作）
python3 main.py
```

起動成功時の表示:
```
==================================================
AST Audio Event Detection API
Model: MIT/ast-finetuned-audioset-10-10-0.4593
==================================================
モデルをロード中: MIT/ast-finetuned-audioset-10-10-0.4593
✅ モデルのロードに成功しました
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8017
```

## APIの使用方法

### 利用可能なサーバー

このプロジェクトには2つのAPIサーバーがあります：

1. **`main.py`** - 基本的な音響イベント検出
2. **`main_timeline.py`** - 時系列分析機能付き（推奨）

### サーバーの起動

```bash
# 時系列分析機能付きサーバー（推奨）
python3 main_timeline.py

# または基本サーバー
python3 main.py
```

### ヘルスチェック

```bash
# サーバーの状態を確認
curl http://localhost:8017/health
```

レスポンス例:
```json
{
  "status": "healthy",
  "model_loaded": true
}
```

## エンドポイント

### 1. `/analyze_sound` - 音声ファイル全体の分析

音声ファイル全体から主要な音響イベントを検出します。

```bash
# 音声ファイルをアップロードして分析
curl -X POST "http://localhost:8017/analyze_sound" \
  -F "file=@test_audio.wav" \
  -H "accept: application/json"
```

#### パラメータ
- `file`: 音声ファイル（必須）
  - 対応形式: WAV, MP3, FLAC, OGG, M4A
- `top_k`: 返す予測結果の数（オプション、デフォルト: 5）

#### レスポンス例
```json
{
  "predictions": [
    { "label": "Speech", "score": 0.8521 },
    { "label": "Music", "score": 0.0754 },
    { "label": "Cough", "score": 0.0213 },
    { "label": "Laughter", "score": 0.0152 },
    { "label": "Silence", "score": 0.0081 }
  ],
  "audio_info": {
    "filename": "test_audio.wav",
    "duration_seconds": 10.5,
    "sample_rate": 16000
  }
}
```

### 2. `/analyze_timeline` - 時系列分析（新機能）

音声を時系列で分析し、1秒ごとの音響イベントを検出します。

```bash
# 時系列分析（1秒ごと、50%オーバーラップ）
curl -X POST "http://localhost:8017/analyze_timeline" \
  -F "file=@test_audio.wav" \
  -F "segment_duration=1.0" \
  -F "overlap=0.5" \
  -F "top_k=3"
```

#### パラメータ
- `file`: 音声ファイル（必須）
- `segment_duration`: セグメントの長さ（秒）（オプション、デフォルト: 1.0）
- `overlap`: オーバーラップ率 0-1（オプション、デフォルト: 0.5）
- `top_k`: 各時刻で返すイベント数（オプション、デフォルト: 3）

#### レスポンス例
```json
{
  "timeline": [
    {
      "time": 0.0,
      "events": [
        { "label": "Speech", "score": 0.7521 },
        { "label": "Background noise", "score": 0.1234 },
        { "label": "Music", "score": 0.0521 }
      ]
    },
    {
      "time": 0.5,
      "events": [
        { "label": "Cough", "score": 0.8921 },
        { "label": "Throat clearing", "score": 0.0621 },
        { "label": "Speech", "score": 0.0234 }
      ]
    }
  ],
  "summary": {
    "total_segments": 78,
    "duration_seconds": 39.9,
    "segment_duration": 1.0,
    "overlap": 0.5,
    "most_common_events": [
      {
        "label": "Speech",
        "occurrences": 47,
        "average_score": 0.352
      }
    ]
  },
  "audio_info": {
    "filename": "test_audio.wav",
    "duration_seconds": 39.9,
    "sample_rate": 16000
  }
}
```

## S3統合機能

AWS S3から直接音声ファイルを取得して分析できます。

### S3音声ファイルの分析

```bash
# 基本的な分析
python3 analyze_s3_audio.py

# 時系列分析
python3 analyze_s3_timeline.py

# カスタムS3パスを指定
python3 analyze_s3_timeline.py "files/device_id/date/time/audio.wav"
```

### 必要な環境変数（.env）

```env
# AWS S3設定
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
S3_BUCKET_NAME=your_bucket
AWS_REGION=us-east-1
```

### 出力ファイル

時系列分析を実行すると、以下のファイルが生成されます：

- `timeline_result.json` - 完全な時系列データ
- `timeline.csv` - CSV形式の時系列データ（Excel等で開ける）
- `analysis_result.json` - 全体分析の結果

## テスト用音声ファイルの作成

macOSの場合、以下のコマンドで簡単なテスト音声を録音できます:

```bash
# 5秒間の音声を録音
rec -r 16000 -c 1 test_audio.wav trim 0 5

# または、macOSの標準コマンドで
say "This is a test audio for AST model" -o test_speech.wav --data-format=LEI16@16000
```

## 検出可能な音響イベントの例

このモデルはAudioSetデータセットで学習されており、以下のような音響イベントを検出できます:

### 人間の音
- Speech（会話）
- Laughter（笑い声）
- Cough（咳）
- Sneeze（くしゃみ）
- Crying（泣き声）
- Singing（歌声）

### 環境音
- Music（音楽）
- Silence（静寂）
- Door（ドアの音）
- Footsteps（足音）
- Applause（拍手）

### その他
- 動物の鳴き声
- 楽器の音
- 機械音
- 自然音

完全なリストは527種類のカテゴリを含みます。

## トラブルシューティング

### モデルのダウンロードが遅い

初回起動時にHugging Faceからモデルをダウンロードするため、ネットワーク環境によっては時間がかかることがあります。モデルは `~/.cache/huggingface/` にキャッシュされます。

### メモリ不足エラー

ASTモデルは比較的大きいため、最低4GB以上のRAMが推奨されます。

### ポート8017が使用中

```bash
# 使用中のプロセスを確認
lsof -i :8017

# 別のポートで起動する場合はmain.pyを編集
# port=8017 を port=8018 などに変更
```

## 技術詳細

- **モデル**: MIT/ast-finetuned-audioset-10-10-0.4593
- **アーキテクチャ**: Audio Spectrogram Transformer (AST)
- **入力**: 16kHz サンプリングレートの音声
- **出力**: 527クラスの確率分布
- **フレームワーク**: PyTorch + Transformers

## ライセンス

このプロトタイプは検証用です。モデル自体のライセンスはMITライセンスに従います。

## 参考資料

- [AST論文](https://arxiv.org/abs/2104.01778)
- [Hugging Face Model Card](https://huggingface.co/MIT/ast-finetuned-audioset-10-10-0.4593)
- [AudioSetデータセット](https://research.google.com/audioset/)