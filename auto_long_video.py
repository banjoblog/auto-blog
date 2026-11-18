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

HISTORY_FILE = "used_topics.json"

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
    topics = topics[-150:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)

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
# ベクター風立ち絵キャラクター生成（口閉じ / 口開き）
# ==========================================
def draw_avatar_image(role="A", mouth_open=False, size=240):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2

    if role == "A":
        # 解説博士（ブルー系スーツ・メガネ・落ち着いた知的キャラ）
        bg_col = (30, 58, 138, 255)
        ring_col = (56, 189, 248, 255)
        suit_col = (15, 23, 42, 255)
        hair_col = (30, 41, 59, 255)
    else:
        # 質問役アシスタント（ピンク系・明るいリアクションキャラ）
        bg_col = (131, 24, 67, 255)
        ring_col = (244, 114, 182, 255)
        suit_col = (219, 39, 119, 255)
        hair_col = (88, 28, 135, 255)

    # 背景サークル枠
    draw.ellipse([8, 8, size - 8, size - 8], fill=bg_col, outline=ring_col, width=7)

    # 体（肩）
    draw.pieslice([38, 148, size - 38, size + 40], start=180, end=360, fill=suit_col, outline=(255, 255, 255, 200), width=3)
    if role == "A":
        # ネクタイ
        draw.polygon([(cx - 10, 165), (cx + 10, 165), (cx + 14, 215), (cx, 228), (cx - 14, 215)], fill=(239, 68, 68, 255))
    else:
        # リボン
        draw.polygon([(cx, 175), (cx - 24, 162), (cx - 24, 188)], fill=(250, 204, 21, 255))
        draw.polygon([(cx, 175), (cx + 24, 162), (cx + 24, 188)], fill=(250, 204, 21, 255))

    # 後ろ髪（質問役のみ）
    if role == "B":
        draw.ellipse([52, 42, size - 52, 168], fill=hair_col)

    # 顔の輪郭
    skin_col = (255, 228, 196, 255)
    draw.ellipse([66, 52, size - 66, 158], fill=skin_col, outline=(180, 130, 100, 255), width=3)

    # 前髪
    draw.pieslice([62, 44, size - 62, 120], start=180, end=360, fill=hair_col)

    # 目
    eye_y = 102
    draw.ellipse([88, eye_y - 7, 102, eye_y + 7], fill=(20, 20, 30, 255))
    draw.ellipse([size - 102, eye_y - 7, size - 88, eye_y + 7], fill=(20, 20, 30, 255))
    draw.ellipse([91, eye_y - 4, 96, eye_y + 1], fill=(255, 255, 255, 255))
    draw.ellipse([size - 99, eye_y - 4, size - 94, eye_y + 1], fill=(255, 255, 255, 255))

    if role == "A":
        # 博士メガネ
        draw.rectangle([80, eye_y - 12, 110, eye_y + 12], outline=(250, 204, 21, 255), width=3)
        draw.rectangle([size - 110, eye_y - 12, size - 80, eye_y + 12], outline=(250, 204, 21, 255), width=3)
        draw.line([(110, eye_y), (size - 110, eye_y)], fill=(250, 204, 21, 255), width=3)
    else:
        # チーク
        draw.ellipse([76, 114, 94, 124], fill=(251, 113, 133, 150))
        draw.ellipse([size - 94, 114, size - 76, 124], fill=(251, 113, 133, 150))

    # 口（口パク切り替え）
    mouth_y = 132
    if mouth_open:
        draw.ellipse([cx - 14, mouth_y - 9, cx + 14, mouth_y + 11], fill=(220, 38, 38, 255), outline=(80, 20, 20, 255), width=2)
        draw.pieslice([cx - 10, mouth_y, cx + 10, mouth_y + 10], start=0, end=180, fill=(251, 146, 160, 255))
    else:
        draw.arc([cx - 14, mouth_y - 6, cx + 14, mouth_y + 8], start=15, end=165, fill=(120, 40, 40, 255), width=4)

    return np.array(img)

