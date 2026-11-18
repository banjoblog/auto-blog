import os
import re
import glob
import json
import math
import time
import random
import asyncio
import urllib.parse
import requests
import edge_tts
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, VideoClip, CompositeVideoClip, ColorClip
from moviepy.audio.AudioClip import CompositeAudioClip, AudioClip
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

HISTORY_FILE = "used_topics.json"

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
    # 最新150件を保持
    topics = topics[-150:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)

def clean_url(u):
    m = re.search(r'\((https?://[^\)]+)\)', u)
    if m:
        return m.group(1)
    return u.replace("[", "").replace("]", "")

def get_jp_font(size):
    font_candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ] + glob.glob("/usr/share/fonts/**/*Noto*CJK*", recursive=True) + glob.glob("/usr/share/fonts/**/*Gothic*", recursive=True)
    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def make_animated_bg(total_duration):
    W, H = 1080, 1920
    palettes = [
        ((15, 23, 42), (49, 46, 129)),
        ((20, 30, 48), (36, 59, 85)),
        ((28, 25, 23), (87, 37, 45)),
        ((17, 24, 39), (19, 78, 74)),
    ]
    c1, c2 = random.choice(palettes)
    y_grid = np.linspace(0, 1, H)[:, None, None]
    grad = (np.array(c1) * (1 - y_grid) + np.array(c2) * y_grid).astype(np.uint8)
    base_bg = np.broadcast_to(grad, (H, W, 3)).copy()
    
    rng = np.random.default_rng(42)
    particles = []
    for _ in range(25):
        particles.append({
            "x": rng.uniform(0, W),
            "y": rng.uniform(0, H),
            "r": rng.uniform(8, 36),
            "speed_y": rng.uniform(30, 90),
            "phase": rng.uniform(0, 2 * math.pi),
            "alpha": rng.uniform(0.08, 0.25),
        })

    def make_frame(t):
        frame = base_bg.copy()
        img = Image.fromarray(frame).convert("RGBA")
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for p in particles:
            px = (p["x"] + math.sin(t * 1.2 + p["phase"]) * 40) % W
            py = (p["y"] - t * p["speed_y"]) % H
            r = p["r"]
            a = int(255 * p["alpha"])
            draw.ellipse([px - r, py - r, px + r, py + r], fill=(255, 255, 255, a))
        out = Image.alpha_composite(img, overlay).convert("RGB")
        return np.array(out)

    return VideoClip(make_frame, duration=total_duration)

def make_header_clip(title_text, total_duration):
    W, H = 1080, 1920
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_jp_font(56)
    
    wrapped = "\n".join([title_text[j:j+14] for j in range(0, len(title_text), 14)])
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=12, align="center")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    
    box_pad_x, box_pad_y = 50, 28
    box_w = min(W - 80, tw + box_pad_x * 2)
    box_h = th + box_pad_y * 2
    box_x = (W - box_w) // 2
    box_y = 220
    
    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=24,
        fill=(255, 215, 0, 245),
        outline=(0, 0, 0, 255),
        width=6,
    )
    
    tx = (W - tw) // 2
    ty = box_y + box_pad_y
    draw.multiline_text(
        (tx, ty),
        wrapped,
        font=font,
        fill=(15, 15, 15, 255),
        spacing=12,
        align="center",
    )
    return ImageClip(np.array(img)).set_start(0).set_duration(total_duration)

def make_subtitle_clip(text, duration, start_time):
    W, H = 1080, 1920
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_jp_font(66)
    
    wrapped = "\n".join([text[j:j+13] for j in range(0, len(text), 13)])
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=18, align="center")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) // 2
    y = (H - th) // 2 + 80
    
    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=8,
        stroke_fill=(0, 0, 0, 255),
        spacing=18,
        align="center",
    )
    return ImageClip(np.array(img)).set_start(start_time).set_duration(duration)

