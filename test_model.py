#!/usr/bin/env python3
"""
AST (Audio Spectrogram Transformer) モデルの動作確認スクリプト
MIT/ast-finetuned-audioset-10-10-0.4593 モデルをテスト
"""

import torch
from transformers import AutoFeatureExtractor, ASTForAudioClassification
import numpy as np

def test_model():
    """モデルの基本動作を確認"""
    print("=" * 50)
    print("AST Model Test Script")
    print("=" * 50)
    
    # モデル名
    model_name = "MIT/ast-finetuned-audioset-10-10-0.4593"
    print(f"\n1. モデルをダウンロード中: {model_name}")
    
    try:
        # Feature ExtractorとModelの読み込み
        feature_extractor = AutoFeatureExtractor.from_pretrained(model_name)
        model = ASTForAudioClassification.from_pretrained(model_name)
        print("✅ モデルのダウンロードに成功しました")
        
        # モデル情報の表示
        print(f"\n2. モデル情報:")
        print(f"   - ラベル数: {model.config.num_labels}")
        print(f"   - サンプリングレート: {feature_extractor.sampling_rate} Hz")
        
        # ダミー音声データの生成（1秒間、16kHz）
        print(f"\n3. テスト用音声データを生成中...")
        duration = 1.0  # 1秒
        sample_rate = feature_extractor.sampling_rate
        num_samples = int(duration * sample_rate)
        
        # ランダムノイズを生成（実際の音声の代わり）
        dummy_audio = np.random.randn(num_samples).astype(np.float32)
        print(f"   - 音声長: {duration}秒")
        print(f"   - サンプル数: {num_samples}")
        
        # 特徴抽出
        print(f"\n4. 特徴抽出中...")
        inputs = feature_extractor(
            dummy_audio, 
            sampling_rate=sample_rate, 
            return_tensors="pt"
        )
        print("✅ 特徴抽出に成功しました")
        
        # 推論実行
        print(f"\n5. 推論実行中...")
        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits
        print(f"✅ 推論に成功しました")
        print(f"   - 出力形状: {logits.shape}")
        
        # 上位5つのラベルを取得
        probs = torch.nn.functional.softmax(logits, dim=-1)[0]
        top5_probs, top5_indices = torch.topk(probs, 5)
        
        print(f"\n6. 推論結果（上位5件）:")
        print("   注: これはランダムノイズに対する結果です")
        for i, (prob, idx) in enumerate(zip(top5_probs, top5_indices), 1):
            label_id = idx.item()
            score = prob.item()
            # AudioSetのラベルIDを表示（実際のラベル名はid2labelマッピングが必要）
            print(f"   {i}. Label ID: {label_id:3d}, Score: {score:.4f}")
        
        print("\n" + "=" * 50)
        print("✅ すべてのテストが成功しました！")
        print("=" * 50)
        
        return True
        
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_model()
    exit(0 if success else 1)