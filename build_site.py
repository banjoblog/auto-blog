import os
import json
import time
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client_genai = genai.Client(api_key=GEMINI_API_KEY)

os.makedirs("dist/tools", exist_ok=True)

def generate_tool_content(tool_info):
    prompt = f"""
    あなたはWebツールの専門アナリストです。
    以下のツールに関するSEOに強くて読みやすい詳細解説レビュー（日本語）を作成してください。

    【ツール情報】
    - 名前: {tool_info['name']}
    - カテゴリ: {tool_info['category']}
    - 価格帯: {tool_info['pricing']}
    - 主な機能: {', '.join(tool_info['features'])}
    - おすすめ対象: {tool_info['target']}

    【出力形式】
    以下の構成でHTML本文（<div>...</div>）のみを出力してください。
    - 概要とおすすめの理由
    - 主な特徴・メリット（箇条書き）
    - 想定される活用シーン
    - まとめ・こんな人におすすめ
    """
    
    for attempt in range(3):
        try:
            response = client_genai.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt
            )
            if response and response.text:
                return response.text
        except Exception as e:
            time.sleep(5)
    return "<p>コンテンツの自動生成中にエラーが発生しました。</p>"

def build():
    with open("tools.json", "r", encoding="utf-8") as f:
        tools = json.load(f)

    tool_links = []

    for tool in tools:
        print(f"Generating page for {tool['name']}...")
        content_html = generate_tool_content(tool)
        
        page_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{tool['name']} の特徴・料金・徹底比較カタログ</title>
    <style>
        body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }}
        header {{ border-bottom: 2px solid #2563eb; padding-bottom: 10px; margin-bottom: 20px; }}
        .badge {{ background: #eff6ff; color: #1d4ed8; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 14px; }}
        .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-top: 20px; }}
        a {{ color: #2563eb; text-decoration: none; font-weight: bold; }}
    </style>
</head>
<body>
    <p><a href="../index.html">← ツール一覧に戻る</a></p>
    <header>
        <span class="badge">{tool['category']}</span>
        <h1>{tool['name']}</h1>
        <p>料金モデル: <strong>{tool['pricing']}</strong> | 対象: {tool['target']}</p>
    </header>
    <main>
        {content_html}
    </main>
    <footer style="margin-top: 40px; border-top: 1px solid #e2e8f0; padding-top: 10px; font-size: 12px; color: #64748b;">
        © AI & Web Tools Database - Programmatic SEO Directory
    </footer>
</body>
</html>"""
        
        file_path = f"dist/tools/{tool['id']}.html"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(page_html)
        
        tool_links.append(f'<li><a href="tools/{tool["id"]}.html"><strong>{tool["name"]}</strong> ({tool["category"]})</a> - {tool["pricing"]}</li>')

    # トップ（インデックス）ページの生成
    links_html = "\n".join(tool_links)
    index_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI & Webツール徹底比較データベース</title>
    <style>
        body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }}
        header {{ border-bottom: 2px solid #2563eb; padding-bottom: 10px; margin-bottom: 20px; }}
        ul {{ list-style-type: none; padding: 0; }}
        li {{ background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 12px; margin-bottom: 10px; }}
        a {{ color: #2563eb; text-decoration: none; }}
    </style>
</head>
<body>
    <header>
        <h1>🚀 最新AI & Webツール比較データベース</h1>
        <p>注目の最新ツールやAIアシスタントの料金・特徴をプログラムで自動収集・比較しています。</p>
    </header>
    <main>
        <h2>掲載ツール一覧</h2>
        <ul>
            {links_html}
        </ul>
    </main>
</body>
</html>"""

    with open("dist/index.html", "w", encoding="utf-8") as f:
        f.write(index_html)
        
    print("Build completed! Output directory: dist/")

if __name__ == "__main__":
    build()
