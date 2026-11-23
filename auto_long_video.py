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

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

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


def pick_weighted_theme(themes):
    if os.path.exists(WEIGHTS_FILE):
        try:
            with open(WEIGHTS_FILE, "r", encoding="utf-8") as f:
                weights_map = json.load(f)
            weights = []
            for th in themes:
                matched_w = 1.0
                for key, w in weights_map.items():
                    if key.split("・")[0] in th:
                        matched_w = float(w)
                        break
                weights.append(matched_w)
            chosen = random.choices(themes, weights=weights, k=1)[0]
            print(f"重み付け抽選により長尺テーマ選択: {chosen}")
            return chosen
        except Exception as e:
            print(f"重み付け読み込みスキップ: {e}")
    return random.choice(themes)


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

# デマ・都市伝説が混ざりやすい企業系を除外し、学術・辞書ベースの確実なテーマに厳選
long_themes = [
    "夜にゆっくり聴きたい科学・物理・化学の不思議な法則",
    "眠りにつく前に知りたい宇宙・惑星・気象の壮大な雑学",
    "思わず誰かに話したくなる動物の生態・生物学の驚くべき雑学",
    "聞き流すだけで教養が深まる人体の仕組み・脳科学・睡眠の雑学",
    "作業用BGM代わりに聴ける心理学・行動経済学の有名な実験",
    "知ると日常が楽しくなる食べ物・料理の科学的なメカニズム",
    "教養として知っておきたい日本語の語源・漢字の成り立ち雑学",
]
selected_theme = pick_weighted_theme(long_themes)


def call_gemini_json(prompt_text, temp=0.15):
    for attempt in range(6):
        try:
            res = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt_text,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=temp,
                ),
            )
            return json.loads(res.text)
        except Exception as e:
            print(f"gemini-3.8-flash エラー、リトライ ({attempt+1}/6): {e}")
            time.sleep(10)
    raise RuntimeError("Geminiでの生成に失敗しました。")


# Step 1: 5つの確実な雑学ネタを抽出
fact_prompt = f"""
あなたはNHK教養番組や学術ラジオの構成作家兼ファクトチェッカーです。
テーマ「{selected_theme}」に沿った、教科書・学術論文・広辞苑などの公的資料で100%事実と証明されている「9割の人が知らない・勘違いしている雑学」を5つ厳選してください。

【使用禁止リスト（過去投稿済み）】
[{ng_list_text}]

【絶対厳守ルール】
1. ネット上の都市伝説、俗説、商品ロゴの隠し文字などの噂話、不確かな豆知識は**絶対に禁止**。
2. 意味不明な造語や、複数の雑学を勝手に合体させた作り話は**絶対に禁止**。
3. 5つのネタはそれぞれ異なる切り口にすること。
4. 以下のJSON形式のみで出力すること。

{{
  "facts": [
    {{
      "topic_keyword": "主役キーワード（10文字以内）",
      "chapter_title": "目次用チャプタータイトル（20文字以内）",
      "common_myth": "多くの人が勘違いしている常識（30文字以内）",
      "verified_fact": "100%正確な結論と科学的・辞書的な根拠（220文字以内）",
      "takeaway": "聞き手が納得する一言まとめ（40文字以内）"
    }}
  ],
  "pexels_search_words": ["英語検索語1", "英語検索語2", "英語検索語3", "英語検索語4", "英語検索語5"]
}}
"""

raw_fact_bundle = call_gemini_json(fact_prompt, temp=0.1)

# Step 2: 5つのネタすべてに対する2段階目の厳格ファクトチェック
verify_prompt = f"""
あなたは厳格な科学・言語学の査読者です。以下の5つの雑学データすべてについて、「事実誤認」「都市伝説」「架空の造語」「不正確な数値・名称」が含まれていないか1つずつ厳密に検証してください。

【検証対象データ】
{json.dumps(raw_fact_bundle, ensure_ascii=False)}

【検証ルール】
1. 5つのうち1つでも怪しい点、ネットのデマ、架空の単語・名称が含まれている場合は、その項目を破棄して「{selected_theme}」における**100%確実で教科書レベルの有名な雑学**に差し替えること。
2. 問題がない項目も、表現をより正確かつ分かりやすく整えること。
3. 入力と全く同じJSONキー構造で出力すること。
"""

