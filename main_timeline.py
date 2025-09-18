#!/usr/bin/env python3
"""
AST (Audio Spectrogram Transformer) 音響イベント検出API - 時系列版
1秒ごとに音声を分析して時系列データを生成
"""

import os
import io
import json
from typing import List, Dict, Optional
import traceback

import torch
import numpy as np
import librosa
import soundfile as sf
from transformers import AutoFeatureExtractor, ASTForAudioClassification
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# グローバル変数でモデルを保持
model = None
feature_extractor = None
id2label = None

# モデル名
MODEL_NAME = "MIT/ast-finetuned-audioset-10-10-0.4593"

# FastAPIアプリケーション
app = FastAPI(
    title="AST Audio Timeline Detection API",
    description="Audio Spectrogram Transformer を使用した時系列音響イベント検出API",
    version="1.0.0"
)

# レスポンスモデル
class TimelineEvent(BaseModel):
    time: float
    events: List[Dict[str, float]]

class TimelineResponse(BaseModel):
    timeline: List[TimelineEvent]
    audio_info: Dict
    summary: Dict

def load_model():
    """モデルとfeature extractorを読み込む"""
    global model, feature_extractor, id2label
    
    print(f"モデルをロード中: {MODEL_NAME}")
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

def predict_segment(audio_segment: np.ndarray, top_k: int = 3) -> List[Dict[str, float]]:
    """
    音声セグメントから音響イベントを予測
    
    Args:
        audio_segment: 音声セグメント（1秒分）
        top_k: 返す上位予測の数
    
    Returns:
        予測結果のリスト
    """
    # 特徴抽出
    inputs = feature_extractor(
        audio_segment,
        sampling_rate=16000,
        return_tensors="pt",
        padding=True
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
        label_id = idx.item()
        # AudioSetの主要ラベルマッピング
        audioset_labels = {
            0: "Speech", 1: "Male speech", 2: "Female speech",
            3: "Child speech", 7: "Speech synthesizer",
            16: "Laughter", 17: "Baby laughter", 20: "Belly laugh",
            47: "Cough", 48: "Throat clearing", 49: "Sneeze",
            50: "Sniff", 62: "Burping", 63: "Hiccup",
            70: "Conversation", 137: "Music", 
            500: "Silence", 506: "Inside, small room",
            507: "Inside, large room", 508: "Inside, public space",
            509: "Outside, urban", 510: "Outside, rural",
            511: "Reverberation", 512: "Echo",
            513: "Noise", 514: "Environmental noise", 515: "Static",
            516: "Mains hum", 517: "Distortion", 518: "Sidetone",
            519: "Cacophony", 520: "White noise", 521: "Pink noise",
            522: "Throbbing", 523: "Vibration", 524: "Hum",
            525: "Whoosh", 526: "Fire"
        }
        
        # まずid2labelから取得を試みる
        label = id2label.get(label_id) or id2label.get(str(label_id))
        # 見つからなければaudioset_labelsから
        if not label:
            label = audioset_labels.get(label_id, f"Event_{label_id}")
        
        score = prob.item()
        predictions.append({
            "label": label,
            "score": round(score, 4)
        })
    
    return predictions

def analyze_timeline(audio_data: np.ndarray, sample_rate: int, 
                    segment_duration: float = 1.0, 
                    overlap: float = 0.5,
                    top_k: int = 3) -> Dict:
    """
    音声データを時系列で分析
    
    Args:
        audio_data: 音声データ全体
        sample_rate: サンプリングレート
        segment_duration: セグメントの長さ（秒）
        overlap: オーバーラップ（0.5 = 50%）
        top_k: 各時刻で返すイベント数
    
    Returns:
        時系列分析結果
    """
    # モノラルに変換
    if len(audio_data.shape) > 1:
        audio_data = np.mean(audio_data, axis=1)
    
    # 16kHzにリサンプリング
    if sample_rate != 16000:
        audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)
        sample_rate = 16000
    
    # 正規化
    max_val = np.max(np.abs(audio_data))
    if max_val > 0:
        audio_data = audio_data / max_val
    
    # セグメント分割のパラメータ
    segment_samples = int(segment_duration * sample_rate)
    hop_samples = int(segment_samples * (1 - overlap))
    
    # タイムライン結果を格納
    timeline = []
    
    # 全体の統計情報
    all_events = {}
    
    # スライディングウィンドウで分析
    for start_idx in range(0, len(audio_data) - segment_samples + 1, hop_samples):
        # セグメントを抽出
        end_idx = start_idx + segment_samples
        segment = audio_data[start_idx:end_idx]
        
        # 時刻を計算（秒）
        time_sec = start_idx / sample_rate
        
        # セグメントを分析
        events = predict_segment(segment, top_k=top_k)
        
        # タイムラインに追加
        timeline.append({
            "time": round(time_sec, 1),
            "events": events
        })
        
        # 統計情報を更新
        for event in events:
            label = event["label"]
            if label not in all_events:
                all_events[label] = {"count": 0, "total_score": 0}
            all_events[label]["count"] += 1
            all_events[label]["total_score"] += event["score"]
    
    # サマリーを計算
    summary = {
        "total_segments": len(timeline),
        "duration_seconds": len(audio_data) / sample_rate,
        "segment_duration": segment_duration,
        "overlap": overlap,
        "most_common_events": []
    }
    
    # イベントをソートして上位5つを取得
    sorted_events = sorted(
        [(k, v["count"], v["total_score"]/v["count"]) for k, v in all_events.items()],
        key=lambda x: x[1],
        reverse=True
    )[:5]
    
    for label, count, avg_score in sorted_events:
        summary["most_common_events"].append({
            "label": label,
            "occurrences": count,
            "average_score": round(avg_score, 4)
        })
    
    return {
        "timeline": timeline,
        "summary": summary
    }

