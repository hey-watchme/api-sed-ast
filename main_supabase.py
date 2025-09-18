#!/usr/bin/env python3
"""
AST (Audio Spectrogram Transformer) 音響イベント検出API - Supabase統合版
file_pathsベースの処理でaudio_filesテーブルと連携
"""

import os
import io
import json
import tempfile
import traceback
from typing import List, Dict, Optional
from datetime import datetime
import time

import torch
import numpy as np
import librosa
import soundfile as sf
from transformers import AutoFeatureExtractor, ASTForAudioClassification
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# AWS S3とSupabase
import boto3
from botocore.exceptions import ClientError
from supabase import create_client, Client
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

# グローバル変数でモデルを保持
model = None
feature_extractor = None
id2label = None

# モデル名
MODEL_NAME = "MIT/ast-finetuned-audioset-10-10-0.4593"

# Supabaseクライアントの初期化
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URLおよびSUPABASE_KEYが設定されていません")

supabase: Client = create_client(supabase_url, supabase_key)
print(f"✅ Supabase接続設定完了: {supabase_url}")

# AWS S3クライアントの初期化
aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
s3_bucket_name = os.getenv('S3_BUCKET_NAME', 'watchme-vault')
aws_region = os.getenv('AWS_REGION', 'us-east-1')

if not aws_access_key_id or not aws_secret_access_key:
    raise ValueError("AWS_ACCESS_KEY_IDおよびAWS_SECRET_ACCESS_KEYが設定されていません")

s3_client = boto3.client(
    's3',
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    region_name=aws_region
)
print(f"✅ AWS S3接続設定完了: バケット={s3_bucket_name}, リージョン={aws_region}")

# FastAPIアプリケーション
app = FastAPI(
    title="AST Audio Event Detection API with Supabase",
    description="Audio Spectrogram Transformer を使用した音響イベント検出API（Supabase統合版）",
    version="2.0.0"
)

# CORSミドルウェアの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# リクエストモデル
class FetchAndProcessPathsRequest(BaseModel):
    file_paths: List[str]
    threshold: Optional[float] = 0.1
    top_k: Optional[int] = 3
    analyze_timeline: Optional[bool] = True  # タイムライン分析を実行するか
    segment_duration: Optional[float] = 10.0  # セグメントの長さ（秒）- 10秒が最適
    overlap: Optional[float] = 0.0  # オーバーラップ率 - オーバーラップなしが最適

def load_model():
    """モデルとfeature extractorを読み込む"""
    global model, feature_extractor, id2label
    
    print(f"🔄 モデルをロード中: {MODEL_NAME}")
    try:
        feature_extractor = AutoFeatureExtractor.from_pretrained(MODEL_NAME)
        model = ASTForAudioClassification.from_pretrained(MODEL_NAME)
        
        # ラベルマッピングを取得
        id2label = model.config.id2label
        
        # CPUで実行
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
        model.eval()
        
        print(f"✅ モデルのロードに成功しました")
        print(f"   - デバイス: {device}")
        print(f"   - ラベル数: {len(id2label)}")
        
    except Exception as e:
        print(f"❌ モデルのロードに失敗しました: {str(e)}")
        raise

def extract_info_from_file_path(file_path: str) -> Dict[str, str]:
    """
    ファイルパスからデバイスID、日付、時間ブロックを抽出
    
    Args:
        file_path: S3ファイルパス (例: files/device-id/2025-07-20/14-30/audio.wav)
    
    Returns:
        device_id, date, time_block を含む辞書
    """
    parts = file_path.split('/')
    
    if len(parts) >= 5:
        device_id = parts[1]
        date = parts[2]
        time_block = parts[3]
        return {
            'device_id': device_id,
            'date': date,
            'time_block': time_block
        }
    else:
        # パスが期待する形式でない場合
        return {
            'device_id': 'unknown',
            'date': 'unknown',
            'time_block': 'unknown'
        }

