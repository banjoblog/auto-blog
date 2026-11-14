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

def make_animated_bg_landscape(total_duration):
    """1920x1080 横画面用のパーティクル背景"""
    W, H = 1920, 1080
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
    for _ in range(30):
        particles.append({
            "x": rng.uniform(0, W),
            "y": rng.uniform(0, H),
            "r": rng.uniform(8, 32),
            "speed_y": rng.uniform(25, 75),
            "phase": rng.uniform(0, 2 * math.pi),
            "alpha": rng.uniform(0.08, 0.22),
        })

    def make_frame(t):
        frame = base_bg.copy()
        img = Image.fromarray(frame).convert("RGBA")
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for p in particles:
            px = (p["x"] + math.sin(t * 1.1 + p["phase"]) * 50) % W
            py = (p["y"] - t * p["speed_y"]) % H
            r = p["r"]
            a = int(255 * p["alpha"])
            draw.ellipse([px - r, py - r, px + r, py + r], fill=(255, 255, 255, a))
        out = Image.alpha_composite(img, overlay).convert("RGB")
        return np.array(out)

    return VideoClip(make_frame, duration=total_duration)

def make_header_clip_landscape(title_text, total_duration):
    """1920x1080 横画面上部タイトルバー"""
    W, H = 1920, 1080
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_jp_font(44)

    bbox = draw.textbbox((0, 0), title_text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    box_pad_x, box_pad_y = 48, 20
    box_w = min(W - 120, tw + box_pad_x * 2)
    box_h = th + box_pad_y * 2
    box_x = (W - box_w) // 2
    box_y = 50

    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=18,
        fill=(255, 215, 0, 240),
        outline=(0, 0, 0, 255),
        width=5,
    )

    tx = (W - tw) // 2
    ty = box_y + box_pad_y - 4
    draw.text((tx, ty), title_text, font=font, fill=(15, 15, 15, 255))
    return ImageClip(np.array(img)).set_start(0).set_duration(total_duration)

def make_subtitle_clip_landscape(text, duration, start_time):
    """1920x1080 横画面用テロップ（26文字で自動改行）"""
    W, H = 1920, 1080
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_jp_font(58)

    wrapped = "\n".join([text[j:j+26] for j in range(0, len(text), 26)])
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=18, align="center")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) // 2
    y = (H - th) // 2 + 40

    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=7,
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
                out[mask] = wave * 0.05
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

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 通常動画用（1分半〜2分・12文構成）ファクトチェック済み台本生成
# ==========================================
print("YouTube通常動画（横画面）用の解説台本を生成中...")

genres = [
    "科学・物理・化学の実験で証明されている驚くべき法則やメカニズム3選",
    "動物の生態・生物学で学術的に確立されている意外な能力3選",
    "宇宙・惑星・気象のNASAや天文台で観測されている確実な事実3選",
    "人体の仕組み・脳科学・睡眠に関する医学的に広く認められている雑学3選",
    "日本の老舗企業や有名商品の公式に公開されている誕生秘話・社名の由来3選",
    "日本の法律・道路交通法・硬貨や紙幣の公式仕様に基づく意外な雑学3選",
    "心理学・行動経済学の教科書に載っている有名な実験と日常への応用3選",
    "食べ物・野菜・魚・料理の科学的な成分や調理のメカニズム3選",
]
selected_genre = random.choice(genres)
print(f"今回の抽選ジャンル: {selected_genre}")

