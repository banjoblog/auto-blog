import os
import sys
import time
import random
from datetime import datetime
from google import genai
from google.genai import types

# 1回の実行で新規生成するAIツールページの上限数
MAX_TOOL_BATCH = 5

# Trueにすると、すでに生成済みの全ページの「アフィリエイト枠・CTA・CSS」をAPI消費なしで一括更新します
REFRESH_EXISTING_LAYOUT = True

OUTPUT_DIR = "dist"
BLOG_DIR = os.path.join(OUTPUT_DIR, "blog")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(BLOG_DIR, exist_ok=True)

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("GEMINI_API_KEY が設定されていません。", flush=True)
    sys.exit(1)

client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(timeout=90000),
)

def get_available_models():
    models = ["gemini-3.1-flash-lite", "gemini-3.8-flash"]
    try:
        for m in client.models.list():
            name = m.name.replace("models/", "")
            if (
                "gemini-3" in name
                and "embedding" not in name
                and "imagen" not in name
                and "veo" not in name
                and "tts" not in name
                and "image" not in name
                and name not in models
            ):
                models.append(name)
    except Exception as e:
        print(f"モデル一覧取得スキップ: {e}", flush=True)
    return models

CANDIDATE_MODELS = get_available_models()
print(f"使用候補モデル: {CANDIDATE_MODELS}", flush=True)

def generate_with_retry(prompt):
    wait_schedule = [5, 10, 20, 30]
    for model_name in CANDIDATE_MODELS:
        for attempt, wait_sec in enumerate(wait_schedule, start=1):
            try:
                print(f"[{model_name}] 生成リクエスト送信中 ({attempt}/{len(wait_schedule)})...", flush=True)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                return response.text
            except Exception as e:
                err_str = str(e)
                if any(code in err_str for code in ["503", "504", "429", "UNAVAILABLE", "DEADLINE_EXCEEDED", "RESOURCE_EXHAUSTED"]):
                    print(f"[{model_name}] 混雑のため {wait_sec}秒待機して再試行します...", flush=True)
                    time.sleep(wait_sec)
                elif "404" in err_str or "NOT_FOUND" in err_str or "400" in err_str:
                    print(f"[{model_name}] 非対応のため次のモデルへ切り替えます...", flush=True)
                    break
                else:
                    raise e
    raise RuntimeError("すべての候補モデルで生成に失敗しました。")

