import os
import json
import time
import asyncio
import random
import subprocess
import urllib.parse
import numpy as np
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


def format_timestamp(seconds):
    total_sec = int(seconds)
    mins = total_sec // 60
    secs = total_sec % 60
    return f"{mins:02d}:{secs:02d}"


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)
used_topics = load_used_topics()
ng_list_text = "、".join(used_topics[-80:]) if used_topics else "なし"

themes = [
    "眠れなくなるほど面白い科学・宇宙の真実5選",
    "明日誰かに話したくなる人体・脳科学の意外な雑学5選",
    "実は理由が深すぎる日本の言葉・企業・歴史の雑学5選",
    "知ると世界の見え方が変わる心理学・行動経済学の実験5選",
    "自然界と動物の常識が覆る驚異の生態雑学5選",
]
selected_theme = random.choice(themes)


def call_gemini_json(prompt_text, temp=0.35):
    for model in ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]:
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
                time.sleep(6)
    raise RuntimeError("Geminiでの生成に失敗しました。")


plan_prompt = f"""
あなたは人気教養ラジオ・YouTubeチャンネルの構成作家兼ファクトチェッカーです。
テーマ「{selected_theme}」に沿って、100%科学的・公式に事実と証明されている雑学を【5つ】厳選し、聞き流しにも画面視聴にも最適な2人掛け合い台本を作成してください。

【使用禁止キーワード（過去投稿済み）】
[{ng_list_text}]

【厳守ルール】
1. 都市伝説や真偽不明の噂は絶対に除外し、学術的・公式に裏付けのある事実のみを選ぶこと。
2. 難読漢字はTTS（音声合成）が読み間違えないよう、必ずひらがな・カタカナ表記にすること。
3. 各トピック（全5章）は、A（聞き手・質問役の女性）とB（解説役の男性）の自然な会話で構成し、1章あたり **6〜8セリフ**（1セリフ20〜38文字程度）にすること。
4. `thumbnail_top` はサムネイル上部の短い煽り文句（10文字以内）、`thumbnail_main` は中央の衝撃フレーズ（12文字以内）にすること。
5. 以下のJSON形式のみで出力すること。

{{
  "video_title": "クリックしたくなる長尺動画タイトル（38文字以内・【聞き流し/雑学】などを入れる）",
  "thumbnail_top": "【保存版】知らなきゃ損",
  "thumbnail_main": "脳が震える衝撃雑学5選",
  "description": "動画全体の魅力的な紹介文（130文字前後）",
  "tags": ["雑学", "聞き流し", "睡眠用", "豆知識", "教養"],
  "opening_cuts": [
    {{"speaker": "A", "caption": "こんばんは！今日も眠れなくなる雑学をお届けします。", "narration": "こんばんは！今日も眠れなくなる雑学をお届けします。"}},
    {{"speaker": "B", "caption": "今回は厳選した5つの驚くべき事実をわかりやすく解説します。", "narration": "今回は厳選した5つの驚くべき事実をわかりやすく解説します。"}}
  ],
  "chapters": [
    {{
      "chapter_title": "第1話の短い見出し（16文字以内）",
      "topic_keyword": "主役キーワード（10文字以内）",
      "pexels_query": "英語の映像検索キーワード（例: galaxy stars）",
      "cuts": [
        {{"speaker": "A", "style": "normal", "caption": "最初は〇〇についての不思議な話です。", "narration": "最初は〇〇についての不思議な話です。"}},
        {{"speaker": "B", "style": "highlight", "caption": "実はこれ、科学的に△△だと証明されているんです。", "narration": "実はこれ、科学的に△△だと証明されているんです。"}}
      ]
    }}
  ],
  "ending_cuts": [
    {{"speaker": "A", "caption": "どの雑学が一番印象に残りましたか？", "narration": "どの雑学が一番印象に残りましたか？"}},
    {{"speaker": "B", "caption": "ぜひコメント欄で教えてください。チャンネル登録もよろしくお願いします。", "narration": "ぜひコメント欄で教えてください。チャンネル登録もよろしくお願いします。"}}
  ]
}}
"""

