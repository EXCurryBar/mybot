from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from pymongo import MongoClient

class MongoHistoryManager:
    def __init__(self):
        self.conn_str = "mongodb://localhost:27017/"
        self.client = MongoClient(self.conn_str)
        self.db = self.client['line_chat_history']
        
    def get_history(self, session_id):
        """獲取指定session_id的聊天歷史"""
        return MongoDBChatMessageHistory(
            connection_string=self.conn_str,
            session_id=session_id,
            database_name="line_chat_history",
            collection_name="chat_records",
            history_size=30  # 限制歷史記錄數量
        )
        
    def get_messages_as_dict(self, session_id):
        """將歷史記錄轉換為字典格式供OpenAI API使用"""
        history = self.get_history(session_id)
        return [
            {"role": "user" if msg.type == "human" else "assistant", "content": msg.content}
            for msg in history.messages
        ]
