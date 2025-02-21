import os
import whisper
import datetime
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import os
import whisper
import datetime
import logging
from pathlib import Path


class WhisperSubtitleGenerator:
    def __init__(self, model_size="base"):
        self.model = whisper.load_model(model_size)

    @staticmethod
    def _format_time(seconds):
        """静态方法：格式化时间为SRT格式 (HH:MM:SS,mmm)"""
        total_ms = float(seconds) * 1000
        total_ms = round(total_ms)

        hours = total_ms // 3600000
        total_ms %= 3600000

        minutes = total_ms // 60000
        total_ms %= 60000

        seconds = total_ms // 1000
        ms = total_ms % 1000

        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},{int(ms):03d}"

    def generate_srt(self, audio_path, output_path=None):
        try:
            result = self.model.transcribe(
                audio_path,
                word_timestamps=True
            )

            smoothing = 0.5  # 延长时间（单位秒）

            if output_path is None:
                output_path = Path(audio_path).with_suffix('.srt')

            with open(output_path, 'w', encoding='utf-8') as f:
                for i, segment in enumerate(result["segments"], 1):
                    start_time = self._format_time(segment["start"])
                    end_time = self._format_time(segment["end"])
                    text = segment["text"].strip()

                    f.write(f"{i}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{text}\n\n")

            return True

        except Exception as e:
            logging.error(f"生成字幕失败: {str(e)}")
            return False

def check_subtitle_output(output_path):
    """检查生成的字幕文件内容"""
    sample_output = """1
00:00:01,500 --> 00:00:03,800
Good morning, Sir.
早上好，先生。

2
00:00:04,000 --> 00:00:06,500
Is this your handbag?
这是您的手提包吗？

3
00:00:06,800 --> 00:00:09,200
Yes, it is.
是的，是我的。
"""
    print("\n=== 生成的SRT字幕格式示例 ===")
    print(sample_output)
    print("\n=== 实际生成的字幕内容 ===")

    try:
        # 读取实际生成的字幕文件
        with open(output_path, "r", encoding="utf-8") as f:
            actual_content = f.read()
            print(actual_content[:500])  # 只显示前500个字符
    except Exception as e:
        print(f"读取字幕文件失败: {e}")



def main():
    # 设置音频目录
    audio_dir = r'E:\Music新概念英语\新概念英语第1册'
    output_dir = "字幕文件_Whisper"

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 初始化生成器
    generator = WhisperSubtitleGenerator()

    # 处理所有音频文件
    for file in os.listdir(audio_dir):
        if file.lower().endswith(('.mp3', '.wav')):
            audio_path = os.path.join(audio_dir, file)
            output_path = os.path.join(output_dir, Path(file).with_suffix('.srt'))

            if os.path.exists(output_path):
                logging.info(f"跳过已存在的字幕: {output_path}")
                continue

            logging.info(f"正在处理: {file}, {output_path}")
            generator.generate_srt(audio_path, output_path)
            check_subtitle_output(output_path)


if __name__ == "__main__":
    main()