data = call_gemini_json(plan_prompt, temp=0.4)
video_title = data["video_title"]
thumb_top = data.get("thumbnail_top", "【聞き流し】教養雑学")
thumb_main = data.get("thumbnail_main", "衝撃の事実5選")
base_description = data["description"]
tags = data.get("tags", ["雑学", "聞き流し", "睡眠用"])
opening_cuts = data.get("opening_cuts", [])
chapters = data["chapters"]
ending_cuts = data.get("ending_cuts", [])


def download_landscape_pexels(query_list):
    downloaded = {}
    if not PEXELS_API_KEY:
        return downloaded
    headers = {"Authorization": PEXELS_API_KEY}
    for idx, q in enumerate(query_list):
        try:
            encoded_q = urllib.parse.quote(str(q))
            url = f"https://api.pexels.com/videos/search?query={encoded_q}&orientation=landscape&per_page=4"
            res = requests.get(url, headers=headers, timeout=20).json()
            for v in res.get("videos", []):
                best_link = None
                for vf in v.get("video_files", []):
                    if vf.get("file_type") == "video/mp4" and vf.get("width", 0) >= 1280:
                        best_link = vf.get("link")
                        break
                if not best_link and v.get("video_files"):
                    best_link = v["video_files"][0].get("link")
                if best_link:
                    fname = f"long_bg_{idx}.mp4"
                    r_vid = requests.get(best_link, timeout=60)
                    if r_vid.status_code == 200 and len(r_vid.content) > 80000:
                        with open(fname, "wb") as f:
                            f.write(r_vid.content)
                        downloaded[idx] = fname
                        break
        except Exception as e:
            print(f"Pexels横動画取得エラー ({q}): {e}")
    return downloaded


queries = [ch.get("pexels_query", "night sky") for ch in chapters]
bg_map = download_landscape_pexels(queries)


def generate_long_audio_assets(total_dur):
    # 章切り替わり用の穏やかなベルチャイム（F5 -> C6の柔らかい2音）
    subprocess.run(
        [
            FFMPEG_BIN, "-y",
            "-f", "lavfi", "-i", "sine=frequency=698.46:duration=0.45",
            "-f", "lavfi", "-i", "sine=frequency=1046.50:duration=0.75",
            "-filter_complex",
            "[0:a]afade=t=in:st=0:d=0.02,afade=t=out:st=0.1:d=0.35[a1];[1:a]adelay=220|220,afade=t=in:st=0.22:d=0.02,afade=t=out:st=0.35:d=0.60[a2];[a1][a2]amix=inputs=2:duration=longest,volume=0.25",
            "chapter_chime.wav",
        ],
        check=False,
    )
    # 聞き流し・睡眠にも優しい深いローパス和音BGM（Fmaj7パッド）
    subprocess.run(
        [
            FFMPEG_BIN, "-y",
            "-f", "lavfi", "-i", f"sine=frequency=174.61:duration={total_dur}",
            "-f", "lavfi", "-i", f"sine=frequency=220.00:duration={total_dur}",
            "-f", "lavfi", "-i", f"sine=frequency=261.63:duration={total_dur}",
            "-f", "lavfi", "-i", f"sine=frequency=329.63:duration={total_dur}",
            "-filter_complex",
            f"[0:a][1:a][2:a][3:a]amix=inputs=4:duration=first,lowpass=f=360,tremolo=f=0.25:d=0.3,afade=t=in:st=0:d=2.0,afade=t=out:st={max(0, total_dur - 2.5)}:d=2.5,volume=0.075",
            "long_ambient_bgm.wav",
        ],
        check=False,
    )


async def generate_tts(text, speaker, out_path):
    voice = "ja-JP-NanamiNeural" if speaker == "A" else "ja-JP-KeitaNeural"
    # 長尺は聞き心地を重視して少し落ち着いた速度に設定
    rate = "+10%" if speaker == "A" else "+8%"
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(out_path)


def get_font(size):
    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"
    return ImageFont.truetype(font_path, size)


def draw_stroked_text(draw, pos, text, font, fill_color, stroke_color=(0, 0, 0, 255), stroke_w=5):
    x, y = pos
    draw.text((x + 5, y + 6), text, font=font, fill=(0, 0, 0, 190))
    for dx in range(-stroke_w, stroke_w + 1, 2):
        for dy in range(-stroke_w, stroke_w + 1, 2):
            draw.text((x + dx, y + dy), text, font=font, fill=stroke_color)
    draw.text((x, y), text, font=font, fill=fill_color)