# ==========================================
# アフィリエイト広告定義（A8タグは改変せずそのまま保持）
# ==========================================
AFFILIATE_ITEMS = {
    "audible": {
        "title": "🎧 AI・ビジネス最新トレンドを「耳」からインプット（Audible）",
        "desc": "作業中や移動時間に最新のAI解説書・ビジネス書を聴き放題で効率学習。無料体験から気軽に始められます。",
        "html": """<a href="https://px.a8.net/svt/ejp?a8mat=4BGFJB+9T241U+5TB0+5ZMCH" rel="nofollow">
<img border="0" width="300" height="250" alt="" src="https://www22.a8.net/svt/bgt?aid=261107111593&wid=003&eno=01&mid=s00000027126001006000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=4BGFJB+9T241U+5TB0+5ZMCH" alt="">""",
    },
    "xserver": {
        "title": "🚀 AIで作ったWebサイト・ブログを公開するなら「エックスサーバー」",
        "desc": "国内シェアNo.1の高速レンタルサーバー。AIで生成した記事やアプリを安定・高速に公開できます。",
        "html": """<a href="https://px.a8.net/svt/ejp?a8mat=3BHUM6+7L9ZG2+CO4+6CHB5" rel="nofollow">
<img border="0" width="350" height="240" alt="" src="https://www21.a8.net/svt/bgt?aid=200707134459&wid=001&eno=01&mid=s00000001642001066000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=3BHUM6+7L9ZG2+CO4+6CHB5" alt="">""",
    },
    "xserver_domain": {
        "title": "🌐 独自ドメインの取得・管理なら「エックスサーバードメイン」",
        "desc": "AIメディアや個人開発サービスの独自ドメインを低コストで取得・一元管理。",
        "html": """<a href="https://px.a8.net/svt/ejp?a8mat=3BHUM6+7K348I+CO4+15THJ5" rel="nofollow">
<img border="0" width="468" height="60" alt="" src="https://www25.a8.net/svt/bgt?aid=200707134457&wid=001&eno=01&mid=s00000001642007024000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www19.a8.net/0.gif?a8mat=3BHUM6+7K348I+CO4+15THJ5" alt="">""",
    },
    "rakuten_ichiba": {
        "title": "🛒 AI活用を加速するPC・ガジェット・関連書籍を「楽天市場」で探す",
        "desc": "ローカルAI用のGPU搭載PCやマイク、最新AI解説本までポイント還元でお得にチェック。",
        "html": """<a href="https://rpx.a8.net/svt/ejp?a8mat=3BBXGT+8G8KG2+2HOM+61Z81&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0ea62065.34400275.0ea62066.204f04c0%2Fa20043004637_3BBXGT_8G8KG2_2HOM_61Z81%3Fpc%3Dhttp%253A%252F%252Fwww.rakuten.co.jp%252F%26m%3Dhttp%253A%252F%252Fm.rakuten.co.jp%252F" rel="nofollow">
<img src="http://hbb.afl.rakuten.co.jp/hsb/0eb4bbdb.d3e5aa19.0eb4bbaa.95151395/" border="0"></a>
<img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=3BBXGT+8G8KG2+2HOM+61Z81" alt="">""",
    },
    "rakuten_travel": {
        "title": "✈️ AIで作成した旅行プランを「楽天トラベル」で予約",
        "desc": "ChatGPTやPerplexityで組んだ旅程に合わせて、国内・海外のホテルやツアーをスマートに予約。",
        "html": """<a href="https://rpx.a8.net/svt/ejp?a8mat=3BBXGT+8G8KG2+2HOM+6I9N5&rakuten=y&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F0eb4779e.5d30c5ba.0eb4779f.b871e4e3%2Fa20043004637_3BBXGT_8G8KG2_2HOM_6I9N5%3Fpc%3Dhttp%253A%252F%252Ftravel.rakuten.co.jp%252F%26m%3Dhttp%253A%252F%252Ftravel.rakuten.co.jp%252F" rel="nofollow">
<img src="http://hbb.afl.rakuten.co.jp/hsb/0ea7f9a4.79280dcb.0ea7f99d.1ac92fca/153145/" border="0"></a>
<img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=3BBXGT+8G8KG2+2HOM+6I9N5" alt="">""",
    },
    "dmm_fx": {
        "title": "📈 データ分析・マーケットチェックに興味がある方へ（DMM FX）",
        "desc": "AI時代のリスク管理と資産運用に。高機能チャートツールを備えた国内人気口座。",
        "html": """<a href="https://px.a8.net/svt/ejp?a8mat=3BBXGT+8HFFNM+1WP2+6G4HD" rel="nofollow">
<img border="0" width="250" height="250" alt="" src="https://www28.a8.net/svt/bgt?aid=200430893513&wid=003&eno=01&mid=s00000008903001083000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=3BBXGT+8HFFNM+1WP2+6G4HD" alt="">""",
    },
    "amazon": {
        "title": "📦 Amazon でAI関連書籍・PC周辺機器・ガジェットをチェック",
        "desc": "プロンプトエンジニアリング入門書やクリエイター向けデバイスをAmazonで検索。",
        "html": """<a href="https://www.amazon.co.jp?&linkCode=ll2&tag=ntklog0c-22&linkId=c7895fa240d32728460bada24cc0eeb6&ref_=as_li_ss_tl" target="_blank" rel="nofollow sponsored noopener" class="cta-btn" style="background: linear-gradient(135deg, #f59e0b, #d97706);">Amazon.co.jp で詳細を見る →</a>""",
    },
}

def build_pr_section(category="general"):
    """カテゴリに応じて最適なアフィリエイト枠（2〜3件）を自動組み立て"""
    if category in ["Code Generator", "Code Editor", "Text Generator", "Copywriting", "Productivity"]:
        keys = ["xserver", "audible", "amazon"]
    elif category in ["Image Generator", "Video Generator", "Voice Generator", "Music Generator", "Design", "Video Editor", "Avatar Generator"]:
        keys = ["audible", "rakuten_ichiba", "amazon"]
    elif category == "Search Engine":
        keys = ["audible", "rakuten_travel", "amazon"]
    else:
        # ブログ記事・トップページ用
        keys = ["audible", "xserver", "amazon"]

    cards_html = ""
    for k in keys:
        item = AFFILIATE_ITEMS[k]
        cards_html += f"""
        <div class="pr-card">
            <div class="pr-card-body">
                <span class="pr-tag">PR</span>
                <h4>{item['title']}</h4>
                <p>{item['desc']}</p>
            </div>
            <div class="pr-banner">
                {item['html']}
            </div>
        </div>
        """

    # 記事下部にドメイン横長バナーも添える
    domain_banner = AFFILIATE_ITEMS["xserver_domain"]["html"]
    return f"""
    <section class="pr-section">
        <h3 class="pr-section-title">📢 おすすめサービス・関連リソース（PR）</h3>
        <div class="pr-grid">
            {cards_html}
        </div>
        <div class="pr-wide-banner">
            {domain_banner}
        </div>
    </section>
    """

