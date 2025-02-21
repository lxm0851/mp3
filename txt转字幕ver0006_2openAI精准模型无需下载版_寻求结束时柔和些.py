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
            # 规范化音频文件路径
            audio_path = str(Path(audio_path).resolve())
            logging.info(f"处理音频文件: {audio_path}")

            # 转录前检查文件
            if not os.path.isfile(audio_path):
                raise FileNotFoundError(f"找不到音频文件: {audio_path}")

            result = self.model.transcribe(
                audio_path,
                word_timestamps=True
            )

            # 确保输出路径存在
            if output_path is None:
                output_path = Path(audio_path).with_suffix('.srt')
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            result = self.model.transcribe(
                audio_path,
                word_timestamps=True
            )

            # 设置平滑参数
            smoothing = 0.3  # 基础延长时间(秒)
            min_gap = 0.1  # 最小间隔时间(秒)

            if output_path is None:
                output_path = Path(audio_path).with_suffix('.srt')
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            segments = result["segments"]

            with open(output_path, 'w', encoding='utf-8') as f:
                for idx in range(len(segments)):
                    segment = segments[idx]
                    start_time = segment["start"]
                    end_time = segment["end"]

                    # 计算平滑结束时间
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

                    srt_start = self._format_time(start_time)
                    srt_end = self._format_time(new_end)
                    text = segment["text"].strip()

                    f.write(f"{idx + 1}\n")
                    f.write(f"{srt_start} --> {srt_end}\n")
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
    output_dir = os.path.abspath("字幕文件_Whisper")

    print(f"音频目录: {audio_dir}")  # 调试信息
    print(f"输出目录: {output_dir}")  # 调试信息

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 初始化生成器
    generator = WhisperSubtitleGenerator()

    # 处理所有音频文件
    for file in os.listdir(audio_dir):
        if file.lower().endswith(('.mp3', '.wav')):
            try:
                audio_path = os.path.join(audio_dir, file)

                # 打印完整路径进行调试
                print(f"\n当前处理文件完整路径: {audio_path}")
                print(f"文件是否存在: {os.path.exists(audio_path)}")

                if not os.path.exists(audio_path):
                    logging.error(f"无法找到音频文件: {audio_path}")
                    continue

                output_path = os.path.join(output_dir, Path(file).with_suffix('.srt'))

                logging.info(f"正在处理: {file}")
                result = generator.generate_srt(audio_path, output_path)

                if result:
                    logging.info(f"字幕生成成功: {output_path}")
                    check_subtitle_output(output_path)

            except Exception as e:
                logging.error(f"处理文件出错: {file}, 错误: {str(e)}")
                continue


if __name__ == "__main__":
    main()