def create_landscape_vignette(width=1920, height=1080):
    y, x = np.ogrid[:height, :width]
    cx, cy = width / 2.0, height / 2.0
    dist = np.sqrt(((x - cx) / (width * 0.55)) ** 2 + ((y - cy) / (height * 0.55)) ** 2)
    alpha = np.clip(90 + (dist ** 1.8) * 110, 90, 220).astype(np.uint8)
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, 0] = 10
    rgba[:, :, 1] = 14
    rgba[:, :, 2] = 24
    rgba[:, :, 3] = alpha
    return Image.fromarray(rgba, mode="RGBA")


LANDSCAPE_VIGNETTE = create_landscape_vignette()


def create_chapter_card_image(chapter_num, total_chapters, chapter_title, out_path):
    width, height = 1920, 1080
    img = Image.new("RGBA", (width, height), (12, 18, 34, 245))
    draw = ImageDraw.Draw(img)

    # ゴールドの外枠フレーム
    draw.rounded_rectangle(
        [(80, 80), (width - 80, height - 80)],
        radius=32,
        outline=(255, 210, 60, 230),
        width=5,
    )

    font_sub = get_font(44)
    font_main = get_font(78)

    label = f"CHAPTER 0{chapter_num} / 0{total_chapters}"
    l_box = draw.textbbox((0, 0), label, font=font_sub)
    draw.text(((width - (l_box[2] - l_box[0])) // 2, 340), label, font=font_sub, fill=(255, 215, 70, 255))

    draw.line([(620, 420), (width - 620, 420)], fill=(255, 215, 70, 180), width=3)

    m_box = draw.textbbox((0, 0), chapter_title, font=font_main)
    m_w = m_box[2] - m_box[0]
    if m_w > width - 240:
        font_main = get_font(60)
        m_box = draw.textbbox((0, 0), chapter_title, font=font_main)
        m_w = m_box[2] - m_box[0]
    draw_stroked_text(
        draw,
        ((width - m_w) // 2, 480),
        chapter_title,
        font_main,
        fill_color=(255, 255, 255, 255),
        stroke_color=(0, 0, 0, 255),
        stroke_w=5,
    )
    img.save(out_path)


def create_studio_overlay(chapter_label, chapter_title, speaker, style, caption, progress_ratio, out_path):
    width, height = 1920, 1080
    img = LANDSCAPE_VIGNETTE.copy()
    draw = ImageDraw.Draw(img)

    font_tag = get_font(30)
    font_ch = get_font(36)
    font_role = get_font(30)
    font_sub = get_font(54 if style == "highlight" else 50)

    # 左上：教養番組風の常設チャプタープレート
    draw.rounded_rectangle(
        [(56, 48), (860, 165)],
        radius=20,
        fill=(14, 20, 38, 225),
        outline=(255, 210, 60, 220),
        width=3,
    )
    draw.text((84, 62), chapter_label, font=font_tag, fill=(255, 215, 70, 255))
    draw.text((84, 104), chapter_title, font=font_ch, fill=(255, 255, 255, 255))

    # 下部：ワイド字幕パネル
    panel_top = 770
    panel_bottom = 1015
    draw.rounded_rectangle(
        [(90, panel_top), (width - 90, panel_bottom)],
        radius=26,
        fill=(10, 15, 28, 225),
        outline=(255, 215, 0, 240) if style == "highlight" else (120, 145, 190, 160),
        width=4 if style == "highlight" else 2,
    )

    # 話者バッジ
    role_text = "聞き手（ナナミ）" if speaker == "A" else "解説（ケイタ）"
    role_bg = (215, 55, 85, 245) if speaker == "A" else (30, 115, 215, 245)
    draw.rounded_rectangle([(125, panel_top - 24), (395, panel_top + 24)], radius=14, fill=role_bg)
    r_box = draw.textbbox((0, 0), role_text, font=font_role)
    draw.text((125 + (270 - (r_box[2] - r_box[0])) // 2, panel_top - 18), role_text, font=font_role, fill=(255, 255, 255, 255))

    # 字幕自動改行（横画面なので1行26文字目安）
    lines = []
    current = ""
    for ch in caption:
        if len(current) >= 26:
            lines.append(current)
            current = ch
        else:
            current += ch
    if current:
        lines.append(current)

    fill_color = (255, 235, 70, 255) if style == "highlight" else (255, 255, 255, 255)
    line_h = 68
    start_y = panel_top + 48 if len(lines) == 1 else panel_top + 28

    for idx, line in enumerate(lines[:2]):
        bbox = draw.textbbox((0, 0), line, font=font_sub)
        tw = bbox[2] - bbox[0]
        x = (width - tw) // 2
        y = start_y + idx * line_h
        draw_stroked_text(draw, (x, y), line, font_sub, fill_color=fill_color, stroke_w=4)

    # 最下部：全体進行バー
    bar_w = width - 180
    draw.rectangle([(90, 1036), (90 + bar_w, 1046)], fill=(255, 255, 255, 60))
    draw.rectangle([(90, 1036), (90 + max(10, int(bar_w * progress_ratio)), 1046)], fill=(255, 215, 0, 255))

    img.save(out_path)


def create_custom_thumbnail(bg_video_path, top_text, main_text, out_path="thumbnail.jpg"):
    width, height = 1280, 720
    if bg_video_path and os.path.exists(bg_video_path):
        try:
            clip = VideoFileClip(bg_video_path)
            frame = clip.get_frame(min(1.0, clip.duration / 2.0))
            bg_img = Image.fromarray(frame).resize((width, height)).convert("RGBA")
        except Exception:
            bg_img = Image.new("RGBA", (width, height), (18, 28, 55, 255))
    else:
        bg_img = Image.new("RGBA", (width, height), (18, 28, 55, 255))

    # 暗めフィルター＋集中枠で文字を際立たせる
    dark_layer = Image.new("RGBA", (width, height), (8, 12, 24, 155))
    img = Image.alpha_composite(bg_img, dark_layer)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(18, 18), (width - 18, height - 18)], outline=(255, 215, 0, 255), width=12)

    font_top = get_font(62)
    font_main = get_font(104)

    # 上部赤帯
    draw.rounded_rectangle([(140, 110), (width - 140, 215)], radius=24, fill=(215, 25, 45, 250), outline=(255, 255, 255, 255), width=4)
    t_box = draw.textbbox((0, 0), top_text, font=font_top)
    draw.text(((width - (t_box[2] - t_box[0])) // 2, 126), top_text, font=font_top, fill=(255, 255, 255, 255))

    # 中央メイン文字（2行分割）
    mid = len(main_text) // 2 if len(main_text) > 7 else len(main_text)
    lines = [main_text[:mid], main_text[mid:]] if len(main_text) > 7 else [main_text]

    y_cursor = 275 if len(lines) == 2 else 340
    for idx, line in enumerate(lines):
        color = (255, 235, 50, 255) if idx == 0 else (255, 255, 255, 255)
        m_box = draw.textbbox((0, 0), line, font=font_main)
        mw = m_box[2] - m_box[0]
        if mw > width - 120:
            font_small = get_font(82)
            m_box = draw.textbbox((0, 0), line, font=font_small)
            mw = m_box[2] - m_box[0]
            draw_stroked_text(draw, ((width - mw) // 2, y_cursor), line, font_small, fill_color=color, stroke_w=8)
        else:
            draw_stroked_text(draw, ((width - mw) // 2, y_cursor), line, font_main, fill_color=color, stroke_w=8)
        y_cursor += 135

    img.convert("RGB").save(out_path, quality=95)


# 全カットの音声事前生成
cut_queue = []
for c in opening_cuts:
    cut_queue.append(("OPENING", selected_theme, None, c))

for ch_idx, ch in enumerate(chapters):
    cut_queue.append(("CHAPTER_CARD", ch["chapter_title"], ch_idx, None))
    for c in ch.get("cuts", []):
        cut_queue.append((f"CHAPTER 0{ch_idx + 1} / 0{len(chapters)}", ch["chapter_title"], ch_idx, c))

for c in ending_cuts:
    cut_queue.append(("ENDING", selected_theme, None, c))

audio_files = {}
for i, item in enumerate(cut_queue):
    kind, ch_title, ch_idx, c = item
    if kind != "CHAPTER_CARD":
        ap = f"long_cut_{i}.mp3"
        asyncio.run(generate_tts(c["narration"], c.get("speaker", "B"), ap))
        audio_files[i] = AudioFileClip(ap)

est_total_dur = sum(ac.duration + 0.18 for ac in audio_files.values()) + (len(chapters) * 2.2)
generate_long_audio_assets(est_total_dur + 2.0)

loaded_bgs = {}
for idx, bf in bg_map.items():
    try:
        clip = VideoFileClip(bf).without_audio().resize((1920, 1080))
        loaded_bgs[idx] = clip
    except Exception:
        pass

fallback_bg = next(iter(loaded_bgs.values())) if loaded_bgs else None

all_video_clips = []
chapter_timestamps = [("00:00", "オープニング")]
current_time = 0.0
total_steps = len(cut_queue)

for i, item in enumerate(cut_queue):
    kind, ch_title, ch_idx, c = item
    progress = (i + 1) / total_steps

    if kind == "CHAPTER_CARD":
        chapter_timestamps.append((format_timestamp(current_time), f"第{ch_idx + 1}話：{ch_title}"))
        card_img = f"card_{ch_idx}.png"
        create_chapter_card_image(ch_idx + 1, len(chapters), ch_title, card_img)
        card_dur = 2.2
        card_clip = ImageClip(card_img).set_duration(card_dur)
        if os.path.exists("chapter_chime.wav"):
            card_clip = card_clip.set_audio(AudioFileClip("chapter_chime.wav"))
        all_video_clips.append(card_clip)
        current_time += card_dur
        continue

    voice_clip = audio_files[i]
    dur = voice_clip.duration + 0.16

    base_bg = loaded_bgs.get(ch_idx, fallback_bg)
    if base_bg is not None:
        offset = (i % 4) * 2.5
        if base_bg.duration < offset + dur:
            sub = base_bg.loop(duration=offset + dur).subclip(offset, offset + dur)
        else:
            sub = base_bg.subclip(offset, offset + dur)
        bg_clip = sub.resize(lambda t: 1.0 + 0.04 * (t / max(0.1, dur))).set_position(("center", "center"))
    else:
        bg_clip = ColorClip(size=(1920, 1080), color=(14, 20, 38), duration=dur)

    overlay_path = f"long_overlay_{i}.png"
    create_studio_overlay(
        kind,
        ch_title,
        c.get("speaker", "B"),
        c.get("style", "normal"),
        c["caption"],
        progress,
        overlay_path,
    )
    ov_clip = ImageClip(overlay_path).set_duration(dur)

    comp = CompositeVideoClip([bg_clip, ov_clip], size=(1920, 1080)).set_audio(voice_clip)
    all_video_clips.append(comp)
    current_time += dur

final_long = concatenate_videoclips(all_video_clips, method="compose")

if os.path.exists("long_ambient_bgm.wav"):
    bgm = AudioFileClip("long_ambient_bgm.wav").set_duration(final_long.duration)
    final_long = final_long.set_audio(CompositeAudioClip([final_long.audio, bgm]))

output_mp4 = "long_output.mp4"
final_long.write_videofile(
    output_mp4,
    fps=24,
    codec="libx264",
    audio_codec="aac",
    threads=4,
    preset="ultrafast",
)

first_bg_path = bg_map.get(0) if bg_map else None
create_custom_thumbnail(first_bg_path, thumb_top, thumb_main, "thumbnail.jpg")

chapters_text = "\n".join([f"{ts} {label}" for ts, label in chapter_timestamps])
full_description = f"{base_description}\n\n【目次（チャプター）】\n{chapters_text}\n\n#雑学 #聞き流し #睡眠用 #豆知識 #教養"

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
        "title": video_title,
        "description": full_description,
        "tags": tags,
        "categoryId": "27",
    },
    "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
}
media = MediaFileUpload(output_mp4, chunksize=-1, resumable=True, mimetype="video/mp4")
res_yt = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
video_id = res_yt["id"]
print(f"YouTube ロング動画 投稿完了！ Video ID: {video_id}")

if os.path.exists("thumbnail.jpg"):
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload("thumbnail.jpg", mimetype="image/jpeg"),
        ).execute()
        print("カスタムサムネイル設定完了！")
    except Exception as te:
        print(f"サムネイル設定スキップ（チャンネル電話番号認証未完了など）: {te}")

used_keywords = [ch.get("topic_keyword", "") for ch in chapters if ch.get("topic_keyword")]
save_used_topics(used_keywords)
