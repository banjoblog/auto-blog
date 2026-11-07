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

client_genai = genai.Client(api_key=GEMINI_API_KEY)
# 確実に利用可能な安定版モデルを指定
MODEL_ID = 'gemini-1.5-flash'

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

def generate_content_bundle():
    selected_theme = random.choice(THEMES)
    item = random.choice(AFFILIATE_LINKS)
    
    prompt = f"""
    テーマ「{selected_theme}」に関するブログ記事と、ジャンル「{item['category']}」に関するX用ポストを同時に作成してください。
    
    出力は必ず以下の区切り線「---X_POST---」を挟んで出力してください。
    
    【前半：ブログ記事】
    1行目: 読者の目を引く魅力的な記事タイトル（「タイトル: 〇〇」の形式）
    2行目以降: 導入、主要なポイント（見出し付き）、まとめの構成（<p>や<br>を使用したHTML形式、1200〜1500字程度）
    
    ---X_POST---
    
    【後半：X用ポスト】
    ジャンル「{item['category']}」に関する思わず欲しくなるおすすめポイント（140文字以内、絵文字使用、文末に #PR を記載、URLは含めない）
    """
    
    response = client_genai.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
    )
    
    full_text = response.text
    if "---X_POST---" in full_text:
        article_part, x_part = full_text.split("---X_POST---", 1)
    else:
        article_part = full_text
        x_part = f"おすすめの{item['category']}をチェック！ #PR"
        
    x_post = f"{x_part.strip()}\n\n👇詳細はこちら\n{item['url']}"
    return article_part.strip(), x_post

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
    
    print("コンテンツを生成中（Gemini API 1回呼び出し）...")
    article, x_post = generate_content_bundle()
    
    # Blogger投稿処理
    lines = article.split('\n')
    title = "おすすめトレンドニュース"
    for line in lines:
        if line.startswith("タイトル:"):
            title = line.replace("タイトル:", "").strip()
            break
            
    final_content = article + "\n\n" + AFFILIATE_HTML
    
    if BLOGGER_EMAIL and SENDGRID_API_KEY and SENDER_EMAIL:
        send_to_blogger(title, final_content)
        
    # X投稿処理
    post_to_x(x_post)

if __name__ == "__main__":
    main()
