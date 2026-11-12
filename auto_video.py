import os
import sys
import asyncio
import edge_tts
from google import genai
from moviepy.editor import TextClip, CompositeVideoClip, AudioFileClip, ColorClip
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 1. Gemini API設定
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("GEMINI_API_KEY が設定されていません。")
    sys.exit(1)

client = genai.Client(api_key=api_key)
MODEL_NAME = "gemini-2.5-flash"

print("収益化向け雑学動画台本を生成中...")
prompt = """
YouTube Shortsで爆発的に再生され、幅広い層（大人〜子ども）に受けやすい「衝撃の雑学・トリビア」の30秒台本を作成してください。
思わず最後まで見てしまうようなフック（「実は…」「知ってた？」等）を最初に持ってきてください。

以下のフォーマットのみを出力してください（余計な挨拶や解説は不要）：

TITLE: [思わずタップしたくなるタイトル（25文字以内、感嘆符など活用）]
SCRIPT: [ナレーション用テキスト。最初の3秒で惹きつけ、30秒程度で読める日本語文章。句読点を適切に入れ、記号やカッコは使わないこと]
"""

response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
text_output = response.text.strip().split("\n")

title = "知ると誰かに話したくなる雑学"
script_text = "実は日常の中に隠された驚きの事実があります。知っていましたか？"

for line in text_output:
    if line.startswith("TITLE:"):
        title = line.replace("TITLE:", "").strip()
    elif line.startswith("SCRIPT:"):
        script_text = line.replace("SCRIPT:", "").strip()

print(f"タイトル: {title}")
print(f"台本: {script_text}")

# 2. 音声合成 (edge-tts で日本語ナレーション生成)
audio_file = "voice.mp3"
VOICE = "ja-JP-NanamiNeural"

async def generate_speech():
    communicate = edge_tts.Communicate(script_text, VOICE)
    await communicate.save(audio_file)

asyncio.run(generate_speech())
print("音声ファイルを生成しました。")

# 3. 動画の自動レンダリング (MoviePy)
print("動画をレンダリング中...")
audio_clip = AudioFileClip(audio_file)
duration = audio_clip.duration

# 縦型背景（1080x1920、視認性の高いダークネイビー）
bg_clip = ColorClip(size=(1080, 1920), color=(15, 23, 42), duration=duration)

# 日本語対応フォントを指定
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

# タイトル表示（上部・目を引くイエロー）
title_clip = TextClip(
    title,
    fontsize=56,
    color='#FACC15',
    font=FONT_PATH,
    size=(950, None),
    method='caption'
).set_position(('center', 220)).set_duration(duration)

# 本文テロップ表示（中央・白文字）
body_clip = TextClip(
    script_text,
    fontsize=46,
    color='white',
    font=FONT_PATH,
    size=(900, None),
    method='caption'
).set_position(('center', 'center')).set_duration(duration)

final_clip = CompositeVideoClip([bg_clip, title_clip, body_clip]).set_audio(audio_clip)

output_video = "output_shorts.mp4"
final_clip.write_videofile(
    output_video,
    fps=24,
    codec='libx264',
    audio_codec='aac',
    logger=None
)
print(f"動画作成完了: {output_video}")

# 4. YouTube Data API v3 で自動アップロード
print("YouTubeへアップロード中...")
yt_client_id = os.environ.get("YOUTUBE_CLIENT_ID")
yt_client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
yt_refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

if not all([yt_client_id, yt_client_secret, yt_refresh_token]):
    print("YouTubeの認証情報（Secrets）が不足しています。")
    sys.exit(1)

creds = Credentials(
    token=None,
    refresh_token=yt_refresh_token,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=yt_client_id,
    client_secret=yt_client_secret,
    scopes=["https://www.googleapis.com/auth/youtube.upload"]
)
creds.refresh(Request())

youtube = build("youtube", "v3", credentials=creds)

body = {
    "snippet": {
        "title": f"{title} #Shorts #雑学 #トリビア",
        "description": f"{script_text}\n\n#Shorts #雑学 #豆知識 #トリビア",
        "tags": ["Shorts", "雑学", "トリビア", "豆知識"],
        "categoryId": "24"
    },
    "status": {
        "privacyStatus": "public",
        "selfDeclaredMadeForKids": False
    }
}

media = MediaFileUpload(output_video, chunksize=-1, resumable=True, mimetype="video/mp4")
request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
response_upload = request.execute()

print(f"アップロード完了！動画ID: {response_upload.get('id')}")
