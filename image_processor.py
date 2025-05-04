from linebot.v3.messaging import ApiClient, MessagingApiBlob
import base64
import logging

class ImageProcessor:
    def __init__(self, config):
        self.config = config
        logging.basicConfig(level=logging.INFO)

    def download_image(self, message_id):
        """強化型圖片下載方法"""
        try:
            with ApiClient(self.config) as api_client:
                blob_api = MessagingApiBlob(api_client)
                content = blob_api.get_message_content(message_id)
                
                # 強化型數據處理
                file_content = bytearray()
                for chunk in content:
                    if isinstance(chunk, bytes):
                        file_content.extend(chunk)
                    elif isinstance(chunk, int):
                        file_content.append(chunk)  # 處理單一字節整數
                    else:
                        logging.warning(f"忽略無效數據類型: {type(chunk)}")
                        
                return base64.b64encode(bytes(file_content)).decode('utf-8')

        except Exception as e:
            logging.error(f"圖片下載失敗: {str(e)}")
            return None
