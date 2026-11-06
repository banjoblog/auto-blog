import os
import random
from google import genai
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import tweepy

# 環境変数の取得
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BLOGGER_EMAIL = os.environ.get("BLOGGER_EMAIL")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")

# X (Twitter) API Keys
X_API_KEY = os.environ.get("X_API_KEY")
X_API_SECRET = os.environ.get("X_API_SECRET")
X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.environ.get("X_ACCESS_SECRET")

# Gemini クライアントの初期化
client_genai = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID = 'gemini-3.8-flash'

# A8.net 250x250バナー（Blogger記事用）
AFFILIATE_HTML = """
<div style="margin: 30px 0; padding: 20px; border: 1px solid #e2e8f0; background-color: #f8fafc; text-align: center; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
    <p style="font-weight: bold; font-size: 15px; margin-bottom: 15px; color: #334155;">＼ おすすめのサービスをチェック ／</p>
    <div style="display: inline-block;">
        <a href="https://px.a8.net/svt/ejp?a8mat=3BBXGT+8HFFNM+1WP2+6G4HD" rel="nofollow">
        <img border="0" width="250" height="250" alt="" src="https://www26.a8.net/svt/bgt?aid=200430893513&wid=003&eno=01&mid=s00000008903001083000&mc=1" style="border-radius: 8px; max-width: 100%; height: auto;"></a>
        <img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=3BBXGT+8HFFNM+1WP2+6G4HD" alt="">
    </div>
</div>
"""

# X投稿用のアフィリエイトリンク集
AFFILIATE_LINKS = [
    {"category": "最新ガジェット", "url": "https://www.amazon.co.jp/s?k=ガジェット&tag=YOUR_AMAZON_ID-22"},
    {"category": "便利家電", "url": "https://www.amazon.co.jp/s?k=便利家電&tag=YOUR_AMAZON_ID-22"},
    {"category": "人気本・Kindle", "url": "https://www.amazon.co.jp/s?k=ビジネス書&tag=YOUR_AMAZON_ID-22"}
]

THEMES = [
    "初心者向けの節約術や資産形成・ポイ活のトレンド",
    "日常作業を爆速化するAIツールやおすすめアプリ",
    "最新の買ってよかった便利ガジェット・生活家電",
    "未経験から始められる人気の在宅副業・スキルアップ",
    "仕事や勉強の生産性を高めるタイムマネジメント・効率化テクニック"
]

def generate_blogger_article():
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
    response = client_genai.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
    )
    return response.text

def generate_x_post():
    item = random.choice(AFFILIATE_LINKS)
    
    prompt = f"""
    ジャンル「{item['category']}」に関する、思わず欲しくなるおすすめポイントを140文字以内でまとめたX（Twitter）用ポストを作成してください。
    
    【要件】
    1. 絵文字を適度に使って魅力的に紹介する
    2. 文末に必ず「 #PR 」を記載する
    3. リンクURLは含めないで本文テキストのみを出力する
    """
    response = client_genai.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
    )
    post_text = response.text.strip()
    
    final_post = f"{post_text}\n\n👇詳細はこちら\n{item['url']}"
    return final_post

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
        print(f"【成功】Bloggerへ投稿しました！ (ステータスコード: {response.status_code})")
    except Exception as e:
        print(f"Blogger送信エラー: {e}")

def post_to_x(post_text):
    if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
        print("エラー: X APIキーの設定が不足しています。")
        return
        
    try:
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_SECRET
        )
        response = client.create_tweet(text=post_text)
        print(f"【成功】Xへの自動ポストが完了しました！ (Tweet ID: {response.data['id']})")
    except Exception as e:
        print(f"X投稿エラー: {e}")

def main():
    print("=== 全自動投稿処理を開始します ===")
    
    # 1. Blogger記事生成＆投稿
    print("1. Blogger用記事を生成中...")
    article = generate_blogger_article()
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
        print("エラー: SendGrid Secretsが未設定です。")
        
    # 2. X用アフィリエイトポスト生成＆投稿
    print("2. X用ポストを生成中...")
    x_post = generate_x_post()
    post_to_x(x_post)

if __name__ == "__main__":
    main()
