import os
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

def generate_article():
    # 利用可能な最新モデルを動的に取得
    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    print(f"利用可能なモデル一覧: {models}")
    
    # 優先的に試すモデルリスト
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
        
    print(f"選択されたモデル: {target_model}")
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
