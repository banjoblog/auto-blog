import os
import glob
import json
import time
import asyncio
import random
import subprocess
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
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


def pick_weighted_genre(default_genres):
    if os.path.exists(WEIGHTS_FILE):
        try:
            with open(WEIGHTS_FILE, "r", encoding="utf-8") as f:
                weights_map = json.load(f)
            weights = []
            for g in default_genres:
                matched_w = 1.0
                for key, w in weights_map.items():
                    if key.split("・")[0] in g:
                        matched_w = float(w)
                        break
                weights.append(matched_w)
            chosen = random.choices(default_genres, weights=weights, k=1)[0]
            print(f"重み付け抽選によりジャンル選択: {chosen}")
            return chosen
        except Exception as e:
            print(f"重み付け読み込みスキップ: {e}")
    return random.choice(default_genres)


def get_latest_long_video_url(channel_id):
    if not channel_id:
        return ""
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as res:
            xml_data = res.read()
        root = ET.fromstring(xml_data)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        long_keywords = ["5選", "まとめ", "解説", "聞き流し", "睡眠用", "選"]
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            vid_el = entry.find("yt:videoId", ns)
            title_txt = title_el.text if (title_el is not None and title_el.text) else ""
            if "#Shorts" not in title_txt and any(k in title_txt for k in long_keywords):
                if vid_el is not None and vid_el.text:
                    return f"https://www.youtube.com/watch?v={vid_el.text}"
    except Exception as e:
        print(f"長尺動画URL取得スキップ: {e}")
    return ""


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN")
YOUTUBE_CHANNEL_ID = (os.environ.get("YOUTUBE_CHANNEL_ID") or "").strip()

client = genai.Client(api_key=GEMINI_API_KEY)
used_topics = load_used_topics()
ng_list_text = "、".join(used_topics[-80:]) if used_topics else "なし"

# デマ・都市伝説が混ざりやすい企業系を除外し、学術・辞書ベースの7ジャンルに厳選
genres = [
    "科学・物理・化学の実験で証明されている驚くべき法則",
    "動物の生態・生物学で学術的に確立されている意外な能力",
    "宇宙・惑星・気象のNASAや天文台で観測されている確実な事実",
    "人体の仕組み・脳科学・睡眠に関する医学的に認められている雑学",
    "心理学・行動経済学・お金の判断に関する有名な実験",
    "食べ物・料理の科学的な成分や調理のメカニズム",
    "日本語の語源・漢字の成り立ち・身近な言葉の意外な由来",
]
selected_genre = pick_weighted_genre(genres)
genre_badge = selected_genre.split("・")[0] + "の雑学"


def call_gemini_json(prompt_text, temp=0.15):
    models = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
    for model in models:
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
                err_str = str(e)
                print(f"{model} エラー ({attempt+1}/3): {err_str}")
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    print(f"{model} の日次上限に達したため次のモデルへ切り替えます。")
                    break
                time.sleep(8)
    raise RuntimeError("Geminiでの生成に失敗しました。")


# Step 1: 教科書・学術・辞書ベースのネタ抽出
fact_prompt = f"""
あなたはNHK「チコちゃんに叱られる」や学術番組の厳格なファクトチェッカーです。
「{selected_genre}」のジャンルから、教科書・学術論文・広辞苑などの公的資料で100%事実と証明されている「多くの人が勘違いしている雑学」を1つ厳選してください。

【使用禁止リスト（過去投稿済み）】
[{ng_list_text}]

【絶対厳守ルール】
1. ネット上の都市伝説、俗説、商品ロゴの隠し文字などの噂話、不確かな豆知識は**絶対に禁止**。
2. 意味不明な造語や、複数の雑学を勝手に合体させた作り話は**絶対に禁止**。
3. 学校の理科・社会・国語や百科事典で裏付けが取れる「王道かつ確実な事実」のみを選ぶこと。
4. 以下のJSON形式のみで出力すること。

{{
  "topic_keyword": "主役キーワード（10文字以内）",
  "common_myth": "多くの人が勘違いしている常識（30文字以内）",
  "verified_fact": "100%正確な結論と科学的・辞書的な根拠（180文字以内）",
  "practical_takeaway": "明日誰かに話したくなる確実な一言豆知識（40文字以内）",
  "pexels_search_words": ["英語検索語1", "英語検索語2", "英語検索語3", "英語検索語4", "英語検索語5"]
}}
"""

