import os
import random
import time
from datetime import datetime
from google import genai
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# 環境変数の取得
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BLOGGER_EMAIL = os.environ.get("BLOGGER_EMAIL")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")

client_genai = genai.Client(api_key=GEMINI_API_KEY)

# 利用可能なモデルリスト（フォールバック用）
MODEL_CANDIDATES = [
    'gemini-3.8-flash',
    'gemini-3.1-pro-preview'
]

# 曜日別テーマ設定 (0:月曜日 ~ 6:日曜日)
WEEKLY_THEMES = {
    0: {"genre": "最新ガジェット・家電", "desc": "仕事や暮らしを便利にする買ってよかったガジェットや生活家電"},
    1: {"genre": "節約・資産形成・ポイ活", "desc": "初心者向けの固定費削減、ポイ活トレンド、貯金・投資のコツ"},
    2: {"genre": "AIツール・作業効率化", "desc": "業務効率化を図る最新AIツールや、時短に繋がるデジタル活用術"},
    3: {"genre": "在宅副業・スキルアップ", "desc": "未経験から始められる人気の在宅ワークや副業、おすすめ資格・学び"},
    4: {"genre": "ライフハック・生産性向上", "desc": "時間術、集中力を高める環境作り、日常のストレスを減らすテクニック"},
    5: {"genre": "おすすめ本・Kindle活用", "desc": "ビジネスパーソンが読むべき名著やKindleを使った読書術"},
    6: {"genre": "週末のトレンド・雑学", "desc": "今話題のニュース解説や知っておくと得する生活の豆知識"}
}

AFFILIATE_HTML = """
<div style="margin: 35px 0; padding: 25px; border: 1px solid #e2e8f0; background-color: #f8fafc; text-align: center; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
    <p style="font-weight: bold; font-size: 16px; margin-bottom: 15px; color: #1e293b;">＼ 本日のピックアップおすすめサービス ／</p>
    <div style="display: inline-block;">
        <a href="https://px.a8.net/svt/ejp?a8mat=3BBXGT+8HFFNM+1WP2+6G4HD" rel="nofollow">
        <img border="0" width="250" height="250" alt="" src="https://www26.a8.net/svt/bgt?aid=200430893513&wid=003&eno=01&mid=s00000008903001083000&mc=1" style="border-radius: 8px; max-width: 100%; height: auto;"></a>
        <img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=3BBXGT+8HFFNM+1WP2+6G4HD" alt="">
    </div>
</div>
"""

def generate_seo_article():
    # 曜日に合わせてテーマを自動選択
    weekday = datetime.now().weekday()
    theme_info = WEEKLY_THEMES.get(weekday, WEEKLY_THEMES[0])
    
    print(f"【本日のテーマ】{theme_info['genre']}（{theme_info['desc']}）")

    prompt = f"""
    あなたは月間10万PVのプロブログライターです。
    ジャンル「{theme_info['genre']}（{theme_info['desc']}）」に関する高品質なSEOブログ記事を作成してください。

    以下の出力フォーマットを厳密に守り、「---META---」の区切り線を挟んで出力してください。

    【出力フォーマット】
    タイトル: [読者の検索意図を満たす魅力的でクリックしたくなる記事タイトル]
    ---META---
    [100〜120文字程度の記事の要約（Meta Description用）]
    ---META---
    <p>[読者の悩みに共感し、記事を読むメリットを伝える導入文]</p>

    <h2>1. [主要な見出し1]</h2>
    <p>[具体的な解説文。適宜 <br> や <strong>太字</strong> を使用して読みやすく構成]</p>
    <ul>
        <li>[具体的なポイント1]</li>
        <li>[具体的なポイント2]</li>
    </ul>

    <h2>2. [主要な見出し2]</h2>
    <p>[具体的な解説文や実践方法]</p>

    <h2>3. まとめ</h2>
    <p>[この記事のまとめと、読者へのアクションを促す結び文]</p>

    ※文字数は全体で1500文字程度、HTMLタグ（<h2>, <p>, <ul>, <li>, <strong>, <br>）を適切に使用してください。
    """

    response = None
    last_exception = None

    # モデル切り替え ＆ リトライロジック
    for model_name in MODEL_CANDIDATES:
        for attempt in range(3):
            try:
                print(f"[{model_name}] 記事生成中 (試行 {attempt + 1}/3)...")
                response = client_genai.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    print(f"【成功】{model_name} で記事を作成しました！")
                    break
            except Exception as e:
                last_exception = e
                print(f"[{model_name}] エラー検知: {e}")
                time.sleep(3)
        if response and response.text:
            break

    if not response or not response.text:
        raise Exception(f"記事生成に失敗しました: {last_exception}")

    full_text = response.text
    
    # パーサー処理
    title = f"{theme_info['genre']}のおすすめガイド"
    meta_desc = ""
    body = full_text

    if "---META---" in full_text:
        parts = full_text.split("---META---")
        if len(parts) >= 3:
            title_part = parts[0].strip()
            meta_desc = parts[1].strip()
            body = parts[2].strip()
            
            for line in title_part.split('\n'):
                if line.startswith("タイトル:"):
                    title = line.replace("タイトル:", "").strip()
                    break

    # 記事本文にアフィリエイトHTMLとメタ記述用注釈を結合
    final_html = f"""
    <!-- Meta Description: {meta_desc} -->
    {body}
    {AFFILIATE_HTML}
    """
    
    return title, final_html

def send_to_blogger(title, content):
    if not all([BLOGGER_EMAIL, SENDGRID_API_KEY, SENDER_EMAIL]):
        print("エラー: SendGridまたはBloggerの環境変数が設定されていません。")
        return

    message = Mail(
        from_email=SENDER_EMAIL,
        to_emails=BLOGGER_EMAIL,
        subject=title,
        html_content=content
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"【成功】Bloggerへメール送信完了！ (ステータスコード: {response.status_code})")
    except Exception as e:
        print(f"Blogger送信エラー: {e}")

def main():
    print("=== ブログ自動投稿システム（SEO強化版）を開始します ===")
    title, content = generate_seo_article()
    send_to_blogger(title, content)
    print("=== 全処理が正常に完了しました ===")

if __name__ == "__main__":
    main()