AVATAR_CACHE = {
    ("A", False): draw_avatar_image("A", False),
    ("A", True): draw_avatar_image("A", True),
    ("B", False): draw_avatar_image("B", False),
    ("B", True): draw_avatar_image("B", True),
}

# ==========================================
# 高CTRサムネイル画像（1280x720）の自動生成
# ==========================================
def generate_thumbnail(thumb_top, thumb_main, thumb_sub, out_path="thumbnail.jpg"):
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), (15, 23, 42))
    draw = ImageDraw.Draw(img)

    for y in range(H):
        ratio = y / H
        r = int(20 * (1 - ratio) + 65 * ratio)
        g = int(15 * (1 - ratio) + 12 * ratio)
        b = int(45 * (1 - ratio) + 35 * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    cx, cy = W // 2, H // 2
    for deg in range(0, 360, 10):
        rad = math.radians(deg)
        x1 = cx + math.cos(rad) * 320
        y1 = cy + math.sin(rad) * 200
        x2 = cx + math.cos(rad) * 900
        y2 = cy + math.sin(rad) * 900
        draw.line([(x1, y1), (x2, y2)], fill=(255, 215, 0), width=5)

    draw.rectangle([14, 14, W - 14, H - 14], outline=(255, 215, 0), width=16)

    # 上部赤帯バッジ
    font_top = get_jp_font(48)
    draw.rounded_rectangle([120, 42, W - 120, 134], radius=18, fill=(220, 38, 38), outline=(255, 255, 255), width=6)
    tb = draw.textbbox((0, 0), thumb_top, font=font_top)
    draw.text(((W - (tb[2] - tb[0])) // 2, 58), thumb_top, font=font_top, fill=(255, 255, 255))

    # 中央メイン巨大文字
    font_main = get_jp_font(108)
    wrapped_main = wrap_text(thumb_main, 11)
    mb = draw.multiline_textbbox((0, 0), wrapped_main, font=font_main, spacing=18, align="center")
    mw, mh = mb[2] - mb[0], mb[3] - mb[1]
    mx = (W - mw) // 2
    my = (H - mh) // 2 + 8
    draw.multiline_text(
        (mx, my),
        wrapped_main,
        font=font_main,
        fill=(255, 235, 0),
        stroke_width=14,
        stroke_fill=(0, 0, 0),
        spacing=18,
        align="center",
    )

    # 下部白帯サブキャッチ
    font_sub = get_jp_font(44)
    draw.rounded_rectangle([160, H - 124, W - 160, H - 42], radius=16, fill=(255, 255, 255), outline=(0, 0, 0), width=6)
    sb = draw.textbbox((0, 0), thumb_sub, font=font_sub)
    draw.text(((W - (sb[2] - sb[0])) // 2, H - 108), thumb_sub, font=font_sub, fill=(15, 23, 42))

    img.save(out_path, quality=95)
    print(f"サムネイル画像を生成しました: {out_path}")

# ==========================================
# スライド・図解カード（クイズ伏せ字モード / 正解オープンモード）
# ==========================================
CHAPTER_THEMES = [
    ((15, 23, 42), (30, 58, 138), (56, 189, 248)),
    ((24, 24, 27), (127, 29, 29), (251, 191, 36)),
    ((17, 24, 39), (6, 78, 59), (52, 211, 153)),
    ((23, 23, 38), (88, 28, 135), (216, 180, 254)),
    ((28, 25, 23), (124, 45, 18), (251, 146, 60)),
    ((15, 23, 42), (17, 94, 89), (45, 212, 191)),
    ((30, 27, 46), (131, 24, 67), (244, 114, 182)),
    ((17, 24, 39), (30, 64, 175), (96, 165, 250)),
    ((15, 23, 42), (30, 41, 59), (250, 204, 21)),
]

def make_slide_card_clip(chapter_idx, badge_text, card_headline, card_bullets, key_number, start_t, dur, mystery_mode=False):
    W, H = 1920, 1080
    c1, c2, accent = CHAPTER_THEMES[chapter_idx % len(CHAPTER_THEMES)]

    y_grid = np.linspace(0, 1, H)[:, None, None]
    grad = (np.array(c1) * (1 - y_grid) + np.array(c2) * y_grid).astype(np.uint8)
    base_bg = np.broadcast_to(grad, (H, W, 3)).copy()

    img = Image.fromarray(base_bg).convert("RGBA")
    draw = ImageDraw.Draw(img)

    for gx in range(0, W, 120):
        draw.line([(gx, 0), (gx, H)], fill=(255, 255, 255, 14), width=2)
    for gy in range(0, H, 120):
        draw.line([(0, gy), (W, gy)], fill=(255, 255, 255, 14), width=2)

    board_x1, board_y1, board_x2, board_y2 = 110, 55, W - 110, 715
    draw.rounded_rectangle(
        [board_x1, board_y1, board_x2, board_y2],
        radius=28,
        fill=(15, 23, 42, 230),
        outline=accent + (255,),
        width=6,
    )

    font_badge = get_jp_font(36)
    draw.rounded_rectangle([150, 85, 430, 150], radius=14, fill=accent + (255,))
    bb = draw.textbbox((0, 0), badge_text, font=font_badge)
    draw.text((150 + (280 - (bb[2] - bb[0])) // 2, 96), badge_text, font=font_badge, fill=(15, 23, 42, 255))

    # クイズモードステータス表示
    font_status = get_jp_font(30)
    if mystery_mode:
        draw.rounded_rectangle([455, 88, 740, 148], radius=12, fill=(220, 38, 38, 255))
        draw.text((482, 100), "★ 理由を予想しよう！", font=font_status, fill=(255, 255, 255, 255))
    elif 1 <= chapter_idx <= 7:
        draw.rounded_rectangle([455, 88, 700, 148], radius=12, fill=(22, 163, 74, 255))
        draw.text((485, 100), "✔ 事実解説オープン", font=font_status, fill=(255, 255, 255, 255))

    font_head = get_jp_font(52)
    head_wrapped = wrap_text(card_headline, 24)
    draw.multiline_text((155, 175), head_wrapped, font=font_head, fill=(255, 255, 255, 255), spacing=14)

    # 右側の強調キーワード／数値ボックス
    kw_x1, kw_y1, kw_x2, kw_y2 = 1230, 165, 1760, 420
    draw.rounded_rectangle(
        [kw_x1, kw_y1, kw_x2, kw_y2],
        radius=22,
        fill=(220, 38, 38, 45) if mystery_mode else (255, 255, 255, 25),
        outline=(248, 113, 113, 255) if mystery_mode else accent + (255,),
        width=4,
    )
    font_kw_label = get_jp_font(28)
    draw.text((kw_x1 + 30, kw_y1 + 22), "SECRET ANSWER" if mystery_mode else "KEY POINT", font=font_kw_label, fill=accent + (255,))
    font_kw_val = get_jp_font(54)
    disp_kw = "？？？" if mystery_mode else (key_number or "重要事実")
    kw_wrapped = wrap_text(disp_kw, 9)
    draw.multiline_text((kw_x1 + 30, kw_y1 + 78), kw_wrapped, font=font_kw_val, fill=(255, 230, 0, 255), spacing=12)

    # 要点箇条書き（3行）
    font_bullet = get_jp_font(38)
    by = 355
    for idx_b, b_line in enumerate(card_bullets[:3]):
        if mystery_mode and idx_b > 0:
            # 2行目・3行目の核心理由は答えめくりまで伏せ字カードにする
            draw.rounded_rectangle([160, by - 4, 1180, by + 54], radius=12, fill=(30, 41, 59, 255), outline=(100, 116, 139, 180), width=2)
            draw.text((185, by + 4), "🔒 衝撃のメカニズムはすぐ後に公開！", font=get_jp_font(34), fill=(148, 163, 184, 255))
        else:
            draw.ellipse([160, by + 14, 182, by + 36], fill=accent + (255,))
            draw.text((202, by), b_line[:32], font=font_bullet, fill=(226, 232, 240, 255))
        by += 74

    return ImageClip(np.array(img.convert("RGB"))).set_start(start_t).set_duration(dur)

# ==========================================
# 口パク立ち絵付き字幕帯＋下部プログレスバー
# ==========================================
def make_dialogue_subtitle_with_avatars(speaker, text, start_t, dur, total_dur):
    W, H = 1920, 1080

    # ベースとなる静的UI部分（字幕枠・話者バッジ・セリフ・プログレスバー）を事前描画
    base_ui = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(base_ui)

    # 中央の字幕座布団（左右に立ち絵スペースを確保）
    draw.rounded_rectangle(
        [320, 745, W - 320, 1020],
        radius=24,
        fill=(10, 15, 28, 245),
        outline=(56, 189, 248, 220) if speaker == "A" else (244, 114, 182, 220),
        width=5,
    )

    if speaker == "A":
        sp_name = "解説博士"
        sp_color = (37, 99, 235, 255)
        text_color = (255, 255, 255, 255)
    else:
        sp_name = "質問アシスタント"
        sp_color = (219, 39, 119, 255)
        text_color = (254, 240, 138, 255)

    font_sp = get_jp_font(30)
    draw.rounded_rectangle([355, 765, 625, 818], radius=12, fill=sp_color)
    sb = draw.textbbox((0, 0), sp_name, font=font_sp)
    draw.text((355 + (270 - (sb[2] - sb[0])) // 2, 773), sp_name, font=font_sp, fill=(255, 255, 255, 255))

    font_sub = get_jp_font(46)
    wrapped = wrap_text(text, 23)
    draw.multiline_text(
        (360, 835),
        wrapped,
        font=font_sub,
        fill=text_color,
        stroke_width=4,
        stroke_fill=(0, 0, 0, 255),
        spacing=12,
    )

    progress = min(1.0, (start_t + dur * 0.5) / max(1.0, total_dur))
    draw.rectangle([0, H - 14, W, H], fill=(30, 41, 59, 255))
    draw.rectangle([0, H - 14, int(W * progress), H], fill=(250, 204, 21, 255))

    base_arr = np.array(base_ui)

    # 口パク＆バウンドアニメーションフレーム生成（最後の0.3秒は口を閉じる）
    speak_end = max(0.2, dur - 0.3)

    def make_frame(t):
        frame = base_arr.copy()
        is_speaking = (t < speak_end) and (int(t * 7) % 2 == 0)
        bounce = -8 if is_speaking else 0

        # 左側：解説博士（A）
        a_open = is_speaking if speaker == "A" else False
        a_y = 770 + (bounce if speaker == "A" else 0)
        av_a = AVATAR_CACHE[("A", a_open)]
        h_a, w_a = av_a.shape[:2]
        alpha_a = av_a[:, :, 3:4] / 255.0
        roi_a = frame[a_y:a_y + h_a, 50:50 + w_a]
        frame[a_y:a_y + h_a, 50:50 + w_a, :3] = (av_a[:, :, :3] * alpha_a + roi_a[:, :, :3] * (1 - alpha_a)).astype(np.uint8)
        frame[a_y:a_y + h_a, 50:50 + w_a, 3] = np.maximum(roi_a[:, :, 3], av_a[:, :, 3])

        # 右側：質問アシスタント（B）
        b_open = is_speaking if speaker == "B" else False
        b_y = 770 + (bounce if speaker == "B" else 0)
        av_b = AVATAR_CACHE[("B", b_open)]
        h_b, w_b = av_b.shape[:2]
        rx = W - 50 - w_b
        roi_b = frame[b_y:b_y + h_b, rx:rx + w_b]
        alpha_b = av_b[:, :, 3:4] / 255.0
        frame[b_y:b_y + h_b, rx:rx + w_b, :3] = (av_b[:, :, :3] * alpha_b + roi_b[:, :, :3] * (1 - alpha_b)).astype(np.uint8)
        frame[b_y:b_y + h_b, rx:rx + w_b, 3] = np.maximum(roi_b[:, :, 3], av_b[:, :, 3])

        return frame[:, :, :3]

    def make_mask(t):
        frame = base_arr.copy()
        is_speaking = (t < speak_end) and (int(t * 7) % 2 == 0)
        bounce = -8 if is_speaking else 0

        a_open = is_speaking if speaker == "A" else False
        a_y = 770 + (bounce if speaker == "A" else 0)
        av_a = AVATAR_CACHE[("A", a_open)]
        h_a, w_a = av_a.shape[:2]
        frame[a_y:a_y + h_a, 50:50 + w_a, 3] = np.maximum(frame[a_y:a_y + h_a, 50:50 + w_a, 3], av_a[:, :, 3])

        b_open = is_speaking if speaker == "B" else False
        b_y = 770 + (bounce if speaker == "B" else 0)
        av_b = AVATAR_CACHE[("B", b_open)]
        h_b, w_b = av_b.shape[:2]
        rx = W - 50 - w_b
        frame[b_y:b_y + h_b, rx:rx + w_b, 3] = np.maximum(frame[b_y:b_y + h_b, rx:rx + w_b, 3], av_b[:, :, 3])

        return frame[:, :, 3] / 255.0

    clip = VideoClip(make_frame, duration=dur).set_start(start_t)
    mask_clip = VideoClip(make_mask, duration=dur, ismask=True).set_start(start_t)
    return clip.set_mask(mask_clip)

# ==========================================
# BGM ＆ チャプター切替チャイム ＋ 正解オープン効果音
# ==========================================
def make_bgm_and_sfx(total_duration, transition_times, reveal_times):
    chords = [
        [261.63, 329.63, 392.00, 493.88],
        [220.00, 261.63, 329.63, 392.00],
        [174.61, 220.00, 261.63, 329.63],
        [196.00, 246.94, 293.66, 349.23],
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
                out[mask] = wave * 0.038

        # チャプター切替SE（E5 -> A5）
        for tr_t in transition_times:
            m1 = (t_arr >= tr_t) & (t_arr < tr_t + 0.14)
            if np.any(m1):
                dt = t_arr[m1] - tr_t
                out[m1] += np.sin(2 * np.pi * 659.25 * dt) * np.exp(-dt * 12) * 0.15
            m2 = (t_arr >= tr_t + 0.14) & (t_arr < tr_t + 0.45)
            if np.any(m2):
                dt = t_arr[m2] - (tr_t + 0.14)
                out[m2] += np.sin(2 * np.pi * 880.00 * dt) * np.exp(-dt * 8) * 0.17

        # 正解オープンSE（C5 -> E5 -> G5 -> C6 アルペジオ）
        notes = [(0.0, 523.25), (0.07, 659.25), (0.14, 783.99), (0.21, 1046.50)]
        for rv_t in reveal_times:
            for offset, freq in notes:
                mr = (t_arr >= rv_t + offset) & (t_arr < rv_t + offset + 0.25)
                if np.any(mr):
                    dt = t_arr[mr] - (rv_t + offset)
                    out[mr] += np.sin(2 * np.pi * freq * dt) * np.exp(-dt * 10) * 0.14

        stereo = np.column_stack([out, out])
        return stereo[0] if np.isscalar(t) else stereo

    return AudioClip(make_frame, duration=total_duration, fps=44100)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID") or os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET") or os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN") or os.environ.get("YOUTUBE_REFRESH_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)

def call_gemini_json(prompt_text):
    for model in ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]:
        for attempt in range(3):
            try:
                res = client.models.generate_content(
                    model=model,
                    contents=prompt_text,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.35,
                        max_output_tokens=8192,
                    ),
                )
                return json.loads(res.text)
            except Exception as e:
                print(f"{model} エラー、10秒待機してリトライ ({attempt+1}/3): {e}")
                time.sleep(10)
    raise RuntimeError("すべてのGeminiモデルでの生成に失敗しました。")

used_topics = load_used_topics()
ng_list_text = "、".join(used_topics) if used_topics else "なし"
print(f"投稿済みNGワード数: {len(used_topics)}件")

genres = [
    "科学・物理・化学の実験で証明されている驚くべき法則やメカニズム7選",
    "動物の生態・生物学で学術的に確立されている意外な能力7選",
    "宇宙・惑星・気象のNASAや天文台で観測されている確実な事実7選",
    "人体の仕組み・脳科学・睡眠に関する医学的に広く認められている雑学7選",
    "日本の老舗企業や有名商品の公式に公開されている誕生秘話・社名の由来7選",
    "日本の法律・道路交通法・硬貨や紙幣の公式仕様に基づく意外な雑学7選",
    "心理学・行動経済学の教科書に載っている有名な実験と日常への応用7選",
    "食べ物・野菜・魚・料理の科学的な成分や調理のメカニズム7選",
    "日本語の語源・漢字の成り立ち・身近な言葉の意外な由来7選",
    "世界遺産・建築・歴史の教科書に載っていない確実な裏トリビア7選",
]
selected_genre = random.choice(genres)
print(f"今回の抽選ジャンル: {selected_genre}")

step1_prompt = f"""
あなたは厳格なファクトチェッカー兼雑学リサーチャーです。
「{selected_genre}」のテーマで、100%学術的・公式に事実と認められている具体的なトリビアを【7つ】厳選してください。

【過去投稿済み・重複禁止リスト（絶対に使用禁止）】
以下のテーマ・食材・生物・企業・トピックは過去に動画化済みのため、7つのうち1つも重複させないでください：
[玉ねぎ, ヒクイドリ, サメ, バナナ, エッフェル塔, {ng_list_text}]

【絶対ルール】
1. 都市伝説やデマは除外し、100%事実と断言できるネタだけを選ぶこと。
2. 7つすべて異なる対象を選び、`topic_keyword` に主役となる単語（例：「ペンギン」「500円玉」「セロトニン」）を記載すること。
3. 以下のJSON形式のみで出力すること。

{{
  "video_theme": "7つの雑学をまとめた魅力的な総合テーマ名（24文字以内）",
  "verified_items": [
    {{
      "item_no": 1,
      "topic_keyword": "主役キーワード（10文字以内）",
      "topic": "雑学のタイトル（20文字以内）",
      "conclusion": "結論となる具体的な事実（40文字以内）",
      "mechanism": "なぜそうなるのかの科学的・歴史的・公式な根拠（70文字以内）",
      "extra_detail": "視聴者が納得する具体的な数値・比較・補足エピソード（70文字以内）",
      "key_word": "スライド右枠に表示する重要語句や数値（10文字以内）"
    }}
  ]
}}
"""

fact_data = call_gemini_json(step1_prompt)
verified_items = fact_data.get("verified_items", [])[:7]
new_keywords = [it.get("topic_keyword", it.get("topic", "")) for it in verified_items]
print(f"ステップ1完了: {new_keywords}")

step2_prompt = f"""
以下の【検証済みの7つの事実データ】だけを使って、2人のキャラクター（A: 落ち着いた解説博士 / B: 視聴者目線の明るい質問アシスタント）が掛け合いで進行する、約6分前後の横画面YouTube解説動画の完全台本を作成してください。

【検証済みの7つの事実データ】
{json.dumps(fact_data, ensure_ascii=False, indent=2)}

【台本構成の厳守ルール】
1. 全9チャプター構成にすること：
   - チャプター0: オープニング（掛け合い4セリフ）
   - チャプター1〜7: POINT 01 〜 POINT 07（各チャプターにつき、AとBの掛け合いを【必ず5セリフ】ずつ作成：
     ・1セリフ目(A): 驚くべき現象・事実の問題提起
     ・2セリフ目(B): 視聴者を代弁する「えっ、なんでそうなるの？」という質問
     ・3セリフ目(A): メカニズム・科学的/歴史的理由の核心解説（ここでスライドの答えが開く）
     ・4セリフ目(A): 具体例・数値・補足エピソードの深掘り
     ・5セリフ目(B): 納得と感心のリアクション）
   - チャプター8: まとめ（掛け合い4セリフ）
2. 1セリフあたり **35〜55文字** の読み応えのある日本語にし、動画全体が5〜8分になるボリュームを確保すること。
3. サムネイル文言（`thumb_top`, `thumb_main`, `thumb_sub`）は「9割が知らない」「実は逆だった」などクリックしたくなる強いパワーワードを使うこと。
4. 必ず以下のJSON形式のみで出力すること。

{{
  "title": "クリックしたくなるYouTube動画タイトル（32文字以内・#Shorts禁止）",
  "thumb_top": "サムネイル上部赤帯の短い煽り文句（12文字以内 例: 9割が勘違いしていた！）",
  "thumb_main": "サムネイル中央の巨大メイン文字（18文字以内 例: 実は嘘だった常識7選）",
  "thumb_sub": "サムネイル下部白帯の補足文（16文字以内 例: 科学と公式データで徹底解説）",
  "description": "動画の詳しい概要文とハッシュタグ4〜5個（#雑学 #解説 #豆知識 など）",
  "chapters": [
    {{
      "chapter_title": "オープニング",
      "badge": "INTRODUCTION",
      "slide_headline": "今日のテーマ（22文字以内）",
      "key_number": "厳選7選",
      "bullets": ["要点1（26文字以内）", "要点2（26文字以内）", "要点3（26文字以内）"],
      "dialogues": [
        {{"speaker": "B", "text": "セリフ"}},
        {{"speaker": "A", "text": "セリフ"}},
        {{"speaker": "B", "text": "セリフ"}},
        {{"speaker": "A", "text": "セリフ"}}
      ]
    }}
  ]
}}
"""

data = call_gemini_json(step2_prompt)
title = data["title"].replace("#Shorts", "").replace("#shorts", "").strip()
description = data["description"].replace("#Shorts", "").replace("#shorts", "").strip()
chapters = data["chapters"]

save_used_topics(new_keywords + [title])

thumb_path = "thumbnail.jpg"
generate_thumbnail(
    data.get("thumb_top", "9割が知らなかった衝撃事実"),
    data.get("thumb_main", title[:16]),
    data.get("thumb_sub", "公式データで徹底解説"),
    thumb_path,
)

async def generate_tts(text, speaker, filename):
    if speaker == "A":
        communicate = edge_tts.Communicate(text, "ja-JP-KeitaNeural", rate="+7%", pitch="-5Hz")
    else:
        communicate = edge_tts.Communicate(text, "ja-JP-NanamiNeural", rate="+10%", pitch="+8Hz")
    await communicate.save(filename)

dialogue_entries = []
chapter_ranges = []
current_time = 0.0
part_idx = 0

for c_idx, ch in enumerate(chapters):
    ch_start = current_time
    reveal_t = None
    for d_idx, d in enumerate(ch["dialogues"]):
        if d_idx == 2:
            # 3セリフ目（解説開始）のタイミングで正解カードをオープン
            reveal_t = current_time
        sp = d.get("speaker", "A")
        txt = d["text"]
        audio_file = f"dlg_{part_idx}.mp3"
        asyncio.run(generate_tts(txt, sp, audio_file))

        a_clip = AudioFileClip(audio_file)
        dur = a_clip.duration + 0.25
        dialogue_entries.append({
            "speaker": sp,
            "text": txt,
            "start": current_time,
            "duration": dur,
            "audio_clip": a_clip.set_start(current_time),
        })
        current_time += dur
        part_idx += 1

    current_time += 0.4
    chapter_ranges.append({
        "index": c_idx,
        "title": ch["chapter_title"],
        "badge": ch.get("badge", f"POINT 0{c_idx}" if 0 < c_idx <= 7 else "INFO"),
        "headline": ch.get("slide_headline", ch["chapter_title"]),
        "key_number": ch.get("key_number", ""),
        "bullets": ch.get("bullets", []),
        "start": ch_start,
        "reveal_t": reveal_t,
        "duration": current_time - ch_start,
    })

total_duration = current_time
print(f"完成動画の総再生時間: {total_duration:.1f} 秒（約 {total_duration/60:.1f} 分）")

slide_clips = []
transition_times = []
reveal_times = []

for cr in chapter_ranges:
    if cr["index"] > 0:
        transition_times.append(cr["start"])

    # POINT 01〜07 は前半を「？？？伏せ字カード」、後半を「正解オープンカード」の2段階にする
    if 1 <= cr["index"] <= 7 and cr["reveal_t"] and cr["reveal_t"] > cr["start"] + 1.0:
        mystery_dur = cr["reveal_t"] - cr["start"]
        open_dur = (cr["start"] + cr["duration"]) - cr["reveal_t"]
        reveal_times.append(cr["reveal_t"])

        slide_clips.append(
            make_slide_card_clip(
                cr["index"],
                cr["badge"],
                cr["headline"],
                cr["bullets"],
                cr["key_number"],
                cr["start"],
                mystery_dur,
                mystery_mode=True,
            )
        )
        slide_clips.append(
            make_slide_card_clip(
                cr["index"],
                cr["badge"],
                cr["headline"],
                cr["bullets"],
                cr["key_number"],
                cr["reveal_t"],
                open_dur,
                mystery_mode=False,
            )
        )
    else:
        slide_clips.append(
            make_slide_card_clip(
                cr["index"],
                cr["badge"],
                cr["headline"],
                cr["bullets"],
                cr["key_number"],
                cr["start"],
                cr["duration"],
                mystery_mode=False,
            )
        )

sub_clips = []
audio_clips = []
for entry in dialogue_entries:
    audio_clips.append(entry["audio_clip"])
    sub_clips.append(
        make_dialogue_subtitle_with_avatars(
            entry["speaker"],
            entry["text"],
            entry["start"],
            entry["duration"],
            total_duration,
        )
    )

bgm_sfx_clip = make_bgm_and_sfx(total_duration, transition_times, reveal_times)
final_audio = CompositeAudioClip(audio_clips + [bgm_sfx_clip])

output_video = "output_long.mp4"
final_video = CompositeVideoClip(slide_clips + sub_clips).set_audio(final_audio)
final_video.write_videofile(
    output_video,
    fps=24,
    codec="libx264",
    audio_codec="aac",
    preset="ultrafast",
    threads=4,
)

timestamp_lines = ["【目次（タイムスタンプ）】"]
for cr in chapter_ranges:
    mins = int(cr["start"] // 60)
    secs = int(cr["start"] % 60)
    timestamp_lines.append(f"{mins:02d}:{secs:02d} {cr['headline']}")
timestamps_text = "\n".join(timestamp_lines)

if YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN:
    try:
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
        print(f"YouTube 長尺解説動画アップロード完了！ Video ID: {video_id}")

        if video_id and os.path.exists(thumb_path):
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumb_path, mimetype="image/jpeg"),
                ).execute()
                print("カスタムサムネイルの設定が完了しました！")
            except Exception as te:
                print(f"サムネイル設定スキップ: {te}")

    except Exception as e:
        print(f"YouTube アップロードエラー: {e}")