# ==========================================
# 共通スタイルシート（PRバナー・CTA対応）
# ==========================================
COMMON_CSS = """
<style>
  :root {
    --bg: #f8fafc;
    --surface: #ffffff;
    --text: #0f172a;
    --muted: #475569;
    --border: #e2e8f0;
    --primary: #2563eb;
    --primary-soft: #eff6ff;
    --accent: #7c3aed;
    --success-bg: #dcfce7;
    --success-text: #166534;
    --pending-bg: #f1f5f9;
    --pending-text: #475569;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Hiragino Kaku Gothic ProN", "Noto Sans JP", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.8;
  }
  a { color: var(--primary); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .navbar {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 14px 20px;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .navbar-inner {
    max-width: 1040px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .brand {
    font-weight: 800;
    font-size: 1.15rem;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .brand span {
    background: linear-gradient(135deg, var(--primary), var(--accent));
    color: #fff;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.8rem;
  }
  .hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #312e81 100%);
    color: #fff;
    padding: 56px 20px;
    margin-bottom: 36px;
  }
  .hero-inner {
    max-width: 1040px;
    margin: 0 auto;
  }
  .hero h1 {
    margin: 0 0 12px;
    font-size: clamp(1.8rem, 4vw, 2.6rem);
    line-height: 1.25;
  }
  .hero p {
    margin: 0;
    color: #cbd5e1;
    font-size: 1.05rem;
    max-width: 680px;
  }
  .container {
    max-width: 1040px;
    margin: 0 auto;
    padding: 0 20px 64px;
  }
  .article-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: clamp(24px, 4vw, 44px);
    box-shadow: 0 4px 20px rgba(15, 23, 42, 0.04);
  }
  .breadcrumb {
    font-size: 0.88rem;
    color: var(--muted);
    margin-bottom: 18px;
  }
  .pr-notice {
    font-size: 0.78rem;
    color: var(--muted);
    background: #f8fafc;
    border: 1px solid var(--border);
    padding: 6px 12px;
    border-radius: 6px;
    margin-bottom: 16px;
    display: inline-block;
  }
  .badge {
    display: inline-block;
    background: var(--primary-soft);
    color: var(--primary);
    font-weight: 700;
    font-size: 0.8rem;
    padding: 4px 12px;
    border-radius: 999px;
    margin-bottom: 12px;
  }
  .article-header h1 {
    margin: 0 0 12px;
    font-size: clamp(1.6rem, 3.5vw, 2.2rem);
    line-height: 1.3;
  }
  .article-meta {
    color: var(--muted);
    font-size: 0.95rem;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 24px;
  }
  .cta-box {
    background: linear-gradient(135deg, #eff6ff 0%, #f5f3ff 100%);
    border: 1px solid #c7d2fe;
    border-radius: 14px;
    padding: 20px 24px;
    margin: 24px 0;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  .cta-box-text strong {
    display: block;
    font-size: 1.06rem;
    color: #1e1b4b;
    margin-bottom: 4px;
  }
  .cta-box-text span {
    font-size: 0.88rem;
    color: #475569;
  }
  .cta-btn {
    display: inline-block;
    background: linear-gradient(135deg, var(--primary), var(--accent));
    color: #ffffff !important;
    font-weight: 700;
    font-size: 0.95rem;
    padding: 12px 24px;
    border-radius: 10px;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.25);
    transition: transform 0.15s ease;
    text-decoration: none !important;
    white-space: nowrap;
  }
  .cta-btn:hover {
    transform: translateY(-2px);
  }
  /* PRセクション */
  .pr-section {
    margin-top: 36px;
    padding-top: 28px;
    border-top: 1px solid var(--border);
  }
  .pr-section-title {
    font-size: 1.2rem;
    margin: 0 0 18px;
    color: var(--text);
  }
  .pr-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 18px;
  }
  .pr-card {
    background: #f8fafc;
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 14px;
  }
  .pr-tag {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 700;
    color: #64748b;
    border: 1px solid #cbd5e1;
    padding: 1px 6px;
    border-radius: 4px;
    margin-bottom: 6px;
  }
  .pr-card h4 {
    margin: 0 0 6px;
    font-size: 1rem;
    line-height: 1.4;
  }
  .pr-card p {
    margin: 0;
    font-size: 0.85rem;
    color: var(--muted);
    line-height: 1.6;
  }
  .pr-banner {
    text-align: center;
    overflow-x: auto;
  }
  .pr-banner img {
    max-width: 100%;
    height: auto;
    border-radius: 8px;
  }
  .pr-wide-banner {
    margin-top: 18px;
    text-align: center;
    overflow-x: auto;
  }
  .pr-wide-banner img {
    max-width: 100%;
    height: auto;
    border-radius: 6px;
  }
  .article-body h2 {
    margin-top: 38px;
    margin-bottom: 14px;
    font-size: 1.35rem;
    padding-left: 14px;
    border-left: 4px solid var(--primary);
  }
  .article-body h3 {
    margin-top: 24px;
    margin-bottom: 10px;
    font-size: 1.12rem;
    color: #1e293b;
  }
  .article-body p {
    margin: 0 0 16px;
    color: #334155;
  }
  .article-body ul, .article-body ol {
    margin: 0 0 20px;
    padding-left: 22px;
    color: #334155;
  }
  .article-body li {
    margin-bottom: 8px;
  }
  .article-body table {
    width: 100%;
    border-collapse: collapse;
    margin: 24px 0;
    font-size: 0.95rem;
    background: #fff;
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid var(--border);
  }
  .article-body th {
    background: #f1f5f9;
    text-align: left;
    padding: 12px 16px;
    font-weight: 700;
    border-bottom: 1px solid var(--border);
  }
  .article-body td {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
  }
  .article-body blockquote {
    margin: 20px 0;
    padding: 14px 20px;
    background: var(--primary-soft);
    border-left: 4px solid var(--primary);
    border-radius: 0 8px 8px 0;
    color: #1e3a8a;
  }
  .section-title {
    font-size: 1.45rem;
    margin: 40px 0 18px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
    gap: 18px;
  }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 25px rgba(15, 23, 42, 0.07);
  }
  .card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }
  .cat-tag {
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--muted);
    background: #f1f5f9;
    padding: 3px 10px;
    border-radius: 6px;
  }
  .status-pill {
    font-size: 0.75rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 999px;
  }
  .status-live {
    background: var(--success-bg);
    color: var(--success-text);
  }
  .status-pending {
    background: var(--pending-bg);
    color: var(--pending-text);
  }
  .card h3 {
    margin: 4px 0 8px;
    font-size: 1.15rem;
  }
  .card p {
    margin: 0;
    font-size: 0.9rem;
    color: var(--muted);
  }
  .blog-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .blog-item {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 20px;
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .blog-date {
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--primary);
    background: var(--primary-soft);
    padding: 4px 10px;
    border-radius: 6px;
    white-space: nowrap;
  }
  .footer {
    text-align: center;
    padding: 28px 20px;
    color: var(--muted);
    font-size: 0.88rem;
    border-top: 1px solid var(--border);
    background: var(--surface);
  }
</style>
"""