@app.on_event("startup")
async def startup_event():
    """サーバー起動時にモデルをロード"""
    load_model()

@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "message": "AST Audio Timeline Detection API",
        "model": MODEL_NAME,
        "endpoints": {
            "/analyze_timeline": "時系列音響イベント検出",
            "/analyze_sound": "全体音響イベント検出"
        }
    }

@app.post("/analyze_timeline")
async def analyze_timeline_endpoint(
    file: UploadFile = File(...),
    segment_duration: Optional[float] = 1.0,
    overlap: Optional[float] = 0.5,
    top_k: Optional[int] = 3
):
    """
    音声ファイルから時系列で音響イベントを検出
    
    Args:
        file: 音声ファイル
        segment_duration: セグメントの長さ（秒）デフォルト: 1.0
        overlap: オーバーラップ（0-1）デフォルト: 0.5
        top_k: 各時刻で返すイベント数 デフォルト: 3
    
    Returns:
        時系列分析結果
    """
    if model is None or feature_extractor is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # ファイルを読み込む
        print(f"Processing timeline for: {file.filename}")
        content = await file.read()
        
        # 音声データを読み込む
        audio_data, sample_rate = sf.read(io.BytesIO(content))
        print(f"Audio loaded: {len(audio_data)/sample_rate:.2f} seconds, {sample_rate} Hz")
        
        # 時系列分析を実行
        result = analyze_timeline(
            audio_data, sample_rate,
            segment_duration=segment_duration,
            overlap=overlap,
            top_k=top_k
        )
        
        # 音声情報を追加
        result["audio_info"] = {
            "filename": file.filename,
            "duration_seconds": round(len(audio_data) / sample_rate, 2),
            "sample_rate": sample_rate
        }
        
        print(f"✅ Timeline analysis complete: {len(result['timeline'])} segments")
        return JSONResponse(content=result)
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/analyze_sound")
async def analyze_sound(
    file: UploadFile = File(...),
    top_k: Optional[int] = 5
):
    """
    音声ファイル全体から音響イベントを検出（従来版）
    """
    if model is None or feature_extractor is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        content = await file.read()
        audio_data, sample_rate = sf.read(io.BytesIO(content))
        
        # モノラル変換
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)
        
        # リサンプリング
        if sample_rate != 16000:
            audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)
        
        # 正規化
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            audio_data = audio_data / max_val
        
        # 全体を分析
        predictions = predict_segment(audio_data, top_k=top_k)
        
        return JSONResponse(content={
            "predictions": predictions,
            "audio_info": {
                "filename": file.filename,
                "duration_seconds": round(len(audio_data) / 16000, 2),
                "sample_rate": sample_rate
            }
        })
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

if __name__ == "__main__":
    print("=" * 50)
    print("AST Audio Timeline Detection API")
    print(f"Model: {MODEL_NAME}")
    print("=" * 50)
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8017,
        log_level="info"
    )