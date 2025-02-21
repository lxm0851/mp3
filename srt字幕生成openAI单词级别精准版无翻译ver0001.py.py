import os

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import whisper
import re
from pathlib import Path
import logging
from mutagen import File

logging.basicConfig(level=logging.INFO)


class WhisperSubtitleGenerator:
    def __init__(self, model_size="base"):
        self.model = whisper.load_model(model_size)
        self.min_gap = 0.1  # 最小间隔(秒)
        self.smoothing = 0.3  # 平滑时间(秒)

    def transcribe_audio(self, audio_path):
        """使用whisper识别音频"""
        return self.model.transcribe(
            audio_path,
            language="en",
            word_timestamps=True,  # 启用单词级时间戳
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

                # 判断句子结束
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

        # 处理剩余内容
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
        """生成字幕文件"""
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

            # 3. 生成字幕文件
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

                    # 写入SRT格式
                    f.write(f"{idx}\n")
                    f.write(f"{self.format_time(sent['start'])} --> {self.format_time(end_time)}\n")
                    f.write(f"{sent['text']}\n\n")

                    # 打印处理信息
                    print(f"第{idx}句: {sent['text']}")

            logging.info(f"生成字幕: {output_path}")
            return True

        except Exception as e:
            logging.error(f"处理失败: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return False


def main():
    generator = WhisperSubtitleGenerator()
    audio_dir = r'E:\Music新概念英语\新概念英语第1册'
    output_dir = "字幕文件_Whisper"

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 处理所有音频文件
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