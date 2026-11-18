import os
import re
import glob
import json
import math
import time
import random
import asyncio
import urllib.parse
import requests
import edge_tts
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, VideoClip, CompositeVideoClip, ColorClip
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
    topics = topics[-200:]
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

def make_animated_bg(total_duration):
    W, H = 1080, 1920
    palettes = [
        ((15, 23, 42), (49, 46, 129)),
        ((20, 30, 48), (36, 59, 85)),
        ((28, 25, 23), (87, 37, 45)),
        ((17, 24, 39), (19, 78, 74)),
    ]
    c1, c2 = random.choice(palettes)
    y_grid = np.linspace(0, 1, H)[:, None, None]
    grad = (np.array(c1) * (1 - y_grid) + np.array(c2) * y_grid).astype(np.uint8)
    base_bg = np.broadcast_to(grad, (H, W, 3)).copy()
    
    rng = np.random.default_rng(42)
    particles = []
    for _ in range(28):
        particles.append({
            "x": rng.uniform(0, W),
            "y": rng.uniform(0, H),
            "r": rng.uniform(8, 36),
            "speed_y": rng.uniform(35, 95),
            "phase": rng.uniform(0, 2 * math.pi),
            "alpha": rng.uniform(0.08, 0.25),
        })

    def make_frame(t):
        frame = base_bg.copy()
        img = Image.fromarray(frame).convert("RGBA")
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for p in particles:
            px = (p["x"] + math.sin(t * 1.2 + p["phase"]) * 40) % W
            py = (p["y"] - t * p["speed_y"]) % H
            r = p["r"]
            a = int(255 * p["alpha"])
            draw.ellipse([px - r, py - r, px + r, py + r], fill=(255, 255, 255, a))
        out = Image.alpha_composite(img, overlay).convert("RGB")
        return np.array(out)

    return VideoClip(make_frame, duration=total_duration)

def make_header_clip(title_text, hook_badge, total_duration):
    W, H = 1080, 1920
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_small = get_jp_font(34)
    hb = draw.textbbox((0, 0), hook_badge, font=font_small)
    hw, hh = hb[2] - hb[0], hb[3] - hb[1]
    h_box_w = max(440, hw + 80)
    h_box_x = (W - h_box_w) // 2
    draw.rounded_rectangle([h_box_x, 145, h_box_x + h_box_w, 205], radius=14, fill=(220, 38, 38, 255), outline=(255, 255, 255, 255), width=4)
    draw.text(((W - hw) // 2 - hb[0], 145 + (60 - hh) // 2 - hb[1]), hook_badge, font=font_small, fill=(255, 255, 255, 255))

    font = get_jp_font(54)
    wrapped = "\n".join([title_text[j:j+13] for j in range(0, len(title_text), 13)])
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=12, align="center")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    
    box_pad_x, box_pad_y = 48, 26
    box_w = min(W - 120, tw + box_pad_x * 2)
    box_h = th + box_pad_y * 2
    box_x = (W - box_w) // 2
    box_y = 224
    
    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=24,
        fill=(255, 215, 0, 250),
        outline=(0, 0, 0, 255),
        width=6,
    )
    
    tx = (W - tw) // 2 - bbox[0]
    ty = box_y + box_pad_y - bbox[1]
    draw.multiline_text(
        (tx, ty),
        wrapped,
        font=font,
        fill=(15, 15, 15, 255),
        spacing=12,
        align="center",
    )
    return ImageClip(np.array(img)).set_start(0).set_duration(total_duration)

def make_subtitle_clip(text, duration, start_time, total_duration, is_hook=False, is_conclusion=False):
    W, H = 1080, 1920
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_jp_font(62 if is_hook else 60)
    
    wrapped = "\n".join([text[j:j+11] for j in range(0, len(text), 11)])
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=18, align="center")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    
    center_x = 510
    center_y = H // 2 + 40

    if is_hook or is_conclusion:
        pad_x, pad_y = 44, 32
        box_w = tw + pad_x * 2
        box_h = th + pad_y * 2
        box_x1 = center_x - box_w // 2
        box_y1 = center_y - box_h // 2
        box_x2 = box_x1 + box_w
        box_y2 = box_y1 + box_h

        bg_c = (185, 28, 28, 220) if is_hook else (15, 23, 42, 225)
        border_c = (250, 204, 21, 255)
        draw.rounded_rectangle(
            [box_x1, box_y1, box_x2, box_y2],
            radius=24,
            fill=bg_c,
            outline=border_c,
            width=6,
        )

    tx = center_x - tw // 2 - bbox[0]
    ty = center_y - th // 2 - bbox[1]

    txt_fill = (255, 240, 0, 255) if (is_hook or is_conclusion) else (255, 255, 255, 255)
    draw.multiline_text(
        (tx, ty),
        wrapped,
        font=font,
        fill=txt_fill,
        stroke_width=8,
        stroke_fill=(0, 0, 0, 255),
        spacing=18,
        align="center",
    )

    progress = min(1.0, (start_time + duration * 0.5) / max(1.0, total_duration))
    draw.rectangle([0, 0, W, 16], fill=(30, 41, 59, 220))
    draw.rectangle([0, 0, int(W * progress), 16], fill=(250, 204, 21, 255))

    return ImageClip(np.array(img)).set_start(start_time).set_duration(duration)

