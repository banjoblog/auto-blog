import os
import sys
import time
from datetime import datetime
from google import genai

# 1回の実行で生成するAIツールページの上限数
MAX_TOOL_BATCH = 5

OUTPUT_DIR = "dist"
BLOG_DIR = os.path.join(OUTPUT_DIR, "blog")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(BLOG_DIR, exist_ok=True)

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("GEMINI_API_KEY が設定されていません。")
    sys.exit(1)

client = genai.Client(api_key=api_key)
MODEL_NAME = "gemini-3.8-flash"

# ==========================================
# 1. 毎日の自動ブログ記事生成
# ==========================================
today_str = datetime.now().strftime("%Y-%m-%d")
blog_filename = f"post-{today_str}.html"
blog_filepath = os.path.join(BLOG_DIR, blog_filename)

if not os.path.exists(blog_filepath):
    print(f"本日のブログ記事を生成中 ({today_str})...")
    blog_prompt = f"""
    今日は {today_str} です。
    最新のAIトレンド、業務効率化、または最新テクノロジーに関する読み応えのあるブログ記事を1本作成してください。
    以下のルールに従ってください：
    - 1行目に「TITLE: 記事のタイトル」の形式で魅力的なタイトルを出力する
    - 2行目以降に、SEOを意識した見出し（h2, h3）と本文（p, ul, li）をHTML形式で記述する（htmlタグやbodyタグは不要）
    - 日本語で分かりやすく、実用的で親しみやすいトーンで書く
    """
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=blog_prompt,
        )
        lines = response.text.strip().split("\n")
        title = f"{today_str} のAI・テクノロジー最新情報"
        body_lines = []
        
        for line in lines:
            if line.startswith("TITLE:"):
                title = line.replace("TITLE:", "").strip()
            else:
                body_lines.append(line)
                
        body_html = "\n".join(body_lines)
        
        full_blog_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@1/css/pico.min.css">
</head>
<body>
    <main class="container">
        <nav><a href="../index.html">← トップページに戻る</a></nav>
        <article>
            <header>
                <small>{today_str}</small>
                <h1>{title}</h1>
            </header>
            <div>{body_html}</div>
        </article>
    </main>
</body>
</html>"""
        with open(blog_filepath, "w", encoding="utf-8") as f:
            f.write(full_blog_html)
        print(f"ブログ記事を作成しました: {title}")
        time.sleep(5)
    except Exception as e:
        print(f"ブログ生成エラー: {e}")
else:
    print(f"本日のブログ記事（{blog_filename}）はすでに作成済みです。")

# ==========================================
# 2. AIツールデータベース（pSEO）の生成
# ==========================================
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
    {"slug": "perplexity", "name": "Perplexity", "category": "Search Engine"},
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

generated_tools = 0
for item in TOOLS_DB:
    file_path = os.path.join(OUTPUT_DIR, f"{item['slug']}.html")
    if os.path.exists(file_path):
        continue
    if generated_tools >= MAX_TOOL_BATCH:
        break
        
    print(f"ツールページ生成中 ({generated_tools + 1}/{MAX_TOOL_BATCH}): {item['name']}...")
    prompt = f"AIツール『{item['name']}』（カテゴリ: {item['category']}）の詳細な紹介・レビュー記事をSEO最適化したHTML本文形式（h2, h3, pタグを使用）で日本語で作成してください。"
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        full_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{item['