async def update_audio_files_status(file_path: str, status: str = 'completed'):
    """
    audio_filesテーブルのbehavior_features_statusを更新（YamNetと同じフィールドを使用）
    
    Args:
        file_path: ファイルパス
        status: ステータス ('pending', 'processing', 'completed', 'error')
    """
    try:
        update_response = supabase.table('audio_files') \
            .update({'behavior_features_status': status}) \
            .eq('file_path', file_path) \
            .execute()
        
        if update_response.data:
            print(f"✅ ステータス更新成功: {file_path} -> {status}")
            return True
        else:
            print(f"⚠️ 対象レコードが見つかりません: {file_path}")
            return False
            
    except Exception as e:
        print(f"❌ ステータス更新エラー: {str(e)}")
        return False

async def save_to_behavior_yamnet(device_id: str, date: str, time_block: str, 
                                  timeline_data: List[Dict]):
    """
    behavior_yamnetテーブルにタイムライン形式の結果を保存
    
    Args:
        device_id: デバイスID
        date: 日付
        time_block: 時間ブロック
        timeline_data: タイムライン形式のイベントデータ
    """
    try:
        # タイムライン形式のデータをeventsカラムに保存
        data = {
            'device_id': device_id,
            'date': date,
            'time_block': time_block,
            'events': timeline_data,  # タイムライン形式のデータ
            'status': 'completed'  # ASTによる処理完了
        }
        
        # upsert（既存データがあれば更新、なければ挿入）
        response = supabase.table('behavior_yamnet') \
            .upsert(data, on_conflict='device_id,date,time_block') \
            .execute()
        
        if response.data:
            print(f"✅ データ保存成功: {device_id}/{date}/{time_block}")
            return True
        else:
            print(f"⚠️ データ保存失敗: レスポンスが空です")
            return False
            
    except Exception as e:
        print(f"❌ データ保存エラー: {str(e)}")
        traceback.print_exc()
        return False

def download_from_s3(file_path: str, local_path: str) -> bool:
    """
    S3から音声ファイルをダウンロード
    
    Args:
        file_path: S3のファイルパス
        local_path: ローカル保存先パス
    
    Returns:
        成功時True、失敗時False
    """
    try:
        print(f"📥 S3からダウンロード中: {file_path}")
        s3_client.download_file(s3_bucket_name, file_path, local_path)
        print(f"✅ ダウンロード完了: {file_path}")
        return True
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            print(f"❌ ファイルが見つかりません: {file_path}")
        else:
            print(f"❌ S3ダウンロードエラー: {error_code} - {str(e)}")
        return False
    except Exception as e:
        print(f"❌ 予期しないエラー: {str(e)}")
        return False

def process_audio(audio_data: np.ndarray, sample_rate: int) -> np.ndarray:
    """
    音声データを前処理する
    
    Args:
        audio_data: 音声データ（numpy配列）
        sample_rate: サンプリングレート
    
    Returns:
        処理済みの音声データ
    """
    # モノラルに変換
    if len(audio_data.shape) > 1:
        audio_data = np.mean(audio_data, axis=1)
    
    # モデルが期待するサンプリングレートにリサンプリング（16kHz）
    target_sr = feature_extractor.sampling_rate
    if sample_rate != target_sr:
        audio_data = librosa.resample(
            audio_data, 
            orig_sr=sample_rate, 
            target_sr=target_sr
        )
    
    # float32に変換
    if audio_data.dtype != np.float32:
        audio_data = audio_data.astype(np.float32)
    
    # 正規化（-1.0 〜 1.0）
    max_val = np.max(np.abs(audio_data))
    if max_val > 0:
        audio_data = audio_data / max_val
    
    return audio_data

