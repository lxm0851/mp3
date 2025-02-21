
import tkinter as tk
from tkinter import ttk
import pygame
from tkinter import filedialog
import speech_recognition as sr
import threading
import time
import wave
import contextlib
import json
import os
from tkinter import messagebox


class AudioPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("音频播放器")
        self.root.geometry("800x600")

        # 初始化pygame混音器
        pygame.mixer.init()

        # 初始化变量
        self.playlist = []  # 播放列表
        self.current_index = 0  # 当前播放索引
        self.play_mode = "sequential"  # 播放模式：sequential/loop_one/loop_all
        self.settings_file = "player_settings.json"

        # 加载设置
        self.load_settings()

        # 创建界面
        self.create_widgets()

        # 绑定关闭窗口事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        # 创建主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 左侧播放列表框架
        playlist_frame = ttk.LabelFrame(main_frame, text="播放列表")
        playlist_frame.pack(side="left", fill="both", expand=True, padx=5)

        # 播放列表
        self.playlist_box = tk.Listbox(playlist_frame, selectmode=tk.SINGLE)
        self.playlist_box.pack(side="left", fill="both", expand=True)

        # 滚动条
        scrollbar = ttk.Scrollbar(playlist_frame, orient="vertical", command=self.playlist_box.yview)
        scrollbar.pack(side="right", fill="y")
        self.playlist_box.config(yscrollcommand=scrollbar.set)

        # 更新播放列表显示
        self.update_playlist_display()

        # 右侧控制面板
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(side="right", fill="both", padx=5)

        # 文件操作按钮
        file_frame = ttk.LabelFrame(control_frame, text="文件操作")
        file_frame.pack(fill="x", pady=5)

        ttk.Button(file_frame, text="添加文件", command=self.add_files).pack(side="left", padx=5)
        ttk.Button(file_frame, text="添加文件夹", command=self.add_folder).pack(side="left", padx=5)
        ttk.Button(file_frame, text="清空列表", command=self.clear_playlist).pack(side="left", padx=5)

        # 播放模式选择
        mode_frame = ttk.LabelFrame(control_frame, text="播放模式")
        mode_frame.pack(fill="x", pady=5)

        self.mode_var = tk.StringVar(value=self.play_mode)
        ttk.Radiobutton(mode_frame, text="顺序播放", variable=self.mode_var,
                        value="sequential").pack(side="left")
        ttk.Radiobutton(mode_frame, text="单曲循环", variable=self.mode_var,
                        value="loop_one").pack(side="left")
        ttk.Radiobutton(mode_frame, text="列表循环", variable=self.mode_var,
                        value="loop_all").pack(side="left")

        # 播放控制
        control_buttons = ttk.Frame(control_frame)
        control_buttons.pack(fill="x", pady=5)

        self.play_button = ttk.Button(control_buttons, text="播放", command=self.play_pause)
        self.play_button.pack(side="left", padx=5)

        ttk.Button(control_buttons, text="上一曲", command=self.previous_track).pack(side="left", padx=5)
        ttk.Button(control_buttons, text="下一曲", command=self.next_track).pack(side="left", padx=5)
        ttk.Button(control_buttons, text="停止", command=self.stop).pack(side="left", padx=5)

        # 音量控制
        volume_frame = ttk.LabelFrame(control_frame, text="音量控制")
        volume_frame.pack(fill="x", pady=5)

        self.volume_scale = ttk.Scale(volume_frame, from_=0, to=1, orient="horizontal",
                                      command=self.change_volume)
        self.volume_scale.set(0.5)
        self.volume_scale.pack(fill="x", padx=5)

        # 当前播放信息
        self.info_label = ttk.Label(control_frame, text="未播放")
        self.info_label.pack(pady=5)

    def add_files(self):
        """添加音频文件到播放列表"""
        files = filedialog.askopenfilenames(
            filetypes=[("Audio Files", "*.mp3 *.wav")])
        if files:
            self.playlist.extend(files)
            self.update_playlist_display()
            self.save_settings()

    def add_folder(self):
        """添加文件夹中的所有音频文件"""
        folder = filedialog.askdirectory()
        if folder:
            for root, dirs, files in os.walk(folder):
                for file in files:
                    if file.endswith(('.mp3', '.wav')):
                        self.playlist.append(os.path.join(root, file))
            self.update_playlist_display()
            self.save_settings()

    def update_playlist_display(self):
        """更新播放列表显示"""
        self.playlist_box.delete(0, tk.END)
        for file in self.playlist:
            self.playlist_box.insert(tk.END, os.path.basename(file))

    def play_pause(self):
        """播放或暂停"""
        if not self.playlist:
            messagebox.showinfo("提示", "播放列表为空")
            return

        if not pygame.mixer.music.get_busy():
            # 开始播放
            selected = self.playlist_box.curselection()
            if selected:
                self.current_index = selected[0]
            pygame.mixer.music.load(self.playlist[self.current_index])
            pygame.mixer.music.play()
            self.play_button.config(text="暂停")
            self.update_info_label()
        else:
            # 暂停播放
            pygame.mixer.music.pause()
            self.play_button.config(text="播放")

    def stop(self):
        """停止播放"""
        pygame.mixer.music.stop()
        self.play_button.config(text="播放")

    def previous_track(self):
        """播放上一曲"""
        if not self.playlist:
            return
        self.current_index = (self.current_index - 1) % len(self.playlist)
        self.play_current_track()

    def next_track(self):
        """播放下一曲"""
        if not self.playlist:
            return
        self.current_index = (self.current_index + 1) % len(self.playlist)
        self.play_current_track()

    def play_current_track(self):
        """播放当前曲目"""
        if 0 <= self.current_index < len(self.playlist):
            pygame.mixer.music.load(self.playlist[self.current_index])
            pygame.mixer.music.play()
            self.play_button.config(text="暂停")
            self.update_info_label()
            # 设置播放列表选中项
            self.playlist_box.selection_clear(0, tk.END)
            self.playlist_box.selection_set(self.current_index)
            self.playlist_box.see(self.current_index)

    def change_volume(self, value):
        """改变音量"""
        pygame.mixer.music.set_volume(float(value))

    def clear_playlist(self):
        """清空播放列表"""
        self.playlist = []
        self.current_index = 0
        self.update_playlist_display()
        self.stop()
        self.save_settings()

    def update_info_label(self):
        """更新当前播放信息"""
        if self.playlist:
            current_file = os.path.basename(self.playlist[self.current_index])
            self.info_label.config(text=f"正在播放: {current_file}")
        else:
            self.info_label.config(text="未播放")

    def save_settings(self):
        """保存播放器设置"""
        settings = {
            'playlist': self.playlist,
            'volume': self.volume_scale.get(),
            'play_mode': self.mode_var.get()
        }
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False)
        except Exception as e:
            print(f"保存设置失败: {e}")

    def load_settings(self):
        """加载播放器设置"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.playlist = settings.get('playlist', [])
                    self.play_mode = settings.get('play_mode', 'sequential')
                    volume = settings.get('volume', 0.5)
                    if hasattr(self, 'volume_scale'):
                        self.volume_scale.set(volume)
        except Exception as e:
            print(f"加载设置失败: {e}")

    def on_closing(self):
        """关闭窗口时的处理"""
        self.save_settings()
        self.root.destroy()

    def check_end_of_track(self):
        """检查当前曲目是否播放完毕，处理自动播放"""
        if not pygame.mixer.music.get_busy() and self.playlist:
            play_mode = self.mode_var.get()

            if play_mode == "sequential":
                if self.current_index < len(self.playlist) - 1:
                    self.next_track()
                else:
                    self.stop()
            elif play_mode == "loop_one":
                self.play_current_track()
            elif play_mode == "loop_all":
                self.next_track()

        # 定期检查
        self.root.after(1000, self.check_end_of_track)

    def start(self):
        """启动播放器"""
        # 开始检查播放状态
        self.check_end_of_track()
        # 开始主循环
        self.root.mainloop()

def main():
    root = tk.Tk()
    player = AudioPlayer(root)
    player.start()

if __name__ == "__main__":
    main()