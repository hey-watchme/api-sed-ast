#!/usr/bin/env python3
"""
ASTモデルのラベルを確認するスクリプト
"""

from transformers import ASTForAudioClassification
import json

# モデル名
MODEL_NAME = "MIT/ast-finetuned-audioset-10-10-0.4593"

print(f"モデルからラベル情報を取得中: {MODEL_NAME}")

# モデルをロード（configのみ）
model = ASTForAudioClassification.from_pretrained(MODEL_NAME)

# ラベル情報を確認
if hasattr(model.config, 'id2label'):
    id2label = model.config.id2label
    print(f"\n✅ ラベル数: {len(id2label)}")
    
    # 最初の10個を表示
    print("\n最初の10個のラベル:")
    for i in range(min(10, len(id2label))):
        print(f"  {i}: {id2label.get(str(i), 'N/A')}")
    
    # Speechやその他重要そうなラベルを検索
    print("\n重要なラベルを検索:")
    for idx, label in id2label.items():
        if any(keyword in label.lower() for keyword in ['speech', 'music', 'silence', 'cough', 'laugh']):
            print(f"  ID {idx}: {label}")
    
    # ラベル47, 506, 48, 62, 0が何か確認
    print("\n今回検出されたIDのラベル:")
    for idx in [47, 506, 48, 62, 0]:
        label = id2label.get(str(idx), f"ID {idx} not found")
        print(f"  ID {idx}: {label}")
    
else:
    print("❌ ラベル情報が見つかりませんでした")