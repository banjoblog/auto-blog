import os
import json
import urllib.request
import xml.etree.ElementTree as ET

WEIGHTS_FILE = "genre_weights.json"

GENRE_KEYWORDS = {
    "宇宙・惑星・気象": ["宇宙", "惑星", "地球", "太陽", "月", "星", "NASA", "気象", "天気", "雲", "雷", "重力", "ブラックホール"],
    "人体の仕組み・脳科学・睡眠": ["人体", "脳", "睡眠", "心臓", "血液", "筋肉", "骨", "目", "耳", "夢", "記憶", "ストレス", "体温"],
    "動物の生態・生物学": ["動物", "犬", "猫", "鳥", "魚", "虫", "昆虫", "サメ", "クジラ", "ペンギン", "恐竜", "生物", "進化"],
    "科学・物理・化学の法則": ["科学", "物理", "化学", "実験", "電気", "磁石", "光", "音", "水", "氷", "金属", "温度", "空気"],
    "心理学・行動経済学": ["心理", "行動", "人間関係", "錯覚", "バイアス", "印象", "無意識", "感情", "恋愛", "会話"],
    "食べ物・料理の科学": ["食べ物", "料理", "野菜", "果物", "肉", "魚", "コーヒー", "お茶", "塩", "砂糖", "栄養", "味覚"],
    "日本の企業・商品の誕生秘話": ["企業", "会社", "商品", "社名", "由来", "開発", "発明", "コンビニ", "メーカー", "ブランド"],
    "日本語の語源・漢字の由来": ["日本語", "語源", "漢字", "言葉", "意味", "ことわざ", "四字熟語", "敬語", "方言"],
}


def analyze_and_optimize():
    channel_id = (os.environ.get("YOUTUBE_CHANNEL_ID") or "").strip()
    if not channel_id:
        raise RuntimeError("YOUTUBE_CHANNEL_ID が設定されていません。GitHub Secrets に登録してください。")

    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as res:
        xml_data = res.read()

    root = ET.fromstring(xml_data)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "media": "http://search.yahoo.com/mrss/",
    }

    entries = root.findall("atom:entry", ns)
    if not entries:
        print("まだ投稿済み動画がありません。初期重み付けを保存します。")
        default_weights = {g: 1.0 for g in GENRE_KEYWORDS}
        with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_weights, f, ensure_ascii=False, indent=2)
        return

    genre_scores = {g: [] for g in GENRE_KEYWORDS}

    for entry in entries:
        title_el = entry.find("atom:title", ns)
        desc_el = entry.find(".//media:description", ns)
        stats_el = entry.find(".//media:statistics", ns)
        rating_el = entry.find(".//media:starRating", ns)

        title = title_el.text if (title_el is not None and title_el.text) else ""
        desc = desc_el.text if (desc_el is not None and desc_el.text) else ""
        text = f"{title} {desc}"

        views = int(stats_el.attrib.get("views", 0)) if stats_el is not None else 0
        likes = int(rating_el.attrib.get("count", 0)) if rating_el is not None else 0

        score = views + (likes * 15)

        for genre, keywords in GENRE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                genre_scores[genre].append(score)

    avg_scores = {
        genre: (sum(scores) / len(scores)) if scores else 0.0
        for genre, scores in genre_scores.items()
    }
    overall_avg = sum(avg_scores.values()) / len(avg_scores) if any(avg_scores.values()) else 0.0

    weights = {}
    for genre, avg in avg_scores.items():
        if overall_avg > 0 and avg > 0:
            ratio = avg / overall_avg
            weights[genre] = round(max(0.5, min(3.0, ratio)), 2)
        else:
            weights[genre] = 1.0

    with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(weights, f, ensure_ascii=False, indent=2)

    print(f"=== YouTube パフォーマンス分析＆ジャンル重み更新完了（対象動画: {len(entries)}本） ===")
    for g, w in sorted(weights.items(), key=lambda x: x[1], reverse=True):
        print(f"・{g}: 重み {w}倍 (平均スコア: {avg_scores[g]:.1f})")


if __name__ == "__main__":
    analyze_and_optimize()
