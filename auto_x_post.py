import os
import json
import time
import random
import tweepy
from google import genai
from google.genai import types

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
    topics = topics[-250:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
X_API_KEY = (os.environ.get("X_API_KEY") or "").strip()
X_API_SECRET = (os.environ.get("X_API_SECRET") or "").strip()
X_ACCESS_TOKEN = (os.environ.get("X_ACCESS_TOKEN") or "").strip()
X_ACCESS_TOKEN_SECRET = (os.environ.get("X_ACCESS_TOKEN_SECRET") or "").strip()

client = genai.Client(api_key=GEMINI_API_KEY)
used_topics = load_used_topics()
ng_list_text = "、".join(used_topics[-80:]) if used_topics else "なし"

def call_gemini_json(prompt_text):
    for model in ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]:
        for attempt in range(3):
            try:
                res = client.models.generate_content(
                    model=model,
                    contents=prompt_text,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.3,
                    ),
                )
                return json.loads(res.text)
            except Exception as e:
                print(f"{model} エラー、リトライ ({attempt+1}/3): {e}")
                time.sleep(8)
    raise RuntimeError("Geminiでの生成に失敗しました。")

genres = [
    "科学・物理・化学の実験で証明されている驚くべき法則",
    "動物の生態・生物学で学術的に確立されている意外な能力",
    "宇宙・惑星・気象のNASAや天文台で観測されている確実な事実",
    "人体の仕組み・脳科学・睡眠に関する医学的に認められている雑学",
    "日本の老舗企業や有名商品の公式に公開されている誕生秘話・社名の由来",
    "心理学・行動経済学の教科書に載っている有名な実験",
    "食べ物・料理の科学的な成分や調理のメカニズム",
    "日本語の語源・漢字の成り立ち・身近な言葉の意外な由来",
]
selected_genre = random.choice(genres)

# ステップ1：100%正確な事実の確定
fact_prompt = f"""
あなたは厳格なファクトチェッカーです。
「{selected_genre}」のジャンルから、教科書や公式資料で100%事実と証明されている「誰かに話したくなる雑学」を1つ厳選してください。

【使用禁止リスト】
[{ng_list_text}]

【注意】都市伝説や国によって異なる曖昧なルールは絶対に除外し、確実な事実だけを選ぶこと。
以下のJSON形式のみで出力してください。

{{
  "topic_keyword": "主役キーワード（10文字以内）",
  "verified_fact": "100%正確な事実と理由の要約（100文字以内）"
}}
"""

fact_data = call_gemini_json(fact_prompt)
topic_keyword = fact_data.get("topic_keyword", "X雑学")
verified_fact = fact_data["verified_fact"]

# ステップ2：X向けに文字数オーバーせず綺麗に完結するポストを作成
tweet_prompt = f"""
以下の【検証済みの事実】だけを使って、X（旧Twitter）でリポストしたくなる短い雑学ポストを作成してください。

【検証済みの事実】
{verified_fact}

【厳守ルール】
1. 外部URLは一切入れないこと。
2. 1行目に「実は〇〇って、△△なんです。」のような惹きつける見出しを入れること。
3. 途中で文字が切れないよう、ハッシュタグ（#雑学 #豆知識）を含めて【必ず全体で110文字以内】にスッキリ収めること。
4. 以下のJSON形式のみで出力すること。

{{
  "tweet_text": "110文字以内の完成ポスト"
}}
"""

tweet_data = call_gemini_json(tweet_prompt)
tweet_text = tweet_data["tweet_text"].strip()

print(f"生成されたポスト（{len(tweet_text)}文字）:\n{tweet_text}")

x_client = tweepy.Client(
    consumer_key=X_API_KEY,
    consumer_secret=X_API_SECRET,
    access_token=X_ACCESS_TOKEN,
    access_token_secret=X_ACCESS_TOKEN_SECRET,
)
response = x_client.create_tweet(text=tweet_text)
print(f"X（Twitter）自動ポスト完了！ Tweet ID: {response.data['id']}")

save_used_topics([topic_keyword])
