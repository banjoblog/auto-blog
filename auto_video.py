import os
import json
import time
import asyncio
import random
import subprocess
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import requests
import edge_tts
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    ColorClip,
    CompositeVideoClip,
    CompositeAudioClip,
    concatenate_videoclips,
)
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
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
        long_keywords = ["5選", "まとめ", "解説", "聞き流し", "睡眠用", "選"]
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            vid_el = entry.find("yt:videoId", ns)
            title_txt = title_el.text if (title_el is not None and title_el.text) else ""
            if "#Shorts" not in title_txt and any(k in title_txt for k in long_keywords):
                if vid_el is not None and vid_el.text:
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
genre_badge = selected_genre.split("・")[0] + "の雑学"


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
1. 都市伝説、俗説、曖昧なルールは絶対に除外すること。
2. 「AだからBになる」という因果関係が100%論理的に破綻していない事実のみを選ぶこと。
3. 以下のJSON形式のみで出力すること。

{{
  "topic_keyword": "主役キーワード（10文字以内）",
  "verified_fact": "100%正確な結論と科学的・公式な理由（160文字以内）",
  "pexels_search_words": ["英語検索語1（例: galaxy stars）", "英語検索語2（例: earth space）", "英語検索語3（例: laboratory）", "英語検索語4（例: city night）"]
}}
"""

fact_data = call_gemini_json(fact_prompt, temp=0.2)
topic_keyword = fact_data.get("topic_keyword", "雑学")
verified_fact = fact_data["verified_fact"]
pexels_queries = fact_data.get("pexels_search_words", ["night sky", "ocean waves", "city lights", "abstract"])

script_prompt = f"""
以下の【検証済みの事実】のみをベースにして、YouTubeショート・TikTokでバズる「2人のテンポ良い掛け合い雑学台本（約35秒）」を作成してください。

【検証済みの事実】
{verified_fact}

【厳守ルール】
1. 検証済みの事実にない嘘のエピソードや数字は絶対に追加しないこと。
2. 難読漢字はTTS（音声合成）が読み間違えないよう、必ずひらがな表記にすること。
3. `cuts` は全部で **10〜12カット** に細かく分割し、1カットあたり **10〜18文字** の超短文にすること（2秒ごとに画面と声が変わるテンポにする）。
4. `speaker` は `"A"`（驚き・質問役の女性）と `"B"`（解説役の男性）を交互にテンポ良く入れ替えること。
5. `style` は各カットの重要度に合わせて `"hook"`（最初の衝撃フレーズ）、`"highlight"`（結論・重要ポイント）、`"normal"`（通常の会話）を指定すること。
6. 以下のJSON形式のみで出力すること。

