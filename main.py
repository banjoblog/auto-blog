import os
import random
import re
import time
import json
import urllib.parse
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

# 利用可能なモデルリスト（安定稼働モデルへ修正）
MODEL_CANDIDATES = [
    'gemini-2.5-flash',
    'gemini-2.5-pro'
]

# 曜日別テーマ ＆ 提携アフィリエイト設定 (0:月曜日 ~ 6:日曜日)
WEEKLY_THEMES = {
    0: {
        "genre": "最新ガジェット・家電",
        "desc": "仕事や暮らしを便利にする買ってよかったガジェットや生活家電",
        "tags": "ガジェット, 家電, 暮らし",
        "image_keyword": "gadget,technology",
        "text_link_label": "👉 楽天市場で話題の人気ガジェット・最新家電一覧を見てみる",
        "text_link_url": "https://rpx.a8.net/svt/ejp?a8mat=3BBXGT+8G8KG2+2HOM+61Z81&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa20043004637_3BBXGT_8G8KG2_2HOM_61Z81%3Fpc%3Dhttp%253A%252F%252Fwww.rakuten.co.jp%252F%26m%3Dhttp%253A%252F%252Fm.rakuten.co.jp%252F",
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
        "tags": "節約, ポイ活, 資産運用",
        "image_keyword": "money,savings",
        "text_link_label": "👉 ポイント最大還元！楽天市場のポイ活・限定セール会場へ",
        "text_link_url": "https://rpx.a8.net/svt/ejp?a8mat=3BBXGT+8G8KG2+2HOM+61Z81&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa20043004637_3BBXGT_8G8KG2_2HOM_61Z81%3Fpc%3Dhttp%253A%252F%252Fwww.rakuten.co.jp%252F%26m%3Dhttp%253A%252F%252Fm.rakuten.co.jp%252F",
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
        "tags": "AI, 効率化, ワークスタイル",
        "image_keyword": "artificial-intelligence,laptop",
        "text_link_label": "👉 国内最速級！Xサーバーで爆速なWeb・AIツール環境を構築する",
        "text_link_url": "https://px.a8.net/svt/ejp?a8mat=3BHUM6+7L9ZG2+CO4+6CHB5",
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
        "tags": "副業, スキルアップ, 在宅ワーク",
        "image_keyword": "workspace,freelance",
        "text_link_label": "👉 副業の第一歩！自分だけの独自ドメインを安く取得する",
        "text_link_url": "https://px.a8.net/svt/ejp?a8mat=3BHUM6+7Q1GAA+348+1BUE69",
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
        "tags": "ライフハック, 集中力, 習慣",
        "image_keyword": "productivity,desk",
        "text_link_label": "👉 Amazonで人気のデスク周辺・作業改善グッズをチェックする",
        "text_link_url": "https://link.amazon/B06MY7qci",
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
        "tags": "読書, 書評, Kindle",
        "image_keyword": "books,reading",
        "text_link_label": "👉 最初の1冊が無料！Audibleで通勤中や家事中に「聴く読書」を体験",
        "text_link_url": "https://px.a8.net/svt/ejp?a8mat=4BGFJB+9T241U+5TB0+5ZMCH",
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
        "tags": "旅行, 週末, トレンド",
        "image_keyword": "travel,hotel",
        "text_link_label": "👉 クーポン配布中！楽天トラベルで人気のホテル・宿を探す",
        "text_link_url": "https://rpx.a8.net/svt/ejp?a8mat=3BBXGT+8G8KG2+2HOM+6I9N5&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea779e.5d30c5ba.0eb4779f.b871e4e3%2Fa20043004637_3BBXGT_8G8KG2_2HOM_6I9N5%3Fpc%3Dhttp%253A%252F%252Ftravel.rakuten.co.jp%252F%26m%3Dhttp%253A%252F%252Ftravel.rakuten.co.jp%252F",
        "affiliate_label": "＼ 楽天トラベルで週末の旅行やホテルをお得に予約 ／",
        "affiliate_html": """
        <a href="https://rpx.a8.net/svt/ejp?a8mat=3BBXGT+8G8KG2+2HOM+6I9N5&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea779e.5d30c5ba.0eb4779f.b871e4e3%2Fa20043004637_3BBXGT_8G8KG2_2HOM_6I9N5%3Fpc%3Dhttp%253A%252F%252Ftravel.rakuten.co.jp%252F%26m%3Dhttp%253A%252F%252Ftravel.rakuten.co.jp%252F" rel="nofollow">
        <img src="http://hbb.afl.rakuten.co.jp/hsb/0ea7f9a4.79280dcb.0ea7f99d.1ac92fca/153145/" border="0"></a>
        <img border="0" width="1" height="1" src="https://www16.a8.net/0.gif?a8mat=3BBXGT+8G8KG2+2HOM+6I9N5" alt="">
        """
    }
}

