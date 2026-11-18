import os
import json
import time
import asyncio
import random
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip,
    ImageClip,
    concatenate_videoclips,
)
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

HISTORY_FILE = "used_topics.json"
WEIGHTS_FILE = "genre_weights.json"


def load_used_topics():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def save_used_topics(new_items):
    topics = load_used_topics()
    for item in new_items:
        item = item.strip()
        if item and item not in topics:
            topics.append(item)
    topics = topics[-250:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)


def pick_weighted_genre(default_genres):
    if os.path.exists(WEIGHTS_FILE):
        try:
            with open(WEIGHTS_FILE, "r", encoding="utf-8") as f:
                weights_map = json.load(f)
            weights = []
            for g in default_genres:
                matched_w = 1.0
                for key, w in weights_map.items():
                    if key.split("・")[0] in g:
                        matched_w = float(w)
                        break
                weights.append(matched_w)
            chosen = random.choices(default_genres, weights=weights, k=1)[0]
            print(f"重み付け抽選により長尺ジャンル選択: {chosen}")
            return chosen
        except Exception as e:
            print(f"重み付け読み込みスキップ（通常ランダムを使用）: {e}")
    return random.choice(default_genres)


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)
used_topics = load_used_topics()
ng_list_text = "、".join(used_topics[-80:]) if used_topics else "なし"

genres = [
    "宇宙・惑星・気象のNASAや天文台で観測されている確実な事実",
    "人体の仕組み・脳科学・睡眠に関する医学的に認められている雑学",
    "動物の生態・生物学で学術的に確立されている意外な能力",
    "科学・物理・化学の実験で証明されている驚くべき法則",
    "心理学・行動経済学の教科書に載っている有名な実験",
    "食べ物・料理の科学的な成分や調理のメカニズム",
    "日本の老舗企業や有名商品の公式に公開されている誕生秘話・社名の由来",
    "日本語の語源・漢字の成り立ち・身近な言葉の意外な由来",
]
selected_genre = pick_weighted_genre(genres)


def call_gemini_json(prompt_text, temp=0.3):
    for model in ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]:
        for attempt in range(3):
            try:
                res = client.models.generate_content(
                    model=model,
                    contents=prompt_text,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=temp,
                    ),
                )
                return json.loads(res.text)
            except Exception as e:
                print(f"{model} エラー、リトライ ({attempt+1}/3): {e}")
                time.sleep(8)
    raise RuntimeError("Geminiでの生成に失敗しました。")


# ステージ1：オムニバス形式（5選）の100%正確なファクト抽出
fact_prompt = f"""
あなたは厳格な科学・雑学のファクトチェッカーです。
「{selected_genre}」のジャンルから、100%事実と証明されている「誰かに話したくなる厳選雑学」を5つ選んでください。

【使用禁止リスト（過去投稿済み）】
[{ng_list_text}]

【厳守ルール】
1. 都市伝説や俗説は絶対に除外し、教科書・学術論文・公式資料で裏付けられている確実な事実のみを選ぶこと。
2. 5つそれぞれ異なる切り口の雑学にすること。
3. 以下のJSON形式のみで出力すること。

{{
  "theme_title": "動画全体のテーマ（例：宇宙の常識が覆る驚きの雑学5選）",
  "facts": [
    {{
      "keyword": "主役キーワード（10文字以内）",
      "headline": "第1選の見出し（20文字以内）",
      "verified_detail": "100%正確な事実とメカニズムの詳しい解説（220文字前後）"
    }}
  ]
}}
"""

fact_data = call_gemini_json(fact_prompt, temp=0.2)
theme_title = fact_data["theme_title"]
facts_list = fact_data["facts"][:5]

# ステージ2：スライド解説動画用の台本・SEO・チャプター生成
script_prompt = f"""
以下の【検証済みの5つの事実】を元に、聞き流し・睡眠用・作業用としても最後まで見られるYouTube長尺解説動画（16:9横画面スライド形式）の構成データを作成してください。

【動画テーマ】{theme_title}
【検証済みの事実】
{json.dumps(facts_list, ensure_ascii=False)}

【厳守ルール】
1. 事実を曲げず、丁寧で知的なナレーション（です・ます調）にすること。
2. 各セクションは「導入（オープニング）」＋「5つの解説」＋「まとめ（エンディング）」の計7パートにすること。
3. 以下のJSON形式のみで出力すること。

{{
  "video_title": "検索とクリックに強い動画タイトル（36文字以内）",
  "description": "SEOを意識した動画概要文（200文字前後）",
  "tags": ["雑学", "豆知識", "聞き流し", "教養", "睡眠用"],
  "pinned_comment": "視聴者にコメントを促す質問文",
  "chapters": [
    {{
      "section_label": "オープニング / 第1選〜第5選 / まとめ",
      "slide_heading": "スライド上部の見出し（22文字以内）",
      "slide_bullets": ["要点1（24文字以内）", "要点2（24文字以内）", "要点3（24文字以内）"],
      "narration": "ゆっくり丁寧に読み上げる解説ナレーション（220〜300文字）"
    }}
  ]
}}
"""

