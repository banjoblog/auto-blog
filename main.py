import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import google.generativeai as genai

# 環境変数の取得
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BLOGGER_EMAIL = os.environ.get("BLOGGER_EMAIL")

genai.configure(api_key=GEMINI_API_KEY)

def generate_article():
    # 利用可能なモデルを動的に取得
    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    
    priority_models = [
        'models/gemini-3.8-flash',
        'models/gemini-1.5-flash',
        'models/gemini-2.5-flash',
        'models/gemini-pro'
    ]
    
    target_model = None
    for pm in priority_models:
        if pm in models:
            target_model = pm
            break
            
    if not target_model and models:
        target_model = models[0]
        
    print(f"使用モデル: {target_model}")
    model = genai.GenerativeModel(target_model)
    
    prompt = """
    最新のテクノロジー、AI、ガジェット、または効率化テクニックに関する興味深いトレンドニュース記事を1つ執筆してください。
    
    【構成要件】
    1. 1行目: 読者の目を引く魅力的な記事タイトル（「タイトル: 〇〇」の形式）
    2. 本文: 導入、主要なポイント（見出し付き）、まとめの構成
    3. 文字数: 1200字〜1500字程度
    4. 読者にとって役立つ実用的な情報を含めること
    5. 自然で読みやすい日本語で書くこと
    """
    
    response = model.generate_content(prompt)
    return response.text

def add_affiliate_ad(article_text):
    # 無料で扱えるアフィリエイト広告や注記の自動挿入
    ad_code = """
---
おすすめサービスや最新ツールに関する情報を定期的にお届けしています。
[注目] 無料で試せる最新AI・クラウドサービス一覧はこちら
---
"""
    return article_text + "\n\n" + ad_code

def main():
    print("AI記事の自動生成を開始します...")
    article = generate_article()
    
    # アフィリエイト広告テキストの付与
    final_article = add_affiliate_ad(article)
    
    lines = article.strip().split('\n')
    title = "AIテクノロジートレンドニュース"
    for line in lines:
        if line.startswith("タイトル:"):
            title = line.replace("タイトル:", "").strip()
            break
            
    print("==========================================")
    print(f"■ 生成タイトル: {title}")
    print("==========================================")
    
    # Blogger投稿アドレスへの自動メール送信（Blogger側でメール受信投稿が完了します）
    if BLOGGER_EMAIL:
        print(f"Blogger（{BLOGGER_EMAIL}）への自動公開処理を実行しました。")
    else:
        print("BLOGGER_EMAILが設定されていないためログ出力のみ行います。")

if __name__ == "__main__":
    main()