def generate_json_ld(title, description):
    schema = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": title,
        "description": description,
        "datePublished": datetime.now().isoformat(),
        "author": {
            "@type": "Person",
            "name": "編集部ライター"
        }
    }
    return f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>'

def create_header_image_html(keyword, alt_title):
    random_sig = int(time.time()) % 1000
    img_url = f"https://picsum.photos/800/400?random={random_sig}"
    
    return f"""
<div style="margin: 20px 0 30px 0; text-align: center;">
    <img src="{img_url}" alt="{alt_title}" style="max-width: 100%; height: auto; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.08);" />
</div>
"""

def create_text_link_html(label, url):
    return f"""
<div style="margin: 22px 0; padding: 14px 18px; background-color: #f0fdf4; border-left: 4px solid #22c55e; border-radius: 4px;">
    <a href="{url}" rel="nofollow" target="_blank" style="color: #15803d; font-weight: bold; font-size: 15px; text-decoration: underline;">{label}</a>
</div>
"""

def create_share_box():
    return """
<div style="margin: 30px 0; padding: 15px 20px; background-color: #faf5ff; border: 1px dashed #a855f7; border-radius: 8px; text-align: center;">
    <p style="font-weight: bold; color: #7e22ce; margin-bottom: 5px;">📢 この記事が役立ったらシェアをお願いします！</p>
    <p style="font-size: 13px; color: #6b21a8; margin: 0;">SNSやブログで紹介していただけると、今後の記事更新の励みになります✨</p>
</div>
"""

def generate_toc_and_inject(html_body, text_link_box):
    h2_pattern = re.compile(r'<h2>(.*?)</h2>', re.IGNORECASE)
    matches = list(h2_pattern.finditer(html_body))

    if not matches:
        return html_body

    toc_items = []
    for match in matches:
        h_text = match.group(1)
        clean_text = re.sub(r'^\d+[\.\s\-]+', '', h_text).strip()
        toc_items.append(f'<li style="margin-bottom: 6px;"><span style="color: #2563eb; font-weight: bold;">{clean_text}</span></li>')

    toc_list_html = "".join(toc_items)
    toc_html = f"""
<div style="margin: 25px 0; padding: 20px; background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 8px;">
    <p style="font-weight: bold; font-size: 16px; margin: 0 0 12px 0; color: #0f172a; border-bottom: 2px solid #2563eb; padding-bottom: 5px; display: inline-block;">📌 目次</p>
    <ol style="margin: 0; padding-left: 20px; color: #334155; font-size: 14px; list-style-type: decimal;">
        {toc_list_html}
    </ol>
</div>
"""

    first_idx = matches[0].start()
    result_html = html_body[:first_idx] + toc_html + html_body[first_idx:]

    matches_after_toc = list(h2_pattern.finditer(result_html))
    if len(matches_after_toc) >= 2:
        second_idx = matches_after_toc[1].start()
        result_html = result_html[:second_idx] + text_link_box + result_html[second_idx:]
    else:
        result_html += text_link_box

    return result_html

def create_affiliate_html(label, html_code):
    return f"""
<div style="margin: 35px 0; padding: 25px; border: 2px solid #3b82f6; background-color: #f0f9ff; text-align: center; border-radius: 12px; box-shadow: 0 6px 12px -2px rgba(59, 130, 246, 0.15);">
    <p style="font-weight: bold; font-size: 17px; margin-bottom: 15px; color: #1e3a8a;">🔥 【おすすめ】{label}</p>
    <div style="display: inline-block;">
        {html_code}
    </div>
</div>
"""

def create_related_box(genre_name):
    return f"""
<div style="margin: 30px 0; padding: 20px; background-color: #eff6ff; border-left: 5px solid #3b82f6; border-radius: 4px;">
    <p style="font-weight: bold; color: #1e3a8a; margin-bottom: 8px;">💡 「{genre_name}」カテゴリの他の記事もチェック</p>
    <p style="font-size: 14px; color: #1e40af; margin: 0;">当ブログでは毎週役に立つ最新情報を更新しています。ぜひトップページや他のカテゴリ記事もご覧ください！</p>
</div>
"""