def predict_audio_events(audio_data: np.ndarray, top_k: int = 5, threshold: float = 0.1) -> List[Dict]:
    """
    音声データから音響イベントを予測
    
    Args:
        audio_data: 前処理済みの音声データ
        top_k: 返す上位予測の数
        threshold: 最小確率しきい値
    
    Returns:
        予測結果のリスト
    """
    # 特徴抽出
    inputs = feature_extractor(
        audio_data,
        sampling_rate=feature_extractor.sampling_rate,
        return_tensors="pt"
    )
    
    # デバイスに移動
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}
    
    # 推論実行
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
    
    # Softmaxで確率に変換
    probs = torch.nn.functional.softmax(logits, dim=-1)[0]
    
    # 上位k個を取得
    top_probs, top_indices = torch.topk(probs, min(top_k, len(probs)))
    
    # 結果を整形
    predictions = []
    for prob, idx in zip(top_probs.cpu(), top_indices.cpu()):
        score = prob.item()
        if score >= threshold:  # しきい値以上のみ
            label_id = idx.item()
            label = id2label.get(label_id) or id2label.get(str(label_id)) or f"Event_{label_id}"
            predictions.append({
                "label": label,
                "score": round(score, 4)
            })
    
    return predictions

def analyze_timeline(audio_data: np.ndarray, sample_rate: int, 
                    segment_duration: float = 1.0, 
                    overlap: float = 0.5,
                    top_k: int = 3,
                    threshold: float = 0.1) -> Dict:
    """
    音声データを時系列で分析
    
    Args:
        audio_data: 音声データ
        sample_rate: サンプリングレート
        segment_duration: セグメントの長さ（秒）
        overlap: オーバーラップ率 (0-1)
        top_k: 各時刻で返すイベント数
        threshold: 最小確率しきい値
    
    Returns:
        時系列分析結果
    """
    # 音声を前処理
    processed_audio = process_audio(audio_data, sample_rate)
    target_sr = feature_extractor.sampling_rate
    
    # セグメント設定
    segment_samples = int(segment_duration * target_sr)
    hop_samples = int(segment_samples * (1 - overlap))
    
    # タイムライン結果を格納
    timeline = []
    all_events = {}
    
    # セグメントごとに処理
    for i in range(0, len(processed_audio) - segment_samples + 1, hop_samples):
        segment = processed_audio[i:i + segment_samples]
        time_position = i / target_sr
        
        # セグメントの予測
        events = predict_audio_events(segment, top_k, threshold)
        
        # タイムラインに追加
        timeline.append({
            "time": round(time_position, 1),
            "events": events
        })
        
        # イベントの集計
        for event in events:
            label = event["label"]
            if label not in all_events:
                all_events[label] = {"count": 0, "total_score": 0}
            all_events[label]["count"] += 1
            all_events[label]["total_score"] += event["score"]
    
    # 最も頻繁なイベントを集計
    most_common = []
    for label, stats in sorted(all_events.items(), key=lambda x: x[1]["count"], reverse=True)[:5]:
        most_common.append({
            "label": label,
            "occurrences": stats["count"],
            "average_score": round(stats["total_score"] / stats["count"], 4)
        })
    
    return {
        "timeline": timeline,
        "summary": {
            "total_segments": len(timeline),
            "duration_seconds": round(len(processed_audio) / target_sr, 1),
            "segment_duration": segment_duration,
            "overlap": overlap,
            "most_common_events": most_common
        }
    }

