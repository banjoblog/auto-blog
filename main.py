import os
import random
import google.generativeai as genai
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BLOGGER_EMAIL = os.environ.get("BLOGGER_EMAIL")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")

genai.configure(api_key=GEMINI_API_KEY)

# A8.net広告コード
AFFILIATE_HTML = """
<div style="margin: 25px 0; padding: 20px; border: 1px solid #e0e0e0; background-color: #f9f9f9; text-align: center; border-radius: 8px;">
    <p style="font-weight: bold; font-size: 16px; margin-bottom: 12px; color: #333;">【おすすめ情報】気になるサービスを今すぐチェック！</p>
    <a href="https://px.a8.net/svt/ejp?a8mat=3BBXGT+8HFFNM+1WP2+6H729" rel="nofollow">
    <img border="0" width="100" height="60" alt="" src="https://www21.a8.net/svt/bgt?aid=200430893513&wid=003&eno=01&mid=s00000008903001088000&mc=1"></a>
    <img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=3BBXGT+8HFFNM+1WP2+6H729" alt="">
</div>
"""

THEMES = [
    "初心者向けの節約術や資産形成・ポイ活のトレンド",
    "日常作業を爆速化するAIツールやおすすめアプリ",
    "最新の買ってよかった便利ガジェット・生活家電",
    "未経験から始められる人気の在宅副業・スキルアップ",
    "仕事や勉強の生産性を高めるタイムマネジメント・効率化テクニック"
]

def generate_article():
    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    priority_models = [
        'models/gemini-3.8-flash',
        'models/gemini-1.5-flash',
        'models/gemini-2.5-flash',
        'models/gemini-pro'
    ]
    
    target_model = None
    for pm in priority_models:
        if pm in models:
            target_model = pm
            break
            
    if not target_model and models:
        target_model = models[0]
        
    model = genai.GenerativeModel(target_model)
    selected_theme = random.choice(THEMES)
    
    prompt = f"""
    テーマ「{selected_theme}」に関する、検索読者の関心が高い具体的な話題・ニュースを1つ選び、ブログ記事を執筆してください。
    
    【構成要件】
    1. 1行目: 読者の目を引く魅力的な記事タイトル（「タイトル: 〇〇」の形式）
    2. 本文: 導入、主要なポイント（見出し付き）、まとめの構成
    3. 改行や段落を<p>や<br>で整えたHTML形式で出力すること
    4. 文字数: 1200字〜1500字程度
    5. 自然で読みやすい日本語で書くこと
    """
    
    response = model.generate_content(prompt)
    return response.text

def send_to_blogger(title, content):
    message = Mail(
        from_email=SENDER_EMAIL,
        to_emails=BLOGGER_EMAIL,
        subject=title,
        html_content=content
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"【成功】SendGrid経由でBlogger宛てにメールを送信しました！ (ステータスコード: {response.status_code})")
    except Exception as e:
        print(f"送信エラー: {e}")

def main():
    print("AI記事自動生成と送信処理を開始します...")
    article = generate_article()
    
    lines = article.strip().split('\n')
    title = "おすすめトレンドニュース"
    for line in lines:
        if line.startswith("タイトル:"):
            title = line.replace("タイトル:", "").strip()
            break
            
    final_content = article + "\n\n" + AFFILIATE_HTML
    
    if BLOGGER_EMAIL and SENDGRID_API_KEY and SENDER_EMAIL:
        send_to_blogger(title, final_content)
    else:
        print("エラー: Secretsの設定（BLOGGER_EMAIL, SENDGRID_API_KEY, SENDER_EMAIL）を確認してください。")

if __name__ == "__main__":
    main()