prompt = f"""
あなたは厳格なファクトチェッカー兼YouTube解説動画の構成作家です。
YouTubeの通常動画（横画面16:9・約1分半〜2分）向けに、100%事実に裏付けられた見応えのある解説台本を作成してください。

【今回の指定ジャンル】
「{selected_genre}」のテーマで、関連する3つの確実なトリビアを分かりやすく解説する構成にしてください。

【ハルシネーション（嘘・作話）防止の絶対ルール】
1. ネット上の都市伝説、根拠のない噂、デマ、あやふやな記憶のエピソードは絶対に選ばないこと。
2. 自分の知識で100%自信を持って「事実である」と断言できるネタだけを選び、細かい年号や数値に少しでも曖昧さがある場合は無理に書かず、確実に正しい事実だけを書くこと。
3. 必ず最初にJSONの `fact_check_note` 欄で「3つのネタがそれぞれなぜ100%事実と言えるのか（科学的・歴史的・公式な根拠）」を自己検証してから、`script` を作成すること。
4. 必ず以下のJSON形式のみで出力すること（マークダウン記法は不要）。

{{
  "fact_check_note": "取り上げる3つの雑学が100%事実である科学的・歴史的・公式な根拠",
  "title": "YouTube通常動画のクリックしたくなるタイトル（32文字以内・#Shortsは絶対に入れない）",
  "description": "動画の詳しい概要文とハッシュタグ4〜5個（#雑学 #解説 #豆知識 など。#Shortsは入れない）",
  "search_keyword": "背景動画検索用のシンプルな英単語1語（例: science, space, nature, brain, technology）",
  "script": [
    "1文目（導入）：今回のテーマと3つの雑学を紹介する挨拶・フック（30〜45文字）",
    "2文目（1つ目の結論）：1つ目のテーマ名と驚きの結論（30〜45文字）",
    "3文目（1つ目の解説1）：なぜそうなるのかの正確な理由・メカニズム（35〜50文字）",
    "4文目（1つ目の解説2）：さらに納得する具体的な補足データ（35〜50文字）",
    "5文目（2つ目の結論）：2つ目のテーマ名と驚きの結論（30〜45文字）",
    "6文目（2つ目の解説1）：なぜそうなるのかの正確な理由・メカニズム（35〜50文字）",
    "7文目（2つ目の解説2）：さらに納得する具体的な補足データ（35〜50文字）",
    "8文目（3つ目の結論）：3つ目のテーマ名と驚きの結論（30〜45文字）",
    "9文目（3つ目の解説1）：なぜそうなるのかの正確な理由・メカニズム（35〜50文字）",
    "10文目（3つ目の解説2）：さらに納得する具体的な補足データ（35〜50文字）",
    "11文目（まとめ）：3つの共通点や一番印象的なポイントの振り返り（30〜45文字）",
    "12文目（エンディング）：高評価・チャンネル登録の呼びかけ（25〜40文字）"
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
                    temperature=0.25,
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
fact_note = data.get("fact_check_note", "")
title = data["title"].replace("#Shorts", "").replace("#shorts", "").strip()
description = data["description"].replace("#Shorts", "").replace("#shorts", "").strip()
search_keyword = data["search_keyword"]
script_lines = data["script"]

print(f"ファクトチェック根拠: {fact_note}")
print(f"生成完了: {title} (検索ワード: {search_keyword})")
for idx, s in enumerate(script_lines, 1):
    print(f"  台本{idx}: {s}")

# ==========================================
# 3. 横画面背景動画の取得（Pexels landscape または アニメーション背景）
# ==========================================
bg_video_path = "bg_long_video.mp4"
has_bg_video = False

if PEXELS_API_KEY:
    print("Pexelsから横画面（landscape）の背景動画を検索中...")
    headers = {"Authorization": PEXELS_API_KEY}
    encoded_kw = urllib.parse.quote(search_keyword)
    PEXELS_BASE = clean_url("https://" + "api." + "pexels." + "com/videos/search")

    for query_url in [
        f"{PEXELS_BASE}?query={encoded_kw}&orientation=landscape&per_page=10",
        f"{PEXELS_BASE}?query=abstract&orientation=landscape&per_page=10",
    ]:
        r = requests.get(query_url, headers=headers)
        if r.status_code != 200:
            print(f"Pexels API警告 (Status {r.status_code}): {r.text}")
            break
        videos = r.json().get("videos", [])
        if videos:
            selected_video = random.choice(videos)
            video_files = selected_video["video_files"]
            hd_files = [f for f in video_files if f.get("width", 0) >= 1280 and f.get("file_type") == "video/mp4"]
            download_url = hd_files[0]["link"] if hd_files else video_files[0]["link"]
            with open(bg_video_path, "wb") as f:
                f.write(requests.get(download_url).content)
            has_bg_video = True
            print("Pexelsから横画面背景動画を取得しました。")
            break

# ==========================================
# 4. 音声生成（Edge-TTS）＆ 横画面動画合成（1920x1080）
# ==========================================
print("音声とBGM・横画面動画を合成中...")
VOICE = "ja-JP-NanamiNeural"
clips = []
audio_clips = []
current_time = 0.0

async def generate_tts(text, filename):
    communicate = edge_tts.Communicate(text, VOICE, rate="+12%")
    await communicate.save(filename)

for i, line in enumerate(script_lines):
    audio_file = f"long_part_{i}.mp3"
    asyncio.run(generate_tts(line, audio_file))

    a_clip = AudioFileClip(audio_file)
    duration = a_clip.duration + 0.25
    audio_clips.append(a_clip.set_start(current_time))

    sub_clip = make_subtitle_clip_landscape(line, duration, current_time)
    clips.append(sub_clip)
    current_time += duration

total_duration = current_time
print(f"完成予定動画の長さ: {total_duration:.1f} 秒")
bgm_clip = make_bgm_clip(total_duration)
final_audio = CompositeAudioClip(audio_clips + [bgm_clip])

if has_bg_video:
    bg_clip = VideoFileClip(bg_video_path).without_audio()
    if bg_clip.duration < total_duration:
        bg_clip = bg_clip.loop(duration=total_duration)
    else:
        bg_clip = bg_clip.subclip(0, total_duration)

    bg_clip = bg_clip.resize(width=1920)
    if bg_clip.h > 1080:
        bg_clip = bg_clip.crop(y_center=bg_clip.h / 2, height=1080)
    else:
        bg_clip = bg_clip.resize(height=1080)

    dark_overlay = ColorClip(size=(1920, 1080), color=(0, 0, 0), duration=total_duration).set_opacity(0.42)
    base_layers = [bg_clip, dark_overlay]
else:
    print("横画面グラデーション＋パーティクル背景を生成中...")
    base_layers = [make_animated_bg_landscape(total_duration)]

header_clip = make_header_clip_landscape(title, total_duration)

output_video = "output_long.mp4"
final_video = CompositeVideoClip(base_layers + [header_clip] + clips).set_audio(final_audio)
final_video.write_videofile(output_video, fps=30, codec="libx264", audio_codec="aac")

# ==========================================
# 5. YouTube 通常動画としてアップロード
# ==========================================
if YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN:
    try:
        print("YouTube 通常動画（16:9）をアップロード中...")
        TOKEN_URI = clean_url("https://" + "oauth2." + "googleapis." + "com/token")
        creds = Credentials(
            token=None,
            refresh_token=YT_REFRESH_TOKEN,
            token_uri=TOKEN_URI,
            client_id=YT_CLIENT_ID,
            client_secret=YT_CLIENT_SECRET,
        )
        youtube = build("youtube", "v3", credentials=creds)
        yt_description = (
            f"{description}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🤖 最新AIトレンド＆AIツール比較データベース「AI Tech Hub」\n"
            "https://banjoblog.github.io/auto-blog/\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        body = {
            "snippet": {
                "title": title,
                "description": yt_description,
                "categoryId": "27",  # 27: 教育・解説系カテゴリ
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(output_video, chunksize=-1, resumable=True, mimetype="video/mp4")
        yt_res = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
        print(f"YouTube 通常動画アップロード完了！ Video ID: {yt_res.get('id')}")
    except Exception as e:
        print(f"YouTube アップロードエラー: {e}")
else:
    print("YouTube APIの認証情報が設定されていないためスキップしました。")
