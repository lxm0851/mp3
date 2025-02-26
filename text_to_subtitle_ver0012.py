# from baidu_aip import AipTranslator
import whisper
import hashlib
import random
import time
import requests
import pyttsx3  # 新增语音输出模块
import logging
import os
from pathlib import Path
import json

class WhisperSubtitleGenerator:
    def __init__(self, model_size="base"):
        self.model = whisper.load_model(model_size)
        # 百度翻译API配置(从界面获取)
        self.app_id = None
        self.app_key = None
        self.api_url = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
        self.no_translate_mode = False
        self.engine = pyttsx3.init()
        
        # 添加进度回调
        self.progress_callback = None
        self.status_callback = None

    def set_api_config(self, app_id, app_key):
        """设置API配置"""
        self.app_id = app_id
        self.app_key = app_key
        print(f"Generator 中设置的 app_id: {repr(self.app_id)}")
        print(f"Generator 中设置的 app_key: {repr(self.app_key)}")

    def test_translation(self, text):
        """测试翻译API配置是否有效"""
        try:
            # print('APP_ID API_KYA:', self.app_id, self.app_key)
            if not self.app_id or not self.app_key:
                logging.error("API配置未设置")
                return False

            # 生成签名
            salt = str(random.randint(32768, 65536))
            sign = self.app_id + text + salt + self.app_key
            sign = hashlib.md5(sign.encode()).hexdigest()

            # 构建请求
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            payload = {
                'q': text,
                'from': 'en',
                'to': 'zh',
                'appid': self.app_id,
                'salt': salt,
                'sign': sign
            }

            # print(f"翻译请求参数 - app_id: {repr(self.app_id)}, key:{ self.app_key}, salt: {salt}")
            # print(f"翻译请求签名: {sign}")

            # 发送请求
            response = requests.post(self.api_url, headers=headers, data=payload)
            result = response.json()

            # 检查响应
            if 'trans_result' in result:
                return True
            else:
                logging.error(f"API响应错误: {result}")
                return False

        except Exception as e:
            logging.error(f"测试翻译API失败: {e}")
            return False

    def set_callbacks(self, progress_callback=None, status_callback=None):
        """设置进度和状态回调函数"""
        self.progress_callback = progress_callback
        self.status_callback = status_callback

    def update_status(self, message):
        """更新状态"""
        if self.status_callback:
            self.status_callback(message)

    def update_progress(self, current, total):
        """更新进度"""
        if self.progress_callback:
            self.progress_callback(current, total)

    def set_translate_mode(self, enable_translate=True):
        """设置是否进行翻译"""
        self.no_translate_mode = not enable_translate
        if self.no_translate_mode:
            self.update_status("已切换到无翻译模式")
        else:
            self.update_status("已切换到翻译模式")

    def baidu_translate(self, text):
        # 检查API配置
        if not self.app_id or not self.app_key:
            raise ValueError("请先配置百度翻译API信息")

        salt = random.randint(32768, 65536)
        sign = hashlib.md5(f"{self.app_id}{text}{salt}{self.app_key}".encode()).hexdigest()

        params = {
            'q': text,
            'from': 'en',
            'to': 'zh',
            'appid': self.app_id,
            'salt': salt,
            'sign': sign
        }

        # print(f"翻译请求参数 - app_id: {repr(self.app_id)}, salt: {salt}")
        # print(f"翻译请求签名: {sign}")

        try:
            response = requests.get(self.api_url, params=params)
            result = response.json()

            if 'trans_result' in result:
                return result['trans_result'][0]['dst']
            else:
                raise Exception(f"翻译失败: {result.get('error_msg', '未知错误')}")

        except Exception as e:
            logging.error(f"百度翻译API调用失败: {str(e)}")
            return "翻译失败"

    def format_time(self, seconds):
        total_ms = int(seconds * 1000)
        hours = total_ms // 3600000
        total_ms %= 3600000
        minutes = total_ms // 60000
        total_ms %= 60000
        seconds = total_ms // 1000
        ms = total_ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"

    def generate_srt(self, audio_path, output_path=None):
        try:
            print('音频路径：', audio_path)
            print('字幕路径：', output_path)
            # 如果字幕文件已存在，则跳过生成
            if output_path.exists():
                self.update_status(f"字幕文件 {output_path.name} 已存在，跳过生成")
                logging.info(f"字幕文件已存在，跳过生成: {output_path}")
                return True

            self.update_status(f"开始处理: {os.path.basename(audio_path)}")

            # 设置平滑参数
            smoothing = 0.3  # 基础延长时间(秒)
            min_gap = 0.1  # 最小间隔时间(秒)

            # 获取英文识别结果
            result_en = self.model.transcribe(
                audio_path,
                language="en"
            )

            if output_path is None:
                output_path = Path(audio_path).with_suffix('.srt')

            with open(output_path, 'w', encoding='utf-8') as f:
                segments = result_en["segments"]
                total_segments = len(segments)

                for idx, seg_en in enumerate(segments):
                    # 更新进度
                    self.update_progress(idx + 1, total_segments)
                    
                    # 计算平滑结束时间
                    start_time = seg_en["start"]
                    end_time = seg_en["end"]

                    if idx < len(segments) - 1:
                        next_start = segments[idx + 1]["start"]
                        gap = next_start - end_time

                        if gap > smoothing + min_gap:
                            # 有足够空间，添加完整平滑时间
                            new_end = end_time + smoothing
                        else:
                            # 空间不足，保留最小间隔
                            new_end = next_start - min_gap
                    else:
                        # 最后一个片段，直接添加平滑时间
                        new_end = end_time + smoothing

                    text_en = seg_en["text"].strip()
                    text_zh = ""

                    # 更新日志到界面
                    self.update_status(f"第{idx + 1}/{total_segments}段 - {text_en}")

                    # 翻译处理（保持原有逻辑）
                    if not self.no_translate_mode:
                        for retry in range(3):
                            try:
                                text_zh = self.baidu_translate(text_en)
                                if text_zh != "翻译失败":
                                    break
                                time.sleep(1)
                                self.update_status(f"翻译重试第{retry + 1}次...")
                            except Exception as e:
                                self.update_status(f"翻译失败: {str(e)}")
                                time.sleep(1)

                        if not text_zh or text_zh == "翻译失败":
                            self.update_status("翻译失败")
                            return False
                    else:
                        text_zh = "无翻译"

                    # 写入字幕文件（使用平滑后的时间）
                    f.write(f"{idx + 1}\n")
                    f.write(f"{self.format_time(start_time)} --> {self.format_time(new_end)}\n")
                    f.write(f"英文字幕：{text_en}\n")
                    f.write(f"中文字幕：{text_zh}\n\n")

                    print(f"第{idx + 1}段识别结果 - 英文: {text_en}")
                    print(f"第{idx + 1}段翻译结果 - 中文: {text_zh}\n")
                    logging.info(f"处理第{idx + 1}段: 英文[{text_en}] -> 中文[{text_zh}]")

            self.update_status(f"完成: {os.path.basename(audio_path)}")
            return True

        except Exception as e:
            self.update_status(f"错误: {str(e)}")
            logging.error(f"生成字幕失败: {str(e)}")
            return False

