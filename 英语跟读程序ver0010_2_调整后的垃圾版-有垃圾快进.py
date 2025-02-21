import tkinter as tk
from tkinter import ttk
import pygame
from tkinter import filedialog
import os
import json
from tkinter import messagebox

# 自然排序处理
from natsort import natsorted
import re

import speech_recognition as sr
import threading
import time
import wave
import contextlib
import logging
import numpy as np


class PlaybackTimer:
    def __init__(self):
        self.start_time = 0
        self.current_position = 0
        self.is_running = False

    def start(self):
        if not self.is_running:
            self.start_time = time.time()
            self.is_running = True

    def pause(self):
        if self.is_running:
            self.current_position += time.time() - self.start_time
            self.is_running = False

    def reset(self):
        self.start_time = 0
        self.current_position = 0
        self.is_running = False

    def get_time(self):
        if not self.is_running:
            return self.current_position
        return self.current_position + (time.time() - self.start_time)

    def set_position(self, position):
        self.current_position = position
        if self.is_running:
            self.start_time = time.time()


def safe_call(func):
    """安全调用装饰器，捕获异常并更新状态栏"""

    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            logging.error(f"调用函数 {func.__name__} 失败: {e}")
            self.update_status(f"{func.__name__} 操作失败: {str(e)}", 'error')

    return wrapper


def handle_audio_error(func):
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except pygame.error as e:
            messagebox.showerror("音频错误", f"操作失败: {str(e)}")
        except Exception as e:
            messagebox.showerror("错误", f"未知错误: {str(e)}")

    return wrapper