script_data = call_gemini_json(script_prompt, temp=0.4)
video_title = script_data["video_title"]
description = script_data["description"]
tags = script_data.get("tags", ["雑学", "聞き流し", "教養"])
pinned_comment = script_data.get("pinned_comment", "一番驚いた雑学は何番でしたか？コメント欄で教えてください！")
chapters = script_data["chapters"]


def create_slide_image(label, heading, bullets, out_path, width=1920, height=1080):
    img = Image.new("RGB", (width, height), (18, 24, 38))
    draw = ImageDraw.Draw(img)

    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"

    font_label = ImageFont.truetype(font_path, 36)
    font_head = ImageFont.truetype(font_path, 64)
    font_body = ImageFont.truetype(font_path, 48)

    # 上部アクセントバーとカード枠
    draw.rectangle([(80, 70), (width - 80, height - 70)], fill=(28, 36, 56), outline=(70, 130, 220), width=4)
    draw.rectangle([(120, 110), (480, 175)], fill=(70, 130, 220))
    draw.text((145, 120), label[:16], font=font_label, fill=(255, 255, 255))

    # 見出し
    draw.text((120, 220), heading[:24], font=font_head, fill=(255, 230, 120))
    draw.line([(120, 320), (width - 120, 320)], fill=(90, 110, 150), width=3)

    # 箇条書きポイント
    y_pos = 390
    for b in bullets[:4]:
        draw.text((140, y_pos), f"・ {b[:28]}", font=font_body, fill=(240, 245, 255))
        y_pos += 140

    img.save(out_path)


async def generate_tts(text, out_path):
    communicate = edge_tts.Communicate(text, "ja-JP-KeitaNeural", rate="+5%")
    await communicate.save(out_path)


clips = []
timestamp_lines = ["0:00 オープニング"]
elapsed_sec = 0.0

for idx, ch in enumerate(chapters):
    audio_path = f"long_ch_{idx}.mp3"
    slide_path = f"long_slide_{idx}.png"

    asyncio.run(generate_tts(ch["narration"], audio_path))
    audio_clip = AudioFileClip(audio_path)
    dur = audio_clip.duration + 0.5

    if idx > 0:
        mins = int(elapsed_sec // 60)
        secs = int(elapsed_sec % 60)
        timestamp_lines.append(f"{mins}:{secs:02d} {ch['slide_heading']}")

    create_slide_image(
        ch.get("section_label", f"チャプター {idx+1}"),
        ch["slide_heading"],
        ch.get("slide_bullets", []),
        slide_path,
    )
    img_clip = ImageClip(slide_path).set_duration(dur).set_audio(audio_clip)
    clips.append(img_clip)
    elapsed_sec += dur

final_video = concatenate_videoclips(clips, method="compose")
output_mp4 = "long_output.mp4"
final_video.write_videofile(
    output_mp4,
    fps=24,
    codec="libx264",
    audio_codec="aac",
    threads=4,
    preset="ultrafast",
)

full_description = f"{description}\n\n【目次】\n" + "\n".join(timestamp_lines) + "\n\n#雑学 #聞き流し #教養"

creds = Credentials(
    token=None,
    refresh_token=YT_REFRESH_TOKEN,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=YT_CLIENT_ID,
    client_secret=YT_CLIENT_SECRET,
)
youtube = build("youtube", "v3", credentials=creds)

body = {
    "snippet": {
        "title": video_title,
        "description": full_description,
        "tags": tags,
        "categoryId": "27",
    },
    "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
}
media = MediaFileUpload(output_mp4, chunksize=-1, resumable=True, mimetype="video/mp4")
res_yt = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
video_id = res_yt["id"]
print(f"YouTube 長尺解説動画 投稿完了！ Video ID: {video_id}")

try:
    youtube.commentThreads().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {"snippet": {"textOriginal": pinned_comment}},
            }
        },
    ).execute()
    print("YouTube エンゲージメントコメント投稿完了！")
except Exception as ce:
    print(f"コメント投稿スキップ: {ce}")

used_keywords = [f.get("keyword", "") for f in facts_list if f.get("keyword")]
save_used_topics(used_keywords)