def make_bgm_and_pop_sfx(total_duration, sfx_times):
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
                out[mask] = wave * 0.05

        for st in sfx_times:
            m = (t_arr >= st) & (t_arr < st + 0.18)
            if np.any(m):
                dt = t_arr[m] - st
                out[m] += np.sin(2 * np.pi * 880.0 * dt) * np.exp(-dt * 15) * 0.14

        stereo = np.column_stack([out, out])
        return stereo[0] if np.isscalar(t) else stereo

    return AudioClip(make_frame, duration=total_duration, fps=44100)

def add_video_to_playlist(youtube, video_id, playlist_title):
    try:
        playlists_res = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
        playlist_id = None
        for item in playlists_res.get("items", []):
            if item["snippet"]["title"] == playlist_title:
                playlist_id = item["id"]
                break
        if not playlist_id:
            create_res = youtube.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {"title": playlist_title, "description": f"{playlist_title}の連続再生リストです。"},
                    "status": {"privacyStatus": "public"},
                },
            ).execute()
            playlist_id = create_res["id"]
        youtube.playlistItems().insert(
            part="snippet",
            body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}},
        ).execute()
        print(f"再生リスト「{playlist_title}」へ追加完了")
    except Exception as pe:
        print(f"再生リスト追加スキップ: {pe}")

def post_engagement_comment(youtube, video_id, comment_text):
    try:
        youtube.commentThreads().insert(
            part="snippet",
            body={"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": comment_text}}}},
        ).execute()
        print("ショート動画へ誘導コメントを自動投稿しました！")
    except Exception as ce:
        print(f"コメント投稿スキップ: {ce}")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID") or os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET") or os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN") or os.environ.get("YOUTUBE_REFRESH_TOKEN")
TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET")
TIKTOK_REFRESH_TOKEN = os.environ.get("TIKTOK_REFRESH_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)

used_topics = load_used_topics()
ng_list_text = "、".join(used_topics) if used_topics else "なし"
print(f"投稿済みNGワード数: {len(used_topics)}件")

genres = [
    "科学・物理・化学の教科書や実験で証明されている有名な法則や現象",
    "動物の生態・生物学で学術的に確立されている意外な能力",
    "宇宙・惑星・気象のNASAや天文台で観測されている確実なデータ",
    "人体の仕組み・脳科学・睡眠に関する医学的に広く認められている事実",
    "日本の老舗企業や有名商品の公式ホームページ等で公開されている誕生秘話・社名の由来",
    "日本の法律・道路交通法・硬貨や紙幣の公式仕様に基づく意外な雑学",
    "国語辞典や漢字辞典に載っている言葉の語源・漢字の成り立ち",
    "心理学・行動経済学の教科書に載っている有名な実験",
    "食品・魚・料理の科学的な成分や調理のメカニズム",
    "オリンピックやプロスポーツの公式ルールブックに記載されている意外な規定",
]
selected_genre = random.choice(genres)
print(f"今回の抽選ジャンル: {selected_genre}")

prompt = f"""
あなたはYouTube ShortsとTikTokで100万再生を連発する雑学クリエイター兼ファクトチェッカーです。
100%事実に裏付けられた、最後まで見ずにいられないショート動画台本を1つ作成してください。

【今回の指定ジャンル】
「{selected_genre}」のテーマから、学術的・公式に事実と認められている具体的なトリビアを1つ選んでください。

【過去投稿済み・重複禁止リスト（絶対に使用禁止）】
以下のテーマ・対象・食材・生物・企業はすでに動画化済みのため、絶対に選ばないでください：
[玉ねぎ, ヒクイドリ, サメ, バナナ, エッフェル塔, {ng_list_text}]

【バズるショート構成の絶対ルール】
1. 都市伝説やデマは除外し、100%事実と断言できるネタだけを選ぶこと。
2. 1文目は視聴者のスクロールを止める強烈なフック（「9割が勘違いしている〇〇の真実」など）にすること。
3. 2文目で結論を明かし、3〜4文目で「なるほど！」と納得する科学的・公式な根拠をテンポよく語ること。
4. 必ず以下のJSON形式のみで出力すること。

{{
  "fact_check_note": "100%事実である科学的・歴史的・公式な根拠",
  "topic_keyword": "今回の主役キーワード（履歴保存用・10文字以内）",
  "hook_badge": "上部赤帯の短いバッジ（10文字以内 例: 9割が知らない事実）",
  "title": "画面上部に常時表示する短い見出し（18文字以内・ハッシュタグなし）",
  "description": "動画の説明文と関連ハッシュタグ4〜5個（#雑学 #豆知識 など）",
  "tags": ["雑学", "豆知識", "ショート", "トリビア", "教養", "解説"],
  "search_keyword": "背景動画検索用のシンプルな英単語1語",
  "script": [
    "1文目：スクロールを止める強烈なフック・疑問（18〜26文字）",
    "2文目：ズバリ結論となる具体的な事実の発表（20〜30文字）",
    "3文目：なぜそうなるのかの科学的・公式な根拠1（24〜34文字）",
    "4文目：さらに驚く具体的な数値・比較データ（24〜34文字）",
    "5文目：コメント欄で語りたくなる一言まとめ（18〜26文字）"
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
                    temperature=0.35,
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
hook_badge = data.get("hook_badge", "衝撃の事実")
topic_keyword = data.get("topic_keyword", title)
description = data["description"]
tags = data.get("tags", ["雑学", "豆知識", "Shorts", "トリビア"])
search_keyword = data["search_keyword"]
script_lines = data["script"]

print(f"生成完了: {title} (主役: {topic_keyword})")
save_used_topics([topic_keyword, title])

bg_video_path = "bg_video.mp4"
has_bg_video = False

if PEXELS_API_KEY:
    headers = {"Authorization": PEXELS_API_KEY}
    encoded_kw = urllib.parse.quote(search_keyword)
    PEXELS_BASE = clean_url("https://" + "api." + "pexels." + "com/videos/search")
    for query_url in [
        f"{PEXELS_BASE}?query={encoded_kw}&orientation=portrait&per_page=10",
        f"{PEXELS_BASE}?query=nature&orientation=portrait&per_page=10",
    ]:
        r = requests.get(query_url, headers=headers)
        if r.status_code != 200:
            break
        videos = r.json().get("videos", [])
        if videos:
            selected_video = random.choice(videos)
            video_files = selected_video["video_files"]
            hd_files = [f for f in video_files if f.get("width", 0) >= 720 and f.get("file_type") == "video/mp4"]
            download_url = hd_files[0]["link"] if hd_files else video_files[0]["link"]
            with open(bg_video_path, "wb") as f:
                f.write(requests.get(download_url).content)
            has_bg_video = True
            break

VOICE = "ja-JP-NanamiNeural"
audio_entries = []
current_time = 0.0

async def generate_tts(text, filename):
    communicate = edge_tts.Communicate(text, VOICE, rate="+18%", pitch="+5Hz")
    await communicate.save(filename)

for i, line in enumerate(script_lines):
    audio_file = f"part_{i}.mp3"
    asyncio.run(generate_tts(line, audio_file))
    a_clip = AudioFileClip(audio_file)
    duration = a_clip.duration + 0.14
    audio_entries.append({
        "index": i,
        "text": line,
        "start": current_time,
        "duration": duration,
        "audio_clip": a_clip.set_start(current_time),
    })
    current_time += duration

total_duration = current_time
clips = []
audio_clips = []
sfx_times = []

for ent in audio_entries:
    audio_clips.append(ent["audio_clip"])
    idx = ent["index"]
    if idx in (0, 1):
        sfx_times.append(ent["start"])
    clips.append(
        make_subtitle_clip(
            ent["text"],
            ent["duration"],
            ent["start"],
            total_duration,
            is_hook=(idx == 0),
            is_conclusion=(idx == 1),
        )
    )

bgm_clip = make_bgm_and_pop_sfx(total_duration, sfx_times)
final_audio = CompositeAudioClip(audio_clips + [bgm_clip])

if has_bg_video:
    bg_clip = VideoFileClip(bg_video_path).without_audio()
    bg_clip = bg_clip.loop(duration=total_duration) if bg_clip.duration < total_duration else bg_clip.subclip(0, total_duration)
    bg_clip = bg_clip.resize(height=1920)
    bg_clip = bg_clip.crop(x_center=bg_clip.w / 2, width=1080) if bg_clip.w > 1080 else bg_clip.resize(width=1080)
    dark_overlay = ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=total_duration).set_opacity(0.38)
    base_layers = [bg_clip, dark_overlay]
else:
    base_layers = [make_animated_bg(total_duration)]

header_clip = make_header_clip(title, hook_badge, total_duration)
output_video = "output_short.mp4"
final_video = CompositeVideoClip(base_layers + [header_clip] + clips).set_audio(final_audio)
final_video.write_videofile(output_video, fps=30, codec="libx264", audio_codec="aac")

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
        yt_description = f"{description}\n\n🤖 最新AIトレンド＆ツール比較データベース「AI Tech Hub」\nhttps://banjoblog.github.io/auto-blog/"
        body = {
            "snippet": {
                "title": f"{title} #Shorts",
                "description": yt_description,
                "tags": tags,
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(output_video, chunksize=-1, resumable=True, mimetype="video/mp4")
        yt_res = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
        video_id = yt_res.get("id")
        print(f"YouTube アップロード完了！ Video ID: {video_id}")
        if video_id:
            add_video_to_playlist(youtube, video_id, "【1分雑学】ショート動画まとめ")
            post_engagement_comment(
                youtube,
                video_id,
                "この雑学は知っていましたか？感想をぜひコメント欄で教えてください！👇\n"
                "▼ 5〜8分の本格解説まとめ動画もチャンネルページで毎日公開中！",
            )
    except Exception as e:
        print(f"YouTube アップロードエラー: {e}")

if TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET and TIKTOK_REFRESH_TOKEN:
    try:
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
        TIKTOK_DIRECT_URL = clean_url("https://" + "open." + "tiktokapis." + "com/v2/post/publish/video/init/")

        init_res = {}
        for privacy in ["PUBLIC_TO_EVERYONE", "SELF_ONLY"]:
            init_res = requests.post(
                TIKTOK_DIRECT_URL,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={
                    "post_info": {
                        "title": f"{title} {description}"[:150],
                        "privacy_level": privacy,
                        "disable_duet": False,
                        "disable_comment": False,
                        "disable_stitch": False,
                    },
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": video_size,
                        "chunk_size": video_size,
                        "total_chunk_count": 1,
                    },
                },
            ).json()
            if init_res.get("data", {}).get("upload_url"):
                print(f"TikTok 公開モード: {privacy} で初期化成功")
                break

        if not init_res.get("data", {}).get("upload_url"):
            TIKTOK_INBOX_URL = clean_url("https://" + "open." + "tiktokapis." + "com/v2/post/publish/inbox/video/init/")
            init_res = requests.post(
                TIKTOK_INBOX_URL,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={"source_info": {"source": "FILE_UPLOAD", "video_size": video_size, "chunk_size": video_size, "total_chunk_count": 1}},
            ).json()

        upload_url = init_res.get("data", {}).get("upload_url")
        publish_id = init_res.get("data", {}).get("publish_id")
        if upload_url:
            with open(output_video, "rb") as vf:
                video_bytes = vf.read()
            requests.put(
                upload_url,
                headers={"Content-Range": f"bytes 0-{video_size - 1}/{video_size}", "Content-Type": "video/mp4"},
                data=video_bytes,
            )
            STATUS_URL = clean_url("https://" + "open." + "tiktokapis." + "com/v2/post/publish/status/fetch/")
            for _ in range(6):
                time.sleep(5)
                status_res = requests.post(
                    STATUS_URL,
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"publish_id": publish_id},
                ).json()
                if status_res.get("data", {}).get("status") in ["SEND_TO_USER_INBOX", "PUBLISH_COMPLETE", "FAILED"]:
                    print(f"TikTok 投稿ステータス: {status_res.get('data', {}).get('status')}")
                    break
    except Exception as e:
        print(f"TikTok アップロードエラー: {e}")
