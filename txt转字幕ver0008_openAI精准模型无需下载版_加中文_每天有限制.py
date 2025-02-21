import os
import whisper
import datetime
import logging
from pathlib import Path
from deep_translator import MyMemoryTranslator
import time
import pyttsx3  # 新增语音输出模块

class WhisperSubtitleGenerator:
    def __init__(self, model_size="base"):
        self.model = whisper.load_model(model_size)
        # 修改源语言"english"，目标语言"chinese simplified"
        self.translator = MyMemoryTranslator(source='english', target='chinese simplified')
        self.no_translate_mode = False  # 标记是否转换为无翻译模式
        self.engine = pyttsx3.init()     # 初始化语音引擎

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
                for idx, seg_en in enumerate(segments):
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

                    # 翻译处理（保持原有逻辑）
                    if not self.no_translate_mode:
                        for retry in range(3):
                            try:
                                text_zh = self.translator.translate(text_en)
                                break
                            except Exception as e:
                                logging.error(f"第{idx + 1}段翻译失败第{retry + 1}次: {e}")
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

                    # 写入字幕文件（使用平滑后的时间）
                    f.write(f"{idx + 1}\n")
                    f.write(f"{self.format_time(start_time)} --> {self.format_time(new_end)}\n")
                    f.write(f"英文字幕：{text_en}\n")
                    f.write(f"中文字幕：{text_zh}\n\n")

                    print(f"第{idx + 1}段识别结果 - 英文: {text_en}")
                    print(f"第{idx + 1}段翻译结果 - 中文: {text_zh}\n")
                    logging.info(f"处理第{idx + 1}段: 英文[{text_en}] -> 中文[{text_zh}]")

            return True

        except Exception as e:
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
    audio_dir = r'E:\Music新概念英语\新概念英语第1册'
    output_dir = "字幕文件_Whisper_翻译"
    os.makedirs(output_dir, exist_ok=True)
    generator = WhisperSubtitleGenerator()

    for file in os.listdir(audio_dir):
        if file.lower().endswith(('.mp3', '.wav')):
            audio_path = os.path.join(audio_dir, file)
            output_path = os.path.join(output_dir, Path(file).with_suffix('.srt'))
            if os.path.exists(output_path):
                logging.info(f"跳过已存在的字幕: {output_path}")
                continue
            logging.info(f"正在处理: {file}")
            generator.generate_srt(audio_path, output_path)
            check_subtitle_output(output_path)

if __name__ == "__main__":
    main()