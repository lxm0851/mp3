import tkinter as tk
from tkinter import ttk
import pygame
from tkinter import filedialog


class AudioPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("音频播放器")

        # 初始化pygame混音器
        pygame.mixer.init()

        # 创建变量
        self.is_playing = False
        self.current_file = None

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

        # 跟读按钮（功能未实现）
        self.follow_button = ttk.Button(control_frame, text="跟读")
        self.follow_button.pack(side="left", padx=5)

    def select_file(self):
        """选择音频文件"""
        file_path = filedialog.askopenfilename(
            filetypes=[("Audio Files", "*.mp3 *.wav")])
        if file_path:
            self.current_file = file_path
            self.file_label.config(text=file_path.split("/")[-1])

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

    def stop(self):
        """停止播放"""
        pygame.mixer.music.stop()
        self.play_button.config(text="播放")
        self.is_playing = False

    def change_volume(self, value):
        """改变音量"""
        pygame.mixer.music.set_volume(float(value))


def main():
    root = tk.Tk()
    app = AudioPlayer(root)
    root.mainloop()


if __name__ == "__main__":
    main()