# ==========================================
# AIツールデータベース
# ==========================================
TOOLS_DB = [
    {"slug": "chatgpt", "name": "ChatGPT", "category": "Text Generator", "tagline": "対話・文章作成・プログラミングをこなす万能AI", "official_url": "https://chatgpt.com/"},
    {"slug": "claude", "name": "Claude", "category": "Text Generator", "tagline": "長文読解と自然な日本語表現・コーディングに強み", "official_url": "https://claude.ai/"},
    {"slug": "midjourney", "name": "Midjourney", "category": "Image Generator", "tagline": "圧倒的なアート品質を誇る画像生成AIの定番", "official_url": "https://www.midjourney.com/"},
    {"slug": "stable-diffusion", "name": "Stable Diffusion", "category": "Image Generator", "tagline": "ローカル環境や拡張機能で自在に操れるオープンソース画像AI", "official_url": "https://stability.ai/"},
    {"slug": "runway", "name": "Runway", "category": "Video Generator", "tagline": "テキストや画像から映画品質の動画を生成・編集", "official_url": "https://runwayml.com/"},
    {"slug": "sora", "name": "Sora", "category": "Video Generator", "tagline": "物理法則を理解した長尺・高精細な動画生成モデル", "official_url": "https://sora.com/"},
    {"slug": "elevenlabs", "name": "ElevenLabs", "category": "Voice Generator", "tagline": "感情豊かな多言語音声合成・ボイスクローンAI", "official_url": "https://elevenlabs.io/"},
    {"slug": "suno", "name": "Suno AI", "category": "Music Generator", "tagline": "歌詞とジャンル指定だけでボーカル入り楽曲を即生成", "official_url": "https://suno.com/"},
    {"slug": "udio", "name": "Udio", "category": "Music Generator", "tagline": "プロ品質のサウンド構成とリミックスが可能な音楽AI", "official_url": "https://www.udio.com/"},
    {"slug": "perplexity", "name": "Perplexity", "category": "Search Engine", "tagline": "出典リンク付きで最新情報を即座に要約するAI検索", "official_url": "https://www.perplexity.ai/"},
    {"slug": "v0-dev", "name": "v0.dev", "category": "Code Generator", "tagline": "プロンプトからReact/TailwindのUIコードを即生成", "official_url": "https://v0.dev/"},
    {"slug": "cursor", "name": "Cursor", "category": "Code Editor", "tagline": "プロジェクト全体を理解して自律的に実装するAIエディタ", "official_url": "https://www.cursor.com/"},
    {"slug": "github-copilot", "name": "GitHub Copilot", "category": "Code Generator", "tagline": "開発ワークフローに統合された定番AIペアプログラマー", "official_url": "https://github.com/features/copilot"},
    {"slug": "notion-ai", "name": "Notion AI", "category": "Productivity", "tagline": "ドキュメント作成・議事録要約・タスク整理を自動化", "official_url": "https://www.notion.so/product/ai"},
    {"slug": "canva-ai", "name": "Canva AI", "category": "Design", "tagline": "SNS画像・プレゼン資料のデザインをAIで瞬時に生成", "official_url": "https://www.canva.com/"},
    {"slug": "jasper", "name": "Jasper AI", "category": "Copywriting", "tagline": "マーケティング・広告文に特化したビジネス向けAI", "official_url": "https://www.jasper.ai/"},
    {"slug": "copy-ai", "name": "Copy.ai", "category": "Copywriting", "tagline": "セールスコピーやSNS投稿案を量産するライティングAI", "official_url": "https://www.copy.ai/"},
    {"slug": "descript", "name": "Descript", "category": "Video Editor", "tagline": "文字起こしテキストを編集するだけで動画カットが完了", "official_url": "https://www.descript.com/"},
    {"slug": "heygen", "name": "HeyGen", "category": "Avatar Generator", "tagline": "リアルなAIアバターが自然な口パクで話す動画を作成", "official_url": "https://www.heygen.com/"},
]

