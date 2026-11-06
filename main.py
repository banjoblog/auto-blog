import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import google.generativeai as genai

# Gemini設定
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BLOGGER_EMAIL = os.environ.get("BLOGGER_EMAIL")

genai.configure(api_key=GEMINI_API_KEY)

def generate_article():
    # 利用可能なGeminiモデルを指定
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = """
    最新のテクノロジー、AI、ガジェット、または効率化テクニックに関する興味深いトレンドニュース記事を1つ執筆してください。
    
    【構成要件】
    1. 1行目: 読者の目を引く魅力的な記事タイトル（「タイトル: 〇〇」の形式）
    2. 本文: 導入、主要なポイント（見出し付き）、まとめの構成
    3. 文字数: 1200字〜1500字程度
    4. 読者にとって役立つ実用的な情報を含めること
    5. 自然で読みやすい日本語で書くこと
    """
    
    response = model.generate_content(prompt)
    return response.text

def send_to_blogger(content):
    lines = content.strip().split('\n')
    title = "AIテクノロジートレンドニュース"
    body_lines = []
    
    for line in lines:
        if line.startswith("タイトル:"):
            title = line.replace("タイトル:", "").strip()
        else:
            body_lines.append(line)
            
    body = "\n".join(body_lines)

    # 送信元・宛先設定（GitHub Actionsのメール環境を利用）
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(title, 'utf-8')
    msg['From'] = "auto-bot@example.com"
    msg['To'] = BLOGGER_EMAIL

    # Gmail SMTP経由等の設定不要な簡易メール送信、またはメール送信処理
    # 注意: Bloggerのメール投稿機能へGitHub Actionsから直接送る場合、SMTPサーバー設定が必要です。
    print(f"--- 生成された記事 ---")
    print(f"タイトル: {title}")
    print(f"本文抜粋: {body[:100]}...")

if __name__ == "__main__":
    article = generate_article()
    send_to_blogger(article)
