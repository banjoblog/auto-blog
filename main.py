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

# 利用可能なモデルリスト
MODEL_CANDIDATES = [
    'gemini-3.8-flash',
    'gemini-3.1-pro-preview'
]

# 曜日別テーマ ＆ 実際の提携アフィリエイト設定 (0:月曜日 ~ 6:日曜日)
WEEKLY_THEMES = {
    0: {
        "genre": "最新ガジェット・家電",
        "desc": "仕事や暮らしを便利にする買ってよかったガジェットや生活家電",
        "affiliate_label": "＼ 楽天市場で話題の最新ガジェットをチェック ／",
        "affiliate_html": """
        <a href="https://rpx.a8.net/svt/ejp?a8mat=3BBXGT+8G8KG2+2HOM+61Z81&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa20043004637_3BBXGT_8G8KG2_2HOM_61Z81%3Fpc%3Dhttp%253A%252F%252Fwww.rakuten.co.jp%252F%26m%3Dhttp%253A%252F%252Fm.rakuten.co.jp%252F" rel="nofollow">
        <img src="http://hbb.afl.rakuten.co.jp/hsb/0eb4bbdb.d3e5aa19.0eb4bbaa.95151395/" border="0"></a>
        <img border="0" width="1" height="1" src="https://www16.a8.net/0.gif?a8mat=3BBXGT+8G8KG2+2HOM+61Z81" alt="">
        """
    },
    1: {
        "genre": "節約・資産形成・ポイ活",
        "desc": "初心者向けの固定費削減、ポイ活トレンド、貯金・投資のコツ",
        "affiliate_label": "＼ ポイントが貯まる！楽天市場でお得にお買い物 ／",
        "affiliate_html": """
        <a href="https://rpx.a8.net/svt/ejp?a8mat=3BBXGT+8G8KG2+2HOM+61Z81&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa20043004637_3BBXGT_8G8KG2_2HOM_61Z81%3Fpc%3Dhttp%253A%252F%252Fwww.rakuten.co.jp%252F%26m%3Dhttp%253A%252F%252Fm.rakuten.co.jp%252F" rel="nofollow">
        <img src="http://hbb.afl.rakuten.co.jp/hsb/0eb4bbdb.d3e5aa19.0eb4bbaa.95151395/" border="0"></a>
        <img border="0" width="1" height="1" src="https://www16.a8.net/0.gif?a8mat=3BBXGT+8G8KG2+2HOM+61Z81" alt="">
        """
    },
    2: {
        "genre": "AIツール・作業効率化",
        "desc": "業務効率化を図る最新AIツールや、時短に繋がるデジタル活用術",
        "affiliate_label": "＼ 高速・安定のレンタルサーバーでブログ・AI活用 ／",
        "affiliate_html": """
        <a href="https://px.a8.net/svt/ejp?a8mat=3BHUM6+7L9ZG2+CO4+6CHB5" rel="nofollow">
        <img border="0" width="350" height="240" alt="" src="https://www29.a8.net/svt/bgt?aid=200707134459&wid=001&eno=01&mid=s00000001642001066000&mc=1"></a>
        <img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=3BHUM6+7L9ZG2+CO4+6CHB5" alt="">
        """
    },
    3: {
        "genre": "在宅副業・スキルアップ",
        "desc": "未経験から始められる人気の在宅ワークや副業、おすすめ資格・学び",
        "affiliate_label": "＼ 自分だけの独自ドメインを取得して副業スタート ／",
        "affiliate_html": """
        <a href="https://px.a8.net/svt/ejp?a8mat=3BHUM6+7Q1GAA+348+1BUE69" rel="nofollow">
        <img border="0" width="468" height="60" alt="" src="https://www28.a8.net/svt/bgt?aid=200707134467&wid=001&eno=01&mid=s00000000404008036000&mc=1"></a>
        <img border="0" width="1" height="1" src="https://www11.a8.net/0.gif?a8mat=3BHUM6+7Q1GAA+348+1BUE69" alt="">
        """
    },
    4: {
        "genre": "ライフハック・生産性向上",
        "desc": "時間術、集中力を高める環境作り、日常のストレスを減らすテクニック",
        "affiliate_label": "＼ Amazonで生活を快適にする便利アイテムを見る ／",
        "affiliate_html": """
        <div style="margin-top: 15px;">
            <a href="https://link.amazon/B06MY7qci" target="_blank" rel="nofollow" style="background-color: #FF9900; color: #fff; padding: 12px 24px; font-weight: bold; text-decoration: none; border-radius: 6px; display: inline-block;">Amazonでおすすめ商品をチェック ➔</a>
        </div>
        """
    },
    5: {
        "genre": "おすすめ本・Kindle活用",
        "desc": "ビジネスパーソンが読むべき名著やKindleを使った読書術",
        "affiliate_label": "＼ 聴く読書！Audible（オーディブル）を無料体験 ／",
        "affiliate_html": """
        <a href="https://px.a8.net/svt/ejp?a8mat=4BGFJB+9T241U+5TB0+5ZMCH" rel="nofollow">
        <img border="0" width="300" height="250" alt="" src="https://www28.a8.net/svt/bgt?aid=261107111593&wid=003&eno=01&mid=s00000027126001006000&mc=1"></a>
        <img border="0" width="1" height="1" src="https://www15.a8.net/0.gif?a8mat=4BGFJB+9T241U+5TB0+5ZMCH" alt="">
        """
    },
    6: {
        "genre": "週末のトレンド・旅行・お出かけ",
        "desc": "週末の過ごし方、話題のスポット、おすすめの旅行・ホテル情報",
        "affiliate_label": "＼ 楽天トラベルで週末の旅行やホテルをお得に予約 ／",
        "affiliate_html": """
        <a href="https://rpx.a8.net/svt/ejp?a8mat=3BBXGT+8G8KG2+2HOM+6I9N5&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0eb4779e.5d30c5ba.0eb4779f.b871e4e3%2Fa20043004637_3BBXGT_8G8KG2_2HOM_6I9N5%3Fpc%3Dhttp%253A%252F%252Ftravel.rakuten.co.jp%252F%26m%3Dhttp%253A%252F%252Ftravel.rakuten.co.jp%252F" rel="nofollow">
        <img src="http://hbb.afl.rakuten.co.jp/hsb/0ea7f9a4.79280dcb.0ea7f99d.1ac92fca/153145/" border="0"></a>
        <img border="0" width="1" height="1" src="https://www16.a8.net/0.gif?a8mat=3BBXGT+8G8KG2+2HOM+6I9N5" alt="">
        """
    }
}

def create_affiliate_html(label, html_code):
    return f"""
<div style="margin: 35px 0; padding: 25px; border: 1px solid #e2e8f0; background-color: #f8fafc; text-align: center; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
    <p style="font-weight: bold; font-size: 16px; margin-bottom: 15px; color: #1e293b;">{label}</p>
    <div style="display: inline-block;">
        {html_code}
    </div>
</div>
"""

def generate_seo_article():
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

    affiliate_box = create_affiliate_html(theme_info['affiliate_label'], theme_info['affiliate_html'])

    final_html = f"""
    <!-- Meta Description: {meta_desc} -->
    {body}
    {affiliate_box}
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
    print("=== ブログ自動投稿システム（提携アフィリエイト連動版）を開始します ===")
    title, content = generate_seo_article()
    send_to_blogger(title, content)
    print("=== 全処理が正常に完了しました ===")

if __name__ == "__main__":
    main()