fact_bundle = call_gemini_json(verify_prompt, temp=0.1)
facts_list = fact_bundle["facts"][:5]
pexels_queries = fact_bundle.get("pexels_search_words", ["night sky", "stars", "ocean", "rain window", "library"])
print("長尺5選 ファクトチェック完了:", [f.get("topic_keyword") for f in facts_list])

# Step 3: 検証済み5ネタのみを使ったラジオ風台本生成
script_prompt = f"""
あなたは人気教養ラジオ番組（聞き流し・睡眠用雑学チャンネル）の放送作家です。
以下の【検証済みの5つの雑学】**のみ**を使い、視聴者が作業用BGMや睡眠前の聞き流しとして最後まで心地よく聴ける「2人掛け合いラジオ台本（全体で約5〜7分・全45〜55カット程度）」を作成してください。

【テーマ】{selected_theme}
【検証済みの5つの雑学】
{json.dumps(facts_list, ensure_ascii=False, indent=2)}

【超重要ルール（ハルシネーション禁止）】
- 上記の【検証済みの5つの雑学】に書かれていない固有名詞・数字・エピソードを**絶対に勝手に創作して付け足さないこと**。

【構成ルール】
1. オープニング（3カット）：落ち着いた挨拶と今日のテーマ紹介（「こんばんは。今日も1日お疲れ様でした…」）
2. 本編（第1話〜第5話、各章8〜9カット）：
   - 各章の最初に `chapter_index`（0〜4）を指定すること。
   - Aが素朴な疑問を投げかけ、Bが科学・辞書的な根拠を丁寧に分かりやすく解説し、Aが深く納得する流れにする。
3. エンディング（3カット）：全体の振り返りと「おやすみなさい／また次回」の穏やかな締め。

【テロップと音声のルール】
- `caption`（画面中央のテロップ）：読みやすく落ち着いた **12〜22文字の要約テロップ** にする。
- `narration`（読み上げ音声）：ラジオのように自然で耳障りの良い口語にし、難読漢字は必ずひらがな・カタカナにする。
- `style`：章の導入・結論は `"highlight"`、通常は `"normal"`。

【固定コメント】
- `pinned_comment` は視聴者が「一番驚いた話」をコメントしたくなる質問形式にする。

以下のJSON形式のみで出力すること。

{{
  "video_title": "【聞き流し・睡眠用】クリックしたくなる教養雑学5選タイトル（34文字以内）",
  "thumbnail_main": "サムネイル用インパクト見出し（12文字以内）",
  "thumbnail_sub": "サムネイル用サブコピー（16文字以内）",
  "description": "SEOを意識した動画説明文（140文字前後・タイムスタンプは自動挿入されるため不要）",
  "tags": ["雑学", "聞き流し", "睡眠用", "教養", "豆知識"],
  "pinned_comment": "コメント欄を盛り上げる質問コメント",
  "cuts": [
    {{"chapter_index": -1, "speaker": "B", "style": "highlight", "caption": "今夜のテーマはこちら", "narration": "こんばんは。今日も一日お疲れ様でした。"}}
  ]
}}
"""

script_data = call_gemini_json(script_prompt, temp=0.3)
video_title = script_data["video_title"]
thumb_main = script_data.get("thumbnail_main", "知らないと損する雑学5選")
thumb_sub = script_data.get("thumbnail_sub", "睡眠用・作業用聞き流し")
description = script_data["description"]
tags = script_data.get("tags", ["雑学", "聞き流し", "睡眠用"])
pinned_comment = script_data.get("pinned_comment", "どの雑学が一番印象に残りましたか？番号で教えてください！")
cuts = script_data["cuts"]


def download_landscape_pexels_videos(query_list, needed_count=8):
    downloaded = []
    if not PEXELS_API_KEY:
        return downloaded
    headers = {"Authorization": PEXELS_API_KEY}
    search_pool = list(query_list) + ["night sky stars", "calm ocean", "rain window", "fireplace", "library books", "nebula space"]
    for q in search_pool:
        if len(downloaded) >= needed_count:
            break
        try:
            encoded_q = urllib.parse.quote(str(q))
            url = f"https://api.pexels.com/videos/search?query={encoded_q}&orientation=landscape&per_page=5"
            res = requests.get(url, headers=headers, timeout=20).json()
            for v in res.get("videos", []):
                if len(downloaded) >= needed_count:
                    break
                best_link = None
                for vf in v.get("video_files", []):
                    if vf.get("file_type") == "video/mp4" and vf.get("width", 0) >= 1280:
                        best_link = vf.get("link")
                        break
                if not best_link and v.get("video_files"):
                    best_link = v["video_files"][0].get("link")
                if best_link:
                    fname = f"long_bg_{len(downloaded)}.mp4"
                    r_vid = requests.get(best_link, timeout=60)
                    if r_vid.status_code == 200 and len(r_vid.content) > 80000:
                        with open(fname, "wb") as f:
                            f.write(r_vid.content)
                        downloaded.append(fname)
        except Exception as e:
            print(f"Pexels検索エラー ({q}): {e}")
    return downloaded