raw_fact_data = call_gemini_json(fact_prompt, temp=0.1)

# Step 2: 2段階目の厳格ファクトチェック（嘘・造語・都市伝説の排除）
verify_prompt = f"""
あなたは厳格な科学・言語学の査読者です。以下の雑学データに「事実誤認」「都市伝説」「架空の造語」「不正確な数値・名称」が含まれていないか厳密に検証してください。

【検証対象データ】
{json.dumps(raw_fact_data, ensure_ascii=False)}

【検証ルール】
1. 少しでも怪しい点、ネットのデマ、架空の単語・名称が含まれている場合は、破棄して「{selected_genre}」における**100%確実で教科書レベルの有名な雑学**に丸ごと差し替えること。
2. 問題がない場合も、表現をより正確かつ分かりやすく整えること。
3. 入力と全く同じJSONキー構造で出力すること。
"""

fact_data = call_gemini_json(verify_prompt, temp=0.1)
topic_keyword = fact_data.get("topic_keyword", "衝撃雑学")
common_myth = fact_data.get("common_myth", "")
verified_fact = fact_data["verified_fact"]
practical_takeaway = fact_data.get("practical_takeaway", "")
pexels_queries = fact_data.get("pexels_search_words", ["night sky", "ocean waves", "city lights", "abstract", "science"])
print(f"ファクトチェック完了: [{topic_keyword}] {verified_fact}")

# Step 3: 台本生成（検証済みの事実以外を勝手に足さないよう厳命）
script_prompt = f"""
あなたは登録者100万人超えのYouTubeショート専門構成作家です。
以下の【検証済みの事実】**のみ**を使い、視聴者が最初の1秒で指を止め、最後まで一気に見てコメントしたくなる「テレビ雑学番組風の2人掛け合い台本（約38秒）」を作成してください。

【世間の勘違い】{common_myth}
【検証済みの事実】{verified_fact}
【一言オチ】{practical_takeaway}

【超重要ルール（ハルシネーション禁止）】
- 上記の【検証済みの事実】に書かれていない固有名詞・数字・エピソードを**絶対に勝手に創作して付け足さないこと**。

【構成の黄金ルール（全15カット）】
- カット1〜2（フック）：世間の常識を否定する衝撃の一言（「えっ、まだ〇〇だと思ってるの？」「実はそれ、真っ赤なウソなんです！」など）
- カット3〜5（疑問・共感）：Aが視聴者目線で「え、どういうこと！？だって〇〇じゃないの？」と食い気味に質問する
- カット6〜11（種明かし・核心）：Bが科学・公式の理由をテンポよく解説し、Aが「うわ、マジか！」「なるほど〜！」とリアルに相槌を打つ
- カット12〜15（オチ・余韻）：明日誰かに話したくなる一言オチで綺麗に締め、ループ再生したくなる終わり方にする

【テロップと音声の分離ルール】
- `top_banner`（上部常設見出し）：サムネイル一覧でも1行で綺麗に収まる **12文字以内の短い見出し** にすること（例：「なぜ空は青い？」「土星に降る宝石」）。
- `caption`（画面文字）：パッと見て0.5秒で意味が入る **7〜13文字の体言止め・インパクト重視テロップ** にする（例：「99%が勘違い！」「実は逆だった！？」）
- `narration`（読み上げ音声）：人間が自然に喋る口語にし、感情が乗るように読点（、）や「えっ、」「実は…」を入れる。難読漢字は必ずひらがな・カタカナにする。
- `emotion`：`"surprise"`（驚き・フック）、`"explain"`（落ち着いた解説）、`"punchline"`（決めゼリフ・オチ）のいずれかを指定。
- `style`：`"hook"`（冒頭フック）、`"highlight"`（核心・結論・オチ）、`"normal"`（通常）のいずれかを指定。

【コメント欄を伸ばす固定コメント】
- `pinned_comment` は視聴者が思わず返信したくなる「2択アンケート形式」にする（例：「あなたは知ってましたか？ 知ってた ➔ 👍 / 初めて知った ➔ 😱 で教えてください！」）。

以下のJSON形式のみで出力すること。

{{
  "title": "クリックしたくなる動画タイトル（26文字以内・#Shortsなし）",
  "top_banner": "1行で収まる短い見出し（12文字以内）",
  "description": "SEOを意識した動画説明文（110文字前後）",
  "tags": ["雑学", "豆知識", "教育", "{topic_keyword}"],
  "pinned_comment": "2択アンケート形式の固定コメント",
  "cuts": [
    {{"speaker": "A", "style": "hook", "emotion": "surprise", "caption": "まだ〇〇信じてる？", "narration": "えっ、まだ〇〇って信じてるの！？"}},
    {{"speaker": "B", "style": "normal", "emotion": "explain", "caption": "実は完全に逆なんです", "narration": "実はそれ、科学的には完全に逆なんだよね。"}}
  ]
}}
"""

