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

# 添加新的依赖
import moviepy.editor as mp
from pathlib import Path
import tempfile


# 在 WhisperSubtitleGenerator 类中添加视频处理相关的方法
class WhisperSubtitleGenerator:
    def __init__(self, model_size="base"):
        self.model = whisper.load_model(model_size)
        self.app_id = None
        self.app_key = None
        self.api_url = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
        self.no_translate_mode = False
        self.engine = pyttsx3.init()
        self.progress_callback = None
        self.status_callback = None
        # 添加临时文件目录
        self.temp_dir = None

    def extract_audio_from_video(self, video_path):
        """从视频中提取音频"""
        try:
            self.update_status(f"正在从视频中提取音频: {os.path.basename(video_path)}")

            # 创建临时目录
            if not self.temp_dir:
                self.temp_dir = Path(tempfile.mkdtemp())

            # 生成临时音频文件路径
            audio_path = self.temp_dir / f"{Path(video_path).stem}.wav"

            # 使用 moviepy 提取音频
            video = mp.VideoFileClip(video_path)
            video.audio.write_audiofile(str(audio_path))
            video.close()

            self.update_status(f"音频提取完成: {audio_path}")
            return audio_path
        except Exception as e:
            self.update_status(f"音频提取失败: {str(e)}")
            logging.error(f"视频音频提取失败: {str(e)}")
            return None

    def cleanup_temp_files(self):
        """清理临时文件"""
        if self.temp_dir and self.temp_dir.exists():
            try:
                for file in self.temp_dir.glob("*"):
                    file.unlink()
                self.temp_dir.rmdir()
                self.update_status("已清理临时文件")
            except Exception as e:
                logging.error(f"清理临时文件失败: {str(e)}")

    def generate_srt(self, input_path, output_path=None):
        try:
            input_path = Path(input_path)
            is_video = input_path.suffix.lower() in ('.mp4', '.avi', '.mov', '.mkv')

            # 如果是视频文件，先提取音频
            if is_video:
                audio_path = self.extract_audio_from_video(str(input_path))
                if not audio_path:
                    return False
            else:
                audio_path = input_path

            # 如果没有指定输出路径，根据输入文件生成
            if output_path is None:
                output_path = input_path.with_suffix('.srt')
            else:
                output_path = Path(output_path)

            # 如果字幕文件已存在，则跳过生成
            if output_path.exists():
                self.update_status(f"字幕文件 {output_path.name} 已存在，跳过生成")
                logging.info(f"字幕文件已存在，跳过生成: {output_path}")
                return True

            self.update_status(f"开始处理: {os.path.basename(input_path)}")

            # 设置平滑参数
            smoothing = 0.3
            min_gap = 0.1

            # 获取英文识别结果
            result_en = self.model.transcribe(
                str(audio_path),
                language="en"
            )

            with open(output_path, 'w', encoding='utf-8') as f:
                segments = result_en["segments"]
                total_segments = len(segments)

                for idx, seg_en in enumerate(segments):
                    self.update_progress(idx + 1, total_segments)

                    start_time = seg_en["start"]
                    end_time = seg_en["end"]

                    if idx < len(segments) - 1:
                        next_start = segments[idx + 1]["start"]
                        gap = next_start - end_time

                        if gap > smoothing + min_gap:
                            new_end = end_time + smoothing
                        else:
                            new_end = next_start - min_gap
                    else:
                        new_end = end_time + smoothing

                    text_en = seg_en["text"].strip()
                    text_zh = ""

                    self.update_status(f"第{idx + 1}/{total_segments}段 - {text_en}")

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

                    f.write(f"{idx + 1}\n")
                    f.write(f"{self.format_time(start_time)} --> {self.format_time(new_end)}\n")
                    f.write(f"英文字幕：{text_en}\n")
                    f.write(f"中文字幕：{text_zh}\n\n")

                    print(f"第{idx + 1}段识别结果 - 英文: {text_en}")
                    print(f"第{idx + 1}段翻译结果 - 中文: {text_zh}\n")
                    logging.info(f"处理第{idx + 1}段: 英文[{text_en}] -> 中文[{text_zh}]")

            self.update_status(f"完成: {os.path.basename(input_path)}")
            return True

        except Exception as e:
            self.update_status(f"错误: {str(e)}")
            logging.error(f"生成字幕失败: {str(e)}")
            return False
        finally:
            # 清理临时文件
            if is_video:
                self.cleanup_temp_files()


# 修改 main 函数以支持视频文件
def main():
    config_file = os.path.join(os.path.expanduser('~'), '.audio_player', 'baidu_api_config.json')
    app_id = None
    app_key = None

    if os.path.exists(config_file):
        use_saved = input("检测到已保存的API配置，是否使用?(y/n): ").strip().lower() == 'y'
        if use_saved:
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    app_id = config.get('app_id')
                    app_key = config.get('app_key')
                print(f"\n当前配置:\nAPP ID: {app_id}\nAPI Key: {app_key}")
                if input("\n配置是否正确?(y/n): ").strip().lower() != 'y':
                    app_id = None
                    app_key = None
            except Exception as e:
                print(f"读取API配置失败: {e}")
                app_id = None
                app_key = None

    if not app_id or not app_key:
        print("请输入百度翻译API配置信息:")
        app_id = input("APP ID: ").strip()
        app_key = input("API Key: ").strip()

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

    while True:
        input_dir = input("请输入音频或视频文件夹路径: ").strip()
        if os.path.exists(input_dir):
            break
        print("路径不存在,请重新输入")

    output_dir = input("请输入字幕输出文件夹路径(直接回车则使用默认路径'字幕文件_Whisper_翻译'): ").strip()
    if not output_dir:
        output_dir = "字幕文件_Whisper_翻译"

    os.makedirs(output_dir, exist_ok=True)

    generator = WhisperSubtitleGenerator()
    generator.app_id = app_id
    generator.app_key = app_key

    translate_choice = input("是否需要翻译字幕? (y/n): ").strip().lower()
    generator.set_translate_mode(translate_choice == 'y')

    # 支持的音频和视频格式
    supported_formats = ('.mp3', '.wav', '.mp4', '.avi', '.mov', '.mkv')

    for file in os.listdir(input_dir):
        if file.lower().endswith(supported_formats):
            input_path = os.path.join(input_dir, file)
            output_path = os.path.join(output_dir, Path(file).with_suffix('.srt'))

            print(f"正在处理: {file}")
            if generator.generate_srt(input_path, output_path):
                print(f"生成成功: {output_path}")
                check_subtitle_output(output_path)
            else:
                print(f"生成失败: {file}")


if __name__ == "__main__":
    main()