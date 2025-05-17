from pymongo import MongoClient
import logging
from openai import OpenAI
from datetime import datetime
import json


secret = json.loads(open("secret.json", "r").read())

class Accounting:
    def __init__(self):
        self.client = MongoClient("mongodb://localhost:27017/")
        self.db = self.client['accounting']
        self.client = OpenAI(
            api_key=secret["openai"]
        )
        logging.info("manay: class initialized")

    def parse_message(self, command: dict):
        """解析用戶訊息，使用OpenAI識別收入/支出、金額和品名"""
        message = command.get('message', '')
        user_id = command.get('user_id', '')
        
        # 使用OpenAI API解析訊息
        prompt = open("accounting_prompt.txt", "r").read()
        prompt = prompt.replace("{message}", message)
        try:
            response = self.client.responses.create(
                model="gpt-4.1-mini",
                input=[{"role": "user", "content": prompt}]
            ).output_text
            
            try:
                parsed_data = json.loads(response)
                parsed_data['user_id'] = user_id
                return parsed_data
            except json.JSONDecodeError as e:
                logging.error(f"manay: 解析OpenAI回應失敗: {e}")
                return {}
                
        except Exception as e:
            logging.error(f"manay: OpenAI API呼叫失敗: {e}")
            return {}
    
    def save_db(self, record=None):
        """將記帳記錄儲存到MongoDB"""
        if record is None:
            logging.error("manay: 沒有提供記帳資料，無法儲存")
            return False
            
        # 補充時間戳記
        now = datetime.now()
        if record["month"] is None:
            record["month"] = now.month
        if record["year"] is None:
            record["year"] = now.year
        if record["day"] is None:
            record["day"] = now.day
        record.update({
            'created_at': now,
            'updated_at': now
        })
        
        try:
            result = self.db.records.insert_one(record)
            logging.info(f"manay: 記帳記錄已儲存，ID: {result.inserted_id}")
            return True
        except Exception as e:
            logging.error(f"manay: 資料庫儲存失敗: {e}")
            return False
            
    def get_records(self, user_id, year=None, month=None):
        """查詢特定用戶的記帳記錄"""
        query = {'user_id': user_id}
        
        if year:
            query['year'] = year
        if month:
            query['month'] = month
            
        try:
            records = list(self.db.records.find(query))
            return records
        except Exception as e:
            logging.error(f"manay: 查詢記錄失敗: {e}")
            return []
            
    def get_monthly_summary(self, user_id, year, month):
        """取得月度收支統計"""
        try:
            pipeline = [
                {'$match': {'user_id': user_id, 'year': year, 'month': month}},
                {'$group': {
                    '_id': '$type',
                    'total': {'$sum': '$amount'}
                }}
            ]
            
            result = list(self.db.records.aggregate(pipeline))
            summary = {'income': 0, 'expense': 0}
            
            for item in result:
                if item['_id'] == '收入':
                    summary['income'] = item['total']
                elif item['_id'] == '支出':
                    summary['expense'] = item['total']
                    
            summary['balance'] = summary['income'] - summary['expense']
            return summary
        except Exception as e:
            logging.error(f"manay: 計算月度統計失敗: {e}")
            return {'income': 0, 'expense': 0, 'balance': 0}