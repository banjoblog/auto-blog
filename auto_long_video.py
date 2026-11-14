import os
import re
import glob
import json
import math
import time
import random
import asyncio
import edge_tts
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types
from moviepy.editor import AudioFileClip, ImageClip, VideoClip, CompositeVideoClip
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

def wrap_text(text, max_chars):
    return "\n".join([text[j:j+max_chars] for j in range(0, len(text), max_chars)])

# ==========================================
# サムネイル画像（1280x720）の自動生成
# ==========================================
def generate_thumbnail(thumb_top, thumb_main, thumb_sub, out_path="thumbnail.jpg"):
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), (15, 23, 42))
    draw = ImageDraw.Draw(img)

    # グラデーション背景
    for y in range(H):
        ratio = y / H
        r = int(15 * (1 - ratio) + 45 * ratio)
        g = int(23 * (1 - ratio) + 18 * ratio)
        b = int(42 * (1 - ratio) + 85 * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # 集中線風の放射ライン
    cx, cy = W // 2, H // 2
    for deg in range(0, 360, 12):
        rad = math.radians(deg)
        x1 = cx + math.cos(rad) * 340
        y1 = cy + math.sin(rad) * 220
        x2 = cx + math.cos(rad) * 900
        y2 = cy + math.sin(rad) * 900
        draw.line([(x1, y1), (x2, y2)], fill=(255, 215, 0), width=4)

    # 外枠の強調フレーム
    draw.rectangle([16, 16, W - 16, H - 16], outline=(255, 215, 0), width=14)

    # 上部赤帯バッジ
    font_top = get_jp_font(46)
    draw.rounded_rectangle([140, 46, W - 140, 134], radius=18, fill=(220, 38, 38), outline=(255, 255, 255), width=5)
    tb = draw.textbbox((0, 0), thumb_top, font=font_top)
    draw.text(((W - (tb[2] - tb[0])) // 2, 62), thumb_top, font=font_top, fill=(255, 255, 255))

    # 中央メイン巨大文字（2行まで）
    font_main = get_jp_font(104)
    wrapped_main = wrap_text(thumb_main, 11)
    mb = draw.multiline_textbbox((0, 0), wrapped_main, font=font_main, spacing=18, align="center")
    mw, mh = mb[2] - mb[0], mb[3] - mb[1]
    mx = (W - mw) // 2
    my = (H - mh) // 2 + 10
    draw.multiline_text(
        (mx, my),
        wrapped_main,
        font=font_main,
        fill=(255, 230, 0),
        stroke_width=12,
        stroke_fill=(0, 0, 0),
        spacing=18,
        align="center",
    )

    # 下部白帯サブキャッチ
    font_sub = get_jp_font(42)
    draw.rounded_rectangle([180, H - 122, W - 180, H - 44], radius=16, fill=(255, 255, 255), outline=(0, 0, 0), width=5)
    sb = draw.textbbox((0, 0), thumb_sub, font=font_sub)
    draw.text(((W - (sb[2] - sb[0])) // 2, H - 106), thumb_sub, font=font_sub, fill=(15, 23, 42))

    img.save(out_path, quality=95)
    print(f"サムネイル画像を生成しました: {out_path}")

# ==========================================
# スライド・図解カード＆字幕・進行バーの描画
# ==========================================
CHAPTER_THEMES = [
    ((15, 23, 42), (30, 58, 138), (56, 189, 248)),    # 0: オープニング（ブルー）
    ((24, 24, 27), (127, 29, 29), (251, 191, 36)),    # 1: POINT 1（クリムゾン×ゴールド）
    ((17, 24, 39), (6, 78, 59), (52, 211, 153)),      # 2: POINT 2（エメラルド）
    ((23, 23, 38), (88, 28, 135), (216, 180, 254)),   # 3: POINT 3（パープル）
    ((15, 23, 42), (30, 41, 59), (250, 204, 21)),     # 4: まとめ（ゴールド）
]

def make_slide_card_clip(chapter_idx, badge_text, card_headline, card_bullets, key_number, start_t, dur):
    """チャプターごとに切り替わる解説スライドボード（1920x1080）"""
    W, H = 1920, 1080
    c1, c2, accent = CHAPTER_THEMES[chapter_idx % len(CHAPTER_THEMES)]

    y_grid = np.linspace(0, 1, H)[:, None, None]
    grad = (np.array(c1) * (1 - y_grid) + np.array(c2) * y_grid).astype(np.uint8)
    base_bg = np.broadcast_to(grad, (H, W, 3)).copy()

    img = Image.fromarray(base_bg).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # 背景の装飾グリッド線
    for gx in range(0, W, 120):
        draw.line([(gx, 0), (gx, H)], fill=(255, 255, 255, 14), width=2)
    for gy in range(0, H, 120):
        draw.line([(0, gy), (W, gy)], fill=(255, 255, 255, 14), width=2)

    # メインの解説ホワイトボード枠（上〜中央エリア）
    board_x1, board_y1, board_x2, board_y2 = 110, 65, W - 110, 725
    draw.rounded_rectangle(
        [board_x1, board_y1, board_x2, board_y2],
        radius=28,
        fill=(15, 23, 42, 225),
        outline=accent + (255,),
        width=6,
    )

    # 左上チャプターバッジ
    font_badge = get_jp_font(36)
    draw.rounded_rectangle([150, 95, 430, 160], radius=14, fill=accent + (255,))
    bb = draw.textbbox((0, 0), badge_text, font=font_badge)
    draw.text((150 + (280 - (bb[2] - bb[0])) // 2, 106), badge_text, font=font_badge, fill=(15, 23, 42, 255))

    # 見出しタイトル
    font_head = get_jp_font(54)
    head_wrapped = wrap_text(card_headline, 24)
    draw.multiline_text((155, 185), head_wrapped, font=font_head, fill=(255, 255, 255, 255), spacing=14)

    # 右側の強調キーワード／数値ボックス
    if key_number:
        kw_x1, kw_y1, kw_x2, kw_y2 = 1230, 175, 1760, 430
        draw.rounded_rectangle(
            [kw_x1, kw_y1, kw_x2, kw_y2],
            radius=22,
            fill=(255, 255, 255, 25),
            outline=accent + (255,),
            width=4,
        )
        font_kw_label = get_jp_font(28)
        draw.text((kw_x1 + 30, kw_y1 + 22), "KEY POINT", font=font_kw_label, fill=accent + (255,))
        font_kw_val = get_jp_font(52)
        kw_wrapped = wrap_text(key_number, 9)
        draw.multiline_text((kw_x1 + 30, kw_y1 + 75), kw_wrapped, font=font_kw_val, fill=(255, 230, 0, 255), spacing=12)

    # 要点箇条書き（3行）
    font_bullet = get_jp_font(38)
    by = 365
    for b_line in card_bullets[:3]:
        draw.ellipse([160, by + 14, 182, by + 36], fill=accent + (255,))
        draw.text((202, by), b_line[:32], font=font_bullet, fill=(226, 232, 240, 255))
        by += 74

    return ImageClip(np.array(img.convert("RGB"))).set_start(start_t).set_duration(dur)

def make_dialogue_subtitle_clip(speaker, text, start_t, dur, total_dur):
    """話者アイコンバッジ＋ニュース風字幕帯＋下部プログレスバー"""
    W, H = 1920, 1080
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 下部字幕座布団
    draw.rounded_rectangle(
        [110, 755, W - 110, 1015],
        radius=24,
        fill=(10, 15, 28, 240),
        outline=(148, 163, 184, 180),
        width=4,
    )

    # 話者バッジ（A: 解説博士 / B: 聞き手アシスタント）
    if speaker == "A":
        sp_name = "解説ナビ"
        sp_color = (37, 99, 235, 255)
        text_color = (255, 255, 255, 255)
    else:
        sp_name = "質問役"
        sp_color = (219, 39, 119, 255)
        text_color = (254, 240, 138, 255)

    font_sp = get_jp_font(32)
    draw.rounded_rectangle([145, 775, 335, 830], radius=12, fill=sp_color)
    sb = draw.textbbox((0, 0), sp_name, font=font_sp)
    draw.text((145 + (190 - (sb[2] - sb[0])) // 2, 784), sp_name, font=font_sp, fill=(255, 255, 255, 255))

    # セリフ字幕
    font_sub = get_jp_font(50)
    wrapped = wrap_text(text, 28)
    draw.multiline_text(
        (150, 845),
        wrapped,
        font=font_sub,
        fill=text_color,
        stroke_width=4,
        stroke_fill=(0, 0, 0, 255),
        spacing=14,
    )

    # 画面最下部の進行度バー（プログレスバー）
    progress = min(1.0, (start_t + dur * 0.5) / max(1.0, total_dur))
    draw.rectangle([0, H - 14, W, H], fill=(30, 41, 59, 255))
    draw.rectangle([0, H - 14, int(W * progress), H], fill=(250, 204, 21, 255))

    return ImageClip(np.array(img)).set_start(start_t).set_duration(dur)

# ==========================================
# BGM ＆ チャプター切替効果音（ピンポン・チャイム）
# ==========================================
def make_bgm_and_sfx(total_duration, transition_times):
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
                out[mask] = wave * 0.04

        # チャプター切替時の軽快な2音チャイム（E5 -> A5）
        for tr_t in transition_times:
            m1 = (t_arr >= tr_t) & (t_arr < tr_t + 0.14)
            if np.any(m1):
                dt = t_arr[m1] - tr_t
                out[m1] += np.sin(2 * np.pi * 659.25 * dt) * np.exp(-dt * 12) * 0.16
            m2 = (t_arr >= tr_t + 0.14) & (t_arr < tr_t + 0.45)
            if np.any(m2):
                dt = t_arr[m2] - (tr_t + 0.14)
                out[m2] += np.sin(2 * np.pi * 880.00 * dt) * np.exp(-dt * 8) * 0.18

        stereo = np.column_stack([out, out])
        return stereo[0] if np.isscalar(t) else stereo

    return AudioClip(make_frame, duration=total_duration, fps=44100)

# ==========================================
# 1. 環境変数・APIキーの読み込み
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 掛け合い対話＆図解スライド構成の台本生成
# ==========================================
print("掛け合い形式の本格YouTube解説台本を生成中...")

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
あなたはYouTubeの人気雑学解説チャンネルの構成作家兼ファクトチェッカーです。
2人のキャラクター（A: 落ち着いた解説ナビゲーター / B: 視聴者目線の明るい質問役）が掛け合いで進行する、約2分〜2分半の横画面YouTube動画の構成台本を作成してください。

【今回の指定ジャンル】
「{selected_genre}」のテーマで、100%事実に裏付けられた確実なトリビアを3つ取り上げてください。

【ハルシネーション（嘘）防止の絶対ルール】
1. ネット上の都市伝説、根拠のない噂、デマは絶対に選ばないこと。
2. 学術的・公式に100%事実と断言できるネタだけを選び、不確かな数値や年号は書かないこと。
3. 必ず最初に `fact_check_note` で3つのネタの科学的・歴史的根拠を自己検証すること。
4. 全5チャプター構成（0:導入 / 1:ネタ1 / 2:ネタ2 / 3:ネタ3 / 4:まとめ）とし、各チャプターに画面上の図解スライド用データと、A・Bの掛け合いセリフ（合計16〜18セリフ）を入れること。
5. 必ず以下のJSON形式のみで出力すること（マークダウン記法は不要）。

{{
  "fact_check_note": "3つの雑学が100%事実である科学的・歴史的・公式な根拠",
  "title": "クリックしたくなるYouTube動画タイトル（32文字以内・#Shorts禁止）",
  "thumb_top": "サムネイル上部赤帯の短い煽り文句（12文字以内 例: 教科書に載らない衝撃事実）",
  "thumb_main": "サムネイル中央の巨大メイン文字（18文字以内 例: 実は嘘だった常識3選）",
  "thumb_sub": "サムネイル下部白帯の補足文（16文字以内 例: 科学と公式データで徹底解説）",
  "description": "動画の概要欄テキストとハッシュタグ4〜5個（#雑学 #解説 #豆知識 など）",
  "chapters": [
    {{
      "chapter_title": "オープニング",
      "badge": "INTRODUCTION",
      "slide_headline": "今日のテーマ（22文字以内）",
      "key_number": "3つの真実",
      "bullets": ["要点1（26文字以内）", "要点2（26文字以内）", "要点3（26文字以内）"],
      "dialogues": [
        {{"speaker": "B", "text": "Bの問いかけ・導入セリフ（30〜45文字）"}},
        {{"speaker": "A", "text": "Aの結論提示・今回のテーマ紹介（35〜50文字）"}},
        {{"speaker": "B", "text": "Bのリアクション・期待を高める一言（25〜40文字）"}}
      ]
    }},
    {{
      "chapter_title": "1つ目の秘密",
      "badge": "POINT 01",
      "slide_headline": "1つ目の雑学タイトル（22文字以内）",
      "key_number": "強調したい単語や数値（12文字以内）",
      "bullets": ["事実の結論（26文字以内）", "科学的・歴史的理由（26文字以内）", "意外な補足データ（26文字以内）"],
      "dialogues": [
        {{"speaker": "A", "text": "Aの1つ目の結論発表（35〜50文字）"}},
        {{"speaker": "B", "text": "Bの驚きと『なぜ？』の質問（25〜40文字）"}},
        {{"speaker": "A", "text": "Aの理由・メカニズムの詳しい解説（40〜55文字）"}},
        {{"speaker": "B", "text": "Bの納得リアクション（25〜40文字）"}}
      ]
    }},
    {{
      "chapter_title": "2つ目の秘密",
      "badge": "POINT 02",
      "slide_headline": "2つ目の雑学タイトル（22文字以内）",
      "key_number": "強調したい単語や数値（12文字以内）",
      "bullets": ["事実の結論（26文字以内）", "科学的・歴史的理由（26文字以内）", "意外な補足データ（26文字以内）"],
      "dialogues": [
        {{"speaker": "A", "text": "Aの2つ目の結論発表（35〜50文字）"}},
        {{"speaker": "B", "text": "Bの疑問・ツッコミ（25〜40文字）"}},
        {{"speaker": "A", "text": "Aの理由・根拠の詳しい解説（40〜55文字）"}},
        {{"speaker": "B", "text": "Bの感心リアクション（25〜40文字）"}}
      ]
    }},
    {{
      "chapter_title": "3つ目の秘密",
      "badge": "POINT 03",
      "slide_headline": "3つ目の雑学タイトル（22文字以内）",
      "key_number": "強調したい単語や数値（12文字以内）",
      "bullets": ["事実の結論（26文字以内）", "科学的・歴史的理由（26文字以内）", "意外な補足データ（26文字以内）"],
      "dialogues": [
        {{"speaker": "A", "text": "Aの3つ目の結論発表（35〜50文字）"}},
        {{"speaker": "B", "text": "Bの驚き・質問（25〜40文字）"}},
        {{"speaker": "A", "text": "Aの理由・根拠の詳しい解説（40〜55文字）"}},
        {{"speaker": "B", "text": "Bの納得リアクション（25〜40文字）"}}
      ]
    }},
    {{
      "chapter_title": "まとめ",
      "badge": "SUMMARY",
      "slide_headline": "本日の重要ポイントまとめ（22文字以内）",
      "key_number": "完全理解",
      "bullets": ["ポイント1の振り返り（26文字以内）", "ポイント2の振り返り（26文字以内）", "ポイント3の振り返り（26文字以内）"],
      "dialogues": [
        {{"speaker": "A", "text": "Aの全体まとめ（35〜50文字）"}},
        {{"speaker": "B", "text": "Bの感想とチャンネル登録のお願い（30〜45文字）"}}
      ]
    }}
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
title = data["title"].replace("#Shorts", "").replace("#shorts", "").strip()
description = data["description"].replace("#Shorts", "").replace("#shorts", "").strip()
chapters = data["chapters"]

print(f"ファクトチェック根拠: {data.get('fact_check_note', '')}")
print(f"タイトル: {title}")

# サムネイル生成
thumb_path = "thumbnail.jpg"
generate_thumbnail(
    data.get("thumb_top", "知って得する雑学解説"),
    data.get("thumb_main", title[:16]),
    data.get("thumb_sub", "公式データで徹底解説"),
    thumb_path,
)

# ==========================================
# 3. 2人掛け合い音声の生成（Edge-TTS）＆ チャプター時間計算
# ==========================================
print("2人の掛け合い音声と図解スライドを合成中...")

async def generate_tts(text, voice, filename):
    communicate = edge_tts.Communicate(text, voice, rate="+14%")
    await communicate.save(filename)

dialogue_entries = []
chapter_ranges = []
current_time = 0.0
part_idx = 0

for c_idx, ch in enumerate(chapters):
    ch_start = current_time
    for d in ch["dialogues"]:
        sp = d.get("speaker", "A")
        txt = d["text"]
        voice = "ja-JP-KeitaNeural" if sp == "A" else "ja-JP-NanamiNeural"
        audio_file = f"dlg_{part_idx}.mp3"
        asyncio.run(generate_tts(txt, voice, audio_file))

        a_clip = AudioFileClip(audio_file)
        dur = a_clip.duration + 0.22
        dialogue_entries.append({
            "speaker": sp,
            "text": txt,
            "start": current_time,
            "duration": dur,
            "audio_clip": a_clip.set_start(current_time),
        })
        current_time += dur
        part_idx += 1

    # チャプター間の余白（0.35秒）
    current_time += 0.35
    chapter_ranges.append({
        "index": c_idx,
        "title": ch["chapter_title"],
        "badge": ch.get("badge", f"PART {c_idx}"),
        "headline": ch.get("slide_headline", ch["chapter_title"]),
        "key_number": ch.get("key_number", ""),
        "bullets": ch.get("bullets", []),
        "start": ch_start,
        "duration": current_time - ch_start,
    })

total_duration = current_time
print(f"完成動画の総再生時間: {total_duration:.1f} 秒")

# スライドクリップ生成
slide_clips = []
transition_times = []
for cr in chapter_ranges:
    if cr["index"] > 0:
        transition_times.append(cr["start"])
    slide_clips.append(
        make_slide_card_clip(
            cr["index"],
            cr["badge"],
            cr["headline"],
            cr["bullets"],
            cr["key_number"],
            cr["start"],
            cr["duration"],
        )
    )

# 字幕クリップ生成
sub_clips = []
audio_clips = []
for entry in dialogue_entries:
    audio_clips.append(entry["audio_clip"])
    sub_clips.append(
        make_dialogue_subtitle_clip(
            entry["speaker"],
            entry["text"],
            entry["start"],
            entry["duration"],
            total_duration,
        )
    )

bgm_sfx_clip = make_bgm_and_sfx(total_duration, transition_times)
final_audio = CompositeAudioClip(audio_clips + [bgm_sfx_clip])

output_video = "output_long.mp4"
final_video = CompositeVideoClip(slide_clips + sub_clips).set_audio(final_audio)
final_video.write_videofile(output_video, fps=30, codec="libx264", audio_codec="aac")

# タイムスタンプ（目次）の自動生成
timestamp_lines = ["【目次（タイムスタンプ）】"]
for cr in chapter_ranges:
    mins = int(cr["start"] // 60)
    secs = int(cr["start"] % 60)
    timestamp_lines.append(f"{mins:02d}:{secs:02d} {cr['headline']}")
timestamps_text = "\n".join(timestamp_lines)

# ==========================================
# 4. YouTube 通常動画 ＋ カスタムサムネイルのアップロード
# ==========================================
if YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN:
    try:
        print("YouTube 通常動画をアップロード中...")
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
            f"{timestamps_text}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🤖 最新AIトレンド＆AIツール比較データベース「AI Tech Hub」\n"
            "https://banjoblog.github.io/auto-blog/\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        body = {
            "snippet": {
                "title": title,
                "description": yt_description,
                "categoryId": "27",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(output_video, chunksize=-1, resumable=True, mimetype="video/mp4")
        yt_res = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
        video_id = yt_res.get("id")
        print(f"YouTube 通常動画アップロード完了！ Video ID: {video_id}")

        # サムネイル画像を自動設定（未認証チャンネルで失敗しても動画自体は公開済みになるよう保護）
        if video_id and os.path.exists(thumb_path):
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumb_path, mimetype="image/jpeg"),
                ).execute()
                print("カスタムサムネイルの設定が完了しました！")
            except Exception as te:
                print(f"サムネイル設定スキップ（チャンネル電話番号認証が未完了の可能性があります）: {te}")

    except Exception as e:
        print(f"YouTube アップロードエラー: {e}")
else:
    print("YouTube APIの認証情報が設定されていないためスキップしました。")
