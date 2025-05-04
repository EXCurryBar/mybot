import json
from flask import Flask, request, abort
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
from gai import IntelligentChatAssistant
from image_processor import ImageProcessor

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

    # 處理不同類型的訊息來源
    if source_type == "user":
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            # 將整個event傳遞給AI助手，以便提取用戶ID
            response_text = ai.send_query(event, event.message.text)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=response_text)],
                )
            )
    elif source_type == "group":
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
        return  # 下載失敗時靜默處理
    
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        response = ai.send_query(event, "", image_data=image_data)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=response)]
            )
        )


if __name__ == "__main__":
    ai = IntelligentChatAssistant()
    app.run(host=config["host"], debug=config["debug"], port=config["port"])
