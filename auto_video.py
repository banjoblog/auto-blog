import os
import sys
import random
import asyncio
import edge_tts
from google import genai
from moviepy.editor import TextClip, CompositeVideoClip, AudioFileClip, ColorClip

# Gemini API設定
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("GEMINI_API_KEY が設定されていません。")
    sys.exit(1)

client = genai.Client(api_key=api_key)
MODEL_NAME = "gemini-3.8-flash"

# 1. Geminiで収益化＆高視聴維持率を狙う雑学台本を作成
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

# タイトル表示（上部・目を引くイエロー）
title_clip = TextClip(
    title,
    fontsize=52,
    color='#FACC15',
    font='DejaVu-Sans-Bold',
    size=(950, None),
    method='caption'
).set_position(('center', 180)).set_duration(duration)

# 本文テロップ表示（中央・白文字）
body_clip = TextClip(
    script_text,
    fontsize=44,
    color='white',
    font='DejaVu-Sans-Bold',
    size=(900, None),
    method='caption'
).set_position(('center', 'center')).set_duration(duration)

# 映像・音声を合成
final_clip = CompositeVideoClip([bg_clip, title_clip, body_clip])
final_clip = final_clip.set_audio(audio_clip)

output_video = "output_shorts.mp4"
final_clip.write_videofile(
    output_video,
    fps=24,
    codec='libx264',
    audio_codec='aac',
    logger=None
)

print(f"動画作成完了: {output_video}")
