#!/usr/bin/env python3
"""
AST API Supabase統合版のテストスクリプト
fetch-and-process-pathsエンドポイントのテスト
"""

import requests
import json
from datetime import datetime, timedelta

# APIのベースURL
BASE_URL = "http://localhost:8018"

def test_health():
    """ヘルスチェック"""
    print("📋 ヘルスチェック...")
    response = requests.get(f"{BASE_URL}/health")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ ヘルスチェック成功")
        print(f"   - モデル: {'ロード済み' if data['model_loaded'] else '未ロード'}")
        print(f"   - Supabase: {'接続済み' if data['supabase_connected'] else '未接続'}")
        print(f"   - S3: {'接続済み' if data['s3_connected'] else '未接続'}")
        return True
    else:
        print(f"❌ ヘルスチェック失敗: {response.status_code}")
        return False

def test_fetch_and_process_paths():
    """fetch-and-process-pathsエンドポイントのテスト"""
    print("\n📋 fetch-and-process-pathsエンドポイントのテスト...")
    
    # テスト用のfile_paths（実際のファイルパスに置き換える必要があります）
    # 形式: files/{device_id}/{date}/{time_block}/audio.wav
    test_file_paths = [
        "files/d067d407-cf73-4174-a9c1-d91fb60d64d0/2025-07-20/00-00/audio.wav",
        # 必要に応じて追加
    ]
    
    request_data = {
        "file_paths": test_file_paths,
        "threshold": 0.1,
        "top_k": 5,
        "analyze_timeline": True,
        "segment_duration": 1.0,
        "overlap": 0.5
    }
    
    print(f"📤 リクエスト送信中...")
    print(f"   - ファイル数: {len(test_file_paths)}")
    print(f"   - しきい値: {request_data['threshold']}")
    print(f"   - タイムライン分析: {'有効' if request_data['analyze_timeline'] else '無効'}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/fetch-and-process-paths",
            json=request_data,
            timeout=60  # タイムアウトを60秒に設定
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 処理成功")
            print(f"\n📊 処理結果サマリー:")
            print(f"   - ステータス: {data['status']}")
            print(f"   - 総ファイル数: {data['summary']['total_files']}")
            print(f"   - 処理成功: {data['summary']['processed']}")
            print(f"   - エラー: {data['summary']['errors']}")
            print(f"   - 実行時間: {data['execution_time_seconds']}秒")
            
            if data['processed_files']:
                print(f"\n✅ 処理成功ファイル:")
                for file in data['processed_files']:
                    print(f"   - {file}")
            
            if data['error_files']:
                print(f"\n❌ エラーファイル:")
                for error in data['error_files']:
                    print(f"   - {error['file_path']}: {error['error']}")
            
            return True
        else:
            print(f"❌ 処理失敗: {response.status_code}")
            print(f"   エラー詳細: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ タイムアウト: 処理に60秒以上かかりました")
        return False
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return False

def test_with_dummy_path():
    """ダミーパスでのテスト（エラーハンドリング確認用）"""
    print("\n📋 エラーハンドリングテスト（存在しないファイル）...")
    
    dummy_paths = [
        "files/test-device/2025-01-01/00-00/dummy.wav"
    ]
    
    request_data = {
        "file_paths": dummy_paths,
        "threshold": 0.2,
        "analyze_timeline": False  # タイムライン分析は無効
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/fetch-and-process-paths",
            json=request_data,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"📊 レスポンス受信:")
            print(f"   - ステータス: {data['status']}")
            print(f"   - エラー数: {data['summary']['errors']}")
            
            if data['error_files']:
                print(f"✅ エラーハンドリング正常:")
                for error in data['error_files']:
                    print(f"   - {error['file_path']}: {error['error']}")
            
            return True
        else:
            print(f"❌ 予期しないステータスコード: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return False

def main():
    """メインテスト実行"""
    print("=" * 60)
    print("AST API Supabase統合版 テスト開始")
    print("=" * 60)
    
    # ヘルスチェック
    if not test_health():
        print("\n⚠️ APIが起動していない可能性があります")
        print("以下のコマンドでAPIを起動してください:")
        print("  python3 main_supabase.py")
        return
    
    # メインエンドポイントのテスト
    print("\n" + "=" * 60)
    print("1. 正常なファイルパスでのテスト")
    print("=" * 60)
    test_fetch_and_process_paths()
    
    # エラーハンドリングテスト
    print("\n" + "=" * 60)
    print("2. エラーハンドリングテスト")
    print("=" * 60)
    test_with_dummy_path()
    
    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)

if __name__ == "__main__":
    main()