def check_subtitle_output(output_path):
    print("\n=== 实际生成的字幕内容 ===")
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            actual_content = f.read()
            print(actual_content[:500])
    except Exception as e:
        print(f"读取字幕文件失败: {e}")

def main():
    """字幕生成主函数，支持单独运行时的API配置"""
    # 获取API配置
    config_file = os.path.join(os.path.expanduser('~'), '.audio_player', 'baidu_api_config.json')
    app_id = None
    app_key = None
    
    # 先询问用户是否使用已保存的配置
    if os.path.exists(config_file):
        use_saved = input("检测到已保存的API配置，是否使用?(y/n): ").strip().lower() == 'y'
        if use_saved:
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    app_id = config.get('app_id')
                    app_key = config.get('app_key')
                # 让用户确认配置是否正确
                print(f"\n当前配置:\nAPP ID: {app_id}\nAPI Key: {app_key}")
                if input("\n配置是否正确?(y/n): ").strip().lower() != 'y':
                    app_id = None
                    app_key = None
            except Exception as e:
                print(f"读取API配置失败: {e}")
                app_id = None
                app_key = None
    
    # 如果没有配置或用户选择不使用已保存配置，则请求用户输入
    if not app_id or not app_key:
        print("请输入百度翻译API配置信息:")
        app_id = input("APP ID: ").strip()
        app_key = input("API Key: ").strip()
        
        # 保存配置
        try:
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, 'w') as f:
                json.dump({
                    'app_id': app_id,
                    'app_key': app_key
                }, f)
            print("API配置已保存")
        except Exception as e:
            print(f"保存API配置失败: {e}")
    
    # 获取音频文件夹路径
    while True:
        audio_dir = input("请输入音频文件夹路径: ").strip()
        if os.path.exists(audio_dir):
            break
        print("路径不存在,请重新输入")
    
    # 设置输出文件夹
    output_dir = input("请输入字幕输出文件夹路径(直接回车则使用默认路径'字幕文件_Whisper_翻译'): ").strip()
    if not output_dir:
        output_dir = "字幕文件_Whisper_翻译"
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 初始化生成器
    generator = WhisperSubtitleGenerator()
    generator.app_id = app_id
    generator.app_key = app_key
    
    # 添加翻译模式选择
    translate_choice = input("是否需要翻译字幕? (y/n): ").strip().lower()
    generator.set_translate_mode(translate_choice == 'y')
    
    # 处理所有音频文件
    for file in os.listdir(audio_dir):
        if file.lower().endswith(('.mp3', '.wav')):
            audio_path = os.path.join(audio_dir, file)
            output_path = os.path.join(output_dir, Path(file).with_suffix('.srt'))
                
            print(f"正在处理: {file}")
            if generator.generate_srt(audio_path, output_path):
                print(f"生成成功: {output_path}")
                check_subtitle_output(output_path)
            else:
                print(f"生成失败: {file}")

if __name__ == "__main__":
    main()