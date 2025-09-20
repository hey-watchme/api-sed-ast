-- behavior_yamnetテーブルにcreated_atカラムを追加
-- timestamptz型（タイムゾーン付きタイムスタンプ）で作成

-- カラムが存在しない場合のみ追加
ALTER TABLE public.behavior_yamnet 
ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT NOW();

-- 既存レコードのcreated_atをNULLから現在時刻に更新（必要に応じて）
UPDATE public.behavior_yamnet 
SET created_at = NOW() 
WHERE created_at IS NULL;

-- インデックスを作成して検索パフォーマンスを向上
CREATE INDEX IF NOT EXISTS idx_behavior_yamnet_created_at 
ON public.behavior_yamnet(created_at DESC);

-- 確認用：テーブル構造を表示
-- \d public.behavior_yamnet