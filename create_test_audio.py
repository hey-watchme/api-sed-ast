#!/usr/bin/env python3
"""
テスト用音声ファイルを生成するスクリプト
"""

import numpy as np
import soundfile as sf

def create_test_audio():
    """テスト用の音声ファイルを生成"""
    
    print("テスト用音声ファイルを生成中...")
    
    # サンプリングレート
    sample_rate = 16000
    
    # 1. サイン波（1秒）- 音楽的な音
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration))
    frequency = 440  # A4音
    sine_wave = np.sin(2 * np.pi * frequency * t) * 0.5
    
    # 2. ホワイトノイズ（0.5秒）- 環境音のシミュレーション
    noise_duration = 0.5
    white_noise = np.random.randn(int(sample_rate * noise_duration)) * 0.1
    
    # 3. 無音（0.5秒）
    silence = np.zeros(int(sample_rate * 0.5))
    
    # 4. クリック音（打撃音のシミュレーション）
    click = np.zeros(int(sample_rate * 0.2))
    click[100:120] = 0.8  # 短いパルス
    
    # すべてを結合
    test_audio = np.concatenate([
        sine_wave,
        silence,
        white_noise,
        silence,
        click,
        silence
    ])
    
    # ファイルに保存
    output_file = "test_audio.wav"
    sf.write(output_file, test_audio, sample_rate)
    
    total_duration = len(test_audio) / sample_rate
    print(f"✅ テスト音声ファイルを作成しました: {output_file}")
    print(f"   - 長さ: {total_duration:.2f}秒")
    print(f"   - サンプリングレート: {sample_rate} Hz")
    print(f"   - 内容:")
    print(f"     0.0-1.0秒: 440Hz サイン波（音楽的な音）")
    print(f"     1.0-1.5秒: 無音")
    print(f"     1.5-2.0秒: ホワイトノイズ（環境音）")
    print(f"     2.0-2.5秒: 無音")
    print(f"     2.5-2.7秒: クリック音（打撃音）")
    print(f"     2.7-3.2秒: 無音")
    
    return output_file

if __name__ == "__main__":
    create_test_audio()