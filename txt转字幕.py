import re
import chardet  # 检查字符自适应编码


def read_file(file_path):
    """读取文本文件（自动检测编码）"""
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        encoding = chardet.detect(raw_data)['encoding']
    return raw_data.decode(encoding)


# def extract_content(text):
#     """提取Lesson之后到New Word之前的内容"""
#     # 使用正则表达式匹配Lesson到New Word之间的内容
#     pattern = r'Lesson \d+.*?(?=\nNew Word and expressions)'
#     match = re.search(pattern, text, re.DOTALL)
#     if match:
#         # 修改点2：去除多余空白字符
#         return re.sub(r'\s+', ' ', match.group()).strip()
#     else:
#         return ""

def extract_content(text):
    """提取所有Lesson内容（修复多课只取第一课的问题）"""
    # 修改点1：使用finditer处理多课内容
    pattern = r'(Lesson \d+.*?)(?=\nLesson \d+|\nNew Word and expressions)'
    lessons = []
    for match in re.finditer(pattern, text, re.DOTALL):
        lesson = re.sub(r'\s+', ' ', match.group(1)).strip()
        lessons.append(lesson)
    return '\n'.join(lessons)

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


def generate_srt(translated_sentences, output_path, duration=2):
    """生成SRT字幕文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for idx, sentence in enumerate(translated_sentences, 1):
            start_time = f"00:00:{(idx - 1) * duration:02d}"
            end_time = f"00:00:{(idx) * duration:02d}"
            f.write(f"{idx}\n")
            f.write(f"{start_time},000  --> {end_time},000\n")
            f.write(f"{sentence}\n\n")

        # 示例用法

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

if __name__ == "__main__":
    file_path = "新概念英语第一册.txt"
    file_name = 'E:\Music新概念英语\新概念英语第1册'
    output_path = "字幕文件/新概念英语第一册.srt"

    text = read_file(file_path)
    content = extract_content(text)
    sentences = split_sentences(content)
    translated_sentences = add_translations(sentences)
    generate_srt(translated_sentences, output_path)

    # 新增验证输出
    print("\n生成文件内容预览（前3段）：")
    for i, segment in enumerate(read_srt(output_path), 1):
        print(f"[第{i}段]")
        print(segment.strip())