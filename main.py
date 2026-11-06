import os
import google.generativeai as genai

# Gemini APIキーの取得
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

def generate_article():
    # 動作確認済みのモデル候補を順に試行
    candidate_models = [
        'gemini-1.5-flash',
        'gemini-2.0-flash',
        'gemini-1.5-pro',
        'gemini-pro'
    ]
    
    prompt = """
    最新のテクノロジー、AI、ガジェット、または効率化テクニックに関する興味深いトレンドニュース記事を1つ執筆してください。
    
    【構成要件】
    1. 1行目: 読者の目を引く魅力的な記事タイトル（「タイトル: 〇〇」の形式）
    2. 本文: 導入、主要なポイント（見出し付き）、まとめの構成
    3. 文字数: 1200字〜1500字程度
    4. 読者にとって役立つ実用的な情報を含めること
    5. 自然で読みやすい日本語で書くこと
    """
    
    last_exception = None
    for model_name in candidate_models:
        try:
            print(f"モデル '{model_name}' で生成を試みています...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            print(f"成功: モデル '{model_name}' が使用されました。")
            return response.text
        except Exception as e:
            print(f"失敗: モデル '{model_name}' ({e})")
            last_exception = e
            
    raise last_exception

def main():
    print("AI記事作成を開始します...")
    article = generate_article()
    
    lines = article.strip().split('\n')
    title = "AIテクノロジートレンドニュース"
    for line in lines:
        if line.startswith("タイトル:"):
            title = line.replace("タイトル:", "").strip()
            break
            
    print("==========================================")
    print(f"■ タイトル: {title}")
    print("■ 本文プレビュー:")
    print(article[:300] + "...")
    print("==========================================")
    print("AI記事の生成が正常に完了しました！")

if __name__ == "__main__":
    main()
