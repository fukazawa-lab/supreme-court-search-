import gradio as gr
import openai
import requests
import json
import re
import time
from typing import List, Tuple, Dict
from google.colab import userdata

# ================================================
# 2. API設定
# ================================================

# Colab Secretsから取得 (左サイドバーの🔑アイコンで設定)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.environ.get("SEARCH_ENGINE_ID")

# OpenAI設定
openai.api_key = OPENAI_API_KEY

# ================================================
# 3. 法的背景分析機能
# ================================================

def analyze_legal_context(user_query: str) -> str:
    """
    第1段階: ユーザークエリから法的背景を分析
    """
    try:
        system_prompt = """
あなたは法律実務の専門家です。
与えられた法律問題について、以下の形式で法的背景を分析してください：

【関連法条文】
・該当する法律名と条文番号

【主要な法的概念】
・重要な法律用語や概念

【実務上の争点】
・実際の裁判でよく争われるポイント

簡潔で実務的な回答をしてください。
        """

        user_prompt = f"以下の法律問題について分析してください：\n\n{user_query}"

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=500,
            temperature=0.3
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"❌ OpenAI API エラー (法的背景分析): {str(e)}"

# ================================================
# 4. 検索キーワード生成機能
# ================================================

def generate_search_keywords(user_query: str, legal_context: str) -> str:
    """
    第2段階: 法的背景をもとに検索キーワードを生成
    """
    try:
        system_prompt = """
あなたは最高裁判例検索の専門家です。
法的背景分析の結果をもとに、最高裁判例検索に最適なキーワードを生成してください。

要件：
- 5-8個の重要なキーワード
- 実際の判例文で使われる専門用語を使用
- 検索効率を最大化する組み合わせ
- キーワードはスペース区切りで出力

出力例：交通事故 過失割合　
        """

        user_prompt = f"""
元のクエリ：{user_query}

法的背景分析：
{legal_context}

上記をもとに検索キーワードを生成してください。
        """

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=200,
            temperature=0.3
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"❌ OpenAI API エラー (キーワード生成): {str(e)}"

# ================================================
# 5. Google検索機能（修正版）
# ================================================

def search_supreme_court_cases(keywords: str) -> List[Dict]:
    """
    Google Custom Search APIで最高裁判例を検索（修正版）
    """
    try:
        # courts.go.jp/app/files/hanrei_jp配下を検索対象に指定
        search_query = f"site:www.courts.go.jp/assets/hanrei/ {keywords}"
        print(search_query)

        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': GOOGLE_API_KEY,
            'cx': SEARCH_ENGINE_ID,
            'q': search_query,
            'num': 10,  # 最大10件
            'lr': 'lang_ja',
            'safe': 'active'
        }

        response = requests.get(url, params=params)
        print("🔹 Google APIステータスコード:", response.status_code)

        response.raise_for_status()
        data = response.json()

        results = []
        if 'items' in data:
            for item in data['items']:
                results.append({
                    'title': item.get('title', 'タイトルなし'),
                    'link': item.get('link', ''),
                    'snippet': item.get('snippet', '')
                })
        else:
            print("❌ 検索結果はありませんでした")

        return results

    except requests.RequestException as e:
        print(f"❌ Google Search API エラー: {str(e)}")
        return []
    except Exception as e:
        print(f"❌ 検索エラー: {str(e)}")
        return []

# ================================================
# 6. 判例整形機能
# ================================================

def format_case_results(search_results: List[Dict], user_query: str) -> str:
    """
    第3段階: 検索結果を書誌情報形式に整形
    """
    if not search_results:
        return "❌ 関連する最高裁判例が見つかりませんでした。"

    try:
        # 検索結果をテキストにまとめる
        results_text = "\n".join([
            f"タイトル: {item['title']}\nURL: {item['link']}\n概要: {item['snippet']}\n---"
            for item in search_results[:10]  # 最大10件
        ])

        system_prompt = """
あなたは法律判例の書誌情報整理の専門家です。
Google検索結果から最高裁判例を抽出し、以下の形式で出力してください：

出力形式：
最判平成○年○月○日・民集○巻○号○頁
URL: https://www.courts.go.jp/app/files/hanrei_jp/...

要件：
- 最も関連度の高い判例を優先（最大10件）
- 関連度順に並べる
- 各判例に対応するURLを必ず含める
- 書誌情報が不完全な場合は可能な範囲で表示
- 最高裁判例以外は除外
- 判例が見つからない場合は「該当する判例が見つかりませんでした」

必ずタイトルとURLをセットで出力してください。
ユーザークエリとの関連性を考慮して判断してください。
        """

        user_prompt = f"""
ユーザークエリ：{user_query}

Google検索結果：
{results_text}

上記から関連性の高い最高裁判例を抽出し、書誌情報形式で出力してください。
各判例について、タイトル（書誌情報）とURLを必ずセットで表示してください。

例：
最判平成○年○月○日・民集○巻○号○頁
URL: https://www.courts.go.jp/app/files/hanrei_jp/xxx
        """

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=1000,  # URLも含むので少し増量
            temperature=0.2
        )

        formatted_result = response.choices[0].message.content.strip()

        # 万が一URLが含まれていない場合のバックアップ処理
        if "URL:" not in formatted_result and search_results:
            backup_output = []
            for i, result in enumerate(search_results[:5]):  # 上位5件のみ
                backup_output.append(f"""
判例{i+1}: {result['title']}
URL: {result['link']}
""")
            formatted_result += "\n\n--- 参考URL ---\n" + "\n".join(backup_output)

        return formatted_result

    except Exception as e:
        return f"❌ OpenAI API エラー (結果整形): {str(e)}"