def build_official_cta(item):
    return f"""
    <div class="cta-box">
        <div class="cta-box-text">
            <strong>{item['name']} 公式サイトをチェックする</strong>
            <span>{item['tagline']}</span>
        </div>
        <a href="{item['official_url']}" target="_blank" rel="noopener" class="cta-btn">{item['name']} 公式サイトへ →</a>
    </div>
    """

def extract_body(html_text):
    if "<!-- BODY_START -->" in html_text and "<!-- BODY_END -->" in html_text:
        s = html_text.find("<!-- BODY_START -->") + len("<!-- BODY_START -->")
        e = html_text.find("<!-- BODY_END -->")
        return html_text[s:e].strip()
    if '<div class="article-body">' in html_text:
        s = html_text.find('<div class="article-body">') + len('<div class="article-body">')
        e = html_text.find("</div>", s)
        return html_text[s:e].strip()
    return None

# ==========================================
# 1. 毎日の自動ブログ記事生成＆PR枠更新
# ==========================================
today_str = datetime.now().strftime("%Y-%m-%d")
blog_filename = f"post-{today_str}.html"
blog_filepath = os.path.join(BLOG_DIR, blog_filename)

blog_template = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | AI Tech Hub</title>
    {css}
</head>
<body>
    <header class="navbar">
        <div class="navbar-inner">
            <a href="../index.html" class="brand"><span>AI</span> AI Tech Hub</a>
            <nav><a href="../index.html">トップ一覧へ</a></nav>
        </div>
    </header>

    <main class="container" style="padding-top: 32px;">
        <div class="breadcrumb"><a href="../index.html">ホーム</a> &gt; <span>トレンド記事</span></div>
        <article class="article-card">
            <div class="pr-notice">※当サイトはプロモーション（アフィリエイト広告）を含みます。</div>
            <header class="article-header">
                <span class="badge">AI TREND REPORT</span>
                <h1>{title}</h1>
                <div class="article-meta">公開日: {date} ・ 読了目安: 約3分</div>
            </header>
            <div class="article-body">
                <!-- BODY_START -->
                {body}
                <!-- BODY_END -->
            </div>
            {pr_section}
        </article>
    </main>

    <footer class="footer">
        &copy; 2026 AI Tech Hub - Automated AI Knowledge Base
    </footer>
