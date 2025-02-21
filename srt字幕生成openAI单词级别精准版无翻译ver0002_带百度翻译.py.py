import os

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import whisper
import re
import hashlib
import random
import time
import requests
import pyttsx3
import logging
from pathlib import Path
from mutagen import File

logging.basicConfig(level=logging.INFO)


class EnhancedWhisperSubtitleGenerator:
    def __init__(self, model_size="base"):
        self.model = whisper.load_model(model_size)
        self.min_gap = 0.1
        self.smoothing = 0.3

        # 百度翻译配置
        self.app_id = ''  # 填入你的百度翻译API ID
        self.app_key = ''  # 填入你的百度翻译API Key
        self.baidu_api_url = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
        self.no_translate_mode = False
        self.engine = pyttsx3.init()

    def baidu_translate(self, text):
        """百度翻译实现"""
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

        try:
            response = requests.get(self.baidu_api_url, params=params)
            result = response.json()
            if 'trans_result' in result:
                return result['trans_result'][0]['dst']
            raise Exception(f"翻译失败: {result.get('error_msg', '未知错误')}")
        except Exception as e:
            logging.error(f"百度翻译API调用失败: {str(e)}")
            return "翻译失败"

    def transcribe_audio(self, audio_path):
        """使用whisper识别音频"""
        return self.model.transcribe(
            audio_path,
            language="en",
            word_timestamps=True,
            verbose=False
        )

    def split_to_sentences(self, segments):
        """智能分割句子"""
        sentences = []
        current_words = []
        sentence_start = None

        for segment in segments:
            words = segment.get("words", [])
            for word in words:
                if not sentence_start:
                    sentence_start = word["start"]

                current_words.append(word)
                word_text = word["word"].strip()

                if (word_text[-1] in ".!?" and
                        not word_text[-2:] in ["Mr.", "Ms.", "Dr."]):
                    sentences.append({
                        "start": sentence_start,
                        "end": word["end"],
                        "text": "".join(w["word"] for w in current_words).strip(),
                        "words": current_words
                    })
                    current_words = []
                    sentence_start = None

        if current_words:
            sentences.append({
                "start": sentence_start,
                "end": current_words[-1]["end"],
                "text": "".join(w["word"] for w in current_words).strip(),
                "words": current_words
            })

        return sentences

    def format_time(self, seconds):
        """格式化时间为SRT格式"""
        ms = int((seconds % 1) * 1000)
        s = int(seconds)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def generate_srt(self, audio_path, output_path):
        """生成双语字幕文件"""
        try:
            logging.info(f"处理音频: {audio_path}")

            # 1. 识别音频
            result = self.transcribe_audio(audio_path)
            if not result or "segments" not in result:
                logging.error("识别失败")
                return False

            # 2. 分割句子
            sentences = self.split_to_sentences(result["segments"])
            if not sentences:
                logging.error("未检测到句子")
                return False

            # 3. 生成双语字幕文件
            with open(output_path, 'w', encoding='utf-8') as f:
                for idx, sent in enumerate(sentences, 1):
                    # 调整时间戳
                    if idx < len(sentences):
                        next_start = sentences[idx]["start"]
                        gap = next_start - sent["end"]
                        if gap > self.smoothing + self.min_gap:
                            end_time = sent["end"] + self.smoothing
                        else:
                            end_time = next_start - self.min_gap
                    else:
                        end_time = sent["end"] + self.smoothing

                    # 获取英文文本并翻译
                    text_en = sent["text"].strip()
                    text_zh = ""

                    # 翻译处理
                    if not self.no_translate_mode:
                        for retry in range(3):
                            try:
                                text_zh = self.baidu_translate(text_en)
                                if text_zh != "翻译失败":
                                    break
                                time.sleep(1)
                            except Exception as e:
                                logging.error(f"第{idx}句翻译失败第{retry + 1}次: {e}")
                                time.sleep(1)

                        if not text_zh or text_zh == "翻译失败":
                            prompt_msg = "检测到翻译异常，按 N 键切换为无翻译模式，否则程序将停止。"
                            self.engine.say(prompt_msg)
                            self.engine.runAndWait()
                            user_input = input("输入 'N' 切换为无翻译模式，其他任意键退出: ").strip().lower()
                            if user_input == "n":
                                self.no_translate_mode = True
                                text_zh = "无翻译"
                            else:
                                logging.error("用户中断字幕生成。")
                                return False
                    else:
                        text_zh = "无翻译"

                    # 写入SRT格式（双语）
                    f.write(f"{idx}\n")
                    f.write(f"{self.format_time(sent['start'])} --> {self.format_time(end_time)}\n")
                    f.write(f"英文：{text_en}\n")
                    f.write(f"中文：{text_zh}\n\n")

                    # 打印处理信息
                    print(f"第{idx}句识别结果 - 英文: {text_en}")
                    print(f"第{idx}句翻译结果 - 中文: {text_zh}\n")

            logging.info(f"生成字幕: {output_path}")
            return True

        except Exception as e:
            logging.error(f"处理失败: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return False


def main():
    generator = EnhancedWhisperSubtitleGenerator()
    audio_dir = r'E:\Music新概念英语\新概念英语第1册'
    output_dir = "字幕文件_双语"

    os.makedirs(output_dir, exist_ok=True)

    for file in os.listdir(audio_dir):
        if not file.lower().endswith(('.mp3', '.wav', '.m4a')):
            continue

        audio_path = os.path.join(audio_dir, file)
        output_path = os.path.join(output_dir, Path(file).with_suffix('.srt'))

        if os.path.exists(output_path):
            logging.info(f"跳过已存在: {output_path}")
            continue

        generator.generate_srt(audio_path, output_path)


if __name__ == "__main__":
    main()