script_data = call_gemini_json(script_prompt, temp=0.3)
title = script_data["title"]
top_banner = script_data.get("top_banner", f"{topic_keyword}の真実")
description = script_data["description"]
tags = script_data.get("tags", ["雑学", "豆知識"])
pinned_comment = script_data.get("pinned_comment", "知らなかった人はコメントで教えてください！")
cuts = script_data["cuts"]

long_video_url = get_latest_long_video_url(YOUTUBE_CHANNEL_ID)
if long_video_url:
    description = f"{description}\n\n▼作業用・睡眠用の雑学まとめ動画はこちら\n{long_video_url}"
    pinned_comment = f"{pinned_comment}\n\n▼聞き流し用の雑学まとめ動画はこちら！\n{long_video_url}"


def download_multiple_pexels_videos(query_list, needed_count=7):
    downloaded = []
    if not PEXELS_API_KEY:
        return downloaded
    headers = {"Authorization": PEXELS_API_KEY}
    search_pool = list(query_list) + ["galaxy stars", "ocean waves", "city night", "abstract motion", "laboratory"]
    for q in search_pool:
        if len(downloaded) >= needed_count:
            break
        try:
            encoded_q = urllib.parse.quote(str(q))
            url = f"https://api.pexels.com/videos/search?query={encoded_q}&orientation=portrait&per_page=5"
            res = requests.get(url, headers=headers, timeout=20).json()
            for v in res.get("videos", []):
                if len(downloaded) >= needed_count:
                    break
                best_link = None
                for vf in v.get("video_files", []):
                    if vf.get("file_type") == "video/mp4" and vf.get("width", 0) >= 720:
                        best_link = vf.get("link")
                        break
                if not best_link and v.get("video_files"):
                    best_link = v["video_files"][0].get("link")
                if best_link:
                    fname = f"bg_clip_{len(downloaded)}.mp4"
                    r_vid = requests.get(best_link, timeout=60)
                    if r_vid.status_code == 200 and len(r_vid.content) > 50000:
                        with open(fname, "wb") as f:
                            f.write(r_vid.content)
                        downloaded.append(fname)
        except Exception as e:
            print(f"Pexels検索エラー ({q}): {e}")
    return downloaded


bg_files = download_multiple_pexels_videos(pexels_queries, needed_count=7)


