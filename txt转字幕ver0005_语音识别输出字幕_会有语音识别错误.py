import os
import re
import json
import chardet
from mutagen import File
from vosk import Model, KaldiRecognizer
import wave
import logging
import subprocess  # 导入 subprocess 模块，用于执行 FFmpeg 命令

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Vosk 模型路径 (请根据您的实际模型路径修改)
MODEL_PATH = "D:/vosk_models/vosk-model-en-us-0.22"  # 例如 "vosk_models/vosk-model-en-us-0.22"
# Pause duration threshold in seconds to consider as sentence break
PAUSE_THRESHOLD = 0.8  # Adjust this value as needed

def is_ffmpeg_installed():
    """检查 FFmpeg 是否已安装 (带详细日志)"""
    try:
        logging.info("开始检查 FFmpeg 是否安装...")
        logging.info(f"当前系统 PATH 环境变量: {os.environ['PATH']}") # 打印 PATH 环境变量
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        logging.info("FFmpeg 检查成功，'ffmpeg -version' 命令执行正常。")
        return True
    except FileNotFoundError:
        logging.error("FileNotFoundError 异常: FFmpeg 未找到。")
        return False
    except subprocess.CalledProcessError as e:
        logging.error(f"subprocess.CalledProcessError 异常: 'ffmpeg -version' 命令执行出错: {e}")
        return False
    except Exception as e:
        logging.error(f"检查 FFmpeg 安装时发生未知异常: {e}")
        return False


def convert_mp3_to_wav(mp3_filepath, wav_filepath):
    """使用 FFmpeg 将 MP3 文件转换为 WAV (单声道, 16-bit PCM, 16kHz)"""
    try:
        # 检查 FFmpeg 是否安装
        ffmpeg_path = None
        for path in os.environ["PATH"].split(os.pathsep):
            fp = os.path.join(path, "ffmpeg.exe")
            if os.path.isfile(fp):
                ffmpeg_path = fp
                break

        if not ffmpeg_path:
            logging.error("未找到 FFmpeg，请确保已正确安装")
            return False

        # 检查源文件
        if not os.path.exists(mp3_filepath):
            logging.error(f"源文件不存在: {mp3_filepath}")
            return False

        # 检查目标路径
        wav_dir = os.path.dirname(wav_filepath)
        if not os.path.exists(wav_dir):
            os.makedirs(wav_dir)

        # 使用绝对路径
        mp3_abs = os.path.abspath(mp3_filepath)
        wav_abs = os.path.abspath(wav_filepath)

        logging.info(f"FFmpeg路径: {ffmpeg_path}")
        logging.info(f"源文件: {mp3_abs}")
        logging.info(f"目标文件: {wav_abs}")

        command = [
            ffmpeg_path,
            "-y",  # 覆盖已存在文件
            "-i", mp3_abs,
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", "16000",
            wav_abs
        ]

        # 执行转换
        process = subprocess.run(
            command,
            check=True,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW  # Windows特定
        )

        # 验证输出文件
        if not os.path.exists(wav_filepath):
            logging.error("转换失败：未生成输出文件")
            return False

        # 检查文件大小
        if os.path.getsize(wav_filepath) == 0:
            logging.error("转换失败：输出文件大小为0")
            os.remove(wav_filepath)
            return False

        logging.info(f"转换成功: {wav_filepath}")
        return True

    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg执行失败: {e.returncode}")
        logging.error(f"错误输出:\n{e.stderr.decode('utf-8', errors='ignore')}")
        return False
    except Exception as e:
        logging.error(f"转换过程发生未知错误: {str(e)}")
        return False

def get_audio_duration(audio_path):
    """获取音频文件时长（秒）"""
    try:
        audio = File(audio_path)
        if audio is not None:
            return int(audio.info.length)
        return 0
    except Exception as e:
        logging.error(f"获取音频时长出错: {e}")
        return 0

def read_file(file_path):
    """读取文本文件（自动检测编码）"""
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            encoding = chardet.detect(raw_data)['encoding']
        return raw_data.decode(encoding)
    except Exception as e:
        logging.error(f"读取文件出错: {e}")
        return ""

def split_sentences(content):
    """改进句子分割逻辑"""
    sentences = re.split(
        r'(?<![A-Za-z)）])(?<=[.!?。！？])[\s\u3000]+',
        content
    )
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 1]

def add_translations(sentences):
    """改进翻译配对逻辑"""
    translated_sentences = []
    i = 0
    while i < len(sentences):
        original = sentences[i]
        j = i + 1
        while j < len(sentences) and len(sentences[j].strip()) < 2:
            j += 1
        translation = sentences[j] if j < len(sentences) else "Translation not available"
        i = j + 1 if j < len(sentences) else i + 1
        translated_sentences.append(f"{original}\n{translation}")
    return translated_sentences

