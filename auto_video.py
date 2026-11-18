import os
import re
import json
import time
import asyncio
import random
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import requests
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    CompositeVideoClip,
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
            print(f"重み付け抽選によりジャンル選択: {chosen}")
            return chosen
        except Exception as e:
            print(f"重み付け読み込みスキップ: {e}")
    return random.choice(default_genres)


def get_latest_long_video_url(channel_id):
    if not channel_id:
        return ""
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as res:
            xml_data = res.read()
        root = ET.fromstring(xml_data)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            vid_el = entry.find("yt:videoId", ns)
            title_txt = title_el.text if (title_el is not None and title_el.text) else ""
            if "#Shorts" not in title_txt and vid_el is not None and vid_el.text:
                return f"https://www.youtube.com/watch?v={vid_el.text}"
    except Exception as e:
        print(f"長尺動画URL取得スキップ: {e}")
    return ""


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN")
YOUTUBE_CHANNEL_ID = (os.environ.get("YOUTUBE_CHANNEL_ID") or "").strip()

client = genai.Client(api_key=GEMINI_API_KEY)
used_topics = load_used_topics()
ng_list_text = "、".join(used_topics[-80:]) if used_topics else "なし"

genres = [
    "科学・物理・化学の実験で証明されている驚くべき法則",
    "動物の生態・生物学で学術的に確立されている意外な能力",
    "宇宙・惑星・気象のNASAや天文台で観測されている確実な事実",
    "人体の仕組み・脳科学・睡眠に関する医学的に認められている雑学",
    "日本の老舗企業や有名商品の公式に公開されている誕生秘話・社名の由来",
    "心理学・行動経済学・お金の判断に関する有名な実験",
    "食べ物・料理の科学的な成分や調理のメカニズム",
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


fact_prompt = f"""
あなたは厳格な科学・雑学のファクトチェッカーです。
「{selected_genre}」のジャンルから、教科書・学術論文・公式発表で100%事実と証明されている「誰かに話したくなる雑学」を1つ厳選してください。

【使用禁止リスト（過去投稿済み）】
[{ng_list_text}]

【厳守ルール】
1. 都市伝説、俗説、国や時代によって変わる曖昧なルール、数字の計算ミスが起こりやすいネタは絶対に除外すること。
2. 「AだからBになる」という因果関係・メカニズムが100%論理的に破綻していない事実のみを選ぶこと。
3. 以下のJSON形式のみで出力すること。

{{
  "topic_keyword": "主役キーワード（10文字以内）",
  "verified_fact": "100%正確な結論と科学的・公式な理由（150文字以内）",
  "pexels_search_word": "背景映像用のシンプルな英単語1〜2語（例: night sky, ocean waves, coffee beans）"
}}
"""

fact_data = call_gemini_json(fact_prompt, temp=0.2)
topic_keyword = fact_data.get("topic_keyword", "雑学")
verified_fact = fact_data["verified_fact"]
pexels_query = fact_data.get("pexels_search_word", "abstract nature")

script_prompt = f"""
以下の【検証済みの事実】のみをベースにして、YouTubeショート・TikTokで最後まで見られる40秒前後の台本と投稿メタデータを作成してください。

【検証済みの事実】
{verified_fact}

【厳守ルール】
1. 検証済みの事実に書かれていない数字や嘘のエピソードを勝手に付け足さないこと。
2. 音声読み上げ（TTS）で不自然な漢字誤読が起きないよう、難読漢字はひらがな表記にすること。
3. `scenes` は5〜6シーンに分け、1シーンあたり15〜28文字のテンポ良い日本語にすること。
4. 最初のシーン（フック）は疑問形または衝撃の結論から入り、1秒目で視聴者を惹きつけること。
5. 以下のJSON形式のみで出力すること。

{{
  "title": "クリックしたくなる動画タイトル（32文字以内・#Shortsなし）",
  "description": "SEOを意識した動画説明文（120文字前後・ハッシュタグ3個含む）",
  "tags": ["雑学", "豆知識", "教育", "{topic_keyword}"],
  "pinned_comment": "視聴者がコメント欄に書き込みたくなる一言質問",
  "scenes": [
    {{"caption": "画面中央に出す短い字幕（18文字以内）", "narration": "読み上げ音声テキスト"}},
    {{"caption": "画面中央に出す短い字幕（18文字以内）", "narration": "読み上げ音声テキスト"}}
  ]
}}
"""

script_data = call_gemini_json(script_prompt, temp=0.4)
title = script_data["title"]
description = script_data["description"]
tags = script_data.get("tags", ["雑学", "豆知識"])
pinned_comment = script_data.get("pinned_comment", "知らなかった人は高評価で教えてください！")
scenes = script_data["scenes"]

long_video_url = get_latest_long_video_url(YOUTUBE_CHANNEL_ID)
if long_video_url:
    description = f"{description}\n\n▼作業用・睡眠用の雑学まとめ動画はこちら\n{long_video_url}"
    pinned_comment = f"{pinned_comment}\n\n▼聞き流し用の雑学まとめ動画はこちら！\n{long_video_url}"

bg_video_path = "bg_short.mp4"
headers = {"Authorization": PEXELS_API_KEY}
pexels_url = f"https://api.pexels.com/videos/search?query={pexels_query}&orientation=portrait&size=medium&per_page=5"
res_p = requests.get(pexels_url, headers=headers, timeout=20).json()
videos = res_p.get("videos", [])
if not videos:
    res_p = requests.get(
        "https://api.pexels.com/videos/search?query=nature&orientation=portrait&size=medium&per_page=5",
        headers=headers,
        timeout=20,
    ).json()
    videos = res_p.get("videos", [])

video_link = None
for v in videos:
    for vf in v.get("video_files", []):
        if vf.get("width", 0) >= 720 and vf.get("file_type") == "video/mp4":
            video_link = vf["link"]
            break
    if video_link:
        break
if not video_link and videos:
    video_link = videos[0]["video_files"][0]["link"]

with open(bg_video_path, "wb") as f:
    f.write(requests.get(video_link, timeout=60).content)


async def generate_tts(text, out_path):
    communicate = edge_tts.Communicate(text, "ja-JP-NanamiNeural", rate="+12%")
    await communicate.save(out_path)


def create_caption_image(text, out_path, width=1080, height=1920):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"
    font = ImageFont.truetype(font_path, 68)

    lines = []
    current = ""
    for ch in text:
        if len(current) >= 11:
            lines.append(current)
            current = ch
        else:
            current += ch
    if current:
        lines.append(current)

    line_height = 88
    total_h = len(lines) * line_height
    start_y = (height - total_h) // 2

    pad_y = 35
    draw.rectangle(
        [(60, start_y - pad_y), (width - 60, start_y + total_h + pad_y)],
        fill=(0, 0, 0, 175),
    )

    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        y = start_y + idx * line_height
        for dx, dy in [(-3, -3), (3, -3), (-3, 3), (3, 3)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    img.save(out_path)


raw_bg = VideoFileClip(bg_video_path).resize((1080, 1920))
scene_clips = []
current_t = 0.0

for idx, sc in enumerate(scenes):
    audio_path = f"scene_{idx}.mp3"
    img_path = f"scene_{idx}.png"
    asyncio.run(generate_tts(sc["narration"], audio_path))
    audio_clip = AudioFileClip(audio_path)
    dur = audio_clip.duration + 0.15

    start_bg = current_t % max(1.0, raw_bg.duration - dur)
    if raw_bg.duration < dur:
        bg_sub = raw_bg.loop(duration=dur)
    else:
        bg_sub = raw_bg.subclip(start_bg, start_bg + dur)

    create_caption_image(sc["caption"], img_path)
    txt_clip = ImageClip(img_path).set_duration(dur)

    comp = CompositeVideoClip([bg_sub, txt_clip]).set_audio(audio_clip)
    scene_clips.append(comp)
    current_t += dur

final_video = concatenate_videoclips(scene_clips, method="compose")
output_mp4 = "short_output.mp4"
final_video.write_videofile(
    output_mp4,
    fps=30,
    codec="libx264",
    audio_codec="aac",
    threads=4,
    preset="ultrafast",
)

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
        "title": f"{title} #Shorts",
        "description": f"{description}\n\n#Shorts #雑学 #豆知識",
        "tags": tags,
        "categoryId": "27",
    },
    "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
}
media = MediaFileUpload(output_mp4, chunksize=-1, resumable=True, mimetype="video/mp4")
req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
res_yt = req.execute()
video_id = res_yt["id"]
print(f"YouTube Shorts 投稿完了！ Video ID: {video_id}")

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

if os.path.exists("post_tiktok.py") and os.environ.get("TIKTOK_REFRESH_TOKEN"):
    try:
        subprocess.run(["python", "post_tiktok.py", output_mp4, title], check=True)
    except Exception as te:
        print(f"TikTok 投稿エラー: {te}")

save_used_topics([topic_keyword])
