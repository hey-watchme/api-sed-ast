#!/usr/bin/env python3
"""
S3から音声ファイルをダウンロードして時系列分析するスクリプト
"""

import os
import sys
import tempfile
import boto3
from dotenv import load_dotenv
import requests
import json

# 環境変数を読み込み
load_dotenv()

# AWS S3クライアントの初期化
aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
s3_bucket_name = os.getenv('S3_BUCKET_NAME', 'watchme-vault')
aws_region = os.getenv('AWS_REGION', 'us-east-1')

if not aws_access_key_id or not aws_secret_access_key:
    print("❌ AWS認証情報が設定されていません。.envファイルを確認してください。")
    sys.exit(1)

s3_client = boto3.client(
    's3',
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    region_name=aws_region
)

def download_from_s3(s3_path: str) -> str:
    """S3から音声ファイルをダウンロード"""
    print(f"📥 S3からダウンロード中: {s3_path}")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
        local_path = tmp_file.name
    
    try:
        s3_client.download_file(s3_bucket_name, s3_path, local_path)
        print(f"✅ ダウンロード完了: {local_path}")
        
        file_size = os.path.getsize(local_path)
        print(f"   ファイルサイズ: {file_size / 1024:.1f} KB")
        
        return local_path
        
    except Exception as e:
        print(f"❌ ダウンロードエラー: {str(e)}")
        if os.path.exists(local_path):
            os.remove(local_path)
        raise

def analyze_timeline(file_path: str, api_url: str = "http://localhost:8017"):
    """
    ASTのAPIを使用して音声ファイルを時系列分析
    
    Args:
        file_path: 分析する音声ファイルのパス
        api_url: APIサーバーのURL
    
    Returns:
        分析結果
    """
    print(f"\n🔬 音声ファイルを時系列分析中...")
    print(f"   設定: 1秒ごと、50%オーバーラップ、上位3イベント")
    
    # APIエンドポイント
    endpoint = f"{api_url}/analyze_timeline"
    
    try:
        # パラメータ設定
        params = {
            "segment_duration": 1.0,  # 1秒ごと
            "overlap": 0.5,           # 50%オーバーラップ
            "top_k": 3                # 上位3イベント
        }
        
        # ファイルをアップロード
        with open(file_path, 'rb') as f:
            files = {'file': ('audio.wav', f, 'audio/wav')}
            response = requests.post(endpoint, files=files, params=params)
        
        if response.status_code == 200:
            result = response.json()
            return result
        else:
            print(f"❌ API エラー: {response.status_code}")
            print(f"   {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"❌ APIサーバーに接続できません。")
        print(f"   サーバーが起動していることを確認してください: python3 main_timeline.py")
        return None
    except Exception as e:
        print(f"❌ 分析エラー: {str(e)}")
        return None

def display_timeline(result: dict):
    """時系列結果を見やすく表示"""
    
    print("\n" + "=" * 70)
    print("📊 時系列分析結果")
    print("=" * 70)
    
    # 音声情報
    if 'audio_info' in result:
        info = result['audio_info']
        print(f"\n🎵 音声情報:")
        print(f"   - ファイル名: {info.get('filename', 'N/A')}")
        print(f"   - 長さ: {info.get('duration_seconds', 0):.1f}秒")
        print(f"   - サンプリングレート: {info.get('sample_rate', 0)} Hz")
    
    # サマリー
    if 'summary' in result:
        summary = result['summary']
        print(f"\n📈 分析サマリー:")
        print(f"   - 総セグメント数: {summary.get('total_segments', 0)}")
        print(f"   - セグメント長: {summary.get('segment_duration', 0)}秒")
        print(f"   - オーバーラップ: {summary.get('overlap', 0)*100:.0f}%")
        
        if 'most_common_events' in summary:
            print(f"\n🏆 最も頻出するイベント:")
            for i, event in enumerate(summary['most_common_events'][:5], 1):
                label = event['label']
                count = event['occurrences']
                avg_score = event['average_score']
                print(f"   {i}. {label:<25} 出現: {count:3}回, 平均スコア: {avg_score:.3f}")
    
    # タイムライン（最初の20秒分を表示）
    if 'timeline' in result:
        timeline = result['timeline']
        print(f"\n⏱️  時系列イベント (最初の20秒):")
        print("-" * 70)
        print(f"{'時刻':>5} | {'イベント1':<20} | {'イベント2':<20} | {'イベント3':<20}")
        print("-" * 70)
        
        for segment in timeline[:40]:  # 最初の20秒（0.5秒刻みで40セグメント）
            time_str = f"{segment['time']:.1f}s"
            events = segment['events']
            
            # 各イベントを整形
            event_strs = []
            for evt in events[:3]:
                label = evt['label'][:18]  # 長いラベルは切り詰め
                score = evt['score']
                event_strs.append(f"{label} ({score:.2f})")
            
            # 3つに満たない場合は空文字で埋める
            while len(event_strs) < 3:
                event_strs.append("")
            
            print(f"{time_str:>5} | {event_strs[0]:<20} | {event_strs[1]:<20} | {event_strs[2]:<20}")

def save_timeline_csv(result: dict, output_file: str = "timeline.csv"):
    """時系列データをCSVファイルに保存"""
    import csv
    
    if 'timeline' not in result:
        return
    
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        
        # ヘッダー
        writer.writerow(['Time(s)', 'Event1', 'Score1', 'Event2', 'Score2', 'Event3', 'Score3'])
        
        # データ
        for segment in result['timeline']:
            row = [segment['time']]
            for event in segment['events'][:3]:
                row.extend([event['label'], event['score']])
            # 不足分を埋める
            while len(row) < 7:
                row.extend(['', ''])
            writer.writerow(row)
    
    print(f"\n💾 CSVファイルに保存しました: {output_file}")

def main():
    """メイン処理"""
    
    # 分析対象のS3パス
    if len(sys.argv) > 1:
        s3_path = sys.argv[1]
    else:
        s3_path = "files/d067d407-cf73-4174-a9c1-d91fb60d64d0/2025-09-18/17-00/audio.wav"
    
    print("=" * 70)
    print("AST音響イベント検出 - 時系列分析")
    print("=" * 70)
    print(f"対象ファイル: {s3_path}")
    print()
    
    try:
        # 1. S3からダウンロード
        local_file = download_from_s3(s3_path)
        
        # 2. APIで時系列分析
        result = analyze_timeline(local_file)
        
        if result:
            # 3. 結果を表示
            display_timeline(result)
            
            # 4. JSONで保存
            output_json = "timeline_result.json"
            with open(output_json, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\n💾 JSON結果を保存しました: {output_json}")
            
            # 5. CSVでも保存
            save_timeline_csv(result)
            
        # 6. 一時ファイルを削除
        if os.path.exists(local_file):
            os.remove(local_file)
            print(f"\n🗑️  一時ファイルを削除しました")
            
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()