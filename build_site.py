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
    以下の構成でHTML本文（<div>...</div>）のみを出力してください。見出しは<h3>を使ってください。
    - 概要とおすすめの理由
    - 主な特徴・メリット（箇条書き）
    - 想定される活用シーン
    - まとめ・どんな人におすすめか
    """
    
    last_error = ""
    for attempt in range(3):
        try:
            # 指定された最新モデル 'gemini-3.8-flash' を使用
            response = client_genai.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt
            )
            if response and response.text:
                return response.text
        except Exception as e:
            last_error = str(e)
            print(f"API Retry ({tool_info['name']}) attempt {attempt+1}: {e}")
            time.sleep(5)
            
    return f"""
    <div style="background: #fef2f2; border: 1px solid #fca5a5; padding: 15px; border-radius: 8px; color: #991b1b;">
        <p><strong>⚠️ 生成エラーが発生しました</strong></p>
        <p style="font-family: monospace; font-size: 13px; word-break: break-all;">{last_error}</p>
    </div>
    """

def build():
    with open("tools.json", "r", encoding="utf-8") as f:
        tools = json.load(f)

    tool_links = []

    for i, tool in enumerate(tools):
        print(f"[{i+1}/{len(tools)}] Generating page for {tool['name']}...")
        
        # レート制限回避のためリクエスト間隔を5秒空ける
        if i > 0:
            time.sleep(5)
            
        content_html = generate_tool_content(tool)
        affiliate_url = tool.get("affiliate_url", "#")
        
        cta_box_html = f"""
        <div style="margin: 35px 0; padding: 25px; background: #eff6ff; border: 2px solid #3b82f6; border-radius: 12px; text-align: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
            <h3 style="margin-top: 0; color: #1e40af; font-size: 18px;">🔥 {tool['name']} を今すぐ試してみる</h3>
            <p style="font-size: 14px; color: #334155; margin-bottom: 20px;">最新機能やプランの詳細は公式サイトからチェックできます。</p>
            <a href="{affiliate_url}" target="_blank" rel="nofollow" style="background-color: #2563eb; color: #ffffff; padding: 14px 28px; font-weight: bold; text-decoration: none; border-radius: 8px; display: inline-block; font-size: 16px;">{tool['name']} 公式サイトはこちら ➔</a>
        </div>
        """
        
        page_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{tool['name']} の特徴・料金・徹底比較カタログ | AI & Web Tools Database</title>
    <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 850px; margin: 0 auto; padding: 20px; line-height: 1.7; color: #1e293b; background-color: #f8fafc; }}
        .container {{ background: #ffffff; padding: 30px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        header {{ border-bottom: 2px solid #e2e8f0; padding-bottom: 15px; margin-bottom: 25px; }}
        .badge {{ background: #dbeafe; color: #1e40af; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 13px; display: inline-block; margin-bottom: 10px; }}
        h1 {{ margin: 5px 0 15px 0; color: #0f172a; font-size: 28px; }}
        .meta-info {{ background: #f1f5f9; padding: 12px 18px; border-radius: 6px; font-size: 14px; color: #475569; }}
        h3 {{ color: #1e293b; border-left: 4px solid #2563eb; padding-left: 10px; margin-top: 30px; }}
        a {{ color: #2563eb; text-decoration: none; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <p><a href="../index.html">← ツール一覧に戻る</a></p>
        <header>
            <span class="badge">{tool['category']}</span>
            <h1>{tool['name']}</h1>
            <div class="meta-info">
                💰 料金モデル: <strong>{tool['pricing']}</strong> &nbsp;|&nbsp; 🎯 主な対象: <strong>{tool['target']}</strong>
            </div>
        </header>
        <main>
            {content_html}
            {cta_box_html}
        </main>
        <footer style="margin-top: 40px; border-top: 1px solid #e2e8f0; padding-top: 15px; font-size: 12px; color: #94a3b8; text-align: center;">
            © AI & Web Tools Database - Programmatic SEO Directory
        </footer>
    </div>
</body>
</html>"""
        
        file_path = f"dist/tools/{tool['id']}.html"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(page_html)
        
        tool_links.append(f'''
        <li style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px; margin-bottom: 15px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="background: #eff6ff; color: #1d4ed8; font-size: 12px; padding: 2px 8px; border-radius: 4px; font-weight: bold;">{tool["category"]}</span>
                    <h3 style="margin: 8px 0 4px 0; border: none; padding: 0; font-size: 18px;"><a href="tools/{tool["id"]}.html">{tool["name"]}</a></h3>
                    <p style="margin: 0; font-size: 13px; color: #64748b;">料金: {tool["pricing"]} | 対象: {tool["target"]}</p>
                </div>
                <a href="tools/{tool["id"]}.html" style="background: #2563eb; color: #fff; padding: 8px 16px; border-radius: 6px; font-size: 13px;">詳細を見る ➔</a>
            </div>
        </li>
        ''')

    links_html = "\n".join(tool_links)
    index_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI & Webツール徹底比較データベース</title>
    <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 850px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #1e293b; background-color: #f8fafc; }}
        header {{ background: #ffffff; padding: 30px; border-radius: 12px; margin-bottom: 25px; border: 1px solid #e2e8f0; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        h1 {{ margin: 0 0 10px 0; color: #0f172a; font-size: 26px; }}
        ul {{ list-style-type: none; padding: 0; }}
        a {{ text-decoration: none; }}
    </style>
</head>
<body>
    <header>
        <h1>🚀 最新AI & Webツール比較データベース</h1>
        <p style="margin: 0; color: #64748b; font-size: 15px;">注目の最新AIツールやWebアシスタントの料金・特徴をプログラムで自動収集・比較しています。</p>
    </header>
    <main>
        <h2 style="font-size: 20px; color: #334155; margin-bottom: 15px;">掲載ツール一覧 ({len(tools)}件)</h2>
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