def format_srt_time(seconds):
    """格式化秒数为SRT时间格式 (HH:MM:SS,mmm)"""
    milliseconds = int(seconds * 1000)
    hours = milliseconds // (3600 * 1000)
    milliseconds %= (3600 * 1000)
    minutes = milliseconds // (60 * 1000)
    milliseconds %= (60 * 1000)
    seconds = milliseconds // 1000
    milliseconds %= 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def generate_srt_from_vosk(audio_path, output_path):
    """使用 Vosk API 生成精确时间对齐的英文字幕 with sentence aggregation"""
    try:
        model = Model(MODEL_PATH) # 加载 Vosk 模型
        wf = wave.open(audio_path, "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
            logging.error("音频文件必须是单声道 PCM 16位")
            return False

        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(True) # 启用词级别时间戳

        srt_content = ""
        subtitle_index = 1
        sentence_buffer = []
        current_sentence_words = []
        sentence_start_time = 0
        last_word_end_time = 0

        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if result.get("result"):
                    for word_info in result["result"]:
                        current_sentence_words.append(word_info)
            else:
                partial_result = json.loads(rec.PartialResult())
                if partial_result.get("partial"):
                    logging.debug("Partial result: %s", partial_result["partial"])

        final_result = json.loads(rec.FinalResult())
        if final_result.get("result"):
            current_sentence_words.extend(final_result["result"])

        if not current_sentence_words:
            logging.warning("Vosk 识别结果为空，可能音频文件无法识别")
            return False

        for word_info in current_sentence_words:
            word = word_info["word"]
            start_time = word_info["start"]
            end_time = word_info["end"]

            if not sentence_buffer: # First word of the first sentence
                sentence_start_time = start_time

            pause_duration = start_time - last_word_end_time
            if pause_duration > PAUSE_THRESHOLD or re.search(r'[.!?。！？]$', word): # Sentence break logic
                if sentence_buffer: # If there's a sentence in buffer, finalize it
                    sentence_text = " ".join([w["word"] for w in sentence_buffer])
                    srt_start_time = format_srt_time(sentence_buffer[0]["start"])
                    srt_end_time = format_srt_time(last_word_end_time) # Use last word's end time

                    srt_content += f"{subtitle_index}\n"
                    srt_content += f"{srt_start_time} --> {srt_end_time}\n"
                    srt_content += f"{sentence_text}\n\n"
                    subtitle_index += 1
                    sentence_buffer = [] # Clear buffer for the next sentence
                    sentence_start_time = start_time # Start time of the new sentence

            sentence_buffer.append(word_info) # Add current word to buffer
            last_word_end_time = end_time # Update last word end time

        # Process remaining words in buffer (for the last sentence)
        if sentence_buffer:
            sentence_text = " ".join([w["word"] for w in sentence_buffer])
            srt_start_time = format_srt_time(sentence_buffer[0]["start"])
            srt_end_time = format_srt_time(last_word_end_time)

            srt_content += f"{subtitle_index}\n"
            srt_content += f"{srt_start_time} --> {srt_end_time}\n"
            srt_content += f"{sentence_text}\n\n"


        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        logging.info(f"SRT 字幕文件生成成功: {output_path}")
        return True

    except Exception as e:
        logging.error(f"使用 Vosk 生成 SRT 字幕失败: {e}")
        return False


def extract_lesson_content(text):
    """按课程提取内容"""
    pattern = r'(?i)(Lesson \d+.*?)(?=\nLesson \d+|\nNew Word(?:s)? and expressions|$)'
    lessons = []
    for match in re.finditer(pattern, text, re.DOTALL):
        lesson = re.sub(r'\s+', ' ', match.group(1)).strip()
        lessons.append(lesson)
    return lessons

def extract_content(text):
    """提取所有Lesson内容"""
    pattern = r'(?i)(Lesson \d+.*?)(?=\nLesson \d+|\nNew Word(?:s)? and expressions)'
    lessons = []
    for match in re.finditer(pattern, text, re.DOTALL):
        lesson = re.sub(r'\s+', ' ', match.group(1)).strip()
        lessons.append(lesson)
    return '\n'.join(lessons)

def get_lesson_number(lesson_text):
    """从课程内容中提取课程号"""
    match = re.search(r'Lesson (\d+)', lesson_text)
    return int(match.group(1)) if match else 0

def get_audio_file_name(directory, lesson_num):
    """查找对应音频文件名"""
    pattern = fr'Lesson\s*{lesson_num}\b'
    try:
        for file in os.listdir(directory):
            if re.search(pattern, file, re.IGNORECASE):
                return os.path.splitext(file)[0]
    except OSError:
        return f"Lesson {lesson_num}"
    return f"Lesson {lesson_num}"


if __name__ == "__main__":
    file_path = "新概念英语第一册.txt" # 您的文本文件路径
    audio_dir = r'E:\Music新概念英语\新概念英语第1册' # 您的音频文件目录
    output_dir = "字幕文件_Vosk_Aggregated" # 字幕输出目录
    temp_wav_dir = "temp_wav" # 临时 WAV 文件目录

    # 确保 Vosk 模型路径正确
    if not os.path.exists(MODEL_PATH):
        logging.error(f"Vosk 模型路径不存在: {MODEL_PATH}. 请下载模型并解压到该路径。")
        exit()

    # 检查 FFmpeg 是否安装
    if not is_ffmpeg_installed():
        logging.error("FFmpeg 未安装，MP3 文件转换将不可用。请安装 FFmpeg 并确保其在系统 PATH 中。")

    # 创建输出目录和临时 WAV 目录
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_wav_dir, exist_ok=True)

    # 读取并按课程分割内容 (This part is still kept, but Vosk subtitle generation doesn't rely on text content anymore)
    text = read_file(file_path)
    lessons = extract_lesson_content(text)

    # 为每个课程生成字幕 (Now mainly relies on Vosk recognition)
    for lesson in lessons:
        lesson_num = get_lesson_number(lesson)
        audio_name = get_audio_file_name(audio_dir, lesson_num)
        logging.info(f"开始处理 Lesson {lesson_num}, 音频文件: {audio_name}")  # 新增日志：记录开始处理的课程

        # 查找对应的音频文件 (优先查找 WAV, 如果没有则查找 MP3)
        audio_path = None
        original_audio_path = None # 保存原始音频路径，用于后续判断是否需要删除临时 WAV
        for ext in ['.wav', '.mp3']: # 优先查找 WAV, 然后 MP3
            temp_path = os.path.join(audio_dir, audio_name + ext)
            if os.path.exists(temp_path):
                audio_path = temp_path
                original_audio_path = temp_path # 记录原始音频路径
                break

        if not audio_path:
            logging.warning(f"未找到音频文件 for Lesson {lesson_num}: {audio_name}.wav 或 {audio_name}.mp3")
            continue # Skip if no audio file is found

        output_path = os.path.join(output_dir, f"{audio_name}.srt")

        # **新增：检查 SRT 文件是否已存在**
        if os.path.exists(output_path):
            logging.info(f"SRT 文件已存在: {output_path}, 跳过处理。")
            continue  # 如果 SRT 文件已存在，则跳过当前课程

        # 如果是 MP3 文件，则转换为 WAV
        if audio_path.lower().endswith(".mp3"):
            wav_filename = f"{audio_name}.wav"
            wav_path = os.path.join(temp_wav_dir, wav_filename)
            logging.error(f"开始格式转换")
            if not convert_mp3_to_wav(audio_path, wav_path):
                logging.error(f"Lesson {lesson_num} ({audio_name}) MP3 to WAV 转换失败，跳过字幕生成。")
                continue  # 转换失败，跳过当前音频
            audio_path = wav_path # 使用转换后的 WAV 文件路径
            delete_wav_after_process = True  # 标记为处理后需要删除临时 WAV 文件
        else:
            delete_wav_after_process = False  # WAV 文件，无需删除

        output_path = os.path.join(output_dir, f"{audio_name}.srt")

        # 使用 Vosk 生成 SRT 字幕 (不再需要文本处理和翻译步骤)
        logging.info(f"开始调用 generate_srt_from_vosk 函数，音频路径: {audio_path}, 输出路径: {output_path}")  # 新增日志：记录函数调用开始
        if generate_srt_from_vosk(audio_path, output_path):
            logging.info(f"\n处理完成（Vosk, Aggregated）：{audio_name}")
            logging.info(f"音频时长：{get_audio_duration(audio_path)}秒")
            logging.info(f"字幕文件已保存到: {output_path}")

        else:
            logging.error(f"Lesson {lesson_num} ({audio_name}) Vosk 字幕生成失败.")

        # 如果是 MP3 转换来的 WAV，处理完成后删除临时 WAV 文件
        if delete_wav_after_process:
            try:
                os.remove(audio_path)
                logging.info(f"临时 WAV 文件 '{audio_path}' 已删除。")
            except OSError as e:
                logging.warning(f"删除临时 WAV 文件 '{audio_path}' 失败: {e}")

    logging.info("\n全部 Vosk 字幕生成处理完成 (Aggregated).")