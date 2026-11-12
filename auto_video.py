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

# 1. GeminiでShorts用ショート台本を作成
print("動画台本を生成中...")
prompt = """
YouTube Shorts用の30秒ショート動画の台本を作成してください。
テーマ：おすすめ最新AIツール紹介（例：ChatGPT, Claude, Geminiなどから1つ厳選）
以下のフォーマットのみを出力してください（余計な挨拶や解説は不要）：

TITLE: [動画タイトル（30文字以内）]
SCRIPT: [ナレーション用テキスト。句読点を適切に入れ、余計な記号やカギかっこを使わずに30〜40秒程度で読める日本語文章]
"""

response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
text_output = response.text.strip().split("\n")

title = "おすすめAIツール紹介"
script_text = "最新のAIツールを活用して作業効率を大幅にアップさせましょう。"

for line in text_output:
    if line.startswith("TITLE:"):
        title = line.replace("TITLE:", "").strip()
    elif line.startswith("SCRIPT:"):
        script_text = line.replace("SCRIPT:", "").strip()

print(f"タイトル: {title}")
print(f"台本: {script_text}")

# 2. 音声合成 (edge-tts で日本語ナレーション生成)
audio_file = "voice.mp3"
VOICE = "ja-JP-NanamiNeural"  # 自然な女性音声

async def generate_speech():
    communicate = edge_tts.Communicate(script_text, VOICE)
    await communicate.save(audio_file)

asyncio.run(generate_speech())
print("音声ファイルを生成しました。")

# 3. 動画の自動レンダリング (MoviePy)
print("動画をレンダリング中...")
audio_clip = AudioFileClip(audio_file)
duration = audio_clip.duration

# 縦型背景（1080x1920、ダークブルー背景）
bg_clip = ColorClip(size=(1080, 1920), color=(18, 24, 38), duration=duration)

# タイトル表示（上部）
title_clip = TextClip(
    title,
    fontsize=50,
    color='gold',
    font='DejaVu-Sans-Bold',
    size=(950, None),
    method='caption'
).set_position(('center', 200)).set_duration(duration)

# 本文テロップ表示（中央）
body_clip = TextClip(
    script_text,
    fontsize=42,
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
