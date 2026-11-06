import os
import google.generativeai as genai

# Gemini APIキーの取得
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BLOGGER_EMAIL = os.environ.get("BLOGGER_EMAIL")

genai.configure(api_key=GEMINI_API_KEY)

def generate_article():
    # 利用可能なモデル（gemini-1.5-flash-latest または gemini-2.0-flash など）を使用
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
    except Exception:
        model = genai.GenerativeModel('gemini-pro')
    
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

def main():
    print("AI記事作成を開始します...")
    article = generate_article()
    
    lines = article.strip().split('\n')
    title = "AIテクノロジートレンドニュース"
    for line in lines:
        if line.startswith("タイトル:"):
            title = line.replace("タイトル:", "").strip()
            break
            
    print("--- 生成成功 ---")
    print(f"タイトル: {title}")
    print("本文プレビュー:")
    print(article[:200] + "...")

if __name__ == "__main__":
    main()
