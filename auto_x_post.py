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
X_API_KEY = os.environ.get("X_API_KEY")
X_API_SECRET = os.environ.get("X_API_SECRET")
X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET")

client = genai.Client(api_key=GEMINI_API_KEY)
used_topics = load_used_topics()
ng_list_text = "、".join(used_topics[-80:]) if used_topics else "なし"

genres = [
    "科学・物理・化学の実験で証明されている驚くべき法則",
    "動物の生態・生物学で学術的に確立されている意外な能力",
    "宇宙・惑星・気象のNASAや天文台で観測されている確実な事実",
    "人体の仕組み・脳科学・睡眠に関する医学的に認められている雑学",
    "日本の老舗企業や有名商品の公式に公開されている誕生秘話・社名の由来",
    "日本の法律・道路交通法・硬貨や紙幣の公式仕様に基づく意外な雑学",
    "心理学・行動経済学の教科書に載っている有名な実験",
    "食べ物・料理の科学的な成分や調理のメカニズム",
    "日本語の語源・漢字の成り立ち・身近な言葉の意外な由来",
]
selected_genre = random.choice(genres)

prompt = f"""
あなたはX（旧Twitter）で毎回1万いいねを獲得する雑学アカウントの運用者です。
「{selected_genre}」のジャンルから、100%事実と認められている「思わずリポストしたくなる雑学」を1つ作成してください。

【使用禁止リスト（過去投稿済み）】
[{ng_list_text}]

【バズるポスト作成の厳守ルール】
1. 外部URLは一切入れないこと（純粋なテキストのみで完結させる）。
2. 1行目でスクロールを止める強烈なフック（「9割が勘違いしている〇〇の真実」「実は〇〇って、△△なんです」など）を入れること。
3. 改行や箇条書き（・）を適度に使い、スマホでパッと見やすいレイアウトにすること。
4. 全体で【全角125文字以内】（ハッシュタグ1〜2個込み）に必ず収めること。
5. 以下のJSON形式のみで出力すること。

{{
  "topic_keyword": "主役キーワード（10文字以内）",
  "tweet_text": "そのままXに投稿する完成テキスト（125文字以内）"
}}
"""

data = None
for model in ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]:
    for attempt in range(3):
        try:
            res = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.5,
                ),
            )
            data = json.loads(res.text)
            break
        except Exception as e:
            print(f"{model} エラー、リトライ ({attempt+1}/3): {e}")
            time.sleep(8)
    if data:
        break

if not data:
    raise RuntimeError("Geminiでのポスト生成に失敗しました。")

topic_keyword = data.get("topic_keyword", "X雑学")
tweet_text = data["tweet_text"].strip()

if len(tweet_text) > 138:
    tweet_text = tweet_text[:135] + "…"

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
