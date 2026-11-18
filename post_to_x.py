import os
import sys
import tweepy
from google import genai
from google.genai import types

def post_video_to_x(video_type, title, summary, video_url):
    api_key = os.environ.get("X_API_KEY")
    api_secret = os.environ.get("X_API_SECRET")
    access_token = os.environ.get("X_ACCESS_TOKEN")
    access_token_secret = os.environ.get("X_ACCESS_TOKEN_SECRET")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if not all([api_key, api_secret, access_token, access_token_secret]):
        print("X APIキーが未設定のため、X投稿をスキップします。")
        return

    client = genai.Client(api_key=gemini_key)
    prompt = f"""
以下のYouTube動画（{video_type}）をX（旧Twitter）で宣伝する投稿文を作成してください。

【動画タイトル】{title}
【内容要約】{summary}

【厳守ルール】
1. 1行目でスクロールを止めるフック（「9割が勘違いしてる〇〇の真実…」など）を入れること。
2. URL（23文字換算）を末尾に付けるため、本文＋ハッシュタグ（2個まで）は必ず【全角100文字以内】に収めること。
3. URL自体は出力に含めず、本文とハッシュタグのみをプレーンテキストで出力すること。
"""
    try:
        res = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.5),
        )
        post_body = res.text.strip().replace('"', '')
    except Exception as e:
        print(f"Geminiポスト生成エラー（フォールバック文を使用）: {e}")
        post_body = f"【新着{video_type}】{title}\n思わず誰かに話したくなる雑学を解説しました！👇 #雑学 #豆知識"

    if len(post_body) > 105:
        post_body = post_body[:102] + "…"

    final_tweet = f"{post_body}\n{video_url}"

    try:
        x_client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        response = x_client.create_tweet(text=final_tweet)
        print(f"X（Twitter）自動ポスト完了！ Tweet ID: {response.data['id']}")
    except Exception as xe:
        print(f"X 投稿エラー: {xe}")

if __name__ == "__main__":
    if len(sys.argv) >= 5:
        post_video_to_x(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
