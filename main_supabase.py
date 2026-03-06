#!/usr/bin/env python3
"""
Sound Event Detection API - Supabase Integration
file_paths-based processing with audio_files table integration.
"""

import os
import json
import tempfile
import traceback
from typing import List, Dict, Optional
import time

import numpy as np
import librosa
import soundfile as sf
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# AWS S3 and Supabase
import boto3
from botocore.exceptions import ClientError
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Event filtering
from event_filter_config import apply_event_filter, get_filter_stats
from model_backends import BaseSedBackend, create_backend

# Global model backend (switchable)
sed_backend: Optional[BaseSedBackend] = None
DEFAULT_SAMPLING_RATE = 16000
APP_VERSION = "3.0.0"

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
aws_region = os.getenv('AWS_REGION', 'ap-southeast-2')
FEATURE_COMPLETED_QUEUE_URL = os.environ.get(
    'FEATURE_COMPLETED_QUEUE_URL',
    'https://sqs.ap-southeast-2.amazonaws.com/754724220380/watchme-feature-completed-queue'
)

if not aws_access_key_id or not aws_secret_access_key:
    raise ValueError("AWS_ACCESS_KEY_IDおよびAWS_SECRET_ACCESS_KEYが設定されていません")

s3_client = boto3.client(
    's3',
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    region_name=aws_region
)
print(f"✅ AWS S3接続設定完了: バケット={s3_bucket_name}, リージョン={aws_region}")

# AWS SQSクライアントの初期化
sqs = boto3.client('sqs', region_name=aws_region)