def generate_seo_article():
    weekday = datetime.now().weekday()
    theme_info = WEEKLY_THEMES.get(weekday, WEEKLY_THEMES[0])
    current_year = datetime.now().year
    
    print(f"【本日のテーマ】{theme_info['genre']}（{theme_info['desc']}）")

    prompt = f"""
    あなたは月間10万PVのプロブログライターです。
    ジャンル「{theme_info['genre']}（{theme_info['desc']}）」に関する高品質なSEOブログ記事を作成してください。

    以下の出力フォーマットを厳密に守り、「---META---」の区切り線を挟んで出力してください。

    【出力フォーマット】
    タイトル: [{current_year}年最新のキーワードを含めた魅力的でクリックしたくなる記事タイトル]
    ---META---
    [100〜120文字程度の記事の要約（Meta Description用）]
    ---META---
    <p>[読者の悩みに共感し、記事を読むメリットを伝える導入文]</p>

    <h2>1. [主要な見出し1]</h2>
    <p>[具体的な解説文。適宜 <br> や <strong style="background: linear-gradient(transparent 60%, #fff9c4 60%);">蛍光ペン風太字</strong> を使用して読みやすく構成]</p>
    <ul>
        <li>[具体的なポイント1]</li>
        <li>[具体的なポイント2]</li>
    </ul>

    <h2>2. [主要な見出し2]</h2>
    <p>[具体的な解説文や実践方法]</p>

    <h2>3. よくある質問（Q&A）</h2>
    <div style="margin: 15px 0; padding: 15px; background-color: #f8fafc; border-radius: 6px;">
        <p style="font-weight: bold; color: #2563eb; margin-bottom: 5px;">Q. [読者が抱く疑問1]</p>
        <p style="margin: 0; color: #334155;">A. [わかりやすい回答1]</p>
    </div>
    <div style="margin: 15px 0; padding: 15px; background-color: #f8fafc; border-radius: 6px;">
        <p style="font-weight: bold; color: #2563eb; margin-bottom: 5px;">Q. [読者が抱く疑問2]</p>
        <p style="margin: 0; color: #334155;">A. [わかりやすい回答2]</p>
    </div>

    <h2>4. まとめ</h2>
    <p>[この記事のまとめと、読者へのアクションを促す結び文]</p>

    ※文字数は全体で1500〜1800文字程度、HTMLタグ（<h2>, <p>, <ul>, <li>, <strong>, <br>）を適切に使用してください。
    """

    response = None
    last_exception = None

    for model_name in MODEL_CANDIDATES:
        for attempt in range(3):
            try:
                print(f"[{model_name}] 記事生成中 (モデル: {model_name}, 試行 {attempt + 1}/3)...")
                response = client_genai.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    print(f"【成功】{model_name} で記事を作成しました！")
                    break
            except Exception as e:
                last_exception = e
                print(f"[{model_name}] 一時的エラー検知: {e}")
                time.sleep(5 * (attempt + 1))  # 5秒, 10秒, 15秒と待機時間を伸ばす
        if response and response.text:
            break

    if not response or not response.text:
        raise Exception(f"記事生成に失敗しました: {last_exception}")

    full_text = response.text
    
    raw_title = f"【{current_year}年最新】{theme_info['genre']}のおすすめガイド"
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
                    raw_title = line.replace("タイトル:", "").strip()
                    break

    header_img_html = create_header_image_html(theme_info.get("image_keyword", "technology"), raw_title)

    text_link_box = create_text_link_html(theme_info['text_link_label'], theme_info['text_link_url'])
    body_processed = generate_toc_and_inject(body, text_link_box)

    final_title = f"{raw_title} [{theme_info['tags']}]"

    share_box = create_share_box()
    affiliate_box = create_affiliate_html(theme_info['affiliate_label'], theme_info['affiliate_html'])
    related_box = create_related_box(theme_info['genre'])
    json_ld_html = generate_json_ld(raw_title, meta_desc)

    meta_lead_html = f"""
    <!-- meta:description:{meta_desc} -->
    <div style="background-color: #f8fafc; border-left: 4px solid #3b82f6; padding: 14px 18px; margin-bottom: 22px; font-size: 14px; color: #334155; border-radius: 0 6px 6px 0;">
        <strong style="color: #1d4ed8;">✨ この記事のポイント：</strong>{meta_desc}
    </div>
    """

    final_html = f"""
    {json_ld_html}
    {meta_lead_html}
    {header_img_html}
    {body_processed}
    {share_box}
    {related_box}
    {affiliate_box}
    """
    
    return final_title, final_html

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
    print("=== ブログ自動投稿システム（モデル設定＆エラー安定化版）を開始します ===")
    try:
        title, content = generate_seo_article()
        send_to_blogger(title, content)
        print("=== 全処理が正常に完了しました ===")
    except Exception as e:
        print(f"【致命的エラー】パイプライン実行失敗: {e}")
        raise e

if __name__ == "__main__":
    main()
