# 最高裁判例検索システム - GitHub版 (MVP)
# Google Custom Search + OpenAI + Gradio

import os
import gradio as gr
import openai
import requests
import time
from typing import List, Tuple, Dict

# ================================================
# 1. API設定
# ================================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.environ.get("SEARCH_ENGINE_ID")

openai.api_key = OPENAI_API_KEY


# ================================================
# 2. 法的背景分析
# ================================================

def analyze_legal_context(user_query: str) -> str:
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

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"以下の法律問題について分析してください：\n\n{user_query}"}
            ],
            max_tokens=500,
            temperature=0.3
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"❌ OpenAI API エラー (法的背景分析): {str(e)}"


# ================================================
# 3. 検索キーワード生成
# ================================================

def generate_search_keywords(user_query: str, legal_context: str) -> str:
    try:
        system_prompt = """
あなたは最高裁判例検索の専門家です。
法的背景分析の結果をもとに、最高裁判例検索に最適なキーワードを生成してください。

要件：
- 5-8個の重要キーワード
- 判例文で使われる法律用語を優先
- 日本語、スペース区切り
"""

        user_prompt = f"元のクエリ：{user_query}\n\n法的背景分析：\n{legal_context}"

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
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
# 4. Google Custom Search（修正版）
# ================================================

def search_supreme_court_cases(keywords: str) -> List[Dict]:

    try:
        # ★ GitHub版として修正：正しいディレクトリを検索
        search_query = f"site:www.courts.go.jp/app/files/hanrei_jp/ {keywords}"
        print(f"🔍 Search Query: {search_query}")

        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": GOOGLE_API_KEY,
            "cx": SEARCH_ENGINE_ID,
            "q": search_query,
            "num": 10,
            "lr": "lang_ja"
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if "items" not in data:
            return []

        results = []
        for item in data["items"]:
            results.append({
                "title": item.get("title", "タイトルなし"),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", "")
            })

        return results

    except Exception as e:
        print(f"❌ Google Search API error: {str(e)}")
        return []


# ================================================
# 5. 判例整形（LLM）
# ================================================

def format_case_results(search_results: List[Dict], user_query: str) -> str:

    if not search_results:
        return "❌ 関連する最高裁判例が見つかりませんでした。"

    results_text = "\n".join([
        f"タイトル: {item['title']}\nURL: {item['link']}\n概要: {item['snippet']}\n---"
        for item in search_results[:10]
    ])

    try:
        system_prompt = """
あなたは法律判例整理の専門家です。
Google検索結果をもとに、最高裁判例の書誌情報を作成します。

出力形式：
最判平成○年○月○日・民集○巻○号○頁
URL: https://www.courts.go.jp/app/files/hanrei_jp/...

要件：
- 関連度順に最大10件
- 必ずURLを含める
- 不完全なら推定で補う
"""

        user_prompt = f"ユーザークエリ：{user_query}\n\n検索結果：\n{results_text}"

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=1200,
            temperature=0.2
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"❌ OpenAI API エラー (整形): {str(e)}"


# ================================================
# 6. メイン処理
# ================================================

def legal_case_search(user_query: str) -> Tuple[str, str, str, str]:

    if not user_query.strip():
        return "❌ クエリを入力してください", "", "", ""

    legal_context = analyze_legal_context(user_query)
    if "❌" in legal_context:
        return legal_context, "", "", ""

    time.sleep(1)
    keywords = generate_search_keywords(user_query, legal_context)

    time.sleep(1)
    search_results = search_supreme_court_cases(keywords)
    search_info = f"検索件数: {len(search_results)}件 \n ここからOPENAIに入れて最高裁判例を抽出するため減ります。"

    time.sleep(1)
    formatted_results = format_case_results(search_results, user_query)

    return legal_context, keywords, search_info, formatted_results


# ================================================
# 7. Gradio Interface
# ================================================

def create_interface():

    with gr.Blocks(title="最高裁判例検索システム") as interface:

        gr.Markdown("# ⚖️ 最高裁判例検索システム (GitHub版)")
        gr.Markdown("自然言語 → 判例検索 → 書誌情報まで自動生成")

        with gr.Row():
            with gr.Column():
                q = gr.Textbox(label="法律問題を入力", lines=3)
                btn = gr.Button("🔍 判例検索", variant="primary")

            with gr.Column():
                out1 = gr.Textbox(label="📋 法的背景分析", lines=8)
                out2 = gr.Textbox(label="🎯 キーワード")
                out3 = gr.Textbox(label="📊 検索件数")
                out4 = gr.Markdown(label="結果")

        btn.click(legal_case_search, inputs=[q], outputs=[out1, out2, out3, out4])

    return interface


if __name__ == "__main__":
    interface = create_interface()
    interface.launch(server_name="0.0.0.0", server_port=7860)
