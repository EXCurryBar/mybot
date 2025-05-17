from openai import OpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from googlesearch import search
import json
from .mongo_history import MongoHistoryManager
import logging


MODEL = json.loads(open("config/config.json", "r").read())["model"]
PROMPT = open("prompt/prompt.txt", "r").read()
secret = json.loads(open("config/secret.json", "r").read())

class IntelligentChatAssistant:
    def __init__(self):
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
        self.history_manager = MongoHistoryManager()
        logging.info("gai: class initialized")

    def _get_session_id(self, source_type, user_id, group_id=None, room_id=None):
        """根據來源類型生成會話ID"""
        if source_type == "user":
            return f"user_{user_id}"
        elif source_type == "group" and group_id:
            return f"group_{group_id}_user_{user_id}"
        elif source_type == "room" and room_id:
            return f"room_{room_id}_user_{user_id}"
        return f"default_{user_id}"  # 預設情況

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
            messages = [{"role": "system", "content": PROMPT}]
            messages += history_messages
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{image_data}",
                        "detail": "high"  # 可選參數，控制圖片解析度
                    }
                ]
            })
            response = self.client.responses.create(
                model=MODEL,
                input=messages,
                tools=[{"type": "web_search"}]
            ).output_text
            # 儲存圖片分析對話
            chat_history.add_user_message("[圖片]")
            chat_history.add_ai_message(response)
            return response

        
        
        # 文字訊息
        response = self.client.responses.create(
            model=MODEL,
            input=[
                {"role": "system", "content": PROMPT},
                *history_messages,
                {"role": "user", "content": user_input},
            ],
            tools=[{"type": "web_search"}]
        ).output_text

        
        # 更新對話歷史到MongoDB
        chat_history.add_user_message(user_input)
        chat_history.add_ai_message(response)

        return response
