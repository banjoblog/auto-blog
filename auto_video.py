import os
import re
import glob
import json
import time
import asyncio
import urllib.parse
import requests
import edge_tts
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, ColorClip
from moviepy.audio.AudioClip import CompositeAudioClip
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

def make_subtitle_clip(text, duration, start_time):
    W, H = 1080, 1920
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_jp_font(68)
    
    wrapped = "\n".join([text[j:j+12] for j in range(0, len(text), 12)])
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=16, align="center")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) // 2
    y = (H - th) // 2
    
    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=6,
        stroke_fill=(0, 0, 0, 255),
        spacing=16,
        align="center",
    )
    return ImageClip(np.array(img)).set_start(start_time).set_duration(duration)

# ==========================================
# 1. 環境変数・APIキーの読み込み
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

# YouTube用
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN")

# TikTok用
TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET")
TIKTOK_REFRESH_TOKEN = os.environ.get("TIKTOK_REFRESH_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 雑学台本の生成（混雑・制限回避リトライ付）
# ==========================================
print("収益化向け雑学動画台本を生成中...")
prompt = """
YouTube ShortsとTikTok向けの、思わず最後まで見てしまう面白い雑学・豆知識の台本を1つ作成してください。
必ず以下のJSON形式のみで出力してください（マークダウンの ```json などは不要です）。

{
  "title": "動画のキャッチーなタイトル（30文字以内・ハッシュタグなし）",
  "description": "動画の説明文と関連ハッシュタグ3〜5個（#雑学 #豆知識 など）",
  "search_keyword": "背景動画検索用のシンプルな英単語1語（例: space, ocean, brain, money, nature）",
  "script": [
    "1文目（視聴者を引き込むフック・疑問形など、15〜20文字程度）",
    "2文目（意外な事実・解説1、20〜25文字程度）",
    "3文目（詳しい理由・解説2、20〜25文字程度）",
    "4文目（まとめ・オチ、15〜20文字程度）"
  ]
}
"""

response = None
for model in ["gemini-3.5-flash-lite", "gemini-3.8-flash"]:
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
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

# ==========================================
# 3. 背景動画のダウンロード（Pexels API + 自動フォールバック）
# ==========================================
print("背景動画をダウンロード中...")
bg_video_path = "bg_video.mp4"
has_bg_video = False

if PEXELS_API_KEY:
    headers = {"Authorization": PEXELS_API_KEY}
    encoded_kw = urllib.parse.quote(search_keyword)
    PEXELS_BASE = clean_url("https://" + "api." + "pexels." + "com/videos/search")
    
    for query_url in [
        f"{PEXELS_BASE}?query={encoded_kw}&orientation=portrait&per_page=5",
        f"{PEXELS_BASE}?query=nature&per_page=5",
    ]:
        r = requests.get(query_url, headers=headers)
        if r.status_code != 200:
            print(f"Pexels API警告 (Status {r.status_code}): {r.text}")
            break
        videos = r.json().get("videos", [])
        if videos:
            video_files = videos[0]["video_files"]
            hd_files = [f for f in video_files if f.get("width", 0) >= 720 and f.get("file_type") == "video/mp4"]
            download_url = hd_files[0]["link"] if hd_files else video_files[0]["link"]
            with open(bg_video_path, "wb") as f:
                f.write(requests.get(download_url).content)
            has_bg_video = True
            print("Pexelsから背景動画を取得しました。")
            break
else:
    print("PEXELS_API_KEYが未設定のため、デフォルト背景を使用します。")

# ==========================================
# 4. 音声生成（Edge-TTS）＆ 動画合成（Pillow + MoviePy）
# ==========================================
print("音声と字幕動画を合成中...")
VOICE = "ja-JP-NanamiNeural"
clips = []
audio_clips = []
current_time = 0.0

async def generate_tts(text, filename):
    communicate = edge_tts.Communicate(text, VOICE, rate="+15%")
    await communicate.save(filename)

for i, line in enumerate(script_lines):
    audio_file = f"part_{i}.mp3"
    asyncio.run(generate_tts(line, audio_file))
    
    a_clip = AudioFileClip(audio_file)
    duration = a_clip.duration + 0.2
    audio_clips.append(a_clip.set_start(current_time))
    
    sub_clip = make_subtitle_clip(line, duration, current_time)
    clips.append(sub_clip)
    current_time += duration

total_duration = current_time
final_audio = CompositeAudioClip(audio_clips)

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
else:
    bg_clip = ColorClip(size=(1080, 1920), color=(20, 28, 48), duration=total_duration)

output_video = "output_short.mp4"
final_video = CompositeVideoClip([bg_clip] + clips).set_audio(final_audio)
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
# 6. TikTok へアップロード（Inbox/下書き送信）
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

        TIKTOK_INIT_URL = clean_url("https://" + "open." + "tiktokapis." + "com/v2/post/publish/inbox/video/init/")
        init_res = requests.post(
            TIKTOK_INIT_URL,
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
        print(f"TikTok アップロード完了！ (Status: {put_res.status_code}, Publish ID: {publish_id})")
    except Exception as e:
        print(f"TikTok アップロードエラー: {e}")