def generate_pro_audio_assets(total_dur):
    subprocess.run(
        [
            FFMPEG_BIN, "-y", "-f", "lavfi",
            "-i", "sine=frequency=523.25:duration=0.45",
            "-f", "lavfi", "-i", "sine=frequency=659.25:duration=0.45",
            "-f", "lavfi", "-i", "sine=frequency=783.99:duration=0.45",
            "-filter_complex",
            "[0:a][1:a][2:a]amix=inputs=3:duration=first,afade=t=in:st=0:d=0.015,afade=t=out:st=0.08:d=0.37,volume=0.42",
            "se_impact.wav",
        ],
        check=False,
    )
    subprocess.run(
        [
            FFMPEG_BIN, "-y", "-f", "lavfi",
            "-i", "anoisesrc=d=0.16:c=white:r=44100:a=0.22",
            "-af", "bandpass=f=1600:width_type=h:w=900,afade=t=in:st=0:d=0.04,afade=t=out:st=0.06:d=0.10",
            "se_whoosh.wav",
        ],
        check=False,
    )
    subprocess.run(
        [
            FFMPEG_BIN, "-y",
            "-f", "lavfi", "-i", f"sine=frequency=261.63:duration={total_dur}",
            "-f", "lavfi", "-i", f"sine=frequency=329.63:duration={total_dur}",
            "-f", "lavfi", "-i", f"sine=frequency=392.00:duration={total_dur}",
            "-f", "lavfi", "-i", f"sine=frequency=587.33:duration={total_dur}",
            "-filter_complex",
            f"[0:a][1:a][2:a][3:a]amix=inputs=4:duration=first,lowpass=f=480,tremolo=f=0.35:d=0.35,afade=t=in:st=0:d=1.2,afade=t=out:st={max(0, total_dur - 1.5)}:d=1.5,volume=0.085",
            "ambient_bgm.wav",
        ],
        check=False,
    )


async def generate_tts(text, speaker, emotion, out_path):
    voice = "ja-JP-NanamiNeural" if speaker == "A" else "ja-JP-KeitaNeural"
    if emotion == "surprise":
        rate = "+24%" if speaker == "A" else "+20%"
        pitch = "+6Hz" if speaker == "A" else "+3Hz"
    elif emotion == "punchline":
        rate = "+16%"
        pitch = "+2Hz" if speaker == "A" else "-2Hz"
    else:
        rate = "+20%" if speaker == "A" else "+17%"
        pitch = "+0Hz"
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(out_path)


def create_vignette_mask(width=1080, height=1920):
    y, x = np.ogrid[:height, :width]
    cx, cy = width / 2.0, height / 2.0
    dist = np.sqrt(((x - cx) / (width * 0.55)) ** 2 + ((y - cy) / (height * 0.55)) ** 2)
    alpha = np.clip(95 + (dist ** 1.8) * 115, 95, 225).astype(np.uint8)
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, 0] = 8
    rgba[:, :, 1] = 12
    rgba[:, :, 2] = 22
    rgba[:, :, 3] = alpha
    return Image.fromarray(rgba, mode="RGBA")


VIGNETTE_IMG = create_vignette_mask()


def draw_triple_stroked_text(draw, pos, text, font, fill_color, inner_stroke, outer_stroke=(0, 0, 0, 255)):
    x, y = pos
    draw.text((x + 7, y + 9), text, font=font, fill=(0, 0, 0, 210))
    for dx in range(-7, 8, 2):
        for dy in range(-7, 8, 2):
            if dx * dx + dy * dy <= 52:
                draw.text((x + dx, y + dy), text, font=font, fill=outer_stroke)
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            draw.text((x + dx, y + dy), text, font=font, fill=inner_stroke)
    draw.text((x, y), text, font=font, fill=fill_color)


