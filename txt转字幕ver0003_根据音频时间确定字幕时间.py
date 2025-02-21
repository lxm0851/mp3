import re
import chardet  # 检查字符自适应编码
import os
from mutagen import File

def get_audio_duration(audio_path):
    """获取音频文件时长（秒）"""
    try:
        audio = File(audio_path)
        if audio is not None:
            return int(audio.info.length)
        return 0
    except Exception as e:
        print(f"获取音频时长出错: {e}")
        return 0

def read_file(file_path):
    """读取文本文件（自动检测编码）"""
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        encoding = chardet.detect(raw_data)['encoding']
    return raw_data.decode(encoding)


# def split_sentences(content):
#     """将内容拆分成句子"""
#     sentences = re.split(r'(?<=[.!?])[\s\u3000]+', content)  # \u3000匹配中文空格
#     sentences = [s.strip() for s in sentences if s.strip()]
#     return sentences

def split_sentences(content):
    """改进句子分割逻辑"""
    # 修改点：精确匹配中英文句尾
    sentences = re.split(
        r'(?<![A-Za-z)）])(?<=[.!?。！？])[\s\u3000]+',  # 增加中文右括号排除
        content
    )
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 1]  # 过滤短文本

def add_translations(sentences):
    """改进翻译配对逻辑"""
    translated_sentences = []
    # 修改点：增加步长检测和容错机制
    i = 0
    while i < len(sentences):
        original = sentences[i]
        # 寻找下一个非空行作为翻译
        j = i + 1
        while j < len(sentences) and len(sentences[j].strip()) < 2:  # 过滤短文本
            j += 1
        # 提取翻译内容
        translation = sentences[j] if j < len(sentences) else "Translation not available"
        # 跳过已处理的翻译行
        i = j + 1 if j < len(sentences) else i + 1
        translated_sentences.append(f"{original}\n{translation}")
    return translated_sentences


def generate_srt(translated_sentences, output_path, audio_path=None):
    """生成SRT字幕文件（根据音频时长调整）"""
    # 获取音频总时长
    total_duration = get_audio_duration(audio_path) if audio_path else 0

    # 如果无法获取音频时长，使用默认值
    if not total_duration:
        total_duration = len(translated_sentences) * 3  # 每句默认3秒

    # 计算每句话平均时长
    avg_duration = total_duration / len(translated_sentences)

    with open(output_path, 'w', encoding='utf-8') as f:
        for idx, sentence in enumerate(translated_sentences, 1):
            start_seconds = int((idx - 1) * avg_duration)
            end_seconds = int(idx * avg_duration)

            # 转换为 HH:MM:SS 格式
            start_time = f"{start_seconds // 3600:02d}:{(start_seconds % 3600) // 60:02d}:{start_seconds % 60:02d}"
            end_time = f"{end_seconds // 3600:02d}:{(end_seconds % 3600) // 60:02d}:{end_seconds % 60:02d}"

            f.write(f"{idx}\n")
            f.write(f"{start_time},000 --> {end_time},000\n")
            f.write(f"{sentence}\n\n")

# def read_srt(output_path, num=3):
#     """读取并返回前N段SRT内容"""
#     try:
#         with open(output_path, 'r', encoding='utf-8') as f:
#             content = f.read()
#             # 按空行分割字幕段落
#             segments = re.split(r'\n{100,}', content)
#             return segments[:num]
#     except FileNotFoundError:
#         return []

def read_srt(output_path, num=3):
    """修复SRT读取逻辑"""
    try:
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 修改点3：正确分割段落（两个换行符）
            segments = re.split(r'\n{50,}', content)
            return [s for s in segments[:num] if s.strip()]
    except FileNotFoundError:
        return []

def extract_lesson_content(text):
    """按课程提取内容"""
    # 将(?i)移到正则表达式开头
    pattern = r'(?i)(Lesson \d+.*?)(?=\nLesson \d+|\nNew Word(?:s)? and expressions|$)'
    lessons = []
    for match in re.finditer(pattern, text, re.DOTALL):
        lesson = re.sub(r'\s+', ' ', match.group(1)).strip()
        lessons.append(lesson)
    return lessons

def extract_content(text):
    """提取所有Lesson内容"""
    # 将(?i)移到正则表达式开头
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
    file_path = "新概念英语第一册.txt"
    audio_dir = r'E:\Music新概念英语\新概念英语第1册'
    output_dir = "字幕文件"

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 读取并按课程分割内容
    text = read_file(file_path)
    lessons = extract_lesson_content(text)

    # 为每个课程生成字幕
    for lesson in lessons:
        lesson_num = get_lesson_number(lesson)
        audio_name = get_audio_file_name(audio_dir, lesson_num)

        # 查找对应的音频文件
        audio_path = None
        for ext in ['.mp3', '.wav', '.m4a']:  # 支持多种音频格式
            temp_path = os.path.join(audio_dir, audio_name + ext)
            if os.path.exists(temp_path):
                audio_path = temp_path
                break

        output_path = os.path.join(output_dir, f"{audio_name}.srt")

        # 处理单课内容
        sentences = split_sentences(lesson)
        translated_sentences = add_translations(sentences)

        # 生成字幕（传入音频文件路径）
        generate_srt(translated_sentences, output_path, audio_path)

        # 打印处理信息
        print(f"\n处理完成：{audio_name}")
        if audio_path:
            print(f"音频时长：{get_audio_duration(audio_path)}秒")
        print("内容预览（前3段）：")
        for i, segment in enumerate(read_srt(output_path, 3), 1):
            print(f"[第{i}段]")
            print(segment.strip())