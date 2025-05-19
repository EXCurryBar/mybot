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
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent
from script.gai import IntelligentChatAssistant
from datetime import datetime
from script.manay import Accounting


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
config = json.loads(open("config/config.json", "r").read())
secret = json.loads(open("config/secret.json", "r").read())
configuration = Configuration(access_token=secret["access_token"])
handler = WebhookHandler(secret["channel_secret"])


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
            reply_message_request = ac.parse_message(event)
            if type(reply_message_request) == ReplyMessageRequest:
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    line_bot_api.reply_message_with_http_info(reply_message_request)
            else:
                response_text = ai.send_query(event, event.message.text)
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
            if mention and any(
                getattr(m, "is_self", False) for m in mention.mentionees
            ):
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
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

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # 使用AI分析收據圖片並轉換為記帳資訊
        try:
            reply_message_request = ac.parse_image(event)
            if type(reply_message_request) == ReplyMessageRequest:
                line_bot_api.reply_message_with_http_info(reply_message_request)
            else:
                image_data = reply_message_request.get("image")
                response_text = ai.send_query(event, "",  image_data=image_data)
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=response_text)],
                    )
                )
        except Exception as e:
            logging.error(f"Error processing image: {e}")
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="無法處理圖片，請稍後再試。")],
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