# FastAPI application
app = FastAPI(
    title="AST Audio Event Detection API with Supabase",
    description="Audio Spectrogram Transformer for sound event detection (Supabase integration) - v3",
    version=APP_VERSION
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
    threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    top_k: int = Field(default=5, ge=1)
    analyze_timeline: Optional[bool] = True
    segment_duration: float = Field(default=2.0, gt=0.0)  # 高感度検出向け
    overlap: float = Field(default=0.5, ge=0.0, lt=1.0)  # 50% overlap for short events

def load_model():
    """Load configured SED backend model."""
    global sed_backend

    try:
        sed_backend = create_backend()
        sed_backend.load()
    except Exception as e:
        print(f"❌ Failed to load model backend: {str(e)}")
        traceback.print_exc()
        raise


def get_model_name() -> str:
    if sed_backend is not None:
        return sed_backend.model_name
    return os.getenv("SED_MODEL_NAME", "MIT/ast-finetuned-audioset-10-10-0.4593")


def get_sampling_rate() -> int:
    if sed_backend is not None:
        return sed_backend.sample_rate
    return DEFAULT_SAMPLING_RATE


def get_backend_id() -> str:
    if sed_backend is not None:
        return sed_backend.backend_id
    return os.getenv("SED_MODEL_BACKEND", "ast_hf")

def validate_processing_options(
    *,
    segment_duration: float,
    overlap: float,
    top_k: int,
    threshold: float,
) -> None:
    """Validate processing options before timeline slicing."""
    if segment_duration <= 0:
        raise ValueError("segment_duration must be greater than 0")
    if not 0 <= overlap < 1:
        raise ValueError("overlap must be between 0 and 1 (1 is not allowed)")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")

async def save_to_spot_features(device_id: str, recorded_at: str,
                                 timeline_data: List[Dict]):
    """
    spot_featuresテーブルにタイムライン形式の結果を保存

    Args:
        device_id: デバイスID
        recorded_at: 録音日時 (UTC timestamp)
        timeline_data: タイムライン形式のイベントデータ
    """
    try:
        # Get local_date and local_time from audio_files table
        local_date = None
        local_time = None
        try:
            audio_file_response = supabase.table('audio_files').select('local_date, local_time').eq(
                'device_id', device_id
            ).eq(
                'recorded_at', recorded_at
            ).execute()

            if audio_file_response.data and len(audio_file_response.data) > 0:
                local_date = audio_file_response.data[0].get('local_date')
                local_time = audio_file_response.data[0].get('local_time')
                print(f"Retrieved local_date from audio_files: {local_date}")
                print(f"Retrieved local_time from audio_files: {local_time}")
            else:
                print(f"⚠️ No audio_files record found for device_id={device_id}, recorded_at={recorded_at}")
        except Exception as e:
            print(f"❌ Error fetching local_date/local_time from audio_files: {e}")

        data = {
            'device_id': device_id,
            'recorded_at': recorded_at,
            'local_date': local_date,  # Local date from audio_files
            'local_time': local_time,  # Local time from audio_files
            'behavior_extractor_result': timeline_data  # JSONB形式
        }

        response = supabase.table('spot_features') \
            .upsert(data) \
            .execute()

        if response.data:
            print(f"✅ spot_features保存成功: {device_id}/{recorded_at}")
            return True
        else:
            print(f"⚠️ データ保存失敗: レスポンスが空です")
            return False

    except Exception as e:
        print(f"❌ データ保存エラー: {str(e)}")
        traceback.print_exc()
        return False

def download_from_s3(file_path: str, local_path: str) -> bool:
    """S3から音声ファイルをダウンロード"""
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
    Preprocess audio data for AST model

    Args:
        audio_data: Audio data (numpy array)
        sample_rate: Original sampling rate

    Returns:
        Processed audio data
    """
    # Convert to mono
    if len(audio_data.shape) > 1:
        audio_data = np.mean(audio_data, axis=1)

    # Resample to model backend's expected sampling rate
    target_sr = get_sampling_rate()
    if sample_rate != target_sr:
        audio_data = librosa.resample(
            audio_data,
            orig_sr=sample_rate,
            target_sr=target_sr
        )

    # Convert to float32
    if audio_data.dtype != np.float32:
        audio_data = audio_data.astype(np.float32)

    # Normalize (-1.0 to 1.0)
    max_val = np.max(np.abs(audio_data))
    if max_val > 0:
        audio_data = audio_data / max_val

    return audio_data

def predict_audio_events(audio_data: np.ndarray, top_k: int = 5,
                        threshold: float = 0.1) -> List[Dict]:
    """
    Predict audio events from audio data

    Args:
        audio_data: Preprocessed audio data
        top_k: Number of top predictions to return
        threshold: Minimum probability threshold

    Returns:
        List of predicted events
    """
    if sed_backend is None:
        raise RuntimeError("Model backend is not loaded")

    predictions = sed_backend.predict_events(
        audio_data=audio_data,
        top_k=top_k,
        threshold=threshold
    )

    # Apply event filtering (v2 feature)
    predictions = apply_event_filter(predictions)

    return predictions

def analyze_timeline(audio_data: np.ndarray, sample_rate: int,
                    segment_duration: float = 2.0,
                    overlap: float = 0.5,
                    top_k: int = 5,
                    threshold: float = 0.1) -> Dict:
    """
    Analyze audio data in timeline segments

    Args:
        audio_data: Audio data
        sample_rate: Sampling rate
        segment_duration: Segment length in seconds (default 2s)
        overlap: Overlap ratio (0-1, default 0.5)
        top_k: Number of events to return per segment (default 5)
        threshold: Minimum probability threshold

    Returns:
        Timeline analysis results
    """
    validate_processing_options(
        segment_duration=segment_duration,
        overlap=overlap,
        top_k=top_k,
        threshold=threshold,
    )

    # Preprocess audio
    processed_audio = process_audio(audio_data, sample_rate)
    target_sr = get_sampling_rate()

    # Segment configuration
    segment_samples = int(segment_duration * target_sr)
    hop_samples = int(segment_samples * (1 - overlap))

    # Store timeline results
    timeline = []
    all_events = {}

    # Handle short audio (less than segment_duration)
    if len(processed_audio) < segment_samples:
        events = predict_audio_events(processed_audio, top_k, threshold)
        timeline.append({
            "time": 0.0,
            "events": events
        })
        for event in events:
            label = event["label"]
            if label not in all_events:
                all_events[label] = {"count": 0, "total_score": 0}
            all_events[label]["count"] += 1
            all_events[label]["total_score"] += event["score"]
    else:
        # Normal segment processing
        for i in range(0, len(processed_audio) - segment_samples + 1, hop_samples):
            segment = processed_audio[i:i + segment_samples]
            time_position = i / target_sr

            # Predict events for segment
            events = predict_audio_events(segment, top_k, threshold)

            # Add to timeline
            timeline.append({
                "time": round(time_position, 1),
                "events": events
            })

            # Aggregate events
            for event in events:
                label = event["label"]
                if label not in all_events:
                    all_events[label] = {"count": 0, "total_score": 0}
                all_events[label]["count"] += 1
                all_events[label]["total_score"] += event["score"]

    # Get most common events
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
                             segment_duration: float = 2.0,
                             overlap: float = 0.5) -> Dict:
    """
    単一ファイルを処理（タイムライン形式で保存）
    """
    temp_file = None
    try:
        # audio_filesテーブルからrecorded_atを取得
        audio_file_response = supabase.table('audio_files') \
            .select('device_id, recorded_at') \
            .eq('file_path', file_path) \
            .single() \
            .execute()

        if not audio_file_response.data:
            return {"status": "error", "file_path": file_path, "error": "Audio file record not found"}

        device_id = audio_file_response.data['device_id']
        recorded_at = audio_file_response.data['recorded_at']

        # 一時ファイルを作成してダウンロード
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            temp_file = tmp.name

        if not download_from_s3(file_path, temp_file):
            return {"status": "error", "file_path": file_path, "error": "Download failed"}

        # 音声データを読み込む
        audio_data, sample_rate = sf.read(temp_file)
        print(f"🎵 音声ロード完了: {len(audio_data)/sample_rate:.2f}秒, {sample_rate}Hz")

        # タイムライン分析を実行
        timeline_result = analyze_timeline(
            audio_data, sample_rate,
            segment_duration, overlap, top_k, threshold
        )

        # spot_featuresテーブルに保存
        save_success = await save_to_spot_features(
            device_id,
            recorded_at,
            timeline_result['timeline']
        )

        if save_success:
            return {
                "status": "success",
                "file_path": file_path,
                "device_id": device_id,
                "recorded_at": recorded_at,
                "timeline": timeline_result
            }
        else:
            return {"status": "error", "file_path": file_path, "error": "Save failed"}

    except Exception as e:
        print(f"❌ ファイル処理エラー: {file_path} - {str(e)}")
        traceback.print_exc()
        return {"status": "error", "file_path": file_path, "error": str(e)}

    finally:
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)

@app.on_event("startup")
async def startup_event():
    """サーバー起動時にモデルをロード"""
    load_model()

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Audio Event Detection API with Supabase Integration (Pluggable backend)",
        "backend": get_backend_id(),
        "model": get_model_name(),
        "version": APP_VERSION,
        "sampling_rate": get_sampling_rate(),
        "status": "ready" if sed_backend is not None else "not ready",
        "endpoints": {
            "/async-process": "Process a single S3 audio file asynchronously",
            "/fetch-and-process-paths": "Process audio files from S3 via file paths",
            "/health": "Health check endpoint",
            "/filter-config": "Get event filter configuration"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    filter_stats = get_filter_stats()
    return {
        "status": "healthy" if sed_backend is not None else "unhealthy",
        "model_loaded": sed_backend is not None,
        "backend": get_backend_id(),
        "model_name": get_model_name(),
        "sampling_rate": get_sampling_rate(),
        "supabase_connected": supabase is not None,
        "s3_connected": s3_client is not None,
        "event_filtering": filter_stats
    }

@app.get("/filter-config")
async def get_filter_config():
    """Get current event filter configuration"""
    return get_filter_stats()

# Request model for async processing
class AsyncProcessRequest(BaseModel):
    file_path: str
    device_id: str
    recorded_at: str

@app.post("/async-process", status_code=202)
async def async_process(
    request: AsyncProcessRequest,
    background_tasks: BackgroundTasks
):
    """Asynchronous processing endpoint - returns 202 Accepted immediately"""
    print(f"Starting async processing for {request.device_id} at {request.recorded_at}")

    # Add to background tasks (including status update)
    background_tasks.add_task(
        process_in_background,
        request.file_path,
        request.device_id,
        request.recorded_at
    )

    return {
        "status": "accepted",
        "message": "Processing started in background",
        "device_id": request.device_id,
        "recorded_at": request.recorded_at
    }


async def process_in_background(file_path: str, device_id: str, recorded_at: str):
    """Background processing function"""
    print(f"Background processing started for {device_id}")

    # Check if already completed to prevent duplicate processing
    try:
        response = supabase.table('spot_features').select('behavior_status').eq(
            'device_id', device_id
        ).eq(
            'recorded_at', recorded_at
        ).execute()

        if response.data and len(response.data) > 0:
            current_status = response.data[0].get('behavior_status')
            if current_status == 'completed':
                print(f"Already completed, skipping processing: {device_id}/{recorded_at}")
                return
    except Exception as e:
        print(f"Failed to check status: {e}")

    # Update status to 'processing'
    try:
        update_status(device_id, recorded_at, "behavior_status", "processing")
    except Exception as e:
        print(f"Failed to update status to processing: {e}")

    try:
        result = await process_single_file(file_path)

        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "Unknown processing error"))

        update_status(device_id, recorded_at, "behavior_status", "completed")

        sqs.send_message(
            QueueUrl=FEATURE_COMPLETED_QUEUE_URL,
            MessageBody=json.dumps({
                "device_id": device_id,
                "recorded_at": recorded_at,
                "feature_type": "behavior",
                "status": "completed"
            })
        )

        print(f"Background processing completed for {device_id}")

    except Exception as e:
        print(f"Background processing failed for {device_id}: {str(e)}")

        try:
            update_status(device_id, recorded_at, "behavior_status", "failed")
        except:
            pass

        sqs.send_message(
            QueueUrl=FEATURE_COMPLETED_QUEUE_URL,
            MessageBody=json.dumps({
                "device_id": device_id,
                "recorded_at": recorded_at,
                "feature_type": "behavior",
                "status": "failed",
                "error": str(e)
            })
        )


def update_status(device_id: str, recorded_at: str, status_field: str, status_value: str):
    """Update processing status in spot_features table"""
    try:
        response = supabase.table('spot_features').update({
            status_field: status_value
        }).eq(
            'device_id', device_id
        ).eq(
            'recorded_at', recorded_at
        ).execute()

        if response.data:
            print(f"Status updated: {device_id}/{recorded_at} - {status_field}={status_value}")
        else:
            insert_data = {
                'device_id': device_id,
                'recorded_at': recorded_at,
                status_field: status_value
            }
            supabase.table('spot_features').insert(insert_data).execute()
            print(f"Status record created: {device_id}/{recorded_at} - {status_field}={status_value}")

    except Exception as e:
        print(f"Failed to update status: {str(e)}")
        raise


@app.post("/fetch-and-process-paths")
async def fetch_and_process_paths(request: FetchAndProcessPathsRequest):
    """
    file_pathsベースの音響イベント検出エンドポイント（v2完全互換）

    Args:
        request: file_paths配列とオプションパラメータ

    Returns:
        処理結果のサマリーと詳細
    """
    if sed_backend is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    if not request.file_paths:
        raise HTTPException(status_code=422, detail="file_paths must contain at least one entry")

    start_time = time.time()

    processed_files = []
    error_files = []

    print(f"🚀 処理開始: {len(request.file_paths)}個のファイル")

    for file_path in request.file_paths:
        result = await process_single_file(
            file_path,
            request.threshold,
            request.top_k,
            request.segment_duration,
            request.overlap
        )

        if result["status"] == "success":
            processed_files.append(file_path)
        else:
            error_files.append({
                "file_path": file_path,
                "error": result.get("error", "Unknown error")
            })

    execution_time = time.time() - start_time

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
        "error_files": error_files if error_files else None,
        "execution_time_seconds": round(execution_time, 1),
        "message": f"{total_files}件中{success_count}件を正常に処理しました"
    }

    print(f"✅ 処理完了: {success_count}/{total_files}件成功 (実行時間: {execution_time:.1f}秒)")

    return JSONResponse(content=response)

if __name__ == "__main__":
    print("=" * 50)
    print("Audio Event Detection API with Supabase")
    print(f"Backend: {get_backend_id()}")
    print(f"Model: {get_model_name()}")
    print(f"Sampling Rate: {get_sampling_rate()} Hz")
    print("=" * 50)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8017,
        log_level="info"
    )