def make_bgm_clip(total_duration):
    chords = [
        [261.63, 329.63, 392.00, 493.88],
        [220.00, 261.63, 329.63, 392.00],
        [174.61, 220.00, 261.63, 329.63],
        [196.00, 246.94, 293.66, 349.23],
    ]

    def make_frame(t):
        t_arr = np.atleast_1d(t)
        idx = ((t_arr // 4.0).astype(int)) % len(chords)
        out = np.zeros_like(t_arr, dtype=np.float64)
        for c_i, freqs in enumerate(chords):
            mask = (idx == c_i)
            if np.any(mask):
                t_sub = t_arr[mask]
                wave = sum(np.sin(2 * np.pi * f * t_sub) for f in freqs) / len(freqs)
                out[mask] = wave * 0.055
        stereo = np.column_stack([out, out])
        return stereo[0] if np.isscalar(t) else stereo

    return AudioClip(make_frame, duration=total_duration, fps=44100)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID") or os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET") or os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN") or os.environ.get("YOUTUBE_REFRESH_TOKEN")
TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET")
TIKTOK_REFRESH_TOKEN = os.environ.get("TIKTOK_REFRESH_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)

used_topics = load_used_topics()
ng_list_text = "、".join(used_topics) if used_topics else "なし"
print(f"投稿済みNGワード数: {len(used_topics)}件")

genres = [
    "科学・物理・化学の教科書や実験で証明されている有名な法則や現象",
    "動物の生態・生物学で学術的に確立されている意外な能力",
    "宇宙・惑星・気象のNASAや天文台で観測されている確実なデータ",
    "人体の仕組み・脳科学・睡眠に関する医学的に広く認められている事実",
    "日本の老舗企業や有名商品の公式ホームページ等で公開されている誕生秘話・社名の由来",
    "日本の法律・道路交通法・硬貨や紙幣の公式仕様に基づく意外な雑学",
    "国語辞典や漢字辞典に載っている言葉の語源・漢字の成り立ち",
    "心理学・行動経済学の教科書に載っている有名な実験",
    "食品・魚・料理の科学的な成分や調理のメカニズム",
    "オリンピックやプロスポーツの公式ルールブックに記載されている意外な規定",
]
selected_genre = random.choice(genres)
print(f"今回の抽選ジャンル: {selected_genre}")

prompt = f"""
あなたは厳格なファクトチェッカー兼雑学ライターです。
YouTube ShortsとTikTok向けの、100%事実に裏付けられた雑学台本を1つ作成してください。

【今回の指定ジャンル】
「{selected_genre}」のテーマから、学術的・公式に事実と認められている具体的なトリビアを1つ選んでください。

【過去投稿済み・重複禁止リスト（絶対に使用禁止）】
以下のテーマ・対象・食材・生物・企業はすでに動画化済みのため、絶対に選ばないでください：
[玉ねぎ, ヒクイドリ, サメ, バナナ, エッフェル塔, {ng_list_text}]

【ハルシネーション防止ルール】
1. 都市伝説やデマは除外し、100%事実と断言できるネタだけを選ぶこと。
2. `topic_keyword` には、今回の雑学の主役となる単語（例：「ペンギン」「500円玉」「セロトニン」など）を1〜2語で明記すること。
3. 必ず以下のJSON形式のみで出力すること。

{{
  "fact_check_note": "100%事実である科学的・歴史的・公式な根拠",
  "topic_keyword": "今回の主役キーワード（履歴保存用・10文字以内）",
  "title": "画面上部に常時表示する短い見出し（18文字以内・ハッシュタグなし）",
  "description": "動画の説明文と関連ハッシュタグ4〜5個（#雑学 #豆知識 など）",
  "search_keyword": "背景動画検索用のシンプルな英単語1語",
  "script": [
    "1文目：視聴者を引き込む問いかけやフック（20〜28文字）",
    "2文目：結論となる具体的な名前・答えの提示（22〜32文字）",
    "3文目：なぜそうなのかの正確な理由・根拠1（25〜35文字）",
    "4文目：さらに納得する具体的な補足・根拠2（25〜35文字）",
    "5文目：印象に残るまとめ・一言オチ（20〜28文字）"
  ]
}}
"""

response = None
for model in ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]:
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.35,
                ),
            )
            break
        except Exception as e:
            print(f"{model} エラー、10秒待機してリトライ ({attempt+1}/3): {e}")
            time.sleep(10)
    if response:
        break

if not response:
    raise RuntimeError("すべてのGeminiモデルでの台本生成に失敗しました。")

data = json.loads(response.text)
title = data["title"]
topic_keyword = data.get("topic_keyword", title)
description = data["description"]
search_keyword = data["search_keyword"]
script_lines = data["script"]

print(f"生成完了: {title} (主役: {topic_keyword})")
save_used_topics([topic_keyword, title])

bg_video_path = "bg_video.mp4"
has_bg_video = False

if PEXELS_API_KEY:
    headers = {"Authorization": PEXELS_API_KEY}
    encoded_kw = urllib.parse.quote(search_keyword)
    PEXELS_BASE = clean_url("https://" + "api." + "pexels." + "com/videos/search")
    for query_url in [
        f"{PEXELS_BASE}?query={encoded_kw}&orientation=portrait&per_page=10",
        f"{PEXELS_BASE}?query=nature&orientation=portrait&per_page=10",
    ]:
        r = requests.get(query_url, headers=headers)
        if r.status_code != 200:
            break
        videos = r.json().get("videos", [])
        if videos:
            selected_video = random.choice(videos)
            video_files = selected_video["video_files"]
            hd_files = [f for f in video_files if f.get("width", 0) >= 720 and f.get("file_type") == "video/mp4"]
            download_url = hd_files[0]["link"] if hd_files else video_files[0]["link"]
            with open(bg_video_path, "wb") as f:
                f.write(requests.get(download_url).content)
            has_bg_video = True
            break

VOICE = "ja-JP-NanamiNeural"
clips = []
audio_clips = []
current_time = 0.0