bg_files = download_landscape_pexels_videos(pexels_queries, needed_count=8)


def generate_calm_audio_assets(total_dur):
    subprocess.run(
        [
            FFMPEG_BIN, "-y", "-f", "lavfi",
            "-i", "sine=frequency=528.0:duration=0.8",
            "-f", "lavfi", "-i", "sine=frequency=792.0:duration=0.8",
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=first,afade=t=in:st=0:d=0.02,afade=t=out:st=0.15:d=0.65,volume=0.28",
            "chime.wav",
        ],
        check=False,
    )
    subprocess.run(
        [
            FFMPEG_BIN, "-y",
            "-f", "lavfi", "-i", f"sine=frequency=220.00:duration={total_dur}",
            "-f", "lavfi", "-i", f"sine=frequency=261.63:duration={total_dur}",
            "-f", "lavfi", "-i", f"sine=frequency=329.63:duration={total_dur}",
            "-f", "lavfi", "-i", f"sine=frequency=392.00:duration={total_dur}",
            "-filter_complex",
            f"[0:a][1:a][2:a][3:a]amix=inputs=4:duration=first,lowpass=f=420,tremolo=f=0.25:d=0.3,afade=t=in:st=0:d=2.0,afade=t=out:st={max(0, total_dur - 2.5)}:d=2.5,volume=0.075",
            "calm_bgm.wav",
        ],
        check=False,
    )


async def generate_calm_tts(text, speaker, out_path):
    voice = "ja-JP-NanamiNeural" if speaker == "A" else "ja-JP-KeitaNeural"
    rate = "+6%" if speaker == "A" else "+4%"
    pitch = "+0Hz" if speaker == "A" else "-2Hz"
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(out_path)


def create_landscape_vignette(width=1280, height=720):
    y, x = np.ogrid[:height, :width]
    cx, cy = width / 2.0, height / 2.0
    dist = np.sqrt(((x - cx) / (width * 0.55)) ** 2 + ((y - cy) / (height * 0.55)) ** 2)
    alpha = np.clip(120 + (dist ** 1.8) * 110, 120, 235).astype(np.uint8)
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, 0] = 8
    rgba[:, :, 1] = 12
    rgba[:, :, 2] = 24
    rgba[:, :, 3] = alpha
    return Image.fromarray(rgba, mode="RGBA")


LANDSCAPE_VIGNETTE = create_landscape_vignette()


def draw_stroked(draw, pos, text, font, fill_color, stroke_color=(10, 15, 30, 255)):
    x, y = pos
    draw.text((x + 4, y + 5), text, font=font, fill=(0, 0, 0, 200))
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            draw.text((x + dx, y + dy), text, font=font, fill=stroke_color)
    draw.text((x, y), text, font=font, fill=fill_color)


