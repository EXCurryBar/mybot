from linebot.v3.messaging import ApiClient, MessagingApiBlob
import base64
import logging
import imghdr  
from PIL import Image  
import pyheif  
import io


class HeicConverter:
    @staticmethod
    def heic_to_jpeg(heic_data: bytes) -> bytes:
        """將 HEIC 轉為 JPEG 格式"""
        try:
            heif_file = pyheif.read_heif(heic_data)
            image = Image.frombytes(
                heif_file.mode,
                heif_file.size,
                heif_file.data,
                "raw",
                heif_file.mode,
                heif_file.stride,
            )
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=85)
            return buf.getvalue()
        except Exception as e:
            logging.error(f"HEIC 轉換失敗: {str(e)}")
            raise


class ImageProcessor:
    def __init__(self, config):
        self.config = config
        logging.basicConfig(level=logging.INFO)
        self.supported_formats = {'jpeg', 'png', 'gif', 'heic'}
    
    def _detect_image_type(self, image_data: bytes) -> str:
        """強化型圖片格式檢測"""
        # 優先檢查 HEIC (imghdr 無法辨識 HEIC)
        if image_data.startswith(b'\x00\x00\x00\x20ftypheic'):
            return 'heic'
        detected = imghdr.what(None, h=image_data)
        return detected if detected else 'unknown'
    
    def download_image(self, message_id, convert_heic=True) -> str:
        """支援 HEIC 的自動轉換方法"""
        try:
            with ApiClient(self.config) as api_client:
                blob_api = MessagingApiBlob(api_client)
                content = blob_api.get_message_content(message_id)
                
                file_content = bytearray()
                for chunk in content:
                    if isinstance(chunk, (bytes, bytearray)):
                        file_content.extend(chunk)
                    elif isinstance(chunk, int):
                        file_content.append(chunk)
                    else:
                        logging.warning(f"忽略無效數據類型: {type(chunk)}")
                
                raw_data = bytes(file_content)
                img_type = self._detect_image_type(raw_data)
                logging.info(f"received {img_type} image")
                # HEIC 轉換處理
                if img_type == 'heic' and convert_heic:
                    jpeg_data = HeicConverter.heic_to_jpeg(raw_data)
                    return base64.b64encode(jpeg_data).decode('utf-8')
                
                # 非 HEIC 直接返回
                return base64.b64encode(raw_data).decode('utf-8')

        except Exception as e:
            logging.error(f"圖片處理失敗: {str(e)}")
            return None
