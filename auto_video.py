import os
import json
import time
import asyncio
import urllib.parse
import requests
import edge_tts
from google import genai
from google.genai import types
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
from moviepy.audio.AudioClip import CompositeAudioClip
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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
# 3. 背景動画のダウンロード（Pexels API）
# ==========================================
print("背景動画をダウンロード中...")
bg_video_path = "bg_video.mp4"
headers = {"Authorization": PEXELS_API_KEY}
encoded_kw = urllib.parse.quote(search_keyword)
PEXELS_BASE = "https://" + "[api.pexels.com/videos/search](https://api.pexels.com/videos/search)"
pexels_url = f"{PEXELS_BASE}?query={encoded_kw}&orientation=portrait&size=medium&per_page=5"
res = requests.get(pexels_url, headers=headers).json()

videos = res.get("videos", [])
if not videos:
    fallback_url = f"{PEXELS_BASE}?query=nature&orientation=portrait&size=medium&per_page=5"
    res = requests.get(fallback_url, headers=headers).json()
    videos = res.get("videos", [])

video_files = videos[0]["video_files"]
hd_files = [f for f in video_files if f.get("width", 0) >= 720 and f.get("file_type") == "video/mp4"]
download_url = hd_files[0]["link"] if hd_files else video_files[0]["link"]

with open(bg_video_path, "wb") as f:
    f.write(requests.get(download_url).content)

# ==========================================
# 4. 音声生成（Edge-TTS）＆ 動画合成（MoviePy）
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
    
    # 改行処理（12文字ごとに改行）
    wrapped_line = "\n".join([line[j:j+12] for j in range(0, len(line), 12)])
    
    txt_clip = (
        TextClip(
            wrapped_line,
            fontsize=65,
            color="white",
            font="Noto-Sans-CJK-JP-Bold",
            stroke_color="black",
            stroke_width=3,
            method="caption",
            size=(950, None),
        )
        .set_position("center")
        .set_start(current_time)
        .set_duration(duration)
    )
    clips.append(txt_clip)
    current_time += duration

total_duration = current_time
final_audio = CompositeAudioClip(audio_clips)

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

output_video = "output_short.mp4"
final_video = CompositeVideoClip([bg_clip] + clips).set_audio(final_audio)
final_video.write_videofile(output_video, fps=30, codec="libx264", audio_codec="aac")

# ==========================================
# 5. YouTube Shorts へアップロード
# ==========================================
if YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN:
    try:
        print("YouTube Shorts へアップロード中...")
        creds = Credentials(
            token=None,
            refresh_token=YT_REFRESH_TOKEN,
            token_uri="https://" + "[oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)",
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
        TIKTOK_TOKEN_URL = "https://" + "[open.tiktokapis.com/v2/oauth/token/](https://open.tiktokapis.com/v2/oauth/token/)"
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

        TIKTOK_INIT_URL = "https://" + "[open.tiktokapis.com/v2/post/publish/inbox/video/init/](https://open.tiktokapis.com/v2/post/publish/inbox/video/init/)"
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
