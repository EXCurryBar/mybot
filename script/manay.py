from pymongo import MongoClient
import logging
from openai import OpenAI
from datetime import datetime
import json
import time
import os
from script.image_processor import ImageProcessor
from script.generate_graph import GenPieChart
from linebot.v3.messaging import (
    Configuration,
    ReplyMessageRequest,
    TextMessage,
    ImageMessage,
)

secret = json.loads(open("config/secret.json", "r").read())
config = json.loads(open("config/config.json", "r").read())
configuration = Configuration(access_token=secret["access_token"])
image_processor = ImageProcessor(configuration)


class Accounting:
    def __init__(self):
        self.client = MongoClient("mongodb://localhost:27017/")
        self.db = self.client['accounting']
        self.client = OpenAI(
            api_key=secret["openai"]
        )
        logging.info("manay: class initialized")

    def parse_message(self, event):
        """解析用戶訊息，使用OpenAI識別收入/支出、金額和品名"""
        message = event.message.text
        user_id = event.source.user_id
        
        # 使用OpenAI API解析訊息
        prompt = open("prompt/accounting_prompt.txt", "r").read()
        prompt = prompt.replace("{message}", message)
        try:
            response = self.client.responses.create(
                model=config["model"],
                input=[{"role": "user", "content": prompt}]
            ).output_text
        except json.JSONDecodeError as e:
            logging.error(f"manay: 解析OpenAI回應失敗: {e}")
            return {"type": "error"}
            
        try:
            parsed_result = json.loads(response)
            parsed_result['user_id'] = user_id
            if parsed_result["type"] == "收入" or parsed_result["type"] == "支出":
                # 成功解析為記帳資訊
                if self.save_db(parsed_result):
                    now = datetime.now()
                    y = now.year
                    m = now.month
                    d = now.day
                    if parsed_result["year"] is None and parsed_result["month"] is None and parsed_result["day"] is None:
                        y = now.year
                        m = now.month
                        d = now.day
                    else:
                        y = parsed_result["year"]
                        m = parsed_result["month"]
                        d = parsed_result["day"]
                        
                    if parsed_result.get('type') == '收入':
                        response_text = f"✅ 已記錄收入：\n在{y}年{m}月{d}日 {parsed_result['item']} 賺了 {parsed_result['amount']}元"
                    else:  # 支出
                        response_text = f"✅ 已記錄支出：\n在{y}年{m}月{d}日 {parsed_result['item']} 花了 {parsed_result['amount']}元"
                    
                    # 取得當月統計
                    now = datetime.now()
                    summary = self.get_monthly_summary(user_id, now.year, now.month)
                    response_text += f"\n\n本月收入：{summary['income']}元\n本月支出：{summary['expense']}元\n本月結餘：{summary['balance']}元"
                else:
                    response_text = "❌ 記帳失敗，請稍後再試"
                
                return ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=response_text)],
                )
            
            elif parsed_result["type"] == "分析":
                logging.debug("main: 收到分析請求")
                spending_data = list()
                if "month" in parsed_result and "year" in parsed_result:
                    spending_data = self.get_records(user_id, parsed_result["year"], parsed_result["month"])
                    
                elif "month" in parsed_result:
                    spending_data = self.get_records(user_id, datetime.now().year, parsed_result["month"])
                else:
                    spending_data = self.get_records(user_id, datetime.now().year, datetime.now().month)
                GenPieChart.generate_pie_chart(spending_data)
                trailing = f"images/{user_id}.png"
                image_url = f"https://{config['url']}/{trailing}"
                while not os.path.exists(trailing):
                    time.sleep(0.5)
                    
                return ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        ImageMessage(
                            original_content_url=image_url,
                            preview_image_url=image_url,
                        ),
                    ],
                )
 
        except Exception as e:
            logging.error(f"manay: OpenAI API呼叫失敗: {e}")
            return {"type": "error"}
        
    def parse_image(self, event):
        """解析圖片，使用OpenAI識別收入/支出、金額和品名"""
        image_data = image_processor.download_image(event.message.id)
        if not image_data:
            logging.warning("manay: 下載圖片失敗")
            return {"type": "error"}
        
        prompt = open("prompt/accounting_prompt.txt", "r").read()
        messages = [{"role": "user", "content": prompt}]
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
        try:
            response = self.client.responses.create(
                model="gpt-4.1",
                input=messages
            ).output_text
        except Exception as e:
            logging.error(f"manay: OpenAI API呼叫失敗: {e}")
            return ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="❌ 無法解析圖片，請稍後再試")],
            )
        try:
            parsed_data = json.loads(response)
        except json.JSONDecodeError as e:
            logging.error(f"manay: OpenAI解析圖片失敗: {e}")
            return {"type": "error", "image": image_data}

        if parsed_data["type"] == "收入" or parsed_data["type"] == "支出":
            parsed_data['user_id'] = event.source.user_id
            if self.save_db(parsed_data):
                now = datetime.now()
                y = now.year
                m = now.month
                d = now.day
                if parsed_data["year"] is None and parsed_data["month"] is None and parsed_data["day"] is None:
                    y = now.year
                    m = now.month
                    d = now.day
                else:
                    y = parsed_data["year"]
                    m = parsed_data["month"]
                    d = parsed_data["day"]
                    
                if parsed_data.get('type') == '收入':
                    response_text = f"✅ 已記錄收入：\n在{y}年{m}月{d}日 {parsed_data['item']} 賺了 {parsed_data['amount']}元"
                else:  # 支出
                    response_text = f"✅ 已記錄支出：\n在{y}年{m}月{d}日 {parsed_data['item']} 花了 {parsed_data['amount']}元"
                
                return ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=response_text)],
                )
            else:
                logging.error("manay: 儲存資料庫失敗")
                return ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="❌ 記帳失敗，請稍後再試")],
                )
    
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