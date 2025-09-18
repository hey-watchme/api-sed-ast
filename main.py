#!/usr/bin/env python3
"""
AST (Audio Spectrogram Transformer) 音響イベント検出API
MIT/ast-finetuned-audioset-10-10-0.4593 モデルを使用
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
import uvicorn

# グローバル変数でモデルを保持（起動時に一度だけロード）
model = None
feature_extractor = None
id2label = None

# モデル名
MODEL_NAME = "MIT/ast-finetuned-audioset-10-10-0.4593"

# FastAPIアプリケーション
app = FastAPI(
    title="AST Audio Event Detection API",
    description="Audio Spectrogram Transformer を使用した音響イベント検出API",
    version="1.0.0"
)

def load_model():
    """モデルとfeature extractorを読み込む"""
    global model, feature_extractor, id2label
    
    print(f"モデルをロード中: {MODEL_NAME}")
    try:
        # Feature ExtractorとModelの読み込み
        feature_extractor = AutoFeatureExtractor.from_pretrained(MODEL_NAME)
        model = ASTForAudioClassification.from_pretrained(MODEL_NAME)
        
        # ラベルマッピングを取得
        id2label = model.config.id2label
        
        # CPUで実行（GPUがあればGPUを使用）
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
        model.eval()
        
        print(f"✅ モデルのロードに成功しました")
        print(f"   - デバイス: {device}")
        print(f"   - ラベル数: {len(id2label)}")
        print(f"   - サンプリングレート: {feature_extractor.sampling_rate} Hz")
        
    except Exception as e:
        print(f"❌ モデルのロードに失敗しました: {str(e)}")
        traceback.print_exc()
        raise

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

def predict_audio_events(audio_data: np.ndarray, top_k: int = 5) -> List[Dict[str, float]]:
    """
    音声データから音響イベントを予測
    
    Args:
        audio_data: 前処理済みの音声データ
        top_k: 返す上位予測の数
    
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
        label_id = idx.item()
        # id2labelのキーは整数と文字列の両方を試す
        label = id2label.get(label_id) or id2label.get(str(label_id))
        if not label:
            # AudioSetの標準ラベルマッピング（一部）
            audioset_labels = {
                0: "Speech", 47: "Cough", 48: "Throat clearing",
                62: "Burping, eructation", 137: "Music", 500: "Silence",
                506: "Inside, small room"
            }
            label = audioset_labels.get(label_id, f"Event_{label_id}")
        score = prob.item()
        predictions.append({
            "label": label,
            "score": round(score, 4)
        })
    
    return predictions

@app.on_event("startup")
async def startup_event():
    """サーバー起動時にモデルをロード"""
    load_model()

@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "message": "AST Audio Event Detection API",
        "model": MODEL_NAME,
        "status": "ready" if model is not None else "not ready"
    }

@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {
        "status": "healthy" if model is not None else "unhealthy",
        "model_loaded": model is not None
    }

@app.post("/analyze_sound")
async def analyze_sound(
    file: UploadFile = File(...),
    top_k: Optional[int] = 5
):
    """
    音声ファイルから音響イベントを検出
    
    Args:
        file: アップロードされた音声ファイル（WAV, MP3など）
        top_k: 返す上位予測の数（デフォルト: 5）
    
    Returns:
        JSON形式の予測結果
    """
    # モデルがロードされているか確認
    if model is None or feature_extractor is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    # ファイル形式の確認
    allowed_extensions = ['.wav', '.mp3', '.flac', '.ogg', '.m4a']
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file format. Allowed: {', '.join(allowed_extensions)}"
        )
    
    try:
        # ファイルを読み込む
        print(f"Processing file: {file.filename}")
        content = await file.read()
        
        # 音声データを読み込む
        audio_data, sample_rate = sf.read(io.BytesIO(content))
        print(f"Audio loaded: {len(audio_data)/sample_rate:.2f} seconds, {sample_rate} Hz")
        
        # 音声データの前処理
        processed_audio = process_audio(audio_data, sample_rate)
        
        # 予測実行
        predictions = predict_audio_events(processed_audio, top_k)
        
        # レスポンスを返す
        response = {
            "predictions": predictions,
            "audio_info": {
                "filename": file.filename,
                "duration_seconds": round(len(audio_data) / sample_rate, 2),
                "sample_rate": sample_rate
            }
        }
        
        print(f"✅ Analysis complete for {file.filename}")
        return JSONResponse(content=response)
        
    except Exception as e:
        print(f"❌ Error processing {file.filename}: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing audio: {str(e)}")

if __name__ == "__main__":
    # サーバーを起動（ポート8017で動作）
    print("=" * 50)
    print("AST Audio Event Detection API")
    print(f"Model: {MODEL_NAME}")
    print("=" * 50)
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8017,
        log_level="info"
    )