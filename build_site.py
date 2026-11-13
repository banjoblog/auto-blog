import os
import sys
import time
from datetime import datetime
from google import genai
from google.genai import types

# 1回の実行で生成するAIツールページの上限数
MAX_TOOL_BATCH = 2

OUTPUT_DIR = "dist"
BLOG_DIR = os.path.join(OUTPUT_DIR, "blog")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(BLOG_DIR, exist_ok=True)

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("GEMINI_API_KEY が設定されていません。")
    sys.exit(1)

client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(timeout=60000),
)
MODEL_NAME = "gemini-3.8-flash"

def generate_with_retry(prompt, retries=3, wait=15):
    for attempt in range(1, retries + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                print(f"サーバー混雑 (503) のため {wait}秒後にリトライします ({attempt}/{retries})...")
                time.sleep(wait)
            else:
                raise e
    raise RuntimeError("リトライ上限に達しました（503 UNAVAILABLE）")

# ==========================================
# 1. 毎日の自動ブログ記事生成
# ==========================================
today_str = datetime.now().strftime("%Y-%m-%d")
blog_filename = f"post-{today_str}.html"
blog_filepath = os.path.join(BLOG_DIR, blog_filename)

if not os.path.exists(blog_filepath):
    print(f"本日のブログ記事を生成中 ({today_str})...")
    blog_prompt = f"今日は {today_str} です。最新のAIトレンドや活用法に関するSEO最適化されたブログ記事を日本語で作成してください。1行目に「TITLE: 記事タイトル」を出力し、2行目以降にh2, h3, pタグを使用した本文を出力してください。"
    try:
        text = generate_with_retry(blog_prompt)
        lines = text.strip().split("\n")
        title = f"{today_str} のAI・テクノロジー最新情報"
        body_lines = []

        for line in lines:
            if line.startswith("TITLE:"):
                title = line.replace("TITLE:", "").strip()
            else:
                body_lines.append(line)

        body_html = "\n".join(body_lines)

        blog_template = """<!DOCTYPE html>
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
                <small>{date}</small>
                <h1>{title}</h1>
            </header>
            <div>{body}</div>
        </article>
    </main>
</body>
</html>"""

        full_blog_html = blog_template.format(title=title, date=today_str, body=body_html)
        with open(blog_filepath, "w", encoding="utf-8") as f:
            f.write(full_blog_html)
        print(f"ブログ記事を作成しました: {title}")
        time.sleep(2)
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

tool_template = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} の使い方・特徴まとめ</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@1/css/pico.min.css">
</head>
<body>
    <main class="container">
        <nav><a href="index.html">← トップページに戻る</a></nav>
        <h1>{name}</h1>
        <div>{body}</div>
    </main>
</body>
</html>"""

generated_tools = 0
for item in TOOLS_DB:
    if not item.get("slug"):
        continue
    file_path = os.path.join(OUTPUT_DIR, f"{item['slug']}.html")
    if os.path.exists(file_path):
        continue
    if generated_tools >= MAX_TOOL_BATCH:
        break

    print(f"ツールページ生成中 ({generated_tools + 1}/{MAX_TOOL_BATCH}): {item['name']}...")
    prompt = f"AIツール『{item['name']}』（カテゴリ: {item['category']}）の詳細な紹介・レビュー記事をSEO最適化したHTML本文形式（h2, h3, pタグを使用）で日本語で作成してください。"

    try:
        text = generate_with_retry(prompt)
        full_html = tool_template.format(name=item['name'], body=text)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_html)
        generated_tools += 1
        time.sleep(2)
    except Exception as e:
        print(f"ツール生成エラー: {e}")
        break

# ==========================================
# 3. トップページ (index.html) の更新
# ==========================================
blog_list_html = ""
blog_files = sorted([f for f in os.listdir(BLOG_DIR) if f.endswith(".html")], reverse=True)
for bf in blog_files:
    date_label = bf.replace("post-", "").replace(".html", "")
    with open(os.path.join(BLOG_DIR, bf), "r", encoding="utf-8") as f:
        content = f.read()
        start = content.find("<title>") + 7
        end = content.find("</title>")
        b_title = content[start:end] if start > 6 and end > start else bf
    blog_list_html += f"<li><strong>[{date_label}]</strong> <a href='blog/{bf}'>{b_title}</a></li>\n"

if not blog_list_html:
    blog_list_html = "<li>まだ記事がありません。</li>"

index_items_html = ""
for item in TOOLS_DB:
    if not item.get("slug"):
        continue
    file_path = os.path.join(OUTPUT_DIR, f"{item['slug']}.html")
    status = "✅ 公開中" if os.path.exists(file_path) else "⏳ 順次生成中"
    link = f"<a href='{item['slug']}.html'>{item['name']}</a>" if os.path.exists(file_path) else item['name']
    index_items_html += f"<li>{link} - {item['category']} ({status})</li>\n"

index_template = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Tech Blog & Tool Database</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@1/css/pico.min.css">
</head>
<body>
    <main class="container">
        <h1>AI Tech Blog & Tool Database</h1>
        
        <section>
            <h2>📝 最新の自動生成ブログ記事</h2>
            <ul>
                {blogs}
            </ul>
        </section>

        <hr>

        <section>
            <h2>🛠️ AIツールデータベース</h2>
            <ul>
                {tools}
            </ul>
        </section>
    </main>
</body>
</html>"""

index_html = index_template.format(blogs=blog_list_html, tools=index_items_html)

with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(index_html)

print("すべてのビルド処理が正常に完了しました。")