async def generate_tts(text, filename):
    communicate = edge_tts.Communicate(text, VOICE, rate="+18%")
    await communicate.save(filename)

for i, line in enumerate(script_lines):
    audio_file = f"part_{i}.mp3"
    asyncio.run(generate_tts(line, audio_file))
    a_clip = AudioFileClip(audio_file)
    duration = a_clip.duration + 0.15
    audio_clips.append(a_clip.set_start(current_time))
    sub_clip = make_subtitle_clip(line, duration, current_time)
    clips.append(sub_clip)
    current_time += duration

total_duration = current_time
bgm_clip = make_bgm_clip(total_duration)
final_audio = CompositeAudioClip(audio_clips + [bgm_clip])

if has_bg_video:
    bg_clip = VideoFileClip(bg_video_path).without_audio()
    bg_clip = bg_clip.loop(duration=total_duration) if bg_clip.duration < total_duration else bg_clip.subclip(0, total_duration)
    bg_clip = bg_clip.resize(height=1920)
    bg_clip = bg_clip.crop(x_center=bg_clip.w / 2, width=1080) if bg_clip.w > 1080 else bg_clip.resize(width=1080)
    dark_overlay = ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=total_duration).set_opacity(0.35)
    base_layers = [bg_clip, dark_overlay]
else:
    base_layers = [make_animated_bg(total_duration)]

header_clip = make_header_clip(title, total_duration)
output_video = "output_short.mp4"
final_video = CompositeVideoClip(base_layers + [header_clip] + clips).set_audio(final_audio)
final_video.write_videofile(output_video, fps=30, codec="libx264", audio_codec="aac")

if YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN:
    try:
        TOKEN_URI = clean_url("https://" + "oauth2." + "googleapis." + "com/token")
        creds = Credentials(
            token=None,
            refresh_token=YT_REFRESH_TOKEN,
            token_uri=TOKEN_URI,
            client_id=YT_CLIENT_ID,
            client_secret=YT_CLIENT_SECRET,
        )
        youtube = build("youtube", "v3", credentials=creds)
        yt_description = f"{description}\n\n🤖 最新AIトレンド＆ツール比較データベース「AI Tech Hub」\nhttps://banjoblog.github.io/auto-blog/"
        body = {
            "snippet": {
                "title": f"{title} #Shorts",
                "description": yt_description,
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(output_video, chunksize=-1, resumable=True, mimetype="video/mp4")
        yt_res = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
        print(f"YouTube アップロード完了！ Video ID: {yt_res.get('id')}")
    except Exception as e:
        print(f"YouTube アップロードエラー: {e}")

if TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET and TIKTOK_REFRESH_TOKEN:
    try:
        TIKTOK_TOKEN_URL = clean_url("https://" + "open." + "tiktokapis." + "com/v2/oauth/token/")
        token_res = requests.post(
            TIKTOK_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": TIKTOK_CLIENT_KEY,
                "client_secret": TIKTOK_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": TIKTOK_REFRESH_TOKEN,
            },
        ).json()
        access_token = token_res.get("access_token")
        if not access_token:
            raise RuntimeError(f"TikTok トークン取得失敗: {token_res}")
        video_size = os.path.getsize(output_video)
        TIKTOK_DIRECT_URL = clean_url("https://" + "open." + "tiktokapis." + "com/v2/post/publish/video/init/")
        init_res = requests.post(
            TIKTOK_DIRECT_URL,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={
                "post_info": {
                    "title": f"{title} {description}"[:150],
                    "privacy_level": "SELF_ONLY",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": video_size,
                    "total_chunk_count": 1,
                },
            },
        ).json()
        if not init_res.get("data", {}).get("upload_url"):
            TIKTOK_INBOX_URL = clean_url("https://" + "open." + "tiktokapis." + "com/v2/post/publish/inbox/video/init/")
            init_res = requests.post(
                TIKTOK_INBOX_URL,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={"source_info": {"source": "FILE_UPLOAD", "video_size": video_size, "chunk_size": video_size, "total_chunk_count": 1}},
            ).json()
        upload_url = init_res.get("data", {}).get("upload_url")
        publish_id = init_res.get("data", {}).get("publish_id")
        if upload_url:
            with open(output_video, "rb") as vf:
                video_bytes = vf.read()
            requests.put(
                upload_url,
                headers={"Content-Range": f"bytes 0-{video_size - 1}/{video_size}", "Content-Type": "video/mp4"},
                data=video_bytes,
            )
            STATUS_URL = clean_url("https://" + "open." + "tiktokapis." + "com/v2/post/publish/status/fetch/")
            for _ in range(6):
                time.sleep(5)
                status_res = requests.post(
                    STATUS_URL,
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"publish_id": publish_id},
                ).json()
                if status_res.get("data", {}).get("status") in ["SEND_TO_USER_INBOX", "PUBLISH_COMPLETE", "FAILED"]:
                    break
    except Exception as e:
        print(f"TikTok アップロードエラー: {e}")
