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
        ((15, 23, 42), (49, 46, 129)),   # ディープネイビー × インディゴ
        ((20, 30, 48), (36, 59, 85)),    # ロイヤルダークブルー
        ((28, 25, 23), (87, 37, 45)),    # ダーククリムゾン
        ((17, 24, 39), (19, 78, 74)),    # ダークティール
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
        [261.63, 329.63, 392.00, 493.88],  # Cmaj7
        [220.00, 261.63, 329.63, 392.00],  # Am7
        [174.61, 220.00, 261.63, 329.63],  # Fmaj7
        [196.00, 246.94, 293.66, 349.23],  # G7
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

# ==========================================
# 1. 環境変数・APIキーの読み込み
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN")

TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET")
TIKTOK_REFRESH_TOKEN = os.environ.get("TIKTOK_REFRESH_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 中身の濃い雑学台本の生成（ジャンルランダム抽選でネタ被り防止）
# ==========================================
print("高クオリティ雑学動画台本を生成中...")

genres = [
    "日本の老舗企業や身近な商品の意外な誕生秘話・社名の由来",
    "人体の驚くべき仕組みや脳の錯覚・睡眠の科学",
    "戦国時代・幕末・明治の教科書に載っていない歴史の裏話",
    "身近な法律・交通ルール・お金や硬貨の意外な雑学",
    "スーパーやコンビニの食品・料理の知られざる秘密",
    "深海生物や昆虫・動物の常識外れな生態（ヒクイドリは除外）",
    "宇宙・気象・地球の異常現象に関する驚くべき数値データ",
    "心理学・行動経済学の日常で使える意外な法則",
    "日本語の語源・漢字の成り立ち・方言の意外な由来",
    "世界の変わった文化・建築・世界遺産の裏トリビア",
    "スポーツ・オリンピックのルール変更や伝説の記録の裏話",
    "医療・薬・健康に関する意外と知られていない事実",
]
selected_genre = random.choice(genres)
print(f"今回の抽選ジャンル: {selected_genre}")

prompt = f"""
YouTube ShortsとTikTok向けの、知的好奇心をくすぐる具体的な雑学・豆知識の台本を1つ作成してください。

【今回の指定ジャンル】
「{selected_genre}」のテーマから、あまり知られていないニッチで面白い具体的なトリビアを1つ選んでください。

【絶対に守るルール】
1. 抽象的な表現は禁止。必ず「具体的な生物名・地名・歴史上の人物名・企業名・数値」を台本の中に明記すること。
2. ありきたりな定番雑学（ヒクイドリ、サメ、バナナ、エッフェル塔など）は避け、視聴者が「へぇ〜！」と驚く具体的な事実とオチまで完結させること。
3. 必ず以下のJSON形式のみで出力すること（マークダウン記法は不要）。

{{
  "title": "画面上部に常時表示する短い見出し（18文字以内・ハッシュタグなし）",
  "description": "動画の説明文と関連ハッシュタグ4〜5個（#雑学 #豆知識 など）",
  "search_keyword": "背景動画検索用のシンプルな英単語1語（例: food, history, city, brain, money, space）",
  "script": [
    "1文目：視聴者を引き込む問いかけやフック（20〜28文字）",
    "2文目：結論となる具体的な名前・答えの提示（22〜32文字）",
    "3文目：なぜそうなのかの驚きの理由・具体例1（25〜35文字）",
    "4文目：さらに深い裏話や数値などの具体例2（25〜35文字）",
    "5文目：印象に残るまとめ・一言オチ（20〜28文字）"
  ]
}}
"""

response = None
for model in ["gemini-3.5-flash-lite", "gemini-3.8-flash"]:
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=1.2,
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
description = data["description"]
search_keyword = data["search_keyword"]
script_lines = data["script"]
print(f"生成完了: {title} (検索ワード: {search_keyword})")
for idx, s in enumerate(script_lines, 1):
    print(f"  台本{idx}: {s}")

# ==========================================
# 3. 背景動画の取得（Pexels または 自動アニメーション背景）
# ==========================================
bg_video_path = "bg_video.mp4"
has_bg_video = False

if PEXELS_API_KEY:
    print("Pexelsから背景動画を検索中...")
    headers = {"Authorization": PEXELS_API_KEY}
    encoded_kw = urllib.parse.quote(search_keyword)
    PEXELS_BASE = clean_url("https://" + "api." + "pexels." + "com/videos/search")
    
    for query_url in [
        f"{PEXELS_BASE}?query={encoded_kw}&orientation=portrait&per_page=10",
        f"{PEXELS_BASE}?query=nature&orientation=portrait&per_page=10",
    ]:
        r = requests.get(query_url, headers=headers)
        if r.status_code != 200:
            print(f"Pexels API警告 (Status {r.status_code}): {r.text}")
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
            print("Pexelsから背景動画を取得しました。")
            break

# ==========================================
# 4. 音声生成（Edge-TTS）＆ BGM・動画合成（Pillow + MoviePy）
# ==========================================
print("音声とBGM・字幕動画を合成中...")
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
    if bg_clip.duration < total_duration:
        bg_clip = bg_clip.loop(duration=total_duration)
    else:
        bg_clip = bg_clip.subclip(0, total_duration)

    bg_clip = bg_clip.resize(height=1920)
    if bg_clip.w > 1080:
        bg_clip = bg_clip.crop(x_center=bg_clip.w / 2, width=1080)
    else:
        bg_clip = bg_clip.resize(width=1080)
    
    dark_overlay = ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=total_duration).set_opacity(0.35)
    base_layers = [bg_clip, dark_overlay]
