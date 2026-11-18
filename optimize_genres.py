import os
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

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

def get_youtube_client():
    creds = Credentials(
        token=None,
        refresh_token=os.environ.get("YT_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("YT_CLIENT_ID"),
        client_secret=os.environ.get("YT_CLIENT_SECRET"),
    )
    return build("youtube", "v3", credentials=creds)

def analyze_and_optimize():
    youtube = get_youtube_client()

    # 1. 自分のチャンネルのアップロード済み動画リストIDを取得（1ユニット）
    ch_res = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = ch_res.get("items", [])
    if not items:
        print("チャンネル情報が見つかりませんでした。")
        return

    uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # 2. 直近最大100本の動画IDを取得（1〜2ユニット）
    video_ids = []
    next_page_token = None
    while len(video_ids) < 100:
        pl_res = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=next_page_token
        ).execute()
        for item in pl_res.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
        next_page_token = pl_res.get("nextPageToken")
        if not next_page_token:
            break

    if not video_ids:
        print("まだ投稿済み動画がありません。初期重み付けを保存します。")
        default_weights = {g: 1.0 for g in GENRE_KEYWORDS}
        with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_weights, f, ensure_ascii=False, indent=2)
        return

    # 3. 動画ごとのタイトル・統計（再生数・高評価・コメント数）を一括取得（1〜2ユニット）
    genre_scores = {g: [] for g in GENRE_KEYWORDS}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        v_res = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(batch)
        ).execute()

        for v in v_res.get("items", []):
            title = v["snippet"]["title"]
            desc = v["snippet"].get("description", "")
            text = f"{title} {desc}"
            stats = v.get("statistics", {})

            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))

            # エンゲージメントを加味したパフォーマンススコア
            score = views + (likes * 15) + (comments * 30)

            for genre, keywords in GENRE_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    genre_scores[genre].append(score)

    # 4. 平均スコアから抽選重み（0.5 〜 3.0倍）を算出
    avg_scores = {}
    for genre, scores in genre_scores.items():
        avg_scores[genre] = (sum(scores) / len(scores)) if scores else 0.0

    overall_avg = sum(avg_scores.values()) / len(avg_scores) if any(avg_scores.values()) else 0.0

    weights = {}
    for genre, avg in avg_scores.items():
        if overall_avg > 0 and avg > 0:
            ratio = avg / overall_avg
            # 極端な偏りを防ぎつつ伸びるジャンルを最大3倍優遇
            weights[genre] = round(max(0.5, min(3.0, ratio)), 2)
        else:
            weights[genre] = 1.0

    with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(weights, f, ensure_ascii=False, indent=2)

    print("=== YouTube パフォーマンス分析＆ジャンル重み更新完了 ===")
    for g, w in sorted(weights.items(), key=lambda x: x[1], reverse=True):
        print(f"・{g}: 重み {w}倍 (平均スコア: {avg_scores[g]:.1f})")

if __name__ == "__main__":
    analyze_and_optimize()