async def process_single_file(file_path: str, threshold: float = 0.1, top_k: int = 5,
                             analyze_timeline_flag: bool = True, 
                             segment_duration: float = 1.0,
                             overlap: float = 0.5) -> Dict:
    """
    単一ファイルを処理（タイムライン形式で保存）
    
    Args:
        file_path: S3ファイルパス
        threshold: 最小確率しきい値
        top_k: 返す上位予測の数
        analyze_timeline_flag: タイムライン分析を実行するか（常にTrue推奨）
        segment_duration: セグメントの長さ
        overlap: オーバーラップ率
    
    Returns:
        処理結果
    """
    temp_file = None
    try:
        # ファイル情報を抽出
        file_info = extract_info_from_file_path(file_path)
        
        # ステータスを処理中に更新
        await update_audio_files_status(file_path, 'processing')
        
        # 一時ファイルを作成してダウンロード
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            temp_file = tmp.name
        
        if not download_from_s3(file_path, temp_file):
            await update_audio_files_status(file_path, 'error')
            return {"status": "error", "file_path": file_path, "error": "Download failed"}
        
        # 音声データを読み込む
        audio_data, sample_rate = sf.read(temp_file)
        print(f"🎵 音声ロード完了: {len(audio_data)/sample_rate:.2f}秒, {sample_rate}Hz")
        
        # タイムライン分析を実行（必須）
        timeline_result = analyze_timeline(
            audio_data, sample_rate,
            segment_duration, overlap, top_k, threshold
        )
        
        # タイムライン形式のデータをbehavior_yamnetテーブルに保存
        save_success = await save_to_behavior_yamnet(
            file_info['device_id'],
            file_info['date'],
            file_info['time_block'],
            timeline_result['timeline']  # タイムラインデータのみを保存
        )
        
        if save_success:
            # ステータスを完了に更新
            await update_audio_files_status(file_path, 'completed')
            
            return {
                "status": "success",
                "file_path": file_path,
                "device_id": file_info['device_id'],
                "date": file_info['date'],
                "time_block": file_info['time_block'],
                "timeline": timeline_result
            }
        else:
            await update_audio_files_status(file_path, 'error')
            return {"status": "error", "file_path": file_path, "error": "Save failed"}
            
    except Exception as e:
        print(f"❌ ファイル処理エラー: {file_path} - {str(e)}")
        traceback.print_exc()
        await update_audio_files_status(file_path, 'error')
        return {"status": "error", "file_path": file_path, "error": str(e)}
        
    finally:
        # 一時ファイルを削除
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)

@app.on_event("startup")
async def startup_event():
    """サーバー起動時にモデルをロード"""
    load_model()

@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "message": "AST Audio Event Detection API with Supabase Integration",
        "model": MODEL_NAME,
        "version": "2.0.0",
        "status": "ready" if model is not None else "not ready",
        "endpoints": {
            "/fetch-and-process-paths": "Process audio files from S3 via file paths",
            "/health": "Health check endpoint"
        }
    }

@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {
        "status": "healthy" if model is not None else "unhealthy",
        "model_loaded": model is not None,
        "supabase_connected": supabase is not None,
        "s3_connected": s3_client is not None
    }

@app.post("/fetch-and-process-paths")
async def fetch_and_process_paths(request: FetchAndProcessPathsRequest):
    """
    file_pathsベースの音響イベント検出エンドポイント（Whisper APIパターン）
    
    Args:
        request: file_paths配列とオプションパラメータ
    
    Returns:
        処理結果のサマリーと詳細
    """
    # モデルがロードされているか確認
    if model is None or feature_extractor is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    start_time = time.time()
    
    # 処理結果を格納
    processed_files = []
    error_files = []
    processed_time_blocks = set()
    
    print(f"🚀 処理開始: {len(request.file_paths)}個のファイル")
    
    # 各ファイルを処理
    for file_path in request.file_paths:
        result = await process_single_file(
            file_path,
            request.threshold,
            request.top_k,
            request.analyze_timeline,
            request.segment_duration,
            request.overlap
        )
        
        if result["status"] == "success":
            processed_files.append(file_path)
            processed_time_blocks.add(result["time_block"])
        else:
            error_files.append({
                "file_path": file_path,
                "error": result.get("error", "Unknown error")
            })
    
    # 実行時間を計算
    execution_time = time.time() - start_time
    
    # サマリーを作成
    total_files = len(request.file_paths)
    success_count = len(processed_files)
    error_count = len(error_files)
    
    response = {
        "status": "success" if error_count == 0 else "partial",
        "summary": {
            "total_files": total_files,
            "processed": success_count,
            "errors": error_count
        },
        "processed_files": processed_files,
        "processed_time_blocks": list(processed_time_blocks),
        "error_files": error_files if error_files else None,
        "execution_time_seconds": round(execution_time, 1),
        "message": f"{total_files}件中{success_count}件を正常に処理しました"
    }
    
    print(f"✅ 処理完了: {success_count}/{total_files}件成功 (実行時間: {execution_time:.1f}秒)")
    
    return JSONResponse(content=response)

if __name__ == "__main__":
    # サーバーを起動（ポート8018で動作）
    print("=" * 50)
    print("AST Audio Event Detection API with Supabase")
    print(f"Model: {MODEL_NAME}")
    print("=" * 50)
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8018,
        log_level="info"
    )