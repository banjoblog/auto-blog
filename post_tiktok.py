import os
import sys
import math
import json
import requests

TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()
TIKTOK_REFRESH_TOKEN = os.environ.get("TIKTOK_REFRESH_TOKEN", "").strip()


def refresh_access_token():
    url = "https://open.tiktokapis.com/v2/oauth/token/"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": TIKTOK_REFRESH_TOKEN,
    }
    res = requests.post(url, headers=headers, data=data, timeout=30)
    res_json = res.json()
    if "access_token" not in res_json:
        raise RuntimeError(f"TikTok トークン更新失敗: {res_json}")
    return res_json["access_token"]


def upload_video_to_tiktok(video_path, title_text):
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")

    access_token = refresh_access_token()
    video_size = os.path.getsize(video_path)

    # 10MB単位でチャンク分割計算（64MB未満なら1チャンクで送信）
    chunk_size = min(video_size, 10 * 1024 * 1024) if video_size > 64 * 1024 * 1024 else video_size
    total_chunk_count = math.ceil(video_size / chunk_size)

    caption = f"{title_text} #雑学 #豆知識 #教養 #クイズ"[:150]

    # まず Direct Post（直接投稿）を試行し、未審査アプリ制限時は Inbox（下書き通知）へ自動フォールバック
    endpoints = [
        (
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            {
                "post_info": {
                    "title": caption,
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": total_chunk_count,
                },
            },
        ),
        (
            "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
            {
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": total_chunk_count,
                }
            },
        ),
    ]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    init_data = None
    used_mode = "direct"
    for idx, (ep_url, payload) in enumerate(endpoints):
        res = requests.post(ep_url, headers=headers, json=payload, timeout=30)
        res_json = res.json()
        err_code = res_json.get("error", {}).get("code", "")
        if err_code == "ok" and "data" in res_json:
            init_data = res_json["data"]
            used_mode = "direct" if idx == 0 else "inbox"
            break
        else:
            print(f"TikTok init ({'direct' if idx == 0 else 'inbox'}) 応答: {res_json}")

    if not init_data:
        raise RuntimeError("TikTok 動画アップロード初期化に失敗しました。")

    upload_url = init_data["upload_url"]
    publish_id = init_data.get("publish_id", "")

    with open(video_path, "rb") as f:
        for chunk_idx in range(total_chunk_count):
            start_byte = chunk_idx * chunk_size
            chunk_bytes = f.read(chunk_size)
            end_byte = start_byte + len(chunk_bytes) - 1
            up_headers = {
                "Content-Type": "video/mp4",
                "Content-Length": str(len(chunk_bytes)),
                "Content-Range": f"bytes {start_byte}-{end_byte}/{video_size}",
            }
            up_res = requests.put(upload_url, headers=up_headers, data=chunk_bytes, timeout=120)
            if up_res.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok チャンクアップロード失敗: {up_res.status_code} {up_res.text}")

    print(f"TikTok 投稿完了！ (mode={used_mode}, publish_id={publish_id})")


if __name__ == "__main__":
    v_path = sys.argv[1] if len(sys.argv) > 1 else "short_output.mp4"
    v_title = sys.argv[2] if len(sys.argv) > 2 else "今日の雑学"
    upload_video_to_tiktok(v_path, v_title)