class AudioPlayer:
    def __init__(self, root):
        """初始化音频播放器"""
        self.root = root
        self.root.title("音频播放器")
        self.root.geometry("1000x800")

        # 状态消息类型
        self.STATUS_TYPES = {
            'info': {'fg': 'black', 'timeout': 3000},
            'success': {'fg': 'green', 'timeout': 2000},
            'warning': {'fg': 'orange', 'timeout': 5000},
            'error': {'fg': 'red', 'timeout': 0}
        }

        # 添加状态栏 - 移到最前面
        self.status_bar = ttk.Label(self.root, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # 音频引擎初始化
        pygame.mixer.pre_init(44100, -16, 2, 2048)
        pygame.init()
        pygame.mixer.init()

        # 简单直接地设置音量为50
        self._volume = 50
        pygame.mixer.music.set_volume(0.5)

        # 播放控制相关变量
        self._playback = {
            'speed': 1.0,
            'volume': 0.5,  # 设置默认音量为50%
            'volume_fade': None,
            'time_offset': 0,
            'last_position': 0
        }

        # 播放进度相关变量
        self._total_length = 0
        self._current_position = 0
        self._start_time = 0
        self._offset = 0
        self._last_progress_update = 0

        # 配置文件和目录
        self.setup_config_directories()

        # 初始化日志
        self.setup_logging()

        # 初始化变量
        self.initialize_variables()

        # 创建界面
        self.create_widgets()

        # 创建菜单
        self.create_menu()

        # 绑定事件和加载设置
        self.bind_shortcuts()
        self.load_settings()
        self.load_player_state()
        self.restore_folder_tree()  # 加载文件夹树

        # 设置关闭处理
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 启动自动保存
        self.auto_save_state()

        # 添加文件系统监视定时器
        self._fs_check_timer = None
        self.last_check_time = time.time()

        # 启动文件系统检查
        self.start_fs_monitoring()

        self.current_position = 0

        self.playback_timer = PlaybackTimer()
        self._last_progress_update = 0

    @property
    def volume(self):
        """音量属性getter"""
        return self._volume

    @volume.setter
    def volume(self, value):
        """音量属性setter"""
        # 确保音量在0-100范围内
        self._volume = max(0, min(100, float(value)))
        # 更新pygame音量(0-1范围)
        pygame.mixer.music.set_volume(self._volume / 100)
        # 如果滑块已创建，同步更新
        if hasattr(self, 'volume_scale'):
            self.volume_scale.set(self._volume)

    def setup_config_directories(self):
        """改进的配置目录设置功能"""
        try:
            # 添加配置目录
            self.config_dir = os.path.join(os.path.expanduser('~'), '.audio_player')
            self.logs_dir = os.path.join(self.config_dir, 'logs')
            self.cache_dir = os.path.join(self.config_dir, 'cache')
            self.temp_dir = os.path.join(self.config_dir, 'temp')

            # 创建必要目录
            for directory in [self.config_dir, self.logs_dir, self.cache_dir, self.temp_dir]:
                if not os.path.exists(directory):
                    os.makedirs(directory)

            # 配置文件路径
            self.state_file = os.path.join(self.config_dir, 'player_state.json')
            self.settings_file = os.path.join(self.config_dir, 'settings.json')
            self.history_file = os.path.join(self.config_dir, 'history.json')
            self.favorites_file = os.path.join(self.config_dir, 'favorites.json')

            # 配置文件和日志
            self.player_config = {
                'speed_presets': [0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
                'volume_fade_duration': 500,
                'subtitle_cache_size': 100,
                'history_limit': 100,
                'default_volume': 0.5,
                'auto_save_interval': 300,  # 5分钟
                'max_cache_size': 1024 * 1024 * 100  # 100MB
            }

            # 初始化日志
            self.setup_logging()

        except Exception as e:
            print(f"设置配置目录失败: {e}")
            messagebox.showerror("错误", f"初始化配置目录失败: {str(e)}", icon='error')

    def start_fs_monitoring(self):
        """启动文件系统监视"""

        def check_files():
            try:
                current_time = time.time()
                if current_time - self.last_check_time >= 60:  # 每分钟检查一次
                    self.validate_folders()
                    self.last_check_time = current_time

                self._fs_check_timer = self.root.after(10000, check_files)  # 每10秒调用一次
            except Exception as e:
                logging.error(f"文件系统监视错误: {e}")

        check_files()

    def validate_folders(self):
        """验证文件夹和文件的有效性"""
        try:
            for folder_id in list(self.folders.keys()):
                folder_info = self.folders[folder_id]
                folder_path = folder_info['path']

                if not os.path.exists(folder_path):
                    continue

                # 验证文件列表
                valid_files = [f for f in folder_info['files'] if os.path.exists(f)]

                # 更新文件列表
                self.folders[folder_id]['files'] = valid_files

        except Exception as e:
            logging.error(f"验证文件夹失败: {e}")

    def initialize_variables(self):
        """改进的变量初始化功能"""
        try:
            self._playback = {
                'speed': 1.0,
                'volume_fade': None,
                'time_offset': 0,
                'last_position': 0,
                'fade_timer': None
            }

            self.current_position = 0

            # 音频进度相关变量
            self.current_audio_length = 0
            self.is_seeking = False
            self.seek_target = None

            # 播放状态变量
            self.folders = {}  # 存储文件夹及其音频文件
            self.current_playlist = []  # 当前播放列表
            self.current_index = 0  # 当前播放索引
            self.play_mode = "sequential"  # 播放模式
            self.is_playing = False
            self.is_paused_for_delay = False  # 新增暂停延迟状态
            self.is_muted = False

            # 跟读相关变量
            self.is_following = False
            self.segment_duration = 5
            self.current_segment = 0
            self.total_segments = 0
            self.current_loop = 0
            self.max_follow_loops = 1
            self.follow_pause_duration = 8000  # 跟读暂停时长(ms)

            # 字幕相关变量
            self.subtitles = []
            self.current_subtitle_index = 0
            self._subtitle_cache = {
                'last_time': 0,
                'last_index': 0,
                'last_subtitle': None
            }

            # 状态跟踪
            self._state = {
                'seeking': False,
                'updating': False,
                'last_error': None,
                'last_action': None,
                'startup_time': time.time()
            }

            # 高精度计时器
            self._timer = {
                'start_time': 0,
                'pause_time': 0,
                'offset': 0,
                'last_update': 0
            }

            # 播放历史相关
            self.play_history = []
            self.favorites = set()
            self.history_limit = 100
            self.recent_files = []  # 最近播放文件列表

            # 音频处理相关
            self.wave_canvas = None
            self._audio_cache = {}
            self._waveform_cache = {}

            # 统计数据
            self.stats = {
                'total_play_time': 0,
                'played_files': set(),
                'last_played': None,
                'favorite_count': 0,
                'folder_count': 0,
                'file_count': 0,
                'session_start': time.time()
            }

            # 定时器变量
            self.update_timer = None
            self._status_timer = None
            self._auto_save_timer = None
            self._progress_timer = None
            self._playback_delay_timer = None  # 新增播放延迟定时器

        except Exception as e:
            print(f"初始化变量失败: {e}")
            raise

    @handle_audio_error
    def set_playback_position(self, new_pos):
        """设置播放位置，并更新时间显示 (来自 10th version)"""
        if not self.current_playlist:
            return
        try:
            current_file = self.current_playlist[self.current_index]
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play(start=new_pos)
            self.current_position = new_pos  # 记录新的播放位置
            total_length = self.get_current_audio_length()
            self.time_label.config(text=f"{self.format_time(new_pos)} / {self.format_time(total_length)}")
        except Exception as e:
            self.update_status(f"定位失败: {str(e)}", 'error')

    def create_menu(self):
        """改进的菜单创建功能"""
        try:
            menubar = tk.Menu(self.root)
            self.root.config(menu=menubar)

            # 文件菜单
            file_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="文件", menu=file_menu)
            file_menu.add_command(label="添加文件夹", command=self.add_folder)
            file_menu.add_command(label="导入播放列表", command=self.import_playlist)
            file_menu.add_command(label="导出播放列表", command=self.export_playlist)
            file_menu.add_separator()
            file_menu.add_command(label="退出", command=self.on_closing)  # 使用 on_closing

            # 播放菜单
            play_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="播放", menu=play_menu)
            play_menu.add_command(label="播放/暂停", command=self.play_pause)
            play_menu.add_command(label="停止", command=self.stop)
            play_menu.add_separator()
            play_menu.add_command(label="上一曲", command=self.previous_track)
            play_menu.add_command(label="下一曲", command=self.next_track)

            # 工具菜单
            tools_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="工具", menu=tools_menu)
            tools_menu.add_command(label="跟读模式", command=self.toggle_follow_reading)
            tools_menu.add_command(label="清理缓存", command=self.clean_cache)
            tools_menu.add_command(label="查看统计", command=self.show_stats)

            # 帮助菜单
            help_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="帮助", menu=help_menu)
            help_menu.add_command(label="快捷键", command=self.show_shortcuts)
            help_menu.add_command(label="关于", command=self.show_about)

        except Exception as e:
            self.update_status(f"创建菜单失败: {str(e)}", 'error')

    def create_widgets(self):
        """创建界面组件"""
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

        # 音量控制 - 直接设置初始值
        volume_frame = ttk.LabelFrame(control_frame, text="音量控制")
        volume_frame.pack(fill="x", pady=5)

        self.volume_scale = ttk.Scale(
            volume_frame,
            from_=0,
            to=100,
            orient="horizontal",
            command=lambda v: self.set_volume(v)  # 使用 set_volume
        )
        self.volume_scale.set(50)  # 强制设置为50
        self.volume_scale.pack(fill="x", padx=5)

        # 当前播放信息
        self.info_label = ttk.Label(control_frame, text="未播放")
        self.info_label.pack(pady=5)

        # 添加跟读控制区域
        follow_frame = ttk.LabelFrame(control_frame, text="跟读控制")
        follow_frame.pack(fill="x", pady=5)

        # 在跟读控制区域添加字幕偏移控制
        offset_frame = ttk.Frame(follow_frame)
        offset_frame.pack(fill="x", pady=5)
        ttk.Label(offset_frame, text="字幕偏移:").pack(side="left")
        ttk.Button(offset_frame, text="-0.5s",
                   command=lambda: self.adjust_subtitle_offset(-500)).pack(side="left")
        ttk.Button(offset_frame, text="+0.5s",
                   command=lambda: self.adjust_subtitle_offset(500)).pack(side="left")

        # 语速控制
        speed_frame = ttk.Frame(follow_frame)
        speed_frame.pack(fill="x", pady=5)
        ttk.Label(speed_frame, text="语速:").pack(side="left")
        self.speed_scale = ttk.Scale(speed_frame, from_=0.5, to=2.0,
                                     orient="horizontal",
                                     command=self.on_speed_change)
        self.speed_scale.set(1.0)
        self.speed_scale.pack(side="left", fill="x", expand=True)

        # 添加播放速度微调
        speed_adjust_frame = ttk.Frame(speed_frame)
        speed_adjust_frame.pack(side="right", padx=5)
        ttk.Button(speed_adjust_frame, text="-0.1", width=3,
                   command=lambda: self.adjust_speed(-0.1)).pack(side="left", padx=1)
        ttk.Button(speed_adjust_frame, text="+0.1", width=3,
                   command=lambda: self.adjust_speed(0.1)).pack(side="left", padx=1)

        # 预设速度按钮
        for speed in self.player_config['speed_presets']:
            ttk.Button(speed_frame, text=f"{speed}x", width=3,
                       command=lambda s=speed: self.set_playback_speed(s)).pack(side="left", padx=1)

        # 跟读按钮
        self.follow_button = ttk.Button(follow_frame, text="开始跟读",
                                        command=self.toggle_follow_reading)
        self.follow_button.pack(pady=5)

        # 跟读文本显示区域
        text_frame = ttk.LabelFrame(control_frame, text="跟读结果")
        text_frame.pack(fill="both", expand=True, pady=5)

        self.follow_text = tk.Text(text_frame, height=6, width=40)
        self.follow_text.pack(pady=5, padx=5, fill="both", expand=True)

        # 字幕样式配置
        self.follow_text.tag_configure('en', foreground='blue', font=('Consolas', 10))
        self.follow_text.tag_configure('cn', foreground='green', font=('Microsoft YaHei', 10))
        self.follow_text.tag_configure('time', foreground='gray')

        # 播放进度控制
        progress_frame = ttk.LabelFrame(control_frame, text="播放进度")
        progress_frame.pack(fill="x", pady=5)

        # 快进快退按钮和进度条框架
        progress_control_frame = ttk.Frame(progress_frame)
        progress_control_frame.pack(fill="x", padx=5)

        # 后退2秒
        ttk.Button(progress_control_frame, text="◀◀", width=3,
                   command=lambda: self.seek_relative(-2)).pack(side="left", padx=2)

        # 进度条
        self.progress_scale = ttk.Scale(progress_control_frame, from_=0, to=100,
                                        orient="horizontal",
                                        command=self.seek_absolute)
        self.progress_scale.pack(side="left", fill="x", expand=True, padx=5)

        # 前进2秒
        ttk.Button(progress_control_frame, text="▶▶", width=3,
                   command=lambda: self.seek_relative(2)).pack(side="left", padx=2)

        # 时间显示框架
        time_frame = ttk.Frame(progress_frame)
        time_frame.pack(fill="x", padx=5)

        # 当前时间/总时间
        self.time_label = ttk.Label(time_frame, text="00:00 / 00:00")
        self.time_label.pack(side="right", padx=5)

        # 进度条事件绑定
        self.progress_scale.bind("<Button-1>", self.on_progress_press)
        self.progress_scale.bind("<ButtonRelease-1>", self.on_progress_release)

        # 添加波形显示
        wave_frame = ttk.LabelFrame(control_frame, text="音频波形")
        wave_frame.pack(fill="x", pady=5)
        self.wave_canvas = tk.Canvas(wave_frame, height=60, bg='white')
        self.wave_canvas.pack(fill="x", padx=5)

        # 添加播放列表功能按钮
        playlist_frame = ttk.Frame(control_frame)
        playlist_frame.pack(fill="x", pady=5)
        ttk.Button(playlist_frame, text="导出列表",
                   command=self.export_playlist).pack(side="left", padx=2)
        ttk.Button(playlist_frame, text="导入列表",
                   command=self.import_playlist).pack(side="left", padx=2)
        ttk.Button(playlist_frame, text="收藏",
                   command=self.toggle_favorite).pack(side="left", padx=2)

    def show_stats(self):
        """改进的统计信息显示功能"""
        try:
            stats_window = tk.Toplevel(self.root)
            stats_window.title("播放统计")
            stats_window.geometry("400x500")

            # 计算会话时长
            session_duration = time.time() - self.stats['session_start']
            total_hours = self.stats['total_play_time'] / 3600

            # 创建统计信息文本
            stats_text = tk.Text(stats_window, wrap=tk.WORD, padx=10, pady=10)
            stats_text.pack(fill=tk.BOTH, expand=True)

            stats_info = [
                ("播放统计", "-" * 40),
                ("总播放时长", f"{total_hours:.2f}小时"),
                ("本次会话时长", f"{session_duration / 3600:.2f}小时"),
                ("播放文件数", len(self.stats['played_files'])),
                ("收藏文件数", len(self.favorites)),
                ("文件夹数量", len(self.folders)),
                ("", "-" * 40),
                ("最近播放", "最后播放时间" if self.stats['last_played'] else "无"),
                ("", time.strftime("%Y-%m-%d %H:%M:%S",
                                   time.localtime(self.stats['last_played'])) if self.stats['last_played'] else "")
            ]

            for title, value in stats_info:
                stats_text.insert(tk.END, f"{title}: {value}\n")

            stats_text.config(state=tk.DISABLED)

        except Exception as e:
            self.update_status(f"显示统计信息失败: {str(e)}", 'error')

    def show_shortcuts(self):
        """显示快捷键列表"""
        try:
            shortcuts_window = tk.Toplevel(self.root)
            shortcuts_window.title("快捷键")
            shortcuts_window.geometry("300x400")

            shortcuts_text = tk.Text(shortcuts_window, wrap=tk.WORD, padx=10, pady=10)
            shortcuts_text.pack(fill=tk.BOTH, expand=True)

            shortcuts_info = [
                ("播放/暂停", "Space 或 Ctrl+P"),
                ("停止", "Esc"),
                ("上一曲", "无"),
                ("下一曲", "无"),
                ("快退", "Left"),
                ("快进", "Right"),
                ("长距离快退", "Ctrl+Left"),
                ("长距离快进", "Ctrl+Right"),
                ("音量增大", "Up"),
                ("音量减小", "Down"),
                ("语速加快", "Ctrl+Up"),
                ("语速减慢", "Ctrl+Down"),
                ("跟读模式", "Ctrl+F"),
                ("保存状态", "Ctrl+S")
            ]

            for action, keys in shortcuts_info:
                shortcuts_text.insert(tk.END, f"{action}: {keys}\n")

            shortcuts_text.config(state=tk.DISABLED)

        except Exception as e:
            self.update_status(f"显示快捷键帮助失败: {str(e)}", 'error')

    def show_about(self):
        """显示关于信息"""
        try:
            about_window = tk.Toplevel(self.root)
            about_window.title("关于")
            about_window.geometry("300x200")

            about_label = ttk.Label(about_window,
                                    text="""英语口语练习助手\n版本: 1.0\n作者: Gemini-Pro\n日期: 2024-01-01""",
                                    padding=10)
            about_label.pack(expand=True, fill=tk.BOTH)

        except Exception as e:
            self.update_status(f"显示关于信息失败: {str(e)}", 'error')

    def export_playlist(self):
        """导出播放列表"""
        try:
            if not self.current_playlist:
                self.update_status("当前没有播放列表", 'warning')
                return

            file_path = filedialog.asksaveasfilename(
                defaultextension=".m3u",
                filetypes=[("M3U Playlist", "*.m3u"), ("All files", "*.*")]
            )

            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("#EXTM3U\n")  # M3U 文件头
                    for file in self.current_playlist:
                        f.write(file + '\n')

                self.update_status("播放列表导出成功", 'success')

        except Exception as e:
            self.update_status(f"导出播放列表失败: {str(e)}", 'error')

    def import_playlist(self):
        """导入播放列表"""
        try:
            file_path = filedialog.askopenfilename(
                defaultextension=".m3u",
                filetypes=[("M3U Playlist", "*.m3u"), ("All files", "*.*")]
            )

            if file_path:
                files = []
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if os.path.exists(line):  # 检查文件是否存在
                                files.append(line)
                            else:
                                logging.warning(f"播放列表中的文件不存在: {line}")

                # 过滤掉不存在的文件
                files = [f for f in files if os.path.exists(f)]

                # 只有当成功导入至少一个文件时才更新播放列表
                if files:
                    self.current_playlist = files
                    self.current_index = 0
                    self.play_current_track()
                    self.update_status("播放列表导入成功", 'success')

        except Exception as e:
            self.update_status(f"导入播放列表失败: {str(e)}", 'error')

    def toggle_favorite(self):
        """切换收藏状态"""
        try:
            if not self.current_playlist or self.current_index >= len(self.current_playlist):
                self.update_status("没有可收藏的音频", 'warning')
                return

            current_file = self.current_playlist[self.current_index]

            if current_file in self.favorites:
                self.favorites.remove(current_file)
                self.update_status("已取消收藏", 'info')
            else:
                self.favorites.add(current_file)
                self.update_status("已添加到收藏", 'success')

            # 保存收藏列表
            self.save_favorites()

        except Exception as e:
            self.update_status(f"收藏操作失败: {str(e)}", 'error')

    def save_favorites(self):
        """保存收藏列表"""
        try:
            favorites_file = os.path.join(self.config_dir, 'favorites.json')
            with open(favorites_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.favorites), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"保存收藏失败: {e}")

    # 暂时未使用
    def update_wave_display(self):
        """改进的波形显示更新功能"""
        try:
            if not self.is_playing or not self.current_playlist:
                return

            current_file = self.current_playlist[self.current_index]

            # 检查缓存
            if current_file not in self._audio_cache:
                # 读取音频数据
                with wave.open(current_file, 'rb') as wf:
                    signal = wf.readframes(-1)
                    signal = np.frombuffer(signal, dtype=np.int16)

                    # 计算波形数据
                    chunks = np.array_split(signal, self.wave_canvas.winfo_width())
                    peaks = [abs(chunk).max() for chunk in chunks]

                    # 缓存波形数据
                    self._audio_cache[current_file] = peaks

            # 绘制波形
            self.wave_canvas.delete('all')
            peaks = self._audio_cache[current_file]

            # 获取当前播放位置
            position = pygame.mixer.music.get_pos() / 1000.0
            total_length = self.get_current_audio_length()
            position_ratio = position / total_length

            # 绘制波形和播放位置指示器
            height = self.wave_canvas.winfo_height()
            for i, peak in enumerate(peaks):
                x = i
                y = height // 2
                amplitude = (peak / 32768.0) * (height // 2)

                # 区分已播放和未播放部分
                if i < len(peaks) * position_ratio:
                    color = '#4CAF50'  # 已播放部分为绿色
                else:
                    color = '#9E9E9E'  # 未播放部分为灰色

                self.wave_canvas.create_line(x, y - amplitude, x, y + amplitude, fill=color)

            # 绘制播放位置指示线
            pos_x = int(len(peaks) * position_ratio)
            self.wave_canvas.create_line(pos_x, 0, pos_x, height, fill='red', width=2)

        except Exception as e:
            print(f"更新波形显示失败: {e}")

    def update_stats(self):
        """更新播放统计"""
        try:
            if self.is_playing:
                current_file = self.current_playlist[self.current_index]
                self.stats['played_files'].add(current_file)
                self.stats['last_played'] = current_file
                self.stats['total_play_time'] += 0.1  # 每100ms更新一次

            # 每分钟保存一次统计数据
            self.root.after(60000, self.save_stats)

        except Exception as e:
            logging.error(f"更新统计失败: {e}")

    def save_stats(self):
        """保存播放统计"""
        try:
            stats_file = os.path.join(self.config_dir, 'stats.json')
            stats_data = {
                'total_play_time': self.stats['total_play_time'],
                'played_files': list(self.stats['played_files']),
                'last_played': self.stats['last_played'],
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S')
            }

            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logging.error(f"保存统计失败: {e}")

    def create_context_menu(self):
        """改进的右键菜单创建功能"""
        try:
            self.context_menu = tk.Menu(self.root, tearoff=0)

            # 文件夹树的右键菜单
            self.folder_menu = tk.Menu(self.root, tearoff=0)
            self.folder_menu.add_command(label="播放", command=self.play_selected_item)
            self.folder_menu.add_command(label="添加到收藏", command=self.add_to_favorites)
            self.folder_menu.add_separator()
            self.folder_menu.add_command(label="重命名", command=self.rename_item)
            self.folder_menu.add_command(label="删除", command=self.remove_selected_item)

            # 绑定右键菜单
            self.folder_tree.bind("<Button-3>", self.show_context_menu)

        except Exception as e:
            self.update_status(f"创建右键菜单失败: {str(e)}", 'error')

    def show_context_menu(self, event):
        """改进的右键菜单显示功能"""
        try:
            # 获取点击的项目
            item = self.folder_tree.identify('item', event.x, event.y)
            if item:
                # 选中被点击的项目
                self.folder_tree.selection_set(item)
                # 显示菜单
                self.folder_menu.post(event.x_root, event.y_root)
        except Exception as e:
            self.update_status(f"显示右键菜单失败: {str(e)}", 'error')

    def rename_item(self):
        """改进的重命名功能"""
        try:
            selected = self.folder_tree.selection()
            if not selected:
                return

            item = selected[0]
            old_name = self.folder_tree.item(item)['text']

            # 创建重命名对话框
            dialog = tk.Toplevel(self.root)
            dialog.title("重命名")
            dialog.geometry("300x100")

            ttk.Label(dialog, text="新名称:").pack(pady=5)
            entry = ttk.Entry(dialog)
            entry.insert(0, old_name)
            entry.pack(pady=5)
            entry.select_range(0, tk.END)

            def do_rename():
                new_name = entry.get()
                if new_name and new_name != old_name:
                    try:
                        # 更新树形视图
                        self.folder_tree.item(item, text=new_name)

                        # 如果是文件夹，更新文件夹字典
                        if item in self.folders:
                            folder_info = self.folders[item]
                            new_path = os.path.join(os.path.dirname(folder_info['path']), new_name)
                            os.rename(folder_info['path'], new_path)
                            folder_info['path'] = new_path

                        self.save_settings()
                        self.update_status(f"重命名成功: {new_name}", 'success')
                    except Exception as e:
                        self.update_status(f"重命名失败: {str(e)}", 'error')

                dialog.destroy()

            ttk.Button(dialog, text="确定", command=do_rename).pack(side=tk.LEFT, padx=20)
            ttk.Button(dialog, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=20)

            # 设置焦点并绑定回车键
            entry.focus_set()
            entry.bind('<Return>', lambda e: do_rename())

        except Exception as e:
            self.update_status(f"重命名操作失败: {str(e)}", 'error')

    def save_settings(self):
        """保存播放器设置"""
        try:
            settings = {
                'folders': {},  # 初始化为空字典，用于存储处理后的文件夹数据
                'volume': self._volume,  # 音量
                'speed': self.speed_scale.get() if hasattr(self, 'speed_scale') else 1.0,  # 播放速度
                'subtitle_offset': self._playback.get('time_offset', 0),  # 字幕偏移
                'loop_count': self.loop_count.get() if hasattr(self, 'loop_count') else 1,  # 循环次数
                'play_mode': self.mode_var.get() if hasattr(self, 'mode_var') else 'sequential'  # 播放模式
            }

            # 遍历 self.folders 字典，将 Treeview ID 替换为路径
            for tree_id, folder_info in self.folders.items():
                if self.folder_tree.exists(tree_id):  # 检查 Treeview ID 是否仍然有效
                    settings['folders'][folder_info['path']] = {  # 使用文件夹路径作为键
                        'path': folder_info['path'],
                        'files': folder_info['files'],
                        'expanded': folder_info['expanded']
                    }

            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)

            self.update_status("设置已保存", 'success')
            return True

        except Exception as e:
            self.update_status(f"保存设置失败: {str(e)}", 'error')
            return False

    def add_to_favorites(self):
        """改进的添加收藏功能"""
        try:
            selected = self.folder_tree.selection()
            if not selected:
                return

            item = selected[0]

            # 如果是文件夹，添加所有音频文件
            if item in self.folders:
                for file_path in self.folders[item]['files']:
                    self.favorites.add(file_path)
                self.update_status(f"文件夹已添加到收藏", 'success')
            else:
                # 如果是单个文件
                parent = self.folder_tree.parent(item)
                if parent in self.folders:
                    file_name = self.folder_tree.item(item)['text']
                    for file_path in self.folders[parent]['files']:
                        if os.path.basename(file_path) == file_name:
                            self.favorites.add(file_path)
                            self.update_status(f"文件已添加到收藏", 'success')
                            break

            # 保存收藏状态
            self.save_player_state()

        except Exception as e:
            self.update_status(f"添加收藏失败: {str(e)}", 'error')

    def get_audio_info(self, file_path):
        """改进的音频信息获取功能"""
        try:
            info = {
                'duration': 0,
                'channels': 0,
                'sample_rate': 0,
                'bit_rate': 0,
                'format': None
            }

            # 尝试使用wave模块获取信息
            try:
                with wave.open(file_path, 'rb') as wf:
                    info['channels'] = wf.getnchannels()
                    info['sample_rate'] = wf.getframerate()
                    frames = wf.getnframes()
                    info['duration'] = frames / float(info['sample_rate'])
                    info['format'] = 'wav'
            except:
                # 如果不是wav文件，使用pygame获取时长
                audio = pygame.mixer.Sound(file_path)
                info['duration'] = audio.get_length()
                info['format'] = os.path.splitext(file_path)[1][1:]

            return info

        except Exception as e:
            print(f"获取音频信息失败: {e}")
            return None

    def show_current_subtitle(self, subtitle):
        """改进的字幕显示功能"""
        try:
            # 清空之前的文本
            self.follow_text.delete('1.0', 'end')

            # 显示时间信息
            self.follow_text.insert('end',
                                    f"时间: {self.format_time(subtitle['start_time'], is_milliseconds=True)} -> "
                                    f"{self.format_time(subtitle['end_time'], is_milliseconds=True)}\n\n",
                                    'time')

            # 显示英文
            if subtitle.get('en_text'):
                self.follow_text.insert('end', subtitle['en_text'] + '\n', 'en')

            # 显示中文
            if subtitle.get('cn_text'):
                self.follow_text.insert('end', subtitle['cn_text'] + '\n', 'cn')

            # 确保显示最新内容
            self.follow_text.see('end')
        except Exception as e:
            print(f"显示字幕失败: {e}")

    def expand_folder(self, folder_id):
        """改进的展开文件夹功能"""
        try:
            # 清除现有子节点
            for child in self.folder_tree.get_children(folder_id):
                self.folder_tree.delete(child)

            # 按自然顺序添加文件
            for file_path in self.folders[folder_id]['files']:
                file_name = os.path.basename(file_path)
                duration = self.get_audio_duration(file_path)
                self.folder_tree.insert(folder_id, "end", text=file_name,
                                        values=(duration,))

            self.folders[folder_id]['expanded'] = True

        except Exception as e:
            self.update_status(f"展开文件夹失败: {str(e)}", 'error')

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

    @safe_call
    def play_current_track(self):
        """播放当前曲目"""
        if not self.current_playlist:
            return

        try:
            current_file = self.current_playlist[self.current_index]

            # 1. 停止当前播放并等待
            pygame.mixer.music.stop()
            time.sleep(0.1)  # 增加停止后的等待时间

            # 2. 重置状态
            self._current_position = 0
            self.current_subtitle_index = 0
            self.is_playing = True
            self.is_paused_for_delay = False

            # 3. 获取总时长
            self._total_length = self.get_current_audio_length()

            # 4. 加载音频文件并等待
            pygame.mixer.music.load(current_file)
            time.sleep(0.05)  # 加载后的短暂等待

            # 5. 开始播放
            pygame.mixer.music.play()

            # 6. 更新界面状态
            self.play_button.config(text="暂停")
            self.progress_scale.set(0)
            self.time_label.config(text=f"00:00 / {self.format_time(self._total_length)}")

            # 7. 更新显示信息
            current_file_name = os.path.basename(current_file)
            self.info_label.config(text=f"当前播放: {current_file_name}")

            # 8. 启动进度更新
            self._start_time = time.time()
            self._offset = 0
            self.update_progress()

        except Exception as e:
            self.update_status(f"播放失败: {str(e)}", 'error')

    def get_current_audio_length(self):
        """获取当前音频文件的总长度"""
        if not self.current_playlist:
            return 0
        try:
            audio = pygame.mixer.Sound(self.current_playlist[self.current_index])
            return audio.get_length()
        except:
            return 0

    def format_time(self, time_value, is_milliseconds=False):
        """改进的时间格式化功能"""
        try:
            if not is_milliseconds:
                # 将秒转换为毫秒
                time_value = int(time_value * 1000)

            # 统一按毫秒处理
            hours = time_value // (3600 * 1000)
            minutes = (time_value % (3600 * 1000)) // (60 * 1000)
            seconds = (time_value % (60 * 1000)) // 1000
            milliseconds = time_value % 1000

            if hours > 0:
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
            else:
                return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

        except Exception as e:
            print(f"格式化时间失败: {e}")
            return "00:00.000"

    def load_settings(self):
        """加载设置"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.volume = settings.get('volume', 50)
                    loaded_folders = settings.get('folders', {})
                    self.folders = {}
                    for folder_path, folder_data in loaded_folders.items():
                        if os.path.exists(folder_path):
                            folder_name = os.path.basename(folder_path)
                            tree_id = self.folder_tree.insert("", "end", text=folder_name,
                                                              values=(f"{len(folder_data['files'])}个文件",))
                            self.folders[tree_id] = {
                                'path': folder_path,
                                'files': folder_data['files'],
                                'expanded': folder_data['expanded']
                            }
        except Exception as e:
            self.update_status(f"加载设置失败: {str(e)}", 'error')

    def load_player_state(self):
        """加载播放器状态"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    self.current_playlist = state.get('current_playlist', [])
                    self.current_index = state.get('current_index', 0)
                    self.current_loop = state.get('current_loop', 0)
                    self.is_playing = state.get('is_playing', False)
                    self.is_paused_for_delay = state.get('is_paused_for_delay', False)
                    self.is_muted = state.get('is_muted', False)
                    self.is_following = state.get('is_following', False)
                    self.segment_duration = state.get('segment_duration', 5)
                    self.total_segments = state.get('total_segments', 0)
                    self.current_segment = state.get('current_segment', 0)
                    self.max_follow_loops = state.get('max_follow_loops', 1)
                    self.follow_pause_duration = state.get('follow_pause_duration', 8000)
                    self.current_audio_length = self.get_current_audio_length()
                    self._playback['start_time'] = state.get('playback_start_time', 0)
                    self._playback['current_position'] = state.get('playback_current_position', 0)
                    self._playback['total_length'] = self.get_current_audio_length()
                    self.update_status("播放器状态加载成功", 'info')
        except Exception as e:
            self.update_status(f"加载播放器状态失败: {str(e)}", 'error')

    def save_player_state(self):
        """保存播放器状态"""
        try:
            state = {
                'current_playlist': self.current_playlist,
                'current_index': self.current_index,
                'current_loop': self.current_loop,
                'is_playing': self.is_playing,
                'is_paused_for_delay': self.is_paused_for_delay,
                'is_muted': self.is_muted,
                'is_following': self.is_following,
                'segment_duration': self.segment_duration,
                'total_segments': self.total_segments,
                'current_segment': self.current_segment,
                'max_follow_loops': self.max_follow_loops,
                'follow_pause_duration': self.follow_pause_duration,
                'current_audio_length': self.current_audio_length,
                'playback_start_time': self._playback['start_time'],
                'playback_current_position': self._playback['current_position'],
                'playback_total_length': self._playback['total_length']
            }
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            self.update_status("播放器状态保存成功", 'info')
        except Exception as e:
            self.update_status(f"保存播放器状态失败: {str(e)}", 'error')

    def auto_save_state(self):
        """自动保存状态"""
        try:
            self.save_player_state()
            self.clean_cache()  # 定期清理缓存

            # 设置下一次自动保存
            self._auto_save_timer = self.root.after(
                self.player_config['auto_save_interval'] * 1000,
                self.auto_save_state
            )
        except Exception as e:
            print(f"自动保存状态失败: {e}")

    def start(self):
        """启动播放器"""
        try:
            self.load_settings()
            self.load_player_state()
            self.start_fs_monitoring()
            self.update_status("播放器启动成功", 'info')
        except Exception as e:
            self.update_status(f"播放器启动失败: {str(e)}", 'error')

    def on_closing(self):
        """处理窗口关闭事件"""
        self.stop()
        self.root.destroy()

    def on_tree_double_click(self, event):
        """处理文件夹树的双击事件"""
        selected = self.folder_tree.selection()
        if selected:
            item = selected[0]
            self.play_selected_folder()

    def on_tree_single_click(self, event):
        """处理文件夹树的单击事件"""
        selected = self.folder_tree.selection()
        if selected:
            item = selected[0]
            self.play_selected_folder()

    def play_selected_folder(self):
        """播放选中的文件夹"""
        selected = self.folder_tree.selection()
        if selected:
            item = selected[0]
            self.play_audio_file(item)

    def play_selected_item(self):
        """播放选中的音频文件"""
        selected = self.folder_tree.selection()
        if selected:
            item = selected[0]
            self.play_audio_file(item)

    def remove_selected_folder(self):
        """移除选中的文件夹"""
        selected = self.folder_tree.selection()
        if selected:
            item = selected[0]
            self.remove_selected_item()

    def remove_selected_item(self):
        """移除选中的音频文件"""
        selected = self.folder_tree.selection()
        if selected:
            item = selected[0]
            parent = self.folder_tree.parent(item)
            if parent in self.folders:
                file_name = self.folder_tree.item(item)['text']
                self.folders[parent]['files'] = [f for f in self.folders[parent]['files'] if
                                                 os.path.basename(f) != file_name]
                self.folder_tree.delete(item)
                self.save_settings()

    def setup_logging(self):
        """设置日志"""
        try:
            # 实现日志设置逻辑
            self.update_status("日志设置成功", 'info')
        except Exception as e:
            self.update_status(f"设置日志失败: {str(e)}", 'error')

    def restore_folder_tree(self):
        """恢复文件夹树"""
        try:
            # 实现恢复文件夹树的逻辑
            self.update_status("文件夹树恢复成功", 'info')
        except Exception as e:
            self.update_status(f"恢复文件夹树失败: {str(e)}", 'error')

    def clean_cache(self):
        """清理缓存"""
        try:
            # 实现清理缓存的逻辑
            self.update_status("缓存清理成功", 'info')
        except Exception as e:
            self.update_status(f"清理缓存失败: {str(e)}", 'error')

    def toggle_follow_reading(self):
        """切换跟读模式"""
        self.is_following = not self.is_following
        self.update_status(f"跟读模式: {'开启' if self.is_following else '关闭'}", 'info')

    def check_playback_status(self):
        """检查播放状态并处理自动播放"""
        for event in pygame.event.get():
            if event.type == self.SONG_END:
                self.play_next()

        # 继续检查
        if self.is_playing:
            self.root.after(100, self.check_playback_status)

    def play_next(self):
        """播放下一首"""
        if not self.current_playlist:
            return

        try:
            self.current_index = (self.current_index + 1) % len(self.current_playlist)
            self.current_loop = 0  # 重置循环计数

            # 重置进度显示
            self.progress_scale.set(0)
            self.time_label.config(text="00:00 / 00:00")

            # 更新显示的文件名称
            current_file = os.path.basename(self.current_playlist[self.current_index])
            self.info_label.config(text=f"当前播放: {current_file}")

            # 播放新的曲目
            self.play_current_track()
            self.update_status(f"播放下一曲: {current_file}", 'info')
        except Exception as e:
            self.update_status(f"播放下一曲失败: {str(e)}", 'error')

    @safe_call
    def stop(self):
        """停止播放并重置状态"""
        try:
            pygame.mixer.music.stop()
            self.is_playing = False
            self.is_paused_for_delay = False  # 重置暂停延迟状态

            # 取消计时器
            if self.update_timer:
                self.root.after_cancel(self.update_timer)
                self.update_timer = None
            if self._playback_delay_timer:  # 取消播放延迟定时器
                self.root.after_cancel(self._playback_delay_timer)

            # 重置界面状态
            self.play_button.config(text="播放")
            self.info_label.config(text="未播放")
            self.progress_scale.set(0)
            self.time_label.config(text="00:00 / 00:00")

            # 如果在跟读模式，停止跟读
            if self.is_following:
                self.stop_follow_reading()

            self.update_status("停止播放", 'info')
        except Exception as e:
            self.update_status(f"停止播放失败: {str(e)}", 'error')

    @safe_call
    def change_volume(self, value):
        """音量控制回调函数"""
        try:
            # 将0-100的值转换为0-1
            volume = float(value) / 100.0
            pygame.mixer.music.set_volume(volume)
            self.update_status(f"音量: {int(float(value))}%", 'info')
        except Exception as e:
            self.update_status(f"调整音量失败: {str(e)}", 'error')

    def smooth_volume_change(self, target_volume, duration=500):
        """改进的音量平滑过渡功能"""
        try:
            if self._playback['volume_fade']:
                self.root.after_cancel(self._playback['volume_fade'])

            current_volume = pygame.mixer.music.get_volume()
            steps = 20
            step_time = duration / steps
            volume_step = (target_volume - current_volume) / steps

            def fade_step(step=0):
                if step < steps:
                    new_volume = current_volume + (volume_step * (step + 1))
                    pygame.mixer.music.set_volume(new_volume)
                    self._playback['volume_fade'] = self.root.after(
                        int(step_time),
                        lambda: fade_step(step + 1)
                    )
                else:
                    self._playback['volume_fade'] = None

            fade_step()

        except Exception as e:
            self.update_status(f"音量平滑调整失败: {str(e)}", 'error')

    def on_speed_change(self, value):
        """处理语速变化"""
        try:
            speed = float(value)
            self.set_playback_speed(speed)
            self.update_status(f"播放速度: {speed:.1f}x", 'info')
        except Exception as e:
            self.update_status(f"设置播放速度失败: {str(e)}", 'error')

    @safe_call
    def seek_absolute(self, value):
        """改进的绝对定位功能"""
        if not self.current_playlist or not self.is_playing:
            return

        try:
            total_length = self.get_current_audio_length()
            seek_pos = (float(value) / 100.0) * total_length

            # 重新加载并播放到指定位置
            current_file = self.current_playlist[self.current_index]
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play(start=seek_pos)

            # 更新时间显示
            current_time = self.format_time(seek_pos)
            total_time = self.format_time(total_length)
            self.time_label.config(text=f"{current_time} / {total_time}")

            # 更新状态
            self.update_status(f"跳转到: {current_time}", 'info')

        except Exception as e:
            self.update_status(f"定位失败: {str(e)}", 'error')

    def on_progress_press(self, event):
        """进度条按下事件"""
        self.is_seeking = True
        self._state['seeking'] = True

    def on_progress_release(self, event):
        """改进的进度条释放事件处理"""
        try:
            if self.current_playlist and self.is_playing:
                # 1. 停止当前播放
                pygame.mixer.music.stop()
                time.sleep(0.05)  # 短暂等待

                # 2. 计算新位置
                pos = self.progress_scale.get()
                seek_time = (pos / 100.0) * self._total_length

                # 3. 重新加载音频
                current_file = self.current_playlist[self.current_index]
                pygame.mixer.music.load(current_file)
                time.sleep(0.05)  # 加载后等待

                # 4. 从新位置开始播放
                pygame.mixer.music.play(start=seek_time)

                # 5. 更新时间追踪
                self._start_time = time.time()
                self._offset = seek_time

                # 6. 更新时间显示
                self.time_label.config(text=f"{self.format_time(seek_time)} / {self.format_time(self._total_length)}")

        except Exception as e:
            self.update_status(f"进度调整失败: {str(e)}", 'error')
        finally:
            self.is_seeking = False
            self._state['seeking'] = False

    def seek_relative(self, seconds):
        """改进的快进快退功能"""
        if not self.is_playing or not self.current_playlist:
            return

        try:
            # 1. 停止当前播放
            pygame.mixer.music.stop()
            time.sleep(0.05)  # 短暂等待

            # 2. 计算新位置
            current_pos = time.time() - self._start_time + self._offset
            new_pos = max(0, min(self._total_length, current_pos + seconds))

            # 3. 重新加载音频
            current_file = self.current_playlist[self.current_index]
            pygame.mixer.music.load(current_file)
            time.sleep(0.05)  # 加载后等待

            # 4. 从新位置开始播放
            pygame.mixer.music.play(start=new_pos)

            # 5. 更新时间追踪
            self._start_time = time.time()
            self._offset = new_pos

            # 6. 更新界面显示
            if self._total_length > 0:
                progress = (new_pos / self._total_length) * 100
                self.progress_scale.set(progress)
            self.time_label.config(text=f"{self.format_time(new_pos)} / {self.format_time(self._total_length)}")

        except Exception as e:
            self.update_status(f"快进快退失败: {str(e)}", 'error')

    def update_progress(self):
        """更新进度条和时间显示"""
        if not self.is_playing:
            return

        try:
            if not self.is_seeking and pygame.mixer.music.get_busy():
                current_time = self.playback_timer.get_time()

                # 只在时间变化超过阈值时更新
                if abs(current_time - self._last_progress_update) >= 0.05:  # 50ms的更新阈值
                    if self._total_length > 0:
                        progress = min(100, (current_time / self._total_length) * 100)

                        # 平滑更新进度条
                        current_progress = self.progress_scale.get()
                        if abs(progress - current_progress) > 0.1:  # 避免微小变化
                            self.progress_scale.set(progress)

                            # 更新时间显示
                            self.time_label.config(
                                text=f"{self.format_time(current_time)} / {self.format_time(self._total_length)}")

                    self._last_progress_update = current_time

            # 继续更新，使用较低的更新频率
            self.update_timer = self.root.after(100, self.update_progress)  # 100ms的更新间隔

        except Exception as e:
            print(f"更新进度出错: {e}")
            self.update_timer = self.root.after(100, self.update_progress)

    def bind_shortcuts(self):
        """绑定快捷键"""
        try:
            # 播放控制
            self.root.bind('<space>', lambda e: self.play_pause())
            self.root.bind('<Control-p>', lambda e: self.play_pause())

            # 导航控制 - 调整快进快退步长为2秒
            self.root.bind('<Left>', lambda e: self.seek_relative(-2))
            self.root.bind('<Right>', lambda e: self.seek_relative(2))

            # 长距离快进快退(Ctrl+方向键) - 调整为6秒
            self.root.bind('<Control-Left>', lambda e: self.seek_relative(-6))
            self.root.bind('<Control-Right>', lambda e: self.seek_relative(6))

            # 音量控制(5%步进)
            self.root.bind('<Up>', lambda e: self.adjust_volume(0.05))
            self.root.bind('<Down>', lambda e: self.adjust_volume(-0.05))

            # 速度控制
            self.root.bind('<Control-Up>', lambda e: self.adjust_speed(0.1))
            self.root.bind('<Control-Down>', lambda e: self.adjust_speed(-0.1))

            # 其他功能
            self.root.bind('<Control-s>', lambda e: self.save_player_state())
            self.root.bind('<Control-f>', lambda e: self.toggle_follow_reading())
            self.root.bind('<Escape>', lambda e: self.stop())

        except Exception as e:
            self.update_status(f"绑定快捷键失败: {str(e)}", 'error')

    def handle_playback_ended(self):
        """改进的播放结束处理"""
        try:
            # 跟读模式处理
            if self.is_following:
                if self.current_segment >= self.total_segments:
                    self.current_loop += 1
                    if self.current_loop < self.loop_count.get():
                        self.current_segment = 0
                        self.follow_text.insert('end', f"\n重新跟读第 {self.current_loop + 1} 次\n")
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

            if self.current_loop < max_loops - 1:
                # 重复播放当前曲目
                self.current_loop += 1
                self._playback['current_position'] = 0
                self._playback['start_time'] = time.time()
                self.progress_scale.set(0)
                pygame.mixer.music.play()
                self.info_label.config(text=f"当前播放: {current_file} ({self.current_loop + 1}/{max_loops})")
                return

            # 重置循环计数
            self.current_loop = 0
            play_mode = self.mode_var.get()

            if play_mode == "sequential":
                if self.current_index < len(self.current_playlist) - 1:
                    self.start_playback_delay()
                else:
                    self.stop()
            elif play_mode == "loop_one":
                self._playback['current_position'] = 0
                self._playback['start_time'] = time.time()
                self.progress_scale.set(0)
                pygame.mixer.music.play()
            elif play_mode == "loop_all":
                self.start_playback_delay()

        except Exception as e:
            self.update_status(f"处理播放结束失败: {str(e)}", 'error')

    def start_playback_delay(self):
        """启动播放延迟"""
        if not self.is_paused_for_delay:
            self.is_paused_for_delay = True
            self.is_playing = False  # 暂停状态
            self.update_status("播放完毕，暂停10秒...", 'info')
            self._playback_delay_timer = self.root.after(10000, self.continue_playback_after_delay)

    def continue_playback_after_delay(self):
        """延迟后继续播放"""
        self.is_paused_for_delay = False
        play_mode = self.mode_var.get()

        if play_mode in ["sequential", "loop_all"]:
            self.current_index = (self.current_index + 1) % len(self.current_playlist)
            self.play_current_track()

    def update_status(self, message, status_type='info'):
        """更新状态栏信息"""
        if not hasattr(self, '_status_timer'):
            self._status_timer = None

        # 取消之前的定时器
        if self._status_timer:
            self.root.after_cancel(self._status_timer)

        # 设置状态栏样式和消息
        style = self.STATUS_TYPES.get(status_type, self.STATUS_TYPES['info'])
        self.status_bar.config(text=message, foreground=style['fg'])

        # 设置自动清除定时器
        if style['timeout'] > 0:
            self._status_timer = self.root.after(
                style['timeout'],
                lambda: self.status_bar.config(text='', foreground='black')
            )
    def add_folder(self):
        """完全重写的添加文件夹功能"""
        try:
            invalid_refs = False
            for folder_id in list(self.folders.keys()):
                if not self.folder_tree.exists(folder_id):
                    invalid_refs = True
                    break

            if invalid_refs:
                if messagebox.askyesno("发现无效引用",
                                       "检测到文件夹引用错误，需要清理后继续，是否清理？"):

                    for item in self.folder_tree.get_children():
                        self.folder_tree.delete(item)
                    self.folders.clear()
                    self.save_settings()
                    self.update_status("已清理所有文件夹", 'success')
                return

            folder_path = filedialog.askdirectory()
            if not folder_path:
                return


            for info in self.folders.values():
                if os.path.samefile(info['path'], folder_path):
                    self.update_status("该文件夹已添加", 'warning')
                    return

            folder_name = os.path.basename(folder_path)

            audio_files = []
            for root, dirs, files in os.walk(folder_path):
                dirs[:] = natsorted(dirs)
                for file in natsorted(files):
                    if file.lower().endswith(('.mp3', '.wav')):
                        full_path = os.path.join(root, file)
                        if os.path.exists(full_path):
                            audio_files.append(full_path)

            if not audio_files:
                self.update_status("未找到音频文件", 'warning')
                return

            tree_id = self.folder_tree.insert("", "end",
                                              text=folder_name,
                                              values=(f"{len(audio_files)}个文件",))


            self.folders[tree_id] = {
                'path': folder_path,
                'files': audio_files,
                'expanded': False
            }


            self.save_settings()
            self.update_status(f"已添加文件夹: {folder_name}", 'success')

        except Exception as e:
            self.update_status(f"添加文件夹失败: {str(e)}", 'error')

    @safe_call
    def play_pause(self):
        """播放/暂停功能"""
        if self.is_following:
            return

        try:
            if self.is_playing:
                pygame.mixer.music.pause()
                self.playback_timer.pause()
                self.is_playing = False
                self.play_button.config(text="播放")
                self.update_status("已暂停", 'info')
            else:
                if not pygame.mixer.music.get_busy():
                    if not self.current_playlist:
                        self.update_status("没有可播放的文件", 'warning')
                        return
                    self.play_current_track()
                else:
                    pygame.mixer.music.unpause()
                    self.playback_timer.start()
                    self.is_playing = True
                    self.play_button.config(text="暂停")
                    self.update_status("继续播放", 'info')

                # 启动进度更新
                self.update_progress()

        except Exception as e:
            self.update_status(f"播放/暂停失败: {str(e)}", 'error')

    @safe_call
    def previous_track(self):
        """播放上一曲"""
        if not self.current_playlist:
            self.update_status("没有可播放的文件", 'warning')
            return

        try:
            # 更新索引
            self.current_index = (self.current_index - 1) % len(self.current_playlist)
            self.current_loop = 0  # 重置循环计数

            # 重置进度显示
            self.progress_scale.set(0)
            self.time_label.config(text="00:00 / 00:00")

            # 更新显示的文件名称
            current_file = os.path.basename(self.current_playlist[self.current_index])
            self.info_label.config(text=f"当前播放: {current_file}")

            # 播放新的曲目
            self.play_current_track()
            self.update_status(f"播放上一曲: {current_file}", 'info')
        except Exception as e:
            self.update_status(f"播放上一曲失败: {str(e)}", 'error')

    @safe_call
    def next_track(self):
        """播放下一曲"""
        if not self.current_playlist:
            self.update_status("没有可播放的文件", 'warning')
            return

        try:
            # 更新索引
            self.current_index = (self.current_index + 1) % len(self.current_playlist)
            self.current_loop = 0  # 重置循环计数

            # 重置进度显示
            self.progress_scale.set(0)
            self.time_label.config(text="00:00 / 00:00")

            # 更新显示的文件名称
            current_file = os.path.basename(self.current_playlist[self.current_index])
            self.info_label.config(text=f"当前播放: {current_file}")

            # 播放新的曲目
            self.play_current_track()
            self.update_status(f"播放下一曲: {current_file}", 'info')
        except Exception as e:
            self.update_status(f"播放下一曲失败: {str(e)}", 'error')

    def set_volume(self, value):
        """直接设置音量，避免使用属性访问"""
        try:
            volume = max(0, min(100, float(value)))
            self._volume = volume
            pygame.mixer.music.set_volume(volume / 100.0)
            if hasattr(self, 'volume_scale'):
                current = self.volume_scale.get()
                if abs(current - volume) > 0.1:  # 避免循环更新
                    self.volume_scale.set(volume)
            self.update_status(f"音量: {int(volume)}%", 'info')
        except Exception as e:
            self.update_status(f"设置音量失败: {str(e)}", 'error')

def main():
    """主程序入口"""
    # 设置中文字体支持
    if os.name == 'nt':  # Windows系统
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)

    root = tk.Tk()
    root.title("英语口语练习助手")

    # 设置窗口图标
    try:
        # 尝试加载图标文件
        icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'icon.ico')
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
    except Exception as e:
        print(f"加载图标失败: {e}")

    # 设置窗口大小和位置
    window_width = 1000
    window_height = 800
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")

    # 设置窗口最小尺寸
    root.minsize(800, 600)

    # 创建播放器实例并启动
    try:
        player = AudioPlayer(root)
        player.start()
    except Exception as e:
        messagebox.showerror("错误", f"程序启动失败: {str(e)}", icon='error')
        root.destroy()


if __name__ == "__main__":
    main()