# ================================================
# 7. メイン検索機能（修正版）
# ================================================

def legal_case_search(user_query: str) -> Tuple[str, str, str, str]:
    """
    統合検索機能：全ての処理を順次実行
    """
    if not user_query.strip():
        return "❌ クエリを入力してください", "", "", ""

    # 段階的処理の実行
    print("🔍 法的背景を分析中...")
    legal_context = analyze_legal_context(user_query)

    if "❌" in legal_context:
        return legal_context, "", "", ""

    time.sleep(1)  # API制限回避

    print("🎯 検索キーワードを生成中...")
    keywords = generate_search_keywords(user_query, legal_context)

    if "❌" in keywords:
        return legal_context, keywords, "", ""

    time.sleep(1)  # API制限回避

    print("📚 最高裁判例を検索中...")
    search_results = search_supreme_court_cases(keywords)

    # 検索結果が0件でもエラー扱いせず0件として返す
    search_count_info = f"検索件数: {len(search_results)}件 \n ここからOPENAIに入れて最高裁判例を抽出するため減ります。"

    time.sleep(1)  # API制限回避

    print("📋 結果を整形中...")
    formatted_results = format_case_results(search_results, user_query)

    return legal_context, keywords, search_count_info, formatted_results


# ================================================
# 8. Gradio インターフェース
# ================================================

def create_interface():
    """
    Gradio UIを作成
    """

    with gr.Blocks(title="最高裁判例検索システム - MVP版") as interface:

        gr.Markdown("# 📚 最高裁判例検索システム (MVP版)")
        gr.Markdown("法律実務者向け - 自然言語クエリから関連判例を検索")

        with gr.Row():
            with gr.Column():
                # 入力部分
                input_query = gr.Textbox(
                    label="法律問題を入力してください",
                    placeholder="例：交通事故の損害賠償について",
                    lines=3
                )

                search_button = gr.Button("🔍 判例検索実行", variant="primary")

            with gr.Column():
                # 出力部分
                legal_context_output = gr.Textbox(
                    label="📋 法的背景分析",
                    lines=8,
                    interactive=False
                )

                keywords_output = gr.Textbox(
                    label="🎯 生成されたキーワード",
                    lines=2,
                    interactive=False
                )

                search_info_output = gr.Textbox(
                    label="📊 検索情報",
                    lines=1,
                    interactive=False
                )

                results_output = gr.Markdown(
                    label="⚖️ 最高裁判例（関連度順）"
                )


        # イベントハンドリング
        search_button.click(
            fn=legal_case_search,
            inputs=[input_query],
            outputs=[legal_context_output, keywords_output, search_info_output, results_output]
        )

        # サンプル用
        gr.Markdown("### 💡 使用例")
        gr.Markdown("- 交通事故の損害賠償について\n- 離婚における慰謝料の算定\n- 契約違反による損害賠償請求")

    return interface

# ================================================
# 9. 実行部分
# ================================================

if __name__ == "__main__":

    print("🚀 システム起動中...")

    # API キーの確認
    if not all([OPENAI_API_KEY, GOOGLE_API_KEY, SEARCH_ENGINE_ID]):
        print("❌ エラー: APIキーが設定されていません")
        print("Colab Secretsに以下を設定してください：")
        print("- OPENAI_API_KEY")
        print("- GOOGLE_API_KEY")
        print("- SEARCH_ENGINE_ID")
    else:
        print("✅ APIキー確認完了")

        # インターフェース起動
        interface = create_interface()
        interface.launch(
            share=True,  # 外部アクセス可能なリンク生成
            debug=True   # デバッグモード
        )