else:
    print("グラデーション＋パーティクルアニメーション背景を生成中...")
    base_layers = [make_animated_bg(total_duration)]

header_clip = make_header_clip(title, total_duration)

output_video = "output_short.mp4"
final_video = CompositeVideoClip(base_layers + [header_clip] + clips).set_audio(final_audio)
final_video.write_videofile(output_video, fps=30, codec="libx264", audio_codec="aac")

# ==========================================
# 5. YouTube Shorts へアップロード
# ==========================================
if YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN:
    try:
        print("YouTube Shorts へアップロード中...")
        TOKEN_URI = clean_url("https://" + "oauth2." + "googleapis." + "com/token")
        creds = Credentials(
            token=None,
            refresh_token=YT_REFRESH_TOKEN,
            token_uri=TOKEN_URI,
            client_id=YT_CLIENT_ID,
            client_secret=YT_CLIENT_SECRET,
        )
        youtube = build("youtube", "v3", credentials=creds)
        body = {
            "snippet": {
                "title": f"{title} #Shorts",
                "description": description,
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

# ==========================================
# 6. TikTok へアップロード（Direct Post 優先 ＋ 完了までステータス追跡）
# ==========================================
if TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET and TIKTOK_REFRESH_TOKEN:
    try:
        print("TikTok アクセストークンを更新中...")
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
        print(f"TikTok 動画アップロード初期化中... (サイズ: {video_size} bytes)")

        # まずはプロフィール直接投稿（Direct Post）を試行（video.publishスコープ有効時に動作）
        TIKTOK_DIRECT_URL = clean_url("https://" + "open." + "tiktokapis." + "com/v2/post/publish/video/init/")
        init_res = requests.post(
            TIKTOK_DIRECT_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "post_info": {
                    "title": f"{title} {description}"[:150],
                    "privacy_level": "SELF_ONLY", # 本番審査通過後は "PUBLIC_TO_EVERYONE" に変更
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

        # Direct Post 権限がない場合は Inbox（受信トレイ）送信にフォールバック
        if not init_res.get("data", {}).get("upload_url"):
            print(f"Direct Post スキップ ({init_res.get('error', {}).get('message', '')}) -> Inbox送信へ切替")
            TIKTOK_INBOX_URL = clean_url("https://" + "open." + "tiktokapis." + "com/v2/post/publish/inbox/video/init/")
            init_res = requests.post(
                TIKTOK_INBOX_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": video_size,
                        "chunk_size": video_size,
                        "total_chunk_count": 1,
                    }
                },
            ).json()

        upload_url = init_res.get("data", {}).get("upload_url")
        publish_id = init_res.get("data", {}).get("publish_id")
        if not upload_url:
            raise RuntimeError(f"TikTok 初期化失敗: {init_res}")

        print("TikTok へ動画データを送信中...")
        with open(output_video, "rb") as vf:
            video_bytes = vf.read()

        put_res = requests.put(
            upload_url,
            headers={
                "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
                "Content-Type": "video/mp4",
            },
            data=video_bytes,
        )
        print(f"TikTok データ送信完了 (Status: {put_res.status_code}, Publish ID: {publish_id})")

        # 処理完了（SEND_TO_USER_INBOX / PUBLISH_COMPLETE / FAILED）まで最大30秒追跡
        STATUS_URL = clean_url("https://" + "open." + "tiktokapis." + "com/v2/post/publish/status/fetch/")
        for check_i in range(6):
            time.sleep(5)
            status_res = requests.post(
                STATUS_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"publish_id": publish_id},
            ).json()
            st = status_res.get("data", {}).get("status")
            print(f"TikTok 処理ステータス ({check_i+1}/6): {status_res}")
            if st in ["SEND_TO_USER_INBOX", "PUBLISH_COMPLETE", "FAILED"]:
                break

    except Exception as e:
        print(f"TikTok アップロードエラー: {e}")