def create_radio_overlay(text, speaker, style, chapter_label, progress_ratio, out_path, width=1280, height=720):
    img = LANDSCAPE_VIGNETTE.copy()
    draw = ImageDraw.Draw(img)

    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"

    font_header = ImageFont.truetype(font_path, 24)
    font_role = ImageFont.truetype(font_path, 24)
    font_main = ImageFont.truetype(font_path, 48 if style == "highlight" else 44)

    draw.rectangle([(0, 0), (width, 76)], fill=(10, 15, 28, 225))
    draw.rectangle([(0, 74), (width, 77)], fill=(255, 210, 70, 220))
    draw.text((40, 24), f"教養雑学ラジオ ｜ {chapter_label}", font=font_header, fill=(255, 230, 120, 255))

    role_text = "聞き手（質問・相槌）" if speaker == "A" else "解説（学術・辞書根拠）"
    role_bg = (210, 55, 85, 235) if speaker == "A" else (30, 110, 205, 235)
    r_w = 280
    r_x = (width - r_w) // 2
    draw.rounded_rectangle([(r_x, 220), (r_x + r_w, 260)], radius=20, fill=role_bg)
    r_box = draw.textbbox((0, 0), role_text, font=font_role)
    draw.text(((width - (r_box[2] - r_box[0])) // 2, 226), role_text, font=font_role, fill=(255, 255, 255, 255))

    lines = []
    current = ""
    for ch in text:
        if len(current) >= 18:
            lines.append(current)
            current = ch
        else:
            current += ch
    if current:
        lines.append(current)

    line_h = 66
    total_h = len(lines) * line_h
    start_y = 300

    if style == "highlight":
        draw.rounded_rectangle(
            [(120, start_y - 24), (width - 120, start_y + total_h + 24)],
            radius=20,
            fill=(15, 24, 48, 225),
            outline=(255, 215, 70, 245),
            width=3,
        )
        fill_color = (255, 235, 95, 255)
    else:
        fill_color = (255, 255, 255, 255) if speaker == "B" else (175, 235, 255, 255)

    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font_main)
        tw = bbox[2] - bbox[0]
        draw_stroked(draw, ((width - tw) // 2, start_y + idx * line_h), line, font_main, fill_color=fill_color)

    bar_margin = 120
    bar_w = width - (bar_margin * 2)
    bar_y = height - 48
    draw.rounded_rectangle([(bar_margin, bar_y), (bar_margin + bar_w, bar_y + 10)], radius=5, fill=(255, 255, 255, 60))
    fill_w = max(10, int(bar_w * progress_ratio))
    draw.rounded_rectangle([(bar_margin, bar_y), (bar_margin + fill_w, bar_y + 10)], radius=5, fill=(255, 215, 70, 245))

    img.save(out_path)


def create_custom_thumbnail(main_txt, sub_txt, out_path="thumbnail.jpg", width=1280, height=720):
    img = Image.new("RGB", (width, height), (14, 20, 38))
    draw = ImageDraw.Draw(img)

    for y in range(height):
        r = int(14 + (y / height) * 18)
        g = int(20 + (y / height) * 26)
        b = int(38 + (y / height) * 44)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    draw.rectangle([(28, 28), (width - 28, height - 28)], outline=(255, 215, 65), width=8)

    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"

    font_badge = ImageFont.truetype(font_path, 40)
    font_main = ImageFont.truetype(font_path, 96)
    font_sub = ImageFont.truetype(font_path, 52)

    draw.rounded_rectangle([(380, 75), (900, 145)], radius=35, fill=(215, 35, 65))
    b_txt = "【聞き流し・睡眠用】教養雑学5選"
    b_box = draw.textbbox((0, 0), b_txt, font=font_badge)
    draw.text(((width - (b_box[2] - b_box[0])) // 2, 86), b_txt, font=font_badge, fill=(255, 255, 255))

    m_box = draw.textbbox((0, 0), main_txt, font=font_main)
    m_w = m_box[2] - m_box[0]
    if m_w > width - 140:
        font_main = ImageFont.truetype(font_path, 76)
        m_box = draw.textbbox((0, 0), main_txt, font=font_main)
        m_w = m_box[2] - m_box[0]
    mx = (width - m_w) // 2
    my = 260
    draw.text((mx + 6, my + 8), main_txt, font=font_main, fill=(0, 0, 0))
    draw.text((mx, my), main_txt, font=font_main, fill=(255, 235, 65))

    draw.rounded_rectangle([(180, 440), (width - 180, 535)], radius=24, fill=(25, 40, 75), outline=(255, 255, 255), width=3)
    s_box = draw.textbbox((0, 0), sub_txt, font=font_sub)
    draw.text(((width - (s_box[2] - s_box[0])) // 2, 456), sub_txt, font=font_sub, fill=(255, 255, 255))

    img.save(out_path, quality=95)


cut_audio_infos = []
for idx, cut in enumerate(cuts):
    audio_path = f"long_cut_{idx}.mp3"
    speaker = cut.get("speaker", "B")
    asyncio.run(generate_calm_tts(cut["narration"], speaker, audio_path))
    voice_clip = AudioFileClip(audio_path)
    dur = voice_clip.duration + 0.15
    cut_audio_infos.append((voice_clip, dur))

total_estimated_dur = sum(d for _, d in cut_audio_infos)
generate_calm_audio_assets(total_estimated_dur + 2.0)

loaded_bg_clips = []
for bf in bg_files:
    try:
        c = VideoFileClip(bf).without_audio().resize((1280, 720))
        loaded_bg_clips.append(c)
    except Exception:
        pass

scene_clips = []
total_cuts = len(cuts)
elapsed_time = 0.0
chapter_start_times = {}
prev_chapter = -1

for idx, cut in enumerate(cuts):
    img_path = f"long_cut_{idx}.png"
    speaker = cut.get("speaker", "B")
    style = cut.get("style", "normal")
    ch_idx = int(cut.get("chapter_index", -1))
    voice_clip, dur = cut_audio_infos[idx]

    is_chapter_start = False
    if 0 <= ch_idx < len(facts_list) and ch_idx != prev_chapter:
        chapter_start_times[ch_idx] = elapsed_time
        is_chapter_start = True
        prev_chapter = ch_idx

    if 0 <= ch_idx < len(facts_list):
        ch_label = f"第{ch_idx + 1}話：{facts_list[ch_idx].get('chapter_title', '')}"
    elif ch_idx < 0:
        ch_label = "オープニング"
    else:
        ch_label = "エンディング"

    if loaded_bg_clips:
        bg_idx = max(0, ch_idx) % len(loaded_bg_clips)
        base_bg = loaded_bg_clips[bg_idx]
        start_offset = (idx % 4) * 1.5
        if base_bg.duration < start_offset + dur:
            sub = base_bg.loop(duration=start_offset + dur).subclip(start_offset, start_offset + dur)
        else:
            sub = base_bg.subclip(start_offset, start_offset + dur)
        bg_sub = sub.resize(lambda t: 1.0 + 0.04 * (t / max(0.1, dur))).set_position(("center", "center"))
    else:
        bg_sub = ColorClip(size=(1280, 720), color=(14, 20, 38), duration=dur)

    progress = (idx + 1) / total_cuts
    create_radio_overlay(
        cut["caption"],
        speaker,
        style,
        ch_label,
        progress,
        out_path=img_path,
    )

    txt_clip = ImageClip(img_path).set_duration(dur)

    audio_tracks = [voice_clip]
    if is_chapter_start and os.path.exists("chime.wav"):
        audio_tracks.append(AudioFileClip("chime.wav"))

    comp = CompositeVideoClip([bg_sub, txt_clip], size=(1280, 720)).set_audio(CompositeAudioClip(audio_tracks))
    scene_clips.append(comp)
    elapsed_time += dur

final_video = concatenate_videoclips(scene_clips, method="compose")

if os.path.exists("calm_bgm.wav"):
    bgm_clip = AudioFileClip("calm_bgm.wav").set_duration(final_video.duration)
    final_video = final_video.set_audio(CompositeAudioClip([final_video.audio, bgm_clip]))

output_mp4 = "long_output.mp4"
final_video.write_videofile(
    output_mp4,
    fps=24,
    codec="libx264",
    audio_codec="aac",
    threads=4,
    preset="ultrafast",
)

thumb_path = "thumbnail.jpg"
create_custom_thumbnail(thumb_main, thumb_sub, out_path=thumb_path)

chapter_lines = ["00:00 オープニング"]
for c_idx in sorted(chapter_start_times.keys()):
    ts = format_timestamp(chapter_start_times[c_idx])
    c_title = facts_list[c_idx].get("chapter_title", f"雑学その{c_idx + 1}")
    chapter_lines.append(f"{ts} {c_title}")
chapters_text = "\n".join(chapter_lines)

full_description = f"{description}\n\n【目次】\n{chapters_text}\n\n#雑学 #聞き流し #睡眠用 #教養 #豆知識"

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
req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
res_yt = req.execute()
video_id = res_yt["id"]
print(f"YouTube 長尺動画投稿完了！ Video ID: {video_id}")

try:
    if os.path.exists(thumb_path):
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumb_path, mimetype="image/jpeg"),
        ).execute()
        print("カスタムサムネイル設定完了！")
except Exception as te:
    print(f"サムネイル設定スキップ: {te}")

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
    print("長尺動画コメント投稿完了！")
except Exception as ce:
    print(f"コメント投稿スキップ: {ce}")

save_used_topics([f.get("topic_keyword", "") for f in facts_list])
