import tkinter as tk
from tkinter import ttk
import pygame
from tkinter import filedialog
import speech_recognition as sr
import threading
import time
import wave
import contextlib


class AudioPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("音频播放器")

        # 初始化pygame混音器
        pygame.mixer.init()

        # 初始化语音识别器
        self.recognizer = sr.Recognizer()

        # 创建变量
        self.is_playing = False
        self.is_recording = False
        self.current_file = None
        self.segment_duration = 5
        self.current_segment = 0
        self.total_segments = 0

        # 创建界面
        self.create_widgets()

    def create_widgets(self):
        # 文件选择按钮
        self.select_button = ttk.Button(self.root, text="选择音频文件", command=self.select_file)
        self.select_button.pack(pady=10)

        # 显示当前文件名
        self.file_label = ttk.Label(self.root, text="未选择文件")
        self.file_label.pack(pady=5)

        # 音量控制
        volume_frame = ttk.LabelFrame(self.root, text="音量控制")
        volume_frame.pack(pady=10, padx=10, fill="x")

        self.volume_scale = ttk.Scale(volume_frame, from_=0, to=1, orient="horizontal",
                                    command=self.change_volume)
        self.volume_scale.set(0.5)  # 默认音量
        self.volume_scale.pack(fill="x", padx=10, pady=5)

        # 语速控制
        speed_frame = ttk.LabelFrame(self.root, text="语速控制")
        speed_frame.pack(pady=10, padx=10, fill="x")

        self.speed_scale = ttk.Scale(speed_frame, from_=0.5, to=2.0, orient="horizontal")
        self.speed_scale.set(1.0)  # 默认语速
        self.speed_scale.pack(fill="x", padx=10, pady=5)

        # 控制按钮框架
        control_frame = ttk.Frame(self.root)
        control_frame.pack(pady=10)

        # 播放/暂停按钮
        self.play_button = ttk.Button(control_frame, text="播放", command=self.play_pause)
        self.play_button.pack(side="left", padx=5)

        # 停止按钮
        self.stop_button = ttk.Button(control_frame, text="停止", command=self.stop)
        self.stop_button.pack(side="left", padx=5)

        # 跟读按钮
        self.follow_button = ttk.Button(control_frame, text="开始跟读", command=self.toggle_follow_reading)
        self.follow_button.pack(side="left", padx=5)

        # 文本显示区域
        self.text_frame = ttk.LabelFrame(self.root, text="跟读结果")
        self.text_frame.pack(pady=10, padx=10, fill="both", expand=True)

        self.original_text = tk.Text(self.text_frame, height=3, width=40)
        self.original_text.pack(pady=5, padx=5)

        self.follow_text = tk.Text(self.text_frame, height=3, width=40)
        self.follow_text.pack(pady=5, padx=5)

    # [其余方法保持不变]

    def select_file(self):
        """选择音频文件"""
        file_path = filedialog.askopenfilename(
            filetypes=[("Audio Files", "*.mp3 *.wav")])
        if file_path:
            self.current_file = file_path
            self.file_label.config(text=file_path.split("/")[-1])
            self.prepare_audio_segments()

    def prepare_audio_segments(self):
        """准备音频片段"""
        if self.current_file.endswith('.wav'):
            with contextlib.closing(wave.open(self.current_file, 'r')) as f:
                frames = f.getnframes()
                rate = f.getframerate()
                self.duration = frames / float(rate)
        else:
            # 对于MP3文件，这里使用一个估计值
            self.duration = 30  # 假设30秒

        # 将音频分成5秒一段
        self.segment_duration = 5
        self.total_segments = int(self.duration / self.segment_duration)
        self.current_segment = 0
        print(f"音频总长: {self.duration}秒，共{self.total_segments}段")

    def play_pause(self):
        """播放或暂停音频"""
        if not self.current_file:
            return

        if not self.is_playing:
            pygame.mixer.music.load(self.current_file)
            pygame.mixer.music.play()
            self.play_button.config(text="暂停")
            self.is_playing = True
        else:
            pygame.mixer.music.pause()
            self.play_button.config(text="播放")
            self.is_playing = False

    def play_segment(self):
        """播放当前片段"""
        if self.current_segment >= self.total_segments:
            self.stop()
            return

        start_time = self.current_segment * self.segment_duration
        pygame.mixer.music.load(self.current_file)
        pygame.mixer.music.play(start=start_time)

        # 设置定时器在片段结束时暂停
        self.root.after(self.segment_duration * 1000, self.pause_for_follow)
        print(f"播放第 {self.current_segment + 1} 段，开始时间：{start_time}秒")

    def pause_for_follow(self):
        """暂停等待跟读"""
        pygame.mixer.music.pause()
        print(f"暂停等待跟读，当前段落：{self.current_segment + 1}")

        # 等待10秒后播放下一段
        self.root.after(10000, self.play_next_segment)

    def play_next_segment(self):
        """播放下一段"""
        self.current_segment += 1
        if self.current_segment < self.total_segments:
            self.play_segment()
        else:
            self.stop()

    def toggle_follow_reading(self):
        """切换跟读状态"""
        if not self.is_recording:
            self.start_follow_reading()
            # 从头开始播放第一段
            self.current_segment = 0
            self.play_segment()
        else:
            self.stop_follow_reading()
            self.stop()

    def stop(self):
        """停止播放"""
        pygame.mixer.music.stop()
        self.play_button.config(text="播放")
        self.is_playing = False
        self.current_segment = 0

    def change_volume(self, value):
        """改变音量"""
        pygame.mixer.music.set_volume(float(value))


    def start_follow_reading(self):
        """开始跟读"""
        self.is_recording = True
        self.follow_button.config(text="停止跟读")
        self.recording_thread = threading.Thread(target=self.record_audio)
        self.recording_thread.start()

    def stop_follow_reading(self):
        """停止跟读"""
        self.is_recording = False
        self.follow_button.config(text="开始跟读")

    def record_audio(self):
        """录制音频并识别"""
        with sr.Microphone() as source:
            while self.is_recording:
                try:
                    self.follow_text.insert('end', "正在听取语音...\n")
                    audio = self.recognizer.listen(source, timeout=5)
                    self.follow_text.insert('end', "正在识别...\n")

                    text = self.recognizer.recognize_google(audio, language='zh-CN')
                    self.follow_text.insert('end', f"识别结果: {text}\n")

                except sr.WaitTimeoutError:
                    self.follow_text.insert('end', "未检测到语音输入\n")
                except sr.UnknownValueError:
                    self.follow_text.insert('end', "无法识别语音\n")
                except sr.RequestError:
                    self.follow_text.insert('end', "无法连接到语音识别服务\n")

                self.follow_text.see('end')
                time.sleep(0.1)


def main():
    root = tk.Tk()
    app = AudioPlayer(root)
    root.mainloop()


if __name__ == "__main__":
    main()