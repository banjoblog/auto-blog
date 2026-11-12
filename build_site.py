import os
import sys
import time
from google import genai

# 1回の実行で生成する上限数（タイムアウト防止）
MAX_BATCH_SIZE = 5

# 出力ディレクトリ
OUTPUT_DIR = "dist"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 20件のAIツールデータベース（一例）
TOOLS_DB = [
    {"slug": "chatgpt", "name": "ChatGPT", "category": "Text Generator"},
    {"slug": "claude", "name": "Claude", "category": "Text Generator"},
    {"slug": "gemini", "name": "Gemini", "category": "Text Generator"},
    {"slug": "midjourney", "name": "Midjourney", "category": "Image Generator"},
    {"slug": "stable-diffusion", "name": "Stable Diffusion", "category": "Image Generator"},
    {"slug": "runway", "name": "Runway", "category": "Video Generator"},
    {"slug": "sora", "name": "Sora", "category": "Video Generator"},
    {"slug": "elevenlabs", "name": "ElevenLabs", "category": "Voice Generator"},
    {"slug": "suno", "name": "Suno AI", "category": "Music Generator"},
    {"slug": "udio", "name": "Udio", "category": "Music Generator"},
    {"slug": "perplexitiy", "name": "Perplexity", "category": "Search Engine"},
    {"slug": "v0-dev", "name": "v0.dev", "category": "Code Generator"},
    {"slug": "cursor", "name": "Cursor", "category": "Code Editor"},
    {"slug": "github-copilot", "name": "GitHub Copilot", "category": "Code Generator"},
    {"slug": "notion-ai", "name": "Notion AI", "category": "Productivity"},
    {"slug": "canva-ai", "name": "Canva AI", "category": "Design"},
    {"slug": "jasper", "name": "Jasper AI", "category": "Copywriting"},
    {"slug": "copy-ai", "name": "Copy.ai", "category": "Copywriting"},
    {"slug": "descript", "name": "Descript", "category": "Video Editor"},
    {"slug": "heygen", "name": "HeyGen", "category": "Avatar Generator"},
]

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("GEMINI_API_KEY が設定されていません。")
    sys.exit(1)

client = genai.Client(api_key=api_key)

generated_count = 0

for item in TOOLS_DB:
    file_path = os.path.join(OUTPUT_DIR, f"{item['slug']}.html")
    
    # すでに作成済みのページはスキップ（キャッシュ機能）
    if os.path.exists(file_path):
        print(f"スキップ（生成済み）: {item['name']}")
        continue
    
    # 1回の実行で5件に達したら安全に終了
    if generated_count >= MAX_BATCH_SIZE:
        print(f"\n1回の最大生成上限（{MAX_BATCH_SIZE}件）に達したため、本日の新規生成を終了します。")
        break
        
    print(f"生成中 ({generated_count + 1}/{MAX_BATCH_SIZE}): {item['name']}...")
    
    prompt = f"AIツール『{item['name']}』（カテゴリ: {item['category']}）の詳細な紹介・レビュー記事をSEO最適化したHTML本文形式（h2, h3, pタグを使用）で日本語で作成してください。"
    
    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
        )
        content_html = response.text
        
        # HTMLファイルの保存
        full_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{item['name']} の使い方・特徴まとめ</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@1/css/pico.min.css">
</head>
<body>
    <main class="container">
        <a href="index.html">← トップに戻る</a>
        <h1>{item['name']}</h1>
        <div>{content_html}</div>
    </main>
</body>
</html>"""

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_html)
            
        generated_count += 1
        time.sleep(5)  # レートリミット回避の待機
        
    except Exception as e:
        print(f"APIエラーが発生しました（制限到達の可能性）: {e}")
        print("ここまでに生成されたページを保存して正常終了します。")
        break

# トップページ (index.html) の一覧更新
index_items_html = ""
for item in TOOLS_DB:
    file_path = os.path.join(OUTPUT_DIR, f"{item['slug']}.html")
    status = "✅ 公開中" if os.path.exists(file_path) else "⏳ 順次生成中"
    link = f"<a href='{item['slug']}.html'>{item['name']}</a>" if os.path.exists(file_path) else item['name']
    index_items_html += f"<li>{link} - {item['category']} ({status})</li>\n"

index_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Tool Database</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@1/css/pico.min.css">
</head>
<body>
    <main class="container">
        <h1>AI Tool Database (pSEO)</h1>
        <p>自動生成された最新AIツール一覧</p>
        <ul>
            {index_items_html}
        </ul>
    </main>
</body>
</html>"""

with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(index_html)

print(f"ビルド完了: 新規作成 {generated_count} 件")