def create_tv_telop_overlay(text, speaker, style, badge_text, banner_text, progress_ratio, out_path, width=1080, height=1920):
    img = VIGNETTE_IMG.copy()
    draw = ImageDraw.Draw(img)

    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"

    font_badge = ImageFont.truetype(font_path, 34)
    font_role = ImageFont.truetype(font_path, 34)
    font_size = 94 if style in ("hook", "highlight") else 86
    font_main = ImageFont.truetype(font_path, font_size)

    draw.rectangle([(0, 0), (width, 330)], fill=(10, 14, 26, 225))
    draw.rectangle([(0, 324), (width, 332)], fill=(255, 205, 0, 255))

    badge_w = 360
    badge_x = (width - badge_w) // 2
    draw.rounded_rectangle(
        [(badge_x, 82), (badge_x + badge_w, 138)],
        radius=28,
        fill=(215, 35, 65, 255),
        outline=(255, 255, 255, 230),
        width=2,
    )
    b_box = draw.textbbox((0, 0), badge_text, font=font_badge)
    draw.text(((width - (b_box[2] - b_box[0])) // 2, 91), badge_text, font=font_badge, fill=(255, 255, 255, 255))

    banner_font_size = 50
    font_banner = ImageFont.truetype(font_path, banner_font_size)
    bn_box = draw.textbbox((0, 0), banner_text, font=font_banner)
    bn_w = bn_box[2] - bn_box[0]
    while bn_w > width - 90 and banner_font_size > 32:
        banner_font_size -= 2
        font_banner = ImageFont.truetype(font_path, banner_font_size)
        bn_box = draw.textbbox((0, 0), banner_text, font=font_banner)
        bn_w = bn_box[2] - bn_box[0]

    draw_triple_stroked_text(
        draw,
        ((width - bn_w) // 2, 172),
        banner_text,
        font_banner,
        fill_color=(255, 230, 70, 255),
        inner_stroke=(25, 25, 35, 255),
    )

    role_text = "疑問・リアクション" if speaker == "A" else "公式・科学的解説"
    role_bg = (225, 50, 85, 245) if speaker == "A" else (25, 115, 220, 245)
    r_w = 340
    r_x = (width - r_w) // 2
    role_y = 665
    draw.rounded_rectangle(
        [(r_x, role_y), (r_x + r_w, role_y + 54)],
        radius=27,
        fill=role_bg,
        outline=(255, 255, 255, 220),
        width=2,
    )
    r_box = draw.textbbox((0, 0), role_text, font=font_role)
    draw.text(((width - (r_box[2] - r_box[0])) // 2, role_y + 7), role_text, font=font_role, fill=(255, 255, 255, 255))

    lines = []
    current = ""
    for ch in text:
        if len(current) >= 8:
            lines.append(current)
            current = ch
        else:
            current += ch
    if current:
        lines.append(current)

    line_height = font_size + 28
    total_h = len(lines) * line_height
    start_y = 760

    if style == "hook":
        draw.rounded_rectangle(
            [(44, start_y - 34), (width - 44, start_y + total_h + 34)],
            radius=28,
            fill=(205, 20, 45, 240),
            outline=(255, 230, 80, 255),
            width=6,
        )
        fill_color = (255, 255, 255, 255)
        inner_stroke = (120, 0, 20, 255)
    elif style == "highlight":
        draw.rounded_rectangle(
            [(44, start_y - 34), (width - 44, start_y + total_h + 34)],
            radius=28,
            fill=(15, 22, 42, 235),
            outline=(255, 215, 0, 255),
            width=6,
        )
        fill_color = (255, 235, 65, 255)
        inner_stroke = (20, 30, 60, 255)
    else:
        fill_color = (255, 255, 255, 255) if speaker == "B" else (155, 235, 255, 255)
        inner_stroke = (15, 25, 45, 255)

    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font_main)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        y = start_y + idx * line_height
        draw_triple_stroked_text(draw, (x, y), line, font_main, fill_color=fill_color, inner_stroke=inner_stroke)

    draw.rectangle([(0, height - 240), (width, height)], fill=(10, 14, 26, 180))
    bar_margin = 90
    bar_w = width - (bar_margin * 2)
    bar_y = height - 185
    draw.rounded_rectangle([(bar_margin, bar_y), (bar_margin + bar_w, bar_y + 18)], radius=9, fill=(255, 255, 255, 65))
    fill_w = max(18, int(bar_w * progress_ratio))
    draw.rounded_rectangle([(bar_margin, bar_y), (bar_margin + fill_w, bar_y + 18)], radius=9, fill=(255, 215, 0, 255))

    img.save(out_path)


cut_audio_infos = []
for idx, cut in enumerate(cuts):
    audio_path = f"cut_{idx}.mp3"
    speaker = cut.get("speaker", "B")
    emotion = cut.get("emotion", "explain")
    asyncio.run(generate_tts(cut["narration"], speaker, emotion, audio_path))
    voice_clip = AudioFileClip(audio_path)
    dur = voice_clip.duration + 0.04
    cut_audio_infos.append((voice_clip, dur))

total_estimated_dur = sum(d for _, d in cut_audio_infos)
generate_pro_audio_assets(total_estimated_dur + 1.0)

loaded_bg_clips = []
for bf in bg_files:
    try:
        c = VideoFileClip(bf).without_audio()
        w, h = c.size
        target_ratio = 1080 / 1920
        if w / h > target_ratio:
            c = c.crop(x_center=w / 2, width=int(h * target_ratio))
        else:
            c = c.crop(y_center=h / 2, height=int(w / target_ratio))
        loaded_bg_clips.append(c.resize((1080, 1920)))
    except Exception:
        pass

scene_clips = []
total_cuts = len(cuts)

for idx, cut in enumerate(cuts):
    img_path = f"cut_{idx}.png"
    speaker = cut.get("speaker", "B")
    style = cut.get("style", "normal")
    voice_clip, dur = cut_audio_infos[idx]

    if loaded_bg_clips:
        base_bg = loaded_bg_clips[idx % len(loaded_bg_clips)]
        start_offset = (idx % 3) * 1.2
        if base_bg.duration < start_offset + dur:
            sub = base_bg.loop(duration=start_offset + dur).subclip(start_offset, start_offset + dur)
        else:
            sub = base_bg.subclip(start_offset, start_offset + dur)
        if idx % 2 == 0:
            bg_sub = sub.resize(lambda t: 1.0 + 0.09 * (t / max(0.1, dur))).set_position(("center", "center"))
        else:
            bg_sub = sub.resize(lambda t: 1.09 - 0.09 * (t / max(0.1, dur))).set_position(("center", "center"))
    else:
        bg_sub = ColorClip(size=(1080, 1920), color=(16, 24, 44), duration=dur)

    progress = (idx + 1) / total_cuts
    create_tv_telop_overlay(
        cut["caption"],
        speaker,
        style,
        genre_badge,
        top_banner,
        progress,
        out_path=img_path,
    )

    base_txt_clip = ImageClip(img_path).set_duration(dur)
    txt_clip = base_txt_clip.resize(
        lambda t: 0.92 + 0.08 * min(1.0, t / 0.12)
    ).set_position(("center", "center"))

    audio_tracks = [voice_clip]
    if style in ("hook", "highlight") and os.path.exists("se_impact.wav"):
        audio_tracks.append(AudioFileClip("se_impact.wav"))
    elif idx > 0 and idx % 2 == 0 and os.path.exists("se_whoosh.wav"):
        audio_tracks.append(AudioFileClip("se_whoosh.wav"))

    comp_audio = CompositeAudioClip(audio_tracks)
    comp = CompositeVideoClip([bg_sub, txt_clip], size=(1080, 1920)).set_audio(comp_audio)
    scene_clips.append(comp)

final_video = concatenate_videoclips(scene_clips, method="compose")

if os.path.exists("ambient_bgm.wav"):
    bgm_clip = AudioFileClip("ambient_bgm.wav").set_duration(final_video.duration)
    final_video = final_video.set_audio(CompositeAudioClip([final_video.audio, bgm_clip]))

output_mp4 = "short_output.mp4"
final_video.write_videofile(
    output_mp4,
    fps=30,
    codec="libx264",
    audio_codec="aac",
    threads=4,
    preset="ultrafast",
)

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
        "title": f"{title} #Shorts",
        "description": f"{description}\n\n#Shorts #雑学 #豆知識",
        "tags": tags,
        "categoryId": "27",
    },
    "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
}
media = MediaFileUpload(output_mp4, chunksize=-1, resumable=True, mimetype="video/mp4")
req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
res_yt = req.execute()
video_id = res_yt["id"]
print(f"YouTube Shorts 投稿完了！ Video ID: {video_id}")

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
    print("YouTube エンゲージメントコメント投稿完了！")
except Exception as ce:
    print(f"コメント投稿スキップ: {ce}")

tiktok_scripts = [f for f in glob.glob("*.py") if "tiktok" in f.lower()]
print(f"TikTokチェック: scripts={tiktok_scripts}, token_set={bool(os.environ.get('TIKTOK_REFRESH_TOKEN'))}")

if tiktok_scripts and os.environ.get("TIKTOK_REFRESH_TOKEN"):
    try:
        subprocess.run(["python", tiktok_scripts[0], output_mp4, title], check=True)
        print("TikTok 投稿スクリプト実行完了！")
    except Exception as te:
        print(f"TikTok 投稿エラー: {te}")
else:
    print(f"TikTok 投稿スキップ: ルート上のpy一覧={glob.glob('*.py')}")

save_used_topics([topic_keyword])
