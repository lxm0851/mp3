import tkinter as tk
from tkinter import ttk
import pygame
from tkinter import filedialog
import os
import json
from tkinter import messagebox

#自然排序处理
from natsort import natsorted
import re

import speech_recognition as sr
import threading
import time
import wave
import contextlib


class AudioPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("音频播放器")
        self.root.geometry("1000x800")  # 增加高度以容纳跟读功能

        # 初始化pygame混音器
        pygame.mixer.init()

        # 初始化语音识别器
        # self.recognizer = sr.Recognizer()

        # 添加音频进度相关变量
        self.current_audio_length = 0
        self.is_seeking = False

        # 初始化变量
        self.folders = {}  # 存储文件夹及其音频文件
        self.current_playlist = []  # 当前播放列表
        self.current_index = 0  # 当前播放索引
        self.play_mode = "sequential"  # 播放模式
        self.settings_file = "player_settings.json"
        self.is_playing = False

        # 跟读相关变量
        self.is_following = False  # 改名以更好反映功能
        self.segment_duration = 5
        self.current_segment = 0
        self.total_segments = 0

        # 添加循环计数相关变量
        self.current_loop = 0  # 当前循环次数
        self.max_follow_loops = 1  # 跟读模式最大循环次数

        # # 启动进度更新
        # self.update_progress()
        self.update_timer = None  # 添加计时器变量

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

        # 左侧文件夹树形结构
        folder_frame = ttk.LabelFrame(main_frame, text="文件夹")
        folder_frame.pack(side="left", fill="both", expand=True, padx=5)

        # 创建树形视图
        self.folder_tree = ttk.Treeview(folder_frame, selectmode="browse")
        self.folder_tree.pack(side="left", fill="both", expand=True)

        # 添加滚动条
        tree_scroll = ttk.Scrollbar(folder_frame, orient="vertical",
                                    command=self.folder_tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.folder_tree.configure(yscrollcommand=tree_scroll.set)

        # 设置树形列头
        self.folder_tree["columns"] = ("duration",)
        self.folder_tree.column("#0", width=300, minwidth=200)
        self.folder_tree.column("duration", width=100, minwidth=50)
        self.folder_tree.heading("#0", text="名称")
        self.folder_tree.heading("duration", text="时长")

        # 绑定树形视图事件
        self.folder_tree.bind("<Double-1>", self.on_tree_double_click)
        self.folder_tree.bind("<Button-1>", self.on_tree_single_click)

        # 右侧控制面板
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(side="right", fill="both", padx=5)

        # 文件操作按钮
        file_frame = ttk.LabelFrame(control_frame, text="文件操作")
        file_frame.pack(fill="x", pady=5)

        ttk.Button(file_frame, text="添加文件夹",
                   command=self.add_folder).pack(side="left", padx=5)
        ttk.Button(file_frame, text="移除选中文件夹",
                   command=self.remove_selected_folder).pack(side="left", padx=5)
        ttk.Button(file_frame, text="播放选中文件夹",
                   command=self.play_selected_folder).pack(side="left", padx=5)

        # 播放模式选择
        mode_frame = ttk.LabelFrame(control_frame, text="播放模式")
        mode_frame.pack(fill="x", pady=5)

        # 新增循环次数输入框
        loop_frame = ttk.Frame(mode_frame)
        loop_frame.pack(side="left", padx=5)
        ttk.Label(loop_frame, text="循环次数:").pack(side="left")
        self.loop_count = tk.IntVar(value=1)  # 默认循环1次
        self.loop_spin = ttk.Spinbox(loop_frame, from_=1, to=999, width=3, textvariable=self.loop_count)
        self.loop_spin.pack(side="left", padx=2)

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

        self.play_button = ttk.Button(control_buttons, text="播放",
                                      command=self.play_pause)
        self.play_button.pack(side="left", padx=5)

        ttk.Button(control_buttons, text="上一曲",
                   command=self.previous_track).pack(side="left", padx=5)
        ttk.Button(control_buttons, text="下一曲",
                   command=self.next_track).pack(side="left", padx=5)
        ttk.Button(control_buttons, text="停止",
                   command=self.stop).pack(side="left", padx=5)

        # 音量控制
        volume_frame = ttk.LabelFrame(control_frame, text="音量控制")
        volume_frame.pack(fill="x", pady=5)

        self.volume_scale = ttk.Scale(volume_frame, from_=0, to=1,
                                      orient="horizontal", command=self.change_volume)
        self.volume_scale.set(0.5)
        self.volume_scale.pack(fill="x", padx=5)

        # 当前播放信息
        self.info_label = ttk.Label(control_frame, text="未播放")
        self.info_label.pack(pady=5)

        # 添加跟读控制区域
        follow_frame = ttk.LabelFrame(control_frame, text="跟读控制")
        follow_frame.pack(fill="x", pady=5)

        # 语速控制
        speed_frame = ttk.Frame(follow_frame)
        speed_frame.pack(fill="x", pady=5)
        ttk.Label(speed_frame, text="语速:").pack(side="left")
        self.speed_scale = ttk.Scale(speed_frame, from_=0.5, to=2.0,
                                     orient="horizontal")
        self.speed_scale.set(1.0)
        self.speed_scale.pack(side="left", fill="x", expand=True)

        # 跟读按钮
        self.follow_button = ttk.Button(follow_frame, text="开始跟读",
                                        command=self.toggle_follow_reading)
        self.follow_button.pack(pady=5)

        # 跟读文本显示区域
        text_frame = ttk.LabelFrame(control_frame, text="跟读结果")
        text_frame.pack(fill="both", expand=True, pady=5)

        self.follow_text = tk.Text(text_frame, height=6, width=40)
        self.follow_text.pack(pady=5, padx=5, fill="both", expand=True)

        # 播放进度控制
        progress_frame = ttk.LabelFrame(control_frame, text="播放进度")
        progress_frame.pack(fill="x", pady=5)

        # 快进快退按钮和进度条框架
        progress_control_frame = ttk.Frame(progress_frame)
        progress_control_frame.pack(fill="x", padx=5)

        # 后退15秒
        ttk.Button(progress_control_frame, text="◀◀", width=3,
                   command=lambda: self.seek_relative(-15)).pack(side="left", padx=2)

        # 进度条
        self.progress_scale = ttk.Scale(progress_control_frame, from_=0, to=100,
                                        orient="horizontal",
                                        command=self.seek_absolute)
        self.progress_scale.pack(side="left", fill="x", expand=True, padx=5)

        # 前进15秒
        ttk.Button(progress_control_frame, text="▶▶", width=3,
                   command=lambda: self.seek_relative(15)).pack(side="left", padx=2)

        # 时间显示框架
        time_frame = ttk.Frame(progress_frame)
        time_frame.pack(fill="x", padx=5)

        # 当前时间/总时间
        self.time_label = ttk.Label(time_frame, text="00:00 / 00:00")
        self.time_label.pack(side="right", padx=5)

        # 进度条事件绑定
        self.progress_scale.bind("<Button-1>", self.on_progress_press)
        self.progress_scale.bind("<ButtonRelease-1>", self.on_progress_release)

    def on_progress_press(self, event):
        """进度条按下事件"""
        self.is_seeking = True

    def on_progress_release(self, event):
        """进度条释放事件"""
        if self.current_playlist and self.is_playing:
            try:
                pos = self.progress_scale.get()
                total_length = self.get_current_audio_length()
                seek_time = (pos / 100.0) * total_length
                pygame.mixer.music.play(start=seek_time)
            except:
                pass
        self.is_seeking = False

    def seek_relative(self, seconds):
        """相对定位（快进快退）"""
        if not self.current_playlist or not self.is_playing:
            return

        try:
            current_pos = pygame.mixer.music.get_pos() / 1000  # 当前位置（秒）
            if current_pos < 0:  # 如果获取失败，重置为0
                current_pos = 0

            total_length = self.get_current_audio_length()
            new_pos = max(0, min(current_pos + seconds, total_length))  # 确保在有效范围内

            # 重新加载并播放到新位置
            current_file = self.current_playlist[self.current_index]
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play(start=new_pos)

            # 更新进度显示
            if total_length > 0:
                progress = (new_pos / total_length) * 100
                self.progress_scale.set(progress)

            # 更新时间显示
            current_time = self.format_time(new_pos)
            total_time = self.format_time(total_length)
            self.time_label.config(text=f"{current_time} / {total_time}")

        except Exception as e:
            print(f"快进/快退失败: {str(e)}")

    def update_progress(self):
        """更新进度并检测播放状态"""
        if not self.is_playing:
            return

        try:
            # 检查播放状态
            if not pygame.mixer.music.get_busy():
                self.handle_playback_ended()  # 播放结束时调用处理
                return

            # 更新进度显示
            current_pos = pygame.mixer.music.get_pos()
            if current_pos > 0:
                current_pos = current_pos / 1000
                total_length = self.get_current_audio_length()

                if total_length > 0:
                    progress = min((current_pos / total_length) * 100, 100)
                    self.progress_scale.set(progress)

                current_time = self.format_time(current_pos)
                total_time = self.format_time(total_length)
                self.time_label.config(text=f"{current_time} / {total_time}")

        except Exception as e:
            print(f"更新进度出错: {str(e)}")

        # 继续监测
        self.update_timer = self.root.after(100, self.update_progress)

    def format_time(self, seconds):
        """格式化时间显示"""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def get_current_audio_length(self):
        """获取当前音频文件的总长度"""
        if not self.current_playlist:
            return 0
        try:
            audio = pygame.mixer.Sound(self.current_playlist[self.current_index])
            return audio.get_length()
        except:
            return 0

    # 在类中添加自然排序方法
    def natural_sort_key(self, s):
        return [int(text) if text.isdigit() else text.lower()
                for text in re.split(r'(\d+)', s)]

    # 修改add_folder方法中的文件扫描部分
    def add_folder(self):
        """添加文件夹"""
        folder_path = filedialog.askdirectory()
        if folder_path:
            folder_name = os.path.basename(folder_path)
            folder_id = self.folder_tree.insert("", "end", text=folder_name,
                                                values=("",), open=False)

            # 扫描并自然排序音频文件
            audio_files = []
            for root, dirs, files in os.walk(folder_path):
                # 先对目录进行自然排序
                dirs[:] = natsorted(dirs, key=lambda x: re.split(r'(\d+)', x))

                # 对文件进行自然排序
                natural_files = natsorted(
                    [f for f in files if f.endswith(('.mp3', '.wav'))],
                    key=lambda x: re.split(r'(\d+)', x)
                )

                for file in natural_files:
                    full_path = os.path.join(root, file)
                    audio_files.append(full_path)

            self.folders[folder_id] = {
                'path': folder_path,
                'files': audio_files,
                'expanded': False
            }
            self.save_settings()

    def on_tree_double_click(self, event):
        """处理树形视图的双击事件"""
        item = self.folder_tree.selection()[0]
        parent = self.folder_tree.parent(item)

        if not parent:  # 是文件夹节点
            if item in self.folders:
                if not self.folders[item]['expanded']:
                    # 展开文件夹
                    self.expand_folder(item)
                else:
                    # 收起文件夹
                    self.collapse_folder(item)
        else:  # 是音频文件
            self.play_audio_file(item)

    # 修改expand_folder方法
    def expand_folder(self, folder_id):
        """展开文件夹（按自然顺序）"""
        for child in self.folder_tree.get_children(folder_id):
            self.folder_tree.delete(child)

        # 按自然顺序添加文件
        for file_path in self.folders[folder_id]['files']:
            file_name = os.path.basename(file_path)
            duration = self.get_audio_duration(file_path)
            self.folder_tree.insert(folder_id, "end", text=file_name,
                                    values=(duration,))

        self.folders[folder_id]['expanded'] = True

    def collapse_folder(self, folder_id):
        """收起文件夹"""
        for child in self.folder_tree.get_children(folder_id):
            self.folder_tree.delete(child)
        self.folders[folder_id]['expanded'] = False

    def get_audio_duration(self, file_path):
        """获取音频文件时长"""
        try:
            pygame.mixer.music.load(file_path)
            audio = pygame.mixer.Sound(file_path)
            duration = audio.get_length()
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            return f"{minutes}:{seconds:02d}"
        except:
            return "未知"

    def on_tree_single_click(self, event):
        """处理单击事件"""
        selection = self.folder_tree.selection()
        if selection:
            item = selection[0]
            # 更新信息标签
            self.update_info_label(item)

    def play_selected_folder(self):
        """播放选中文件夹的所有音频"""
        selection = self.folder_tree.selection()
        if not selection:
            return

        folder_id = selection[0]
        if folder_id in self.folders:
            self.current_playlist = self.folders[folder_id]['files']
            self.current_index = 0
            self.play_current_track()

    def play_audio_file(self, item):
        """播放选中的音频文件"""
        parent = self.folder_tree.parent(item)
        if parent and parent in self.folders:
            file_name = self.folder_tree.item(item)['text']
            folder_files = self.folders[parent]['files']

            # 查找对应的文件路径
            for file_path in folder_files:
                if os.path.basename(file_path) == file_name:
                    self.current_playlist = folder_files
                    self.current_index = folder_files.index(file_path)
                    self.play_current_track()
                    break

    def handle_audio_error(func):
        # 建议添加一个错误处理装饰器来统一处理异常
        """音频操作错误处理装饰器"""

        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except pygame.error as e:
                messagebox.showerror("音频错误", f"操作失败: {str(e)}")
            except Exception as e:
                messagebox.showerror("错误", f"未知错误: {str(e)}")

        return wrapper

    # 然后可以用于关键方法  建议添加一个错误处理装饰器来统一处理异常
    def handle_playback_ended(self):
        """处理播放结束事件"""
        # 跟读模式处理
        if self.is_following:
            if self.current_segment >= self.total_segments:
                self.current_loop += 1
                if self.current_loop < self.loop_count.get():
                    self.current_segment = 0
                    self.follow_text.insert('end', f"重新跟读第 {self.current_loop + 1} 次\n")
                    self.play_segment()
                else:
                    if self.current_index < len(self.current_playlist) - 1:
                        self.current_index += 1
                        self.current_loop = 0
                        self.start_follow_reading()
                    else:
                        self.stop_follow_reading()
            return

        # 普通模式处理
        max_loops = self.loop_count.get()
        current_file = os.path.basename(self.current_playlist[self.current_index])
        # print('循环次数和总次数1：', self.current_loop, max_loops)

        # 修改这里：确保完整循环次数
        if self.current_loop < max_loops - 1:
            self.current_loop += 1
            # print(f"继续播放当前曲目，第{self.current_loop + 1}次")
            pygame.mixer.music.load(self.current_playlist[self.current_index])
            pygame.mixer.music.play()
            self.info_label.config(text=f"当前播放: {current_file} ({self.current_loop + 1}/{max_loops})")
            # 继续监测状态
            self.check_playback_status()
            return

        # print('循环次数和总次数2：', self.current_loop, max_loops)
        # 达到循环次数后的处理...
        self.current_loop = 0
        play_mode = self.mode_var.get()

        if play_mode == "sequential":
            if self.current_index < len(self.current_playlist) - 1:
                self.next_track()
            else:
                self.stop()
        elif play_mode == "loop_one":
            self.play_current_track()
        elif play_mode == "loop_all":
            self.next_track()

    def play_current_track(self):
        """播放当前曲目"""
        if not self.current_playlist or self.current_index >= len(self.current_playlist):
            return

        try:
            current_file = self.current_playlist[self.current_index]
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play()
            self.is_playing = True
            self.play_button.config(text="暂停")

            # 重置显示和进度
            self.progress_scale.set(0)
            max_loops = self.loop_count.get()
            current_file = os.path.basename(current_file)

            # 不在这里重置循环计数，由handle_playback_ended管理
            self.info_label.config(text=f"当前播放: {current_file} ({self.current_loop + 1}/{max_loops})")

            # 启动状态监测
            self.check_playback_status()

        except Exception as e:
            messagebox.showerror("错误", f"播放失败: {str(e)}")

    def check_playback_status(self):
        """检查播放状态"""
        if self.is_playing:
            if not pygame.mixer.music.get_busy():
                self.handle_playback_ended()
            else:
                # 继续监听
                self.root.after(100, self.check_playback_status)

    def seek_absolute(self, value):
        """绝对定位（拖动进度条）"""
        if not self.current_playlist or not self.is_playing:
            return

        try:
            total_length = self.get_current_audio_length()
            seek_pos = (float(value) / 100.0) * total_length

            # 重新加载并播放到指定位置
            current_file = self.current_playlist[self.current_index]
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play(start=seek_pos)

        except Exception as e:
            print(f"定位出错: {str(e)}")

    def play_pause(self):
        """播放/暂停功能"""
        if self.is_following:
            return  # 跟读模式下不响应普通播放/暂停

        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.play_button.config(text="播放")
        else:
            if not pygame.mixer.music.get_busy():
                # 如果没有正在播放的音频，重新开始播放
                self.play_current_track()
            else:
                # 继续播放暂停的音频
                pygame.mixer.music.unpause()
                self.is_playing = True
                self.play_button.config(text="暂停")

    def stop(self):
        """停止播放并重置状态"""
        pygame.mixer.music.stop()
        self.is_playing = False

        # 取消计时器
        if self.update_timer:
            self.root.after_cancel(self.update_timer)
            self.update_timer = None

        self.play_button.config(text="播放")
        self.info_label.config(text="未播放")
        self.progress_scale.set(0)
        self.time_label.config(text="00:00 / 00:00")

        if self.is_following:
            self.stop_follow_reading()

    def load_audio_file(self, file_path):
        """加载音频文件并获取时长"""
        try:
            pygame.mixer.music.load(file_path)
            audio = pygame.mixer.Sound(file_path)
            self.current_audio_length = audio.get_length()
            return True
        except Exception as e:
            messagebox.showerror("错误", f"加载音频失败: {str(e)}")
            return False

    def previous_track(self):
        """播放上一曲"""
        if not self.current_playlist:
            return

        # 更新索引
        self.current_index = (self.current_index - 1) % len(self.current_playlist)

        # 重置进度显示
        self.progress_scale.set(0)
        self.time_label.config(text="00:00 / 00:00")

        # 更新显示的文件名称
        current_file = os.path.basename(self.current_playlist[self.current_index])
        self.info_label.config(text=f"当前播放: {current_file}")

        # 播放新的曲目
        self.play_current_track()

    def next_track(self):
        """播放下一曲"""
        if not self.current_playlist:
            return

        # 更新索引
        self.current_index = (self.current_index + 1) % len(self.current_playlist)

        # 重置进度显示
        self.progress_scale.set(0)
        self.time_label.config(text="00:00 / 00:00")

        # 更新显示的文件名称
        current_file = os.path.basename(self.current_playlist[self.current_index])
        self.info_label.config(text=f"当前播放: {current_file}")

        # 播放新的曲目
        self.play_current_track()

    def change_volume(self, value):
        """改变音量"""
        pygame.mixer.music.set_volume(float(value))

    def remove_selected_folder(self):
        """移除选中的文件夹"""
        selection = self.folder_tree.selection()
        if selection:
            folder_id = selection[0]
            if folder_id in self.folders:
                # 删除所有子节点
                for child in self.folder_tree.get_children(folder_id):
                    self.folder_tree.delete(child)
                # 删除父节点
                self.folder_tree.delete(folder_id)
                del self.folders[folder_id]
                self.save_settings()
                # 强制刷新界面
                self.root.update()

    def update_info_label(self, item=None):
        """更新信息标签"""
        if item:
            if item in self.folders:
                folder_name = self.folder_tree.item(item)['text']
                file_count = len(self.folders[item]['files'])
                self.info_label.config(text=f"文件夹: {folder_name} ({file_count}个文件)")
            else:
                file_name = self.folder_tree.item(item)['text']
                self.info_label.config(text=f"当前播放: {file_name}")
        elif self.current_playlist and 0 <= self.current_index < len(self.current_playlist):
            current_file = os.path.basename(self.current_playlist[self.current_index])
            self.info_label.config(text=f"当前播放: {current_file}")
        else:
            self.info_label.config(text="未播放")

    def save_settings(self):
        """保存设置"""
        settings = {
            'folders': {k: v for k, v in self.folders.items()},
            'volume': self.volume_scale.get(),
            'play_mode': self.mode_var.get()
        }
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False)
        except Exception as e:
            print(f"保存设置失败: {e}")

    def load_settings(self):
        """加载设置"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.folders = settings.get('folders', {})
                    self.play_mode = settings.get('play_mode', 'sequential')
                    volume = settings.get('volume', 0.5)
                    if hasattr(self, 'volume_scale'):
                        self.volume_scale.set(volume)
        except Exception as e:
            print(f"加载设置失败: {e}")

    # def check_end_of_track(self):
    #     """检查当前曲目是否播放完毕，处理自动播放"""
    #     if self.is_playing and not pygame.mixer.music.get_busy():
    #         play_mode = self.mode_var.get()
    #
    #         if play_mode == "sequential":
    #             if self.current_index < len(self.current_playlist) - 1:
    #                 self.next_track()
    #             else:
    #                 self.stop()
    #         elif play_mode == "loop_one":
    #             self.play_current_track()
    #         elif play_mode == "loop_all":
    #             self.next_track()
    #
    #     # 定期检查
    #     self.root.after(1000, self.check_end_of_track)

    def on_closing(self):
        """关闭窗口时的处理"""
        # 取消计时器
        if self.update_timer:
            self.root.after_cancel(self.update_timer)

        self.save_settings()
        pygame.mixer.quit()
        self.root.destroy()

    def start(self):
        """启动播放器"""
        # 恢复文件夹树形结构
        self.restore_folder_tree()
        # 开始检查播放状态
        # self.check_end_of_track()
        # 开始主循环
        self.root.mainloop()

    # 修改restore_folder_tree方法
    def restore_folder_tree(self):
        """恢复文件夹树形结构（带自然排序）"""
        # 创建原始键的副本列表用于遍历
        original_keys = list(self.folders.keys())

        for folder_id in original_keys:
            # 检查键是否仍然存在（可能在之前的迭代中被删除）
            if folder_id not in self.folders:
                continue

            folder_info = self.folders[folder_id]
            folder_path = folder_info['path']
            folder_name = os.path.basename(folder_path)

            # 创建新的树节点
            new_id = self.folder_tree.insert("", "end", text=folder_name, values=("",))

            # 对文件列表进行自然排序
            sorted_files = natsorted(
                folder_info['files'],
                key=lambda x: re.split(r'(\d+)', os.path.basename(x))
            )

            # 更新字典（先添加新条目再删除旧条目）
            self.folders[new_id] = {
                'path': folder_path,
                'files': sorted_files,
                'expanded': False
            }
            del self.folders[folder_id]  # 安全删除旧键

    def get_folder_size(self, folder_path):
        """获取文件夹大小"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(folder_path):
            for f in filenames:
                if f.endswith(('.mp3', '.wav')):
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
        return self.format_size(total_size)

    def format_size(self, size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f}{unit}"
            size /= 1024
        return f"{size:.2f}TB"

    # 改进跟读功能
    def prepare_audio_segments(self):
        """精确计算音频时长和分段"""
        current_file = self.current_playlist[self.current_index]
        try:
            with contextlib.closing(wave.open(current_file, 'r')) as f:
                frames = f.getnframes()
                rate = f.getframerate()
                self.duration = frames / float(rate)
        except:
            # 非WAV文件使用pygame获取时长
            audio = pygame.mixer.Sound(current_file)
            self.duration = audio.get_length()

        # 精确计算分段
        self.segment_duration = 5
        self.total_segments = int(self.duration // self.segment_duration) + 1
        self.current_segment = 0
        self.follow_text.insert('end', f"音频总长: {self.duration:.1f}秒，共{self.total_segments}段\n")
        self.follow_text.see('end')

    def play_segment(self):
        """播放当前片段"""
        if not self.current_playlist or self.current_segment >= self.total_segments:
            self.stop_follow_reading()
            return

        current_file = self.current_playlist[self.current_index]
        start_time = self.current_segment * self.segment_duration

        try:
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play(start=start_time)
            self.is_playing = True
            self.play_button.config(text="暂停")

            # 更新显示信息
            current_file = os.path.basename(current_file)
            # lesson_num = self.current_index + 1
            # total_lessons = len(self.current_playlist)
            # self.info_label.config(
            #     text=f"课程 {lesson_num}/{total_lessons} - {current_file} "
            #          f"(第{self.current_loop + 1}次跟读, 段{self.current_segment + 1}/{self.total_segments})"
            # )
            max_loops = self.loop_count.get()
            self.info_label.config(text=f"当前播放: {current_file} ({self.current_loop + 1}/{max_loops})")

            # 设置定时器在片段结束时暂停
            self.root.after(self.segment_duration * 1000, self.pause_for_follow)
            self.follow_text.insert('end', f"播放第 {self.current_segment + 1} 段\n")
            self.follow_text.see('end')
        except Exception as e:
            messagebox.showerror("错误", f"播放失败: {str(e)}")

    def pause_for_follow(self):
        """暂停等待跟读"""
        if self.is_following:  # 只在跟读模式下执行
            pygame.mixer.music.pause()
            self.is_playing = False
            self.play_button.config(text="播放")
            self.follow_text.insert('end', "请开始跟读...\n")
            self.follow_text.see('end')

            # 等待8秒后播放下一段
            self.root.after(8000, self.play_next_segment)

    # 修改play_next_segment方法
    def play_next_segment(self):
        """处理跟读模式下的分段播放"""
        if not self.is_following:
            return

        self.current_segment += 1
        if self.current_segment < self.total_segments:
            # 继续播放当前音频的下一段
            self.play_segment()
        else:
            # 当前音频播放完毕
            self.current_loop += 1
            if self.current_loop < self.max_follow_loops:
                # 未达到循环次数,重新开始当前音频
                self.current_segment = 0
                self.follow_text.insert('end',
                                        f"\n重新跟读第 {self.current_loop + 1} 次\n")
                self.play_segment()
            else:
                # 达到循环次数
                if self.current_index < len(self.current_playlist) - 1:
                    # 还有下一个音频,继续跟读
                    self.current_index += 1
                    self.current_loop = 0
                    self.start_follow_reading()
                else:
                    # 所有音频都完成了
                    self.stop_follow_reading()

    def toggle_follow_reading(self):
        """切换跟读状态"""
        if not self.is_following:
            if not self.current_playlist:
                messagebox.showwarning("警告", "请先选择要跟读的音频文件")
                return

            self.start_follow_reading()
        else:
            self.stop_follow_reading()

    # 修改start_follow_reading方法
    def start_follow_reading(self):
        """开始跟读"""
        self.is_following = True
        self.follow_button.config(text="停止跟读")

        # 保存并重置循环计数
        self.current_loop = 0
        self.max_follow_loops = self.loop_count.get()

        self.prepare_audio_segments()
        self.current_segment = 0

        # 重置显示
        self.progress_scale.set(0)
        self.time_label.config(text="00:00 / 00:00")
        self.follow_text.delete('1.0', 'end')
        self.follow_text.insert('end',
                                f"开始跟读第 {self.current_index + 1} 个音频文件 (1/{self.max_follow_loops})\n")
        self.play_segment()

    def stop_follow_reading(self):
        """停止跟读"""
        self.is_following = False
        self.follow_button.config(text="开始跟读")
        pygame.mixer.music.stop()
        self.is_playing = False
        self.play_button.config(text="播放")
        self.follow_text.insert('end', "跟读已停止\n")
        self.follow_text.see('end')

    def record_audio(self):
        """录制音频并识别(已禁用)"""
        self.follow_text.insert('end', "语音识别功能已禁用\n")
        self.follow_text.see('end')
        # 不需要while循环，直接返回
        return

        # while self.is_following:
        #     time.sleep(1)
        #     # 注释掉原有的语音识别代码
        #     # with sr.Microphone() as source:
        #     #     try:
        #     #         self.follow_text.insert('end', "正在听取语音...\n")
        #     #         audio = self.recognizer.listen(source, timeout=5)
        #     #         self.follow_text.insert('end', "正在识别...\n")
        #     #
        #     #         text = self.recognizer.recognize_google(audio, language='zh-CN')
        #     #         self.follow_text.insert('end', f"识别结果: {text}\n")
        #     #
        #     #     except sr.WaitTimeoutError:
        #     #         self.follow_text.insert('end', "未检测到语音输入\n")
        #     #     except sr.UnknownValueError:
        #     #         self.follow_text.insert('end', "无法识别语音\n")
        #     #     except sr.RequestError:
        #     #         self.follow_text.insert('end', "无法连接到语音识别服务\n")
        #     #
        #     #     self.follow_text.see('end')


def main():
    root = tk.Tk()
    root.title("音频播放器")

    # 设置窗口图标（如果有的话）
    try:
        root.iconbitmap('player_icon.ico')
    except:
        pass

    # 设置窗口最小尺寸
    root.minsize(800, 500)

    # 创建播放器实例
    player = AudioPlayer(root)

    # 启动播放器
    player.start()

if __name__ == "__main__":
    main()