</body>
</html>"""

if not os.path.exists(blog_filepath):
    print(f"本日のブログ記事を生成中 ({today_str})...", flush=True)
    blog_prompt = f"""今日は {today_str} です。最新のAIトレンドや実務での活用法に関する読み応えのある解説ブログ記事を日本語で1,400〜1,800文字程度で作成してください。
以下のルールを厳守してください：
- 1行目に「TITLE: 魅力的な記事タイトル」を出力する
- 2行目以降にHTML本文のみを出力する（```html などのマークダウン記法は一切使わない）
- 見出し（h2, h3）、段落（p）、箇条書き（ul, li）、比較やまとめの表（table, tr, th, td）、重要ポイントの引用枠（blockquote）をバランスよく使い、読みやすく構成する"""
    try:
        text = generate_with_retry(blog_prompt)
        text = text.replace("```html", "").replace("```", "").strip()
        lines = text.split("\n")
        title = f"{today_str} のAI・テクノロジー最新情報"
        body_lines = []

        for line in lines:
            if line.startswith("TITLE:"):
                title = line.replace("TITLE:", "").strip()
            else:
                body_lines.append(line)

        body_html = "\n".join(body_lines)
        full_blog_html = blog_template.format(
            title=title,
            date=today_str,
            body=body_html,
            css=COMMON_CSS,
            pr_section=build_pr_section("blog"),
        )
        with open(blog_filepath, "w", encoding="utf-8") as f:
            f.write(full_blog_html)
        print(f"ブログ記事を作成しました: {title}", flush=True)
        time.sleep(2)
    except Exception as e:
        print(f"ブログ生成エラー: {e}", flush=True)
else:
    print(f"本日のブログ記事（{blog_filename}）はすでに作成済みです。", flush=True)
    if REFRESH_EXISTING_LAYOUT:
        for bf in os.listdir(BLOG_DIR):
            if not bf.endswith(".html"):
                continue
            b_path = os.path.join(BLOG_DIR, bf)
            with open(b_path, "r", encoding="utf-8") as f:
                old_html = f.read()
            body_extracted = extract_body(old_html)
            if body_extracted:
                s_t = old_html.find("<title>") + 7
                e_t = old_html.find("</title>")
                old_title = old_html[s_t:e_t].replace(" | AI Tech Hub", "") if s_t > 6 else bf
                d_label = bf.replace("post-", "").replace(".html", "")
                with open(b_path, "w", encoding="utf-8") as f:
                    f.write(blog_template.format(
                        title=old_title,
                        date=d_label,
                        body=body_extracted,
                        css=COMMON_CSS,
                        pr_section=build_pr_section("blog"),
                    ))

# ==========================================
# 2. AIツールデータベース（pSEO）の生成＆PR枠更新
# ==========================================
tool_template = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} の使い方・料金・特徴徹底レビュー | AI Tech Hub</title>
    {css}
</head>
<body>
    <header class="navbar">
        <div class="navbar-inner">
            <a href="index.html" class="brand"><span>AI</span> AI Tech Hub</a>
            <nav><a href="index.html">ツール一覧へ</a></nav>
        </div>
    </header>

    <main class="container" style="padding-top: 32px;">
        <div class="breadcrumb"><a href="index.html">ホーム</a> &gt; <span>{category}</span> &gt; <span>{name}</span></div>
        <article class="article-card">
            <div class="pr-notice">※当ページはプロモーション（アフィリエイト広告）を含みます。</div>
            <header class="article-header">
                <span class="badge">{category}</span>
                <h1>{name} の特徴・使い方・料金まとめ</h1>
                <div class="article-meta">{tagline}</div>
            </header>

            {cta_box}

            <div class="article-body">
                <!-- BODY_START -->
                {body}
                <!-- BODY_END -->
            </div>

            {cta_box}

            {pr_section}
        </article>

        {related_section}
    </main>

    <footer class="footer">
        &copy; 2026 AI Tech Hub - Automated AI Knowledge Base
    </footer>
</body>
</html>"""

def build_related_html(current_item):
    related = [
        t for t in TOOLS_DB
        if t["category"] == current_item["category"] and t["slug"] != current_item["slug"]
    ]
    if not related:
        related = [t for t in TOOLS_DB if t["slug"] != current_item["slug"]][:3]

    cards = ""
    for r in related[:3]:
        r_path = os.path.join(OUTPUT_DIR, f"{r['slug']}.html")
        is_live = os.path.exists(r_path)
        title_html = f"<a href='{r['slug']}.html'>{r['name']}</a>" if is_live else r["name"]
        pill = "<span class='status-pill status-live'>公開中</span>" if is_live else "<span class='status-pill status-pending'>準備中</span>"
        cards += f"""
        <div class="card">
            <div>
                <div class="card-top">
                    <span class="cat-tag">{r['category']}</span>
                    {pill}
                </div>
                <h3>{title_html}</h3>
                <p>{r['tagline']}</p>
            </div>
        </div>
        """
    return f"""
    <section>
        <h2 class="section-title">🔗 関連するおすすめAIツール</h2>
        <div class="grid">{cards}</div>
    </section>
    """

generated_tools = 0
for item in TOOLS_DB:
    if not item.get("slug"):
        continue
    file_path = os.path.join(OUTPUT_DIR, f"{item['slug']}.html")
    cta_html = build_official_cta(item)
    pr_html = build_pr_section(item["category"])
    related_html = build_related_html(item)

    if os.path.exists(file_path):
        if REFRESH_EXISTING_LAYOUT:
            with open(file_path, "r", encoding="utf-8") as f:
                existing_html = f.read()
            existing_body = extract_body(existing_html)
            if existing_body:
                refreshed_html = tool_template.format(
                    name=item["name"],
                    category=item["category"],
                    tagline=item["tagline"],
                    cta_box=cta_html,
                    body=existing_body,
                    pr_section=pr_html,
                    related_section=related_html,
                    css=COMMON_CSS,
                )
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(refreshed_html)
        continue

    if generated_tools >= MAX_TOOL_BATCH:
        continue

    print(f"ツールページ生成中 ({generated_tools + 1}/{MAX_TOOL_BATCH}): {item['name']}...", flush=True)
    prompt = f"""AIツール『{item['name']}』（カテゴリ: {item['category']} / 概要: {item['tagline']}）の詳しいレビュー・使い方ガイド記事を日本語で1,400〜1,800文字程度で作成してください。
以下のルールを厳守してください：
- HTML本文のみを出力する（```html などのマークダウン記法は一切使わない）
- 以下の構成とHTMLタグを使って読みやすく作成する：
  1. <h2>{item['name']}とは？（概要と注目される理由）</h2> と解説段落（p）
  2. <h2>主な機能と強み</h2> と箇条書きリスト（ul, li）
  3. <h2>料金プランの目安</h2> と比較テーブル（table, tr, th, td で無料プラン・有料プランの違いを整理）
  4. <h2>メリット・デメリット</h2>（h3 で分けて整理）
  5. <h2>具体的な活用シーン・実践プロンプト例</h2> と引用枠（blockquote で入力例を1つ提示）
  6. <h2>よくある質問（FAQ）</h2>（Q&Aを2つ）"""

    try:
        text = generate_with_retry(prompt)
        text = text.replace("```html", "").replace("```", "").strip()
        full_html = tool_template.format(
            name=item["name"],
            category=item["category"],
            tagline=item["tagline"],
            cta_box=cta_html,
            body=text,
            pr_section=pr_html,
            related_section=related_html,
            css=COMMON_CSS,
        )
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_html)
        generated_tools += 1
        time.sleep(2)
    except Exception as e:
        print(f"ツール生成エラー: {e}", flush=True)
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
        b_title = content[start:end].replace(" | AI Tech Hub", "") if start > 6 and end > start else bf
    blog_list_html += f"""
    <div class="blog-item">
        <span class="blog-date">{date_label}</span>
        <a href="blog/{bf}" style="font-weight: 700; font-size: 1.05rem;">{b_title}</a>
    </div>
    """

if not blog_list_html:
    blog_list_html = "<div class='blog-item'>まだ記事がありません。</div>"

index_items_html = ""
for item in TOOLS_DB:
    if not item.get("slug"):
        continue
    file_path = os.path.join(OUTPUT_DIR, f"{item['slug']}.html")
    is_live = os.path.exists(file_path)
    status_pill = "<span class='status-pill status-live'>✅ 公開中</span>" if is_live else "<span class='status-pill status-pending'>⏳ 順次生成中</span>"
    link = f"<a href='{item['slug']}.html'>{item['name']}</a>" if is_live else item["name"]
    index_items_html += f"""
    <div class="card">
        <div>
            <div class="card-top">
                <span class="cat-tag">{item['category']}</span>
                {status_pill}
            </div>
            <h3>{link}</h3>
            <p>{item['tagline']}</p>
        </div>
    </div>
    """

# トップページ下部にもおすすめサービスPR枠を配置（Audible / エックスサーバー / DMM FX）
top_pr_cards = ""
for k in ["audible", "xserver", "dmm_fx"]:
    p_item = AFFILIATE_ITEMS[k]
    top_pr_cards += f"""
    <div class="pr-card">
        <div class="pr-card-body">
            <span class="pr-tag">PR</span>
            <h4>{p_item['title']}</h4>
            <p>{p_item['desc']}</p>
        </div>
        <div class="pr-banner">
            {p_item['html']}
        </div>
    </div>
    """

index_template = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Tech Hub | 最新AIトレンド＆AIツール比較データベース</title>
    {css}
</head>
<body>
    <header class="navbar">
        <div class="navbar-inner">
            <a href="index.html" class="brand"><span>AI</span> AI Tech Hub</a>
            <nav style="font-size: 0.9rem; color: var(--muted);">毎日自動更新データベース</nav>
        </div>
    </header>

    <section class="hero">
        <div class="hero-inner">
            <h1>AI Tech Hub</h1>
            <p>最新のAI活用トレンド解説と、主要AIツールの機能・料金・実践プロンプトを網羅した自動更新ナレッジデータベース。</p>
        </div>
    </section>

    <main class="container">
        <section>
            <h2 class="section-title">📝 最新のAIトレンド解説記事</h2>
            <div class="blog-list">
                {blogs}
            </div>
        </section>

        <section>
            <h2 class="section-title">🛠️ AIツールデータベース一覧</h2>
            <div class="grid">
                {tools}
            </div>
        </section>

        <section class="pr-section">
            <h2 class="section-title">📢 ピックアップ・おすすめサービス（PR）</h2>
            <div class="pr-grid">
                {top_pr}
            </div>
            <div class="pr-wide-banner">
                {domain_banner}
            </div>
        </section>
    </main>

    <footer class="footer">
        &copy; 2026 AI Tech Hub - Automated AI Knowledge Base
    </footer>
</body>
</html>"""

index_html = index_template.format(
    blogs=blog_list_html,
    tools=index_items_html,
    top_pr=top_pr_cards,
    domain_banner=AFFILIATE_ITEMS["xserver_domain"]["html"],
    css=COMMON_CSS,
)

with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(index_html)
# ==========================================
# 5. Google検索用 sitemap.xml の自動生成
# ==========================================
base_url = "https://banjoblog.github.io/auto-blog"
urls = [f"{base_url}/"]

for bf in sorted(os.listdir(BLOG_DIR)):
    if bf.endswith(".html"):
        urls.append(f"{base_url}/blog/{bf}")

for item in TOOLS_DB:
    if item.get("slug") and os.path.exists(os.path.join(OUTPUT_DIR, f"{item['slug']}.html")):
        urls.append(f"{base_url}/{item['slug']}.html")

sitemap_items = "\n".join([f"  <url><loc>{u}</loc><lastmod>{today_str}</lastmod></url>" for u in urls])
sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{sitemap_items}
</urlset>"""

with open(os.path.join(OUTPUT_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
    f.write(sitemap_xml)
print("すべてのビルド処理が正常に完了しました。", flush=True)
# ==========================================
# 4. Google Search Console 所有権確認ファイルの自動生成
# ==========================================
gsc_filename = "googlee870bb95f36fa43e.html"
with open(os.path.join(OUTPUT_DIR, gsc_filename), "w", encoding="utf-8") as f:
    f.write(f"google-site-verification: {gsc_filename}")
