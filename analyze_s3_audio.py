#!/usr/bin/env python3
"""
S3から音声ファイルをダウンロードして分析するスクリプト
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
    """
    S3から音声ファイルをダウンロード
    
    Args:
        s3_path: S3のファイルパス (例: files/device_id/date/time/audio.wav)
    
    Returns:
        ダウンロードしたローカルファイルのパス
    """
    print(f"📥 S3からダウンロード中: {s3_path}")
    
    # 一時ファイルを作成
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
        local_path = tmp_file.name
    
    try:
        # S3からダウンロード
        s3_client.download_file(s3_bucket_name, s3_path, local_path)
        print(f"✅ ダウンロード完了: {local_path}")
        
        # ファイルサイズを確認
        file_size = os.path.getsize(local_path)
        print(f"   ファイルサイズ: {file_size / 1024:.1f} KB")
        
        return local_path
        
    except Exception as e:
        print(f"❌ ダウンロードエラー: {str(e)}")
        if os.path.exists(local_path):
            os.remove(local_path)
        raise

def analyze_audio(file_path: str, api_url: str = "http://localhost:8017"):
    """
    ASTのAPIを使用して音声ファイルを分析
    
    Args:
        file_path: 分析する音声ファイルのパス
        api_url: APIサーバーのURL
    
    Returns:
        分析結果
    """
    print(f"\n🔬 音声ファイルを分析中...")
    
    # APIエンドポイント
    endpoint = f"{api_url}/analyze_sound"
    
    try:
        # ファイルをアップロード
        with open(file_path, 'rb') as f:
            files = {'file': ('audio.wav', f, 'audio/wav')}
            response = requests.post(endpoint, files=files)
        
        if response.status_code == 200:
            result = response.json()
            return result
        else:
            print(f"❌ API エラー: {response.status_code}")
            print(f"   {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"❌ APIサーバーに接続できません。")
        print(f"   サーバーが起動していることを確認してください: python3 main.py")
        return None
    except Exception as e:
        print(f"❌ 分析エラー: {str(e)}")
        return None

def main():
    """メイン処理"""
    
    # 分析対象のS3パス
    s3_path = "files/d067d407-cf73-4174-a9c1-d91fb60d64d0/2025-09-18/17-00/audio.wav"
    
    print("=" * 60)
    print("AST音響イベント検出 - S3ファイル分析")
    print("=" * 60)
    print(f"対象ファイル: {s3_path}")
    print()
    
    try:
        # 1. S3からダウンロード
        local_file = download_from_s3(s3_path)
        
        # 2. APIで分析
        result = analyze_audio(local_file)
        
        if result:
            # 3. 結果を表示
            print("\n" + "=" * 60)
            print("📊 分析結果")
            print("=" * 60)
            
            # 音声情報
            if 'audio_info' in result:
                info = result['audio_info']
                print(f"\n🎵 音声情報:")
                print(f"   - ファイル名: {info.get('filename', 'N/A')}")
                print(f"   - 長さ: {info.get('duration_seconds', 0):.1f}秒")
                print(f"   - サンプリングレート: {info.get('sample_rate', 0)} Hz")
            
            # 予測結果
            if 'predictions' in result:
                print(f"\n🎯 検出された音響イベント (上位5件):")
                print("-" * 40)
                for i, pred in enumerate(result['predictions'], 1):
                    label = pred['label']
                    score = pred['score']
                    bar = "█" * int(score * 30)
                    print(f"  {i}. {label:<30} {score:.4f} {bar}")
            
            # JSON形式でも保存
            output_file = "analysis_result.json"
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\n💾 結果を保存しました: {output_file}")
            
        # 4. 一時ファイルを削除
        if os.path.exists(local_file):
            os.remove(local_file)
            print(f"\n🗑️  一時ファイルを削除しました")
            
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # コマンドライン引数でS3パスを指定できるようにする
    if len(sys.argv) > 1:
        s3_path = sys.argv[1]
        print(f"指定されたパス: {s3_path}")
    
    main()