import json
import logging
from flask import Flask, request, abort, send_from_directory
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    ImageMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent
from gai import IntelligentChatAssistant
from image_processor import ImageProcessor
from datetime import datetime
from manay import Accounting
from generate_graph import GenPieChart
import os
import time

log_filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(
            "./log/{}".format(log_filename), "w", "utf-8"
        )
    ],
)

app = Flask(__name__)
config = json.loads(open("config.json", "r").read())
secret = json.loads(open("secret.json", "r").read())
# 請填入你在 LINE Developers 取得的 Channel Access Token 與 Channel Secret
configuration = Configuration(access_token=secret["access_token"])
handler = WebhookHandler(secret["channel_secret"])
image_processor = ImageProcessor(configuration)


@app.route("/callback", methods=["POST"])
def callback():
    # 取得 X-Line-Signature
    signature = request.headers["X-Line-Signature"]
    # 取得請求內容
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info(
            "Invalid signature. Please check your channel access token/channel secret."
        )
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    source_type = event.source.type
    match source_type:
        case "user":
            # 當來源是單一用戶時，處理記帳功能
            user_id = event.source.user_id
            message_text = event.message.text
            
            # 建立指令格式提供給記帳系統
            command = {
                'user_id': user_id,
                'message': message_text
            }
            
            # 使用OpenAI解析記帳訊息
            parsed_result = ac.parse_message(command)
            try:
            
                if parsed_result and 'amount' in parsed_result and 'item' in parsed_result:
                    # 成功解析為記帳資訊
                    if ac.save_db(parsed_result):
                        # 建立回覆訊息
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
                        summary = ac.get_monthly_summary(user_id, now.year, now.month)
                        response_text += f"\n\n本月收入：{summary['income']}元\n本月支出：{summary['expense']}元\n本月結餘：{summary['balance']}元"
                    else:
                        response_text = "❌ 記帳失敗，請稍後再試"
                
                elif parsed_result["type"] == "分析":
                    logging.debug("main: 收到分析請求")
                    spending_data = list()
                    if "month" in parsed_result and "year" in parsed_result:
                        spending_data = ac.get_records(user_id, parsed_result["year"], parsed_result["month"])
                        
                    elif "month" in parsed_result:
                        spending_data = ac.get_records(user_id, datetime.now().year, parsed_result["month"])
                    else:
                        spending_data = ac.get_records(user_id, datetime.now().year, datetime.now().month)
                    GenPieChart.generate_pie_chart(spending_data)
                    trailing = f"images/{user_id}.png"
                    image_url = f"https://{config['url']}/{trailing}"
                    while not os.path.exists(trailing):
                        time.sleep(0.5)
                    try:
                        # 發送圖片訊息
                        with ApiClient(configuration) as api_client:
                            line_bot_api = MessagingApi(api_client)
                            response = line_bot_api.reply_message_with_http_info(
                                ReplyMessageRequest(
                                    reply_token=event.reply_token,
                                    messages=[
                                        ImageMessage(
                                            original_content_url=image_url,
                                            preview_image_url=image_url
                                        )
                                    ]
                                )
                            )
                            # 確認訊息發送成功後刪除檔案
                            if response[1] == 200:  # HTTP 200代表成功
                                time.sleep(1)  # 等待2秒
                                
                                # 刪除檔案
                                if os.path.exists(trailing):
                                    os.unlink(trailing)
                                    logging.info(f"已刪除圖片檔案: {trailing}")
                                else:
                                    logging.warning(f"找不到圖片檔案: {trailing}")
                    except Exception as e:
                        logging.error(f"發送或刪除圖片時發生錯誤: {e}")
                    
                    return
            except KeyError:
                # 不是記帳指令，使用AI助手回覆
                response_text = ai.send_query(event, message_text)
            
            # 回覆用戶
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=response_text)],
                    )
                )
        
        case "group":
            mention = getattr(event.message, "mention", None)
            if mention and any(getattr(m, "is_self", False) for m in mention.mentionees):
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    # 將整個event傳遞給AI助手，以便提取群組ID和用戶ID
                    response_text = ai.send_query(event, event.message.text)
                    line_bot_api.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=response_text)],
                        )
                    )


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):
    if event.source.type != "user":
        return  # 僅處理個人對話
    
    # 使用修正後的圖片處理器
    image_data = image_processor.download_image(event.message.id)
    
    if not image_data:
        logging.warning("main: Failed to download image.")
        return 
    
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        # 使用AI分析收據圖片並轉換為記帳資訊
        response = ai.send_query(event, "", image_data=image_data)
        
        # 嘗試從AI回應中提取記帳資訊
        user_id = event.source.user_id
        try:
            # 假設AI已經將收據解析為結構化資料
            # 這裡可以進一步處理AI返回的資訊，提取記帳相關數據
            parsed_result = {
                'user_id': user_id,
                'type': '支出',  # 收據通常是支出
                'amount': 0,  # 需要從AI回應中提取
                'item': '從收據識別',  # 需要從AI回應中提取
                'created_at': datetime.now()
            }
            
            # 將收據資訊存入資料庫
            # ac.save_db(parsed_result)  # 這裡暫時註釋掉，因為需要進一步開發收據解析功能
            
            # 回覆用戶
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=response)]
                )
            )
        except Exception as e:
            logging.error(f"main: 處理收據圖片時發生錯誤: {e}")
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="無法識別收據，請重新拍攝或手動輸入")]
                )
            )

@app.route("/images/<path:image_id>")
def send_image(image_id):
    try:
        return send_from_directory("images", image_id)
    except FileNotFoundError:
        return "Image not found", 404

if __name__ == "__main__":
    ai = IntelligentChatAssistant()
    ac = Accounting()
    app.run(host=config["host"], debug=config["debug"], port=config["port"])
