from openai import OpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from googlesearch import search
from bs4 import BeautifulSoup
import requests
import re
import json
from mongo_history import MongoHistoryManager


MODEL = json.loads(open("config.json", "r").read())["model"]
PROMPT = open("prompt.txt", "r").read()
secret = json.loads(open("secret.json", "r").read())

class IntelligentChatAssistant:
    def __init__(self, search_depth=5):
        self.client = OpenAI(
            api_key=secret["openai"]
        )
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", PROMPT),
                MessagesPlaceholder(variable_name="chat_history"),
                ("user", "{input}"),
            ]
        )
        self.llm = ChatOpenAI(
            model=MODEL, api_key=secret["openai"]
        )
        self.search_depth = search_depth
        self.search_cache = {}
        self.history_manager = MongoHistoryManager()

    def _get_session_id(self, source_type, user_id, group_id=None, room_id=None):
        """根據來源類型生成會話ID"""
        if source_type == "user":
            return f"user_{user_id}"
        elif source_type == "group" and group_id:
            return f"group_{group_id}_user_{user_id}"
        elif source_type == "room" and room_id:
            return f"room_{room_id}_user_{user_id}"
        return f"default_{user_id}"  # 預設情況

    def _web_search(self, query):
        # 保持原有搜尋邏輯
        try:
            search_results = list(search(query, num_results=self.search_depth))
            summaries = []

            for url in search_results:
                if url in self.search_cache:
                    summaries.append(self.search_cache[url])
                    continue

                response = requests.get(url, timeout=10)
                soup = BeautifulSoup(response.text, "html.parser")
                text = soup.get_text()
                clean_text = re.sub(r"\s+", " ", text)[:5000]

                summary = self.client.responses.create(
                    model=MODEL,
                    instructions="請用繁體中文總結以下內容，限制在300字內",
                    input=clean_text,
                ).output_text

                self.search_cache[url] = summary
                summaries.append(summary)

            return "\n\n".join(summaries)

        except Exception as e:
            print(f"搜尋錯誤: {str(e)}")
            return None

    def send_query(self, event, user_input, image_data=None):
        """處理用戶查詢，整合MongoDB歷史記錄"""
        # 生成會話ID
        source_type = event.source.type
        user_id = event.source.user_id
        group_id = getattr(event.source, "group_id", None)
        room_id = getattr(event.source, "room_id", None)

        session_id = self._get_session_id(source_type, user_id, group_id, room_id)

        # 獲取歷史記錄
        chat_history = self.history_manager.get_history(session_id)
        history_messages = self.history_manager.get_messages_as_dict(session_id)
        messages = [{"role": "system", "content": PROMPT}]
        
        # 圖
        if image_data:
            # o4-mini多模態推理
            messages = [{"role": "system", "content": PROMPT}]
            messages += history_messages
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": """你必須遵守以下規則：
                                            1. 無論影像內容是否可辨識，必須提供至少50字回應
                                            2. 若無法辨識主要物件，需描述色彩、構圖等基本特徵
                                            3. 完全無法分析時，建議使用者調整拍攝角度或提供文字說明"""},
                    {
                        "type": "image_url",
                        "image_url": {  # 改為對象格式
                            "url": f"data:image/jpeg;base64,{image_data}",
                            "detail": "high"  # 可選參數，控制圖片解析度
                        }
                    }
                ]
            })
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_completion_tokens=1000
            ).choices[0].message.content
            # 儲存圖片分析對話
            chat_history.add_user_message("[圖片]")
            chat_history.add_ai_message(response)
            return response

        
        
        # 文字訊息
        initial_response = self.client.responses.create(
            model=MODEL,
            input=[
                {"role": "system", "content": PROMPT},
                *history_messages,
                {"role": "user", "content": user_input},
            ],
        ).output_text

        # 判斷是否需要網路搜尋
        fail_message = json.loads(open("fail.json", "r").read())
        if any(item in initial_response for item in fail_message):
            search_query = (
                user_input if len(user_input) < 100 else user_input[:100] + "..."
            )
            search_result = self._web_search(search_query)

            if search_result:
                final_response = self.client.responses.create(
                    model=MODEL,
                    input=[
                        {"role": "system", "content": "請整合以下資訊回答問題"},
                        {
                            "role": "user",
                            "content": f"問題：{user_input}\n補充資料：{search_result}",
                        },
                    ],
                ).output_text
            else:
                final_response = "無法取得相關網路資訊，請嘗試其他問題"
        else:
            final_response = initial_response

        
        # 更新對話歷史到MongoDB
        chat_history.add_user_message(user_input)
        chat_history.add_ai_message(final_response)

        return final_response