{{
  "title": "クリックしたくなる動画タイトル（30文字以内・#Shortsなし）",
  "description": "SEOを意識した動画説明文（110文字前後）",
  "tags": ["雑学", "豆知識", "教育", "{topic_keyword}"],
  "pinned_comment": "コメント欄が盛り上がる一言質問",
  "cuts": [
    {{"speaker": "A", "style": "hook", "caption": "えっ、これマジなの！？", "narration": "えっ、これマジなの！？"}},
    {{"speaker": "B", "style": "normal", "caption": "実は科学で証明されてる", "narration": "実は科学で証明されてるんだ。"}}
  ]
}}
"""

script_data = call_gemini_json(script_prompt, temp=0.45)
title = script_data["title"]
description = script_data["description"]
tags = script_data.get("tags", ["雑学", "豆知識"])
pinned_comment = script_data.get("pinned_comment", "知らなかった人は高評価で教えてください！")
cuts = script_data["cuts"]

long_video_url = get_latest_long_video_url(YOUTUBE_CHANNEL_ID)
if long_video_url:
    description = f"{description}\n\n▼作業用・睡眠用の雑学まとめ動画はこちら\n{long_video_url}"
    pinned_comment = f"{pinned_comment}\n\n▼聞き流し用の雑学まとめ動画はこちら！\n{long_video_url}"


def download_multiple_pexels_videos(query_list, needed_count=6):
    downloaded = []
    if not PEXELS_API_KEY:
        return downloaded
    headers = {"Authorization": PEXELS_API_KEY}
    search_pool = list(query_list) + ["galaxy stars", "ocean waves", "city night", "abstract motion"]
    for q in search_pool:
        if len(downloaded) >= needed_count:
            break
        try:
            encoded_q = urllib.parse.quote(str(q))
            url = f"https://api.pexels.com/videos/search?query={encoded_q}&orientation=portrait&per_page=5"
            res = requests.get(url, headers=headers, timeout=20).json()
            for v in res.get("videos", []):
                if len(downloaded) >= needed_count:
                    break
                best_link = None
                for vf in v.get("video_files", []):
                    if vf.get("file_type") == "video/mp4" and vf.get("width", 0) >= 720:
                        best_link = vf.get("link")
                        break
                if not best_link and v.get("video_files"):
                    best_link = v["video_files"][0].get("link")
                if best_link:
                    fname = f"bg_clip_{len(downloaded)}.mp4"
                    r_vid = requests.get(best_link, timeout=60)
                    if r_vid.status_code == 200 and len(r_vid.content) > 50000:
                        with open(fname, "wb") as f:
                            f.write(r_vid.content)
                        downloaded.append(fname)
        except Exception as e:
            print(f"Pexels検索エラー ({q}): {e}")
    return downloaded


bg_files = download_multiple_pexels_videos(pexels_queries, needed_count=6)


def generate_sound_effects():
    subprocess.run(
        [
            FFMPEG_BIN, "-y", "-f", "lavfi",
            "-i", "sine=frequency=880:duration=0.18",
            "-af", "afade=t=out:st=0.05:d=0.13,volume=0.35",
            "se_pop.wav",
        ],
        check=False,
    )
    subprocess.run(
        [
            FFMPEG_BIN, "-y", "-f", "lavfi",
            "-i", "anoisesrc=d=0.14:c=white:r=44100:a=0.15",
            "-af", "bandpass=f=1200:width_type=h:w=800,afade=t=in:st=0:d=0.04,afade=t=out:st=0.06:d=0.08",
            "se_whoosh.wav",
        ],
        check=False,
    )


generate_sound_effects()


async def generate_tts(text, speaker, out_path):
    voice = "ja-JP-NanamiNeural" if speaker == "A" else "ja-JP-KeitaNeural"
    rate = "+18%" if speaker == "A" else "+15%"
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(out_path)


def create_tv_telop_overlay(text, speaker, style, badge_text, progress_ratio, out_path, width=1080, height=1920):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"

    font_badge = ImageFont.truetype(font_path, 38)
    font_role = ImageFont.truetype(font_path, 34)
    font_size = 86 if style in ("hook", "highlight") else 78
    font_main = ImageFont.truetype(font_path, font_size)

    draw.rectangle([(0, 0), (width, 280)], fill=(0, 0, 0, 145))
    draw.rectangle([(0, height - 280), (width, height)], fill=(0, 0, 0, 155))

    badge_w = 400
    badge_x = (width - badge_w) // 2
    draw.rounded_rectangle(
        [(badge_x, 105), (badge_x + badge_w, 172)],
        radius=34,
        fill=(20, 28, 45, 230),
        outline=(255, 215, 0, 230),
        width=3,
    )
    b_box = draw.textbbox((0, 0), badge_text, font=font_badge)
    bx = (width - (b_box[2] - b_box[0])) // 2
    draw.text((bx, 117), badge_text, font=font_badge, fill=(255, 225, 90, 255))

    role_text = "【疑問】" if speaker == "A" else "【事実】"
    role_bg = (220, 55, 80, 240) if speaker == "A" else (30, 130, 230, 240)
    r_w = 190
    r_x = (width - r_w) // 2
    role_y = 660
    draw.rounded_rectangle([(r_x, role_y), (r_x + r_w, role_y + 56)], radius=16, fill=role_bg)
    r_box = draw.textbbox((0, 0), role_text, font=font_role)
    draw.text(((width - (r_box[2] - r_box[0])) // 2, role_y + 8), role_text, font=font_role, fill=(255, 255, 255, 255))

    lines = []
    current = ""
    for ch in text:
        if len(current) >= 9:
            lines.append(current)
            current = ch
        else:
            current += ch
    if current:
        lines.append(current)

    line_height = font_size + 24
    total_h = len(lines) * line_height
    start_y = 750

    if style == "hook":
        draw.rounded_rectangle(
            [(50, start_y - 30), (width - 50, start_y + total_h + 30)],
            radius=24,
            fill=(210, 25, 45, 235),
            outline=(255, 255, 255, 255),
            width=5,
        )
        fill_color = (255, 255, 255, 255)
        stroke_color = (80, 0, 10, 255)
    elif style == "highlight":
        draw.rounded_rectangle(
            [(50, start_y - 30), (width - 50, start_y + total_h + 30)],
            radius=24,
            fill=(12, 16, 28, 220),
            outline=(255, 215, 0, 255),
            width=5,
        )
        fill_color = (255, 235, 60, 255)
        stroke_color = (0, 0, 0, 255)
    else:
        fill_color = (255, 255, 255, 255) if speaker == "B" else (140, 230, 255, 255)
        stroke_color = (0, 0, 0, 255)

    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font_main)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        y = start_y + idx * line_height
        draw.text((x + 6, y + 8), line, font=font_main, fill=(0, 0, 0, 200))
        for dx in range(-5, 6, 2):
            for dy in range(-5, 6, 2):
                draw.text((x + dx, y + dy), line, font=font_main, fill=stroke_color)
        draw.text((x, y), line, font=font_main, fill=fill_color)

    bar_margin = 90
    bar_w = width - (bar_margin * 2)
    bar_y = height - 190
    draw.rounded_rectangle([(bar_margin, bar_y), (bar_margin + bar_w, bar_y + 16)], radius=8, fill=(255, 255, 255, 70))
    fill_w = max(16, int(bar_w * progress_ratio))
    draw.rounded_rectangle([(bar_margin, bar_y), (bar_margin + fill_w, bar_y + 16)], radius=8, fill=(255, 215, 0, 255))

    img.save(out_path)


scene_clips = []
total_cuts = len(cuts)
loaded_bg_clips = []

for bf in bg_files:
    try:
        c = VideoFileClip(bf).without_audio()
        w, h = c.size
        target_ratio = 1080 / 1920
        if w / h > target_ratio:
            c = c.crop(x_center=w / 2, width=int(h * target_ratio))
        else:
            c = c.crop(y_center=h / 2, height=int(w / target_ratio))
        loaded_bg_clips.append(c.resize((1080, 1920)))
    except Exception:
        pass

for idx, cut in enumerate(cuts):
    audio_path = f"cut_{idx}.mp3"
    img_path = f"cut_{idx}.png"
    speaker = cut.get("speaker", "B")
    style = cut.get("style", "normal")

    asyncio.run(generate_tts(cut["narration"], speaker, audio_path))
    voice_clip = AudioFileClip(audio_path)
    dur = voice_clip.duration + 0.08

    if loaded_bg_clips:
        base_bg = loaded_bg_clips[(idx // 2) % len(loaded_bg_clips)]
        start_offset = (idx % 2) * 1.5
        if base_bg.duration < start_offset + dur:
            sub = base_bg.loop(duration=start_offset + dur).subclip(start_offset, start_offset + dur)
        else:
            sub = base_bg.subclip(start_offset, start_offset + dur)
        bg_sub = sub.resize(lambda t: 1.0 + 0.08 * (t / max(0.1, dur))).set_position(("center", "center"))
    else:
        bg_sub = ColorClip(size=(1080, 1920), color=(20, 28, 48), duration=dur)

    progress = (idx + 1) / total_cuts
    create_tv_telop_overlay(
        cut["caption"],
        speaker,
        style,
        genre_badge,
        progress,
        out_path=img_path,
    )
    txt_clip = ImageClip(img_path).set_duration(dur)

    audio_tracks = [voice_clip]
    if style in ("hook", "highlight") and os.path.exists("se_pop.wav"):
        audio_tracks.append(AudioFileClip("se_pop.wav"))
    elif idx > 0 and idx % 2 == 0 and os.path.exists("se_whoosh.wav"):
        audio_tracks.append(AudioFileClip("se_whoosh.wav"))

    comp_audio = CompositeAudioClip(audio_tracks)
    comp = CompositeVideoClip([bg_sub, txt_clip], size=(1080, 1920)).set_audio(comp_audio)
    scene_clips.append(comp)

final_video = concatenate_videoclips(scene_clips, method="compose")

bgm_path = "ambient_bgm.wav"
total_dur = final_video.duration
subprocess.run(
    [
        FFMPEG_BIN, "-y", "-f", "lavfi",
        "-i", f"anoisesrc=d={total_dur}:c=pink:r=44100:a=0.012",
        "-af", f"lowpass=f=260,afade=t=in:st=0:d=1,afade=t=out:st={max(0, total_dur - 1.5)}:d=1.5",
        bgm_path,
    ],
    check=False,
)
if os.path.exists(bgm_path):
    bgm_clip = AudioFileClip(bgm_path).set_duration(total_dur)
    final_video = final_video.set_audio(CompositeAudioClip([final_video.audio, bgm_clip]))

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
