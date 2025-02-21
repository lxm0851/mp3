import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pygame
import os
import json
from natsort import natsorted
import re
import time
import wave
import contextlib
import logging
import threading
import speech_recognition as sr

import numpy as np


# 全局错误处理装饰器
def safe_call(func):
    """改进的安全调用装饰器"""

    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            error_msg = f"函数 {func.__name__} 执行出错: {str(e)}"
            print(error_msg)

            # 记录错误日志
            logging.error(error_msg)

            # 更新界面显示
            if hasattr(self, 'follow_text'):
                self.follow_text.insert('end', f"错误: {str(e)}\n")
            if hasattr(self, 'update_status'):
                self.update_status(f"错误: {str(e)}", 'error')

            # 保存错误状态
            self._state['last_error'] = {
                'time': time.time(),
                'function': func.__name__,
                'error': str(e)
            }

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
        # 基础设置
        self.root = root
        self.root.title("音频播放器")
        self.root.geometry("1000x800")

        # 音频引擎初始化
        pygame.mixer.pre_init(44100, -16, 2, 2048)
        pygame.init()
        pygame.mixer.init()

        # 简单直接地设置音量为50
        self._volume = 50
        pygame.mixer.music.set_volume(0.5)


        # 配置文件和目录
        self.setup_config_directories()

        # 初始化变量
        self.initialize_variables()

        # 创建界面
        self.create_widgets()

        # 绑定事件和加载设置
        self.bind_shortcuts()
        self.load_settings()
        self.load_player_state()

        # 设置关闭处理
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 启动自动保存
        self.auto_save_state()

        # 添加文件系统监视定时器
        self._fs_check_timer = None
        self.last_check_time = time.time()

        # 启动文件系统检查
        self.start_fs_monitoring()

        # 播放控制相关变量
        self._playback = {
            'speed': 1.0,
            'volume': 0.5,  # 设置默认音量为50%
            'volume_fade': None,
            'time_offset': 0,
            'last_position': 0,
            'current_position': 0  # 添加当前位置追踪
        }

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
            messagebox.showerror("错误", f"初始化配置目录失败: {str(e)}")

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

            # 状态消息类型
            self.STATUS_TYPES = {
                'info': {'fg': 'black', 'timeout': 3000},
                'success': {'fg': 'green', 'timeout': 2000},
                'warning': {'fg': 'orange', 'timeout': 5000},
                'error': {'fg': 'red', 'timeout': 0}
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

        except Exception as e:
            print(f"初始化变量失败: {e}")
            raise

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
            file_menu.add_command(label="退出", command=self.root.quit)

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
        # 添加状态栏
        self.status_bar = ttk.Label(self.root, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

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
            command=lambda v: pygame.mixer.music.set_volume(float(v) / 100)
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
        """改进的快捷键显示功能"""
        try:
            shortcuts_window = tk.Toplevel(self.root)
            shortcuts_window.title("快捷键说明")
            shortcuts_window.geometry("400x500")

            shortcuts_text = tk.Text(shortcuts_window, wrap=tk.WORD, padx=10, pady=10)
            shortcuts_text.pack(fill=tk.BOTH, expand=True)

            shortcuts = [
                ("播放控制", "-" * 40),
                ("空格", "播放/暂停"),
                ("Ctrl + P", "播放/暂停"),
                ("Esc", "停止播放"),
                ("", ""),
                ("导航控制", "-" * 40),
                ("左方向键", "后退5秒"),
                ("右方向键", "前进5秒"),
                ("Ctrl + 左方向键", "上一曲"),
                ("Ctrl + 右方向键", "下一曲"),
                ("", ""),
                ("音量控制", "-" * 40),
                ("上方向键", "增加音量"),
                ("下方向键", "减少音量"),
                ("", ""),
                ("速度控制", "-" * 40),
                ("Ctrl + 上方向键", "增加速度"),
                ("Ctrl + 下方向键", "减少速度"),
                ("", ""),
                ("其他功能", "-" * 40),
                ("Ctrl + S", "保存状态"),
                ("Ctrl + F", "切换跟读模式")
            ]

            for key, desc in shortcuts:
                if key:
                    shortcuts_text.insert(tk.END, f"{key}: {desc}\n")
                else:
                    shortcuts_text.insert(tk.END, f"{desc}\n")

            shortcuts_text.config(state=tk.DISABLED)

        except Exception as e:
            self.update_status(f"显示快捷键说明失败: {str(e)}", 'error')

    def show_about(self):
        """改进的关于信息显示功能"""
        try:
            about_window = tk.Toplevel(self.root)
            about_window.title("关于")
            about_window.geometry("300x200")

            about_frame = ttk.Frame(about_window, padding="20")
            about_frame.pack(fill=tk.BOTH, expand=True)

            # 添加版本信息
            ttk.Label(about_frame, text="音频播放器",
                      font=('Helvetica', 14, 'bold')).pack(pady=5)
            ttk.Label(about_frame, text=f"版本 1.0.0").pack()

            # 添加作者信息
            ttk.Label(about_frame, text="作者: Your Name").pack(pady=10)

            # 添加描述
            description = ("一个功能强大的音频播放器，\n"
                           "支持文件夹管理、播放列表、跟读练习等功能。")
            ttk.Label(about_frame, text=description,
                      justify=tk.CENTER, wraplength=250).pack(pady=10)

            # 添加确定按钮
            ttk.Button(about_frame, text="确定",
                       command=about_window.destroy).pack(pady=10)

        except Exception as e:
            self.update_status(f"显示关于信息失败: {str(e)}", 'error')

    def export_playlist(self):
        """导出播放列表"""
        try:
            if not self.current_playlist:
                self.update_status("没有可导出的播放列表", 'warning')
                return

            file_path = filedialog.asksaveasfilename(
                defaultextension=".m3u",
                filetypes=[("M3U Playlist", "*.m3u"), ("All Files", "*.*")]
            )

            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("#EXTM3U\n")
                    for file in self.current_playlist:
                        f.write(f"{file}\n")
                self.update_status("播放列表导出成功", 'success')

        except Exception as e:
            self.update_status(f"导出播放列表失败: {str(e)}", 'error')

    def import_playlist(self):
        """导入播放列表"""
        try:
            file_path = filedialog.askopenfilename(
                filetypes=[("M3U Playlist", "*.m3u"), ("All Files", "*.*")]
            )

            if file_path:
                with open(file_path, 'r', encoding='utf-8') as f:
                    files = [line.strip() for line in f if line.strip()
                             and not line.startswith('#')]

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
                'folders': self.folders,  # 文件夹信息
                'volume': self._volume,  # 音量
                'speed': self.speed_scale.get() if hasattr(self, 'speed_scale') else 1.0,  # 播放速度
                'subtitle_offset': self._playback.get('time_offset', 0),  # 字幕偏移
                'loop_count': self.loop_count.get() if hasattr(self, 'loop_count') else 1,  # 循环次数
                'play_mode': self.mode_var.get() if hasattr(self, 'mode_var') else 'sequential'  # 播放模式
            }

            # 保存到文件
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

            # 1. 重置状态
            self._current_position = 0
            self.current_subtitle_index = 0
            self.is_playing = True

            # 2. 更新界面
            self.play_button.config(text="暂停")
            self.follow_text.delete('1.0', 'end')

            # 3. 加载字幕
            self.load_subtitles(current_file)

            # 4. 加载并播放音频
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play()

            # 5. 更新显示信息
            max_loops = self.loop_count.get()
            display_name = os.path.basename(current_file)
            self.info_label.config(text=f"当前播放: {display_name} ({self.current_loop + 1}/{max_loops})")

            # 6. 启动监控
            self.update_progress()
            self.check_playback_status()
            self.update_subtitle()

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

    def load_subtitles(self, audio_file):
        """改进的字幕加载功能"""
        try:
            srt_path = os.path.splitext(audio_file)[0] + '.srt'
            if not os.path.exists(srt_path):
                self.update_status("未找到字幕文件", 'warning')
                return False

            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            # 按空行分割字幕块
            subtitle_blocks = re.split(r'\n\n+', content)
            self.subtitles = []

            for block in subtitle_blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    # 序号
                    index = int(lines[0])

                    # 时间轴
                    time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', lines[1])
                    if not time_match:
                        continue

                    start_time = self.parse_srt_time(time_match.group(1))
                    end_time = self.parse_srt_time(time_match.group(2))

                    # 提取文本并分离中英文
                    texts = lines[2:]
                    en_text = []
                    cn_text = []

                    for line in texts:
                        if re.search('[\u4e00-\u9fff]', line):
                            cn_text.append(line)
                        else:
                            en_text.append(line)

                    self.subtitles.append({
                        'index': index,
                        'start_time': start_time,
                        'end_time': end_time,
                        'duration': end_time - start_time,
                        'en_text': '\n'.join(en_text),
                        'cn_text': '\n'.join(cn_text)
                    })

            # 按时间排序
            self.subtitles.sort(key=lambda x: x['start_time'])
            self.update_status(f"已加载 {len(self.subtitles)} 条字幕", 'success')
            return bool(self.subtitles)

        except Exception as e:
            self.update_status(f"加载字幕失败: {str(e)}", 'error')
            return False

    def parse_srt_time(self, time_str):
            """解析SRT时间为毫秒"""
            try:
                hours, mins, rest = time_str.split(':')
                seconds, milliseconds = rest.split(',')

                total_ms = (int(hours) * 3600 * 1000 +
                            int(mins) * 60 * 1000 +
                            int(seconds) * 1000 +
                            int(milliseconds))
                return total_ms

            except Exception as e:
                print(f"解析时间失败: {e}")
                return 0

    @safe_call
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
                self.current_loop += 1
                pygame.mixer.music.load(self.current_playlist[self.current_index])
                pygame.mixer.music.play()
                self.info_label.config(text=f"当前播放: {current_file} ({self.current_loop + 1}/{max_loops})")
                self.check_playback_status()
                return

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

        except Exception as e:
            self.update_status(f"处理播放结束失败: {str(e)}", 'error')

    def update_subtitle(self):
        """改进的字幕更新功能"""
        if not self.is_playing or not self.subtitles:
            return

        try:
            current_pos = self.get_accurate_position()

            # 使用缓存优化查找
            subtitle = self._find_subtitle_optimized(current_pos)
            if subtitle:
                self._update_subtitle_display(subtitle)

            # 继续更新
            if self.is_playing:
                self.root.after(20, self.update_subtitle)

        except Exception as e:
            print(f"更新字幕失败: {e}")

    def _find_subtitle_optimized(self, current_time):
        """优化的字幕查找算法"""
        try:
            # 缓存优化
            cache_window = 100  # 毫秒
            if abs(current_time - self._subtitle_cache['last_time']) < cache_window:
                return self._subtitle_cache['last_subtitle']

            # 二分查找优化
            start, end = 0, len(self.subtitles) - 1
            while start <= end:
                mid = (start + end) // 2
                subtitle = self.subtitles[mid]

                if subtitle['start_time'] <= current_time <= subtitle['end_time']:
                    self._update_cache(current_time, subtitle)
                    return subtitle

                if current_time < subtitle['start_time']:
                    end = mid - 1
                else:
                    start = mid + 1

            return None
        except Exception as e:
            print(f"查找字幕失败: {e}")
            return None

    def _update_subtitle_display(self, subtitle):
            """优化的字幕显示"""
            if not subtitle:
                return

            try:
                self.follow_text.delete('1.0', 'end')

                # 添加时间戳
                self.follow_text.insert('end',
                                        f"►{self.format_time(subtitle['start_time'], is_milliseconds=True)} - "
                                        f"{self.format_time(subtitle['end_time'], is_milliseconds=True)}◄\n\n")

                # 显示英文(蓝色)
                if subtitle.get('en_text'):
                    self.follow_text.insert('end', subtitle['en_text'] + '\n', 'en')

                # 显示中文(绿色)
                if subtitle.get('cn_text'):
                    self.follow_text.insert('end', subtitle['cn_text'] + '\n', 'cn')

                self.follow_text.see('end')

            except Exception as e:
                print(f"显示字幕错误: {e}")

    def _update_cache(self, time_ms, subtitle):
            """更新字幕缓存"""
            self._subtitle_cache.update({
                'last_time': time_ms,
                'last_subtitle': subtitle,
                'last_index': subtitle['index']
            })

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

    def adjust_subtitle_offset(self, offset_ms):
        """改进的字幕偏移调整功能"""
        try:
            if not self.subtitles:
                self.update_status("没有可调整的字幕", 'warning')
                return

            # 调整所有字幕时间
            for subtitle in self.subtitles:
                subtitle['start_time'] += offset_ms
                subtitle['end_time'] += offset_ms

            # 更新显示
            self._playback['time_offset'] += offset_ms
            self.update_status(f"字幕偏移已调整: {'+' if offset_ms > 0 else ''}{offset_ms}ms", 'info')

            # 保存设置
            self.save_settings()

        except Exception as e:
            self.update_status(f"调整字幕偏移失败: {str(e)}", 'error')

    def export_subtitles(self):
        """改进的字幕导出功能"""
        try:
            if not self.subtitles:
                self.update_status("没有可导出的字幕", 'warning')
                return

            file_path = filedialog.asksaveasfilename(
                defaultextension=".srt",
                filetypes=[("SubRip Subtitle", "*.srt"), ("All files", "*.*")]
            )

            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    for i, subtitle in enumerate(self.subtitles, 1):
                        # 写入序号
                        f.write(f"{i}\n")

                        # 写入时间轴
                        start_time = self.format_time(subtitle['start_time'], True)
                        end_time = self.format_time(subtitle['end_time'], True)
                        f.write(f"{start_time} --> {end_time}\n")

                        # 写入文本
                        if subtitle['en_text']:
                            f.write(subtitle['en_text'] + '\n')
                        if subtitle['cn_text']:
                            f.write(subtitle['cn_text'] + '\n')

                        f.write('\n')

                self.update_status("字幕导出成功", 'success')

        except Exception as e:
            self.update_status(f"导出字幕失败: {str(e)}", 'error')

    def adjust_speed(self, delta):
            """微调播放速度"""
            current_speed = self.speed_scale.get()
            new_speed = max(0.5, min(2.0, current_speed + delta))
            self.speed_scale.set(new_speed)
            self.set_playback_speed(new_speed)
            self.update_status(f"播放速度: {new_speed:.1f}x", 'info')

    def set_playback_speed(self, speed):
            """设置播放速度"""
            try:
                current_pos = self.get_accurate_position()
                self._playback['speed'] = float(speed)

                # 重新加载并调整播放位置
                if self.is_playing and self.current_playlist:
                    current_file = self.current_playlist[self.current_index]
                    pygame.mixer.music.load(current_file)
                    pygame.mixer.music.play(start=current_pos)

            except Exception as e:
                print(f"设置播放速度失败: {e}")

    def get_accurate_position(self):
        """改进的精确播放位置获取功能"""
        try:
            if not self.is_playing:
                return self._playback['last_position']

            current_pos = pygame.mixer.music.get_pos()
            if current_pos < 0:
                return self._playback['last_position']

            # 应用速度和偏移校正
            adjusted_pos = (current_pos * self._playback['speed'] +
                            self._timer['offset'] +
                            self._playback['time_offset'])

            self._playback['last_position'] = adjusted_pos
            return adjusted_pos

        except Exception as e:
            print(f"获取播放位置失败: {e}")
            return 0

    def check_playback_status(self):
            """检查播放状态"""
            if self.is_playing:
                if not pygame.mixer.music.get_busy():
                    self.handle_playback_ended()
                else:
                    # 继续监听
                    self.root.after(100, self.check_playback_status)


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

    def save_player_state(self):
        """改进的播放器状态保存功能"""
        try:
            state = {
                'volume': self.volume_scale.get(),
                'speed': self.speed_scale.get(),
                'subtitle_offset': self._playback.get('time_offset', 0),
                'last_folder': self.current_playlist[0] if self.current_playlist else '',
                'last_position': self._playback.get('last_position', 0),
                'loop_count': self.loop_count.get(),
                'play_mode': self.mode_var.get(),
                'favorites': list(self.favorites),  # 将set转换为list
                'stats': {
                    'total_play_time': self.stats['total_play_time'],
                    'played_files': list(self.stats['played_files']),  # 将set转换为list
                    'last_played': self.stats['last_played']
                }
            }

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
                print(f"状态已保存到: {self.state_file}")

        except Exception as e:
            self.update_status(f"保存状态失败: {str(e)}", 'error')

    def load_settings(self):
        """加载设置"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    # 加载音量
                    self.volume = settings.get('volume', 50)
                    # ...existing code...
        except Exception as e:
            self.update_status(f"加载设置失败: {str(e)}", 'error')

    def on_closing(self):
        """改进的关闭处理功能"""
        try:
            # 取消所有定时器
            if self.update_timer:
                self.root.after_cancel(self.update_timer)
            if self._status_timer:
                self.root.after_cancel(self._status_timer)
            if self._auto_save_timer:
                self.root.after_cancel(self._auto_save_timer)

            # 保存最终状态
            self.save_player_state()
            self.save_settings()

            # 记录关闭事件
            logging.info("播放器正常关闭")

        except Exception as e:
            logging.error(f"关闭时发生错误: {str(e)}")
        finally:
            pygame.mixer.quit()
            self.root.destroy()

    def start(self):
            """启动播放器"""
            # 恢复文件夹树形结构
            self.restore_folder_tree()
            # 开始主循环
            self.root.mainloop()

    def restore_folder_tree(self):
        """改进的文件夹树恢复功能"""
        try:
            # 清空现有树
            for item in self.folder_tree.get_children():
                self.folder_tree.delete(item)

            # 恢复文件夹结构
            for folder_id, folder_info in self.folders.items():
                folder_path = folder_info['path']
                folder_name = os.path.basename(folder_path)

                # 创建文件夹节点
                tree_id = self.folder_tree.insert(
                    "", "end",
                    text=folder_name,
                    values=(f"{len(folder_info['files'])}个文件",)
                )

                # 如果之前是展开状态，则重新展开
                if folder_info.get('expanded', False):
                    self.expand_folder(tree_id)

            self.update_status("文件夹结构已恢复", 'info')

        except Exception as e:
            self.update_status(f"恢复文件夹结构失败: {str(e)}", 'error')

    def setup_logging(self):
        """改进的日志系统设置"""
        try:
            # 设置日志文件路径
            log_file = os.path.join(self.logs_dir, f'player_{time.strftime("%Y%m%d")}.log')

            # 配置日志格式
            logging.basicConfig(
                filename=log_file,
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

            # 添加控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.WARNING)
            formatter = logging.Formatter('%(levelname)s: %(message)s')
            console_handler.setFormatter(formatter)
            logging.getLogger('').addHandler(console_handler)

        except Exception as e:
            print(f"设置日志系统失败: {e}")

    def bind_shortcuts(self):
        """改进的快捷键绑定功能"""
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

    def auto_save_state(self):
        """改进的自动保存状态功能"""
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

    def adjust_volume(self, delta):
        """音量调节函数"""
        try:
            self.volume = self.volume + (delta * 100)
        except Exception as e:
            self.update_status(f"调节音量失败: {str(e)}", 'error')

    def clean_cache(self):
        """清理缓存文件"""
        try:
            # 清理音频缓存
            for key in list(self._audio_cache.keys()):
                if not os.path.exists(key):
                    del self._audio_cache[key]

            # 清理日志文件
            current_time = time.time()
            log_retention_days = 7

            for file in os.listdir(self.logs_dir):
                file_path = os.path.join(self.logs_dir, file)
                if os.path.getmtime(file_path) < current_time - (log_retention_days * 86400):
                    os.remove(file_path)

            # 清理临时文件
            for file in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, file)
                if os.path.getmtime(file_path) < current_time - 86400:  # 1天
                    os.remove(file_path)

        except Exception as e:
            logging.error(f"清理缓存失败: {e}")

    def save_player_state(self):
        """改进的播放器状态保存功能"""
        try:
            state = {
                'volume': self.volume_scale.get(),
                'speed': self.speed_scale.get(),
                'subtitle_offset': self._playback.get('time_offset', 0),
                'last_folder': self.current_playlist[0] if self.current_playlist else '',
                'last_position': self._playback.get('last_position', 0),
                'loop_count': self.loop_count.get(),
                'play_mode': self.mode_var.get(),
                'favorites': list(self.favorites),
                'stats': self.stats
            }

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

        except Exception as e:
            self.update_status(f"保存状态失败: {str(e)}", 'error')

    def load_player_state(self):
        """改进的播放器状态加载功能"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)

                    # 恢复音量
                    self.volume_scale.set(state.get('volume', 0.5))

                    # 恢复播放速度
                    self.speed_scale.set(state.get('speed', 1.0))

                    # 恢复字幕偏移
                    self._playback['time_offset'] = state.get('subtitle_offset', 0)

                    # 恢复循环设置
                    self.loop_count.set(state.get('loop_count', 1))

                    # 恢复播放模式
                    self.mode_var.set(state.get('play_mode', 'sequential'))

                    # 恢复收藏夹
                    self.favorites = set(state.get('favorites', []))

                    # 恢复统计数据
                    self.stats = state.get('stats', {
                        'total_play_time': 0,
                        'played_files': set(),
                        'last_played': None
                    })

                    return True
        except Exception as e:
            self.update_status(f"加载状态失败: {str(e)}", 'error')
        return False

    def toggle_follow_reading(self):
        """改进的跟读切换功能"""
        try:
            if not self.is_following:
                if not self.current_playlist:
                    self.update_status("请先选择要跟读的音频文件", 'warning')
                    return
                self.start_follow_reading()
            else:
                self.stop_follow_reading()
        except Exception as e:
            self.update_status(f"切换跟读模式失败: {str(e)}", 'error')

    def start_follow_reading(self):
        """改进的跟读开始功能"""
        try:
            self.is_following = True
            self.follow_button.config(text="停止跟读")

            # 重置状态
            self.current_loop = 0
            self.max_follow_loops = self.loop_count.get()

            # 准备音频段落
            self.prepare_audio_segments()
            self.current_segment = 0

            # 更新界面
            self.progress_scale.set(0)
            self.time_label.config(text="00:00 / 00:00")
            self.follow_text.delete('1.0', 'end')
            self.follow_text.insert('end',
                                    f"开始跟读第 {self.current_index + 1} 个音频文件 (1/{self.max_follow_loops})\n")

            # 开始播放
            self.play_segment()
            self.update_status("跟读模式已启动", 'info')
        except Exception as e:
            self.update_status(f"启动跟读失败: {str(e)}", 'error')
            self.stop_follow_reading()

    def stop_follow_reading(self):
        """停止跟读"""
        self.is_following = False
        self.follow_button.config(text="开始跟读")
        pygame.mixer.music.stop()
        self.is_playing = False
        self.play_button.config(text="播放")
        self.follow_text.insert('end', "跟读已停止\n")
        self.follow_text.see('end')
        self.update_status("跟读已停止", 'info')

    def prepare_audio_segments(self):
        """改进的音频分段准备功能"""
        try:
            current_file = self.current_playlist[self.current_index]

            # 获取音频时长
            try:
                with contextlib.closing(wave.open(current_file, 'r')) as f:
                    frames = f.getnframes()
                    rate = f.getframerate()
                    self.duration = frames / float(rate)
            except:
                audio = pygame.mixer.Sound(current_file)
                self.duration = audio.get_length()

            # 加载字幕
            has_subtitles = self.load_subtitles(current_file)

            if has_subtitles and self.subtitles:
                self.total_segments = len(self.subtitles)
                segment_type = "字幕"
            else:
                # 无字幕时使用固定时长分段
                self.segment_duration = 5
                self.total_segments = int(self.duration // self.segment_duration) + 1
                segment_type = "时长"

            # 重置状态
            self.current_segment = 0

            # 更新显示
            self.follow_text.delete('1.0', 'end')
            self.follow_text.insert('end',
                                    f"{segment_type}分段：音频总长{self.duration:.1f}秒，共{self.total_segments}段\n")
            self.follow_text.see('end')

        except Exception as e:
            self.update_status(f"准备音频分段失败: {str(e)}", 'error')

    def play_segment(self):
        """改进的段落播放功能"""
        if not self.current_playlist or self.current_segment >= len(self.subtitles):
            self.stop_follow_reading()
            return

        try:
            current_file = self.current_playlist[self.current_index]
            subtitle = self.subtitles[self.current_segment]
            start_time = subtitle['start_time'] / 1000.0
            duration_ms = subtitle['end_time'] - subtitle['start_time']

            # 清空显示
            self.follow_text.delete('1.0', 'end')

            # 播放当前段落
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play(start=start_time)
            self.is_playing = True

            # 显示字幕信息
            self.show_current_subtitle(subtitle)

            # 设置暂停定时器
            self.root.after(duration_ms, self.pause_for_follow)

        except Exception as e:
            self.update_status(f"播放段落失败: {str(e)}", 'error')

    def pause_for_follow(self):
        """暂停等待跟读"""
        if self.is_following:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.play_button.config(text="播放")
            self.follow_text.insert('end', "请开始跟读...\n")
            self.follow_text.see('end')
            self.root.after(8000, self.play_next_segment)

    def play_next_segment(self):
        """播放下一个片段"""
        if not self.is_following:
            return

        self.current_segment += 1
        if self.current_segment < self.total_segments:
            self.play_segment()
        else:
            self.current_loop += 1
            if self.current_loop < self.max_follow_loops:
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

    def on_tree_double_click(self, event):
        """处理树形视图的双击事件"""
        try:
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
        except Exception as e:
            print(f"处理双击事件失败: {e}")

    def on_tree_single_click(self, event):
        """处理树形视图的单击事件"""
        try:
            selection = self.folder_tree.selection()
            if selection:
                item = selection[0]
                # 更新信息标签
                if item in self.folders:
                    # 文件夹节点
                    folder_name = self.folder_tree.item(item)['text']
                    file_count = len(self.folders[item]['files'])
                    self.info_label.config(text=f"文件夹: {folder_name} ({file_count}个文件)")
                else:
                    # 文件节点
                    file_name = self.folder_tree.item(item)['text']
                    self.info_label.config(text=f"选中文件: {file_name}")
        except Exception as e:
            print(f"处理单击事件失败: {e}")

    def remove_selected_folder(self):
        """改进的移除文件夹功能，增加强制移除选项"""
        try:
            selection = self.folder_tree.selection()
            if not selection:
                # 检查是否存在无效文件夹并提供清理选项
                invalid_folders = []
                for folder_id, folder_info in list(self.folders.items()):
                    if not os.path.exists(folder_info['path']):
                        invalid_folders.append((folder_id, folder_info['path']))

                if invalid_folders:
                    if messagebox.askyesno("清理无效文件夹",
                                           f"发现{len(invalid_folders)}个无效文件夹，是否清理？"):
                        for folder_id, _ in invalid_folders:
                            # 从树中删除
                            if self.folder_tree.exists(folder_id):
                                self.folder_tree.delete(folder_id)
                            # 从字典中删除
                            if folder_id in self.folders:
                                del self.folders[folder_id]

                        # 保存更新后的设置
                        self.save_settings()
                        self.update_status("已清理无效文件夹", 'success')
                    return
                else:
                    self.update_status("请先选择要删除的文件夹", 'warning')
                    return

            folder_id = selection[0]
            folder_info = self.folders.get(folder_id)

            if folder_info:
                folder_name = self.folder_tree.item(folder_id)['text']
                folder_path = folder_info['path']

                # 检查文件夹是否存在
                is_invalid = not os.path.exists(folder_path)
                message = f"{'无效' if is_invalid else ''}文件夹 '{folder_name}' {'已无法访问' if is_invalid else ''}\n是否移除？"

                if messagebox.askyesno("确认删除", message):
                    # 删除树节点
                    self.folder_tree.delete(folder_id)

                    # 从字典中删除
                    del self.folders[folder_id]

                    # 清理播放列表
                    if self.current_playlist and folder_info.get('files'):
                        folder_files = set(folder_info['files'])
                        if any(f in folder_files for f in self.current_playlist):
                            self.current_playlist = []
                            self.current_index = 0
                            self.stop()

                    # 保存设置
                    self.save_settings()
                    self.update_status(f"已删除文件夹: {folder_name}", 'success')

        except Exception as e:
            self.update_status(f"删除文件夹失败: {str(e)}", 'error')

    def clean_invalid_folders(self):
        """彻底清理无效文件夹"""
        try:
            # 清理前备份
            backup = dict(self.folders)

            # 清空当前所有节点
            for item in self.folder_tree.get_children():
                self.folder_tree.delete(item)

            # 清空字典
            self.folders.clear()

            # 保存空状态
            self.save_settings()

            self.update_status("所有文件夹引用已清理", 'success')
            return True

        except Exception as e:
            # 发生错误时恢复备份
            self.folders = backup
            self.update_status(f"清理失败: {str(e)}", 'error')
            return False

    def add_folder(self):
        """完全重写的添加文件夹功能"""
        try:
            # 检查现有文件夹状态
            invalid_refs = False
            for folder_id in list(self.folders.keys()):
                if not self.folder_tree.exists(folder_id):
                    invalid_refs = True
                    break

            if invalid_refs:
                if messagebox.askyesno("发现无效引用",
                                       "检测到文件夹引用错误，需要清理后继续，是否清理？"):
                    # 清理所有节点
                    for item in self.folder_tree.get_children():
                        self.folder_tree.delete(item)
                    self.folders.clear()
                    self.save_settings()
                    self.update_status("已清理所有文件夹", 'success')
                return

            folder_path = filedialog.askdirectory()
            if not folder_path:
                return

            # 检查路径是否已存在
            for info in self.folders.values():
                if os.path.samefile(info['path'], folder_path):
                    self.update_status("该文件夹已添加", 'warning')
                    return

            folder_name = os.path.basename(folder_path)

            # 扫描音频文件
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

            # 创建树节点
            tree_id = self.folder_tree.insert("", "end",
                                              text=folder_name,
                                              values=(f"{len(audio_files)}个文件",))

            # 更新文件夹字典
            self.folders[tree_id] = {
                'path': folder_path,
                'files': audio_files,
                'expanded': False
            }

            # 保存设置
            self.save_settings()
            self.update_status(f"已添加文件夹: {folder_name}", 'success')

        except Exception as e:
            self.update_status(f"添加文件夹失败: {str(e)}", 'error')

    def play_selected_folder(self):
        """改进的播放选中文件夹功能"""
        try:
            selection = self.folder_tree.selection()
            if not selection:
                self.update_status("请先选择一个文件夹", 'warning')
                return

            folder_id = selection[0]

            # 检查是否需要清理
            if folder_id not in self.folders:
                if messagebox.askyesno("无效文件夹",
                                       "检测到文件夹引用错误，需要清理后重新添加，是否现在清理？"):
                    # 清理所有节点
                    for item in self.folder_tree.get_children():
                        self.folder_tree.delete(item)
                    self.folders.clear()
                    self.save_settings()
                    self.update_status("已清理所有文件夹，请重新添加", 'success')
                return

            folder_info = self.folders[folder_id]
            folder_path = folder_info['path']

            # 检查文件夹是否存在
            if not os.path.exists(folder_path):
                if messagebox.askyesno("无效文件夹",
                                       f"文件夹 '{folder_path}' 不存在或无法访问，是否移除？"):
                    self.folder_tree.delete(folder_id)
                    del self.folders[folder_id]
                    self.save_settings()
                    self.update_status("已移除无效文件夹", 'success')
                return

            # 验证音频文件
            valid_files = [f for f in folder_info['files'] if os.path.exists(f)]
            if not valid_files:
                if messagebox.askyesno("空文件夹",
                                       "该文件夹没有有效的音频文件，是否移除？"):
                    self.folder_tree.delete(folder_id)
                    del self.folders[folder_id]
                    self.save_settings()
                    self.update_status("已移除空文件夹", 'success')
                return

            # 更新有效文件列表
            self.folders[folder_id]['files'] = valid_files
            self.current_playlist = valid_files
            self.current_index = 0
            self.current_loop = 0

            # 开始播放
            self.play_current_track()

            # 更新显示
            folder_name = self.folder_tree.item(folder_id)['text']
            self.info_label.config(text=f"正在播放文件夹: {folder_name}")
            self.update_status(f"开始播放文件夹: {folder_name}", 'success')

        except Exception as e:
            self.update_status(f"播放文件夹失败: {str(e)}", 'error')

    @safe_call
    def play_pause(self):
        """播放/暂停功能"""
        if self.is_following:
            return  # 跟读模式下不响应普通播放/暂停

        try:
            if self.is_playing:
                pygame.mixer.music.pause()
                self.is_playing = False
                self.play_button.config(text="播放")
                self.update_status("已暂停", 'info')
            else:
                if not pygame.mixer.music.get_busy():
                    # 如果没有正在播放的音频，重新开始播放
                    if not self.current_playlist:
                        self.update_status("没有可播放的文件", 'warning')
                        return
                    self.play_current_track()
                else:
                    # 继续播放暂停的音频
                    pygame.mixer.music.unpause()
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

    @safe_call
    def stop(self):
        """停止播放并重置状态"""
        try:
            pygame.mixer.music.stop()
            self.is_playing = False

            # 取消计时器
            if self.update_timer:
                self.root.after_cancel(self.update_timer)
                self.update_timer = None

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
        """进度条释放事件"""
        try:
            if self.current_playlist and self.is_playing:
                pos = self.progress_scale.get()
                total_length = self.get_current_audio_length()
                seek_time = (pos / 100.0) * total_length

                # 重新加载并播放到指定位置
                current_file = self.current_playlist[self.current_index]
                pygame.mixer.music.load(current_file)
                pygame.mixer.music.play(start=seek_time)

                # 更新时间显示
                current_time = self.format_time(seek_time)
                total_time = self.format_time(total_length)
                self.time_label.config(text=f"{current_time} / {total_time}")

                self.update_status(f"跳转到: {current_time}", 'info')
        except Exception as e:
            self.update_status(f"进度调整失败: {str(e)}", 'error')
        finally:
            self.is_seeking = False
            self._state['seeking'] = False

    def seek_relative(self, seconds):
        """改进的位置调整功能"""
        if not self.current_playlist or not self.is_playing:
            return

        try:
            # 计算新位置
            current_pos = self._playback['current_position']
            total_length = self.get_current_audio_length()
            new_pos = max(0, min(total_length, current_pos + seconds))

            # 更新位置
            self._playback['current_position'] = new_pos

            # 重新加载并播放
            current_file = self.current_playlist[self.current_index]
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play(start=new_pos)

            # 更新显示
            if total_length > 0:
                progress = (new_pos / total_length) * 100
                self.progress_scale.set(progress)

            self.time_label.config(text=f"{self.format_time(new_pos)} / {self.format_time(total_length)}")

        except Exception as e:
            self.update_status(f"快进/快退失败: {str(e)}", 'error')

    def update_progress(self):
        """修正的进度更新"""
        if not self.is_playing:
            return

        try:
            if not pygame.mixer.music.get_busy():
                self.handle_playback_ended()
                return

            # 使用静态变量记录总时长
            if not hasattr(self, '_total_length'):
                self._total_length = self.get_current_audio_length()

            # 使用静态变量跟踪播放位置
            if not hasattr(self, '_start_time'):
                self._start_time = time.time()
                self._offset = 0

            # 计算实际播放时间
            current_pos = time.time() - self._start_time + self._offset

            # 更新进度条
            if self._total_length > 0:
                progress = min(100, (current_pos / self._total_length) * 100)
                self.progress_scale.set(progress)

            # 更新时间显示
            self.time_label.config(text=f"{self.format_time(current_pos)} / {self.format_time(self._total_length)}")

        except Exception as e:
            print(f"更新进度出错: {e}")

        # 降低更新频率
        self.update_timer = self.root.after(200, self.update_progress)

    def seek_relative(self, seconds):
        """修正的快进快退"""
        if not self.is_playing:
            return

        try:
            # 更新偏移量
            self._offset += seconds

            # 重新计算当前位置
            current_pos = time.time() - self._start_time + self._offset
            current_pos = max(0, min(self._total_length, current_pos))

            # 重新加载并播放
            current_file = self.current_playlist[self.current_index]
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play(start=current_pos)

            # 更新开始时间和偏移量
            self._start_time = time.time()
            self._offset = current_pos

        except Exception as e:
            self.update_status(f"快进快退失败: {str(e)}", 'error')


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
        messagebox.showerror("错误", f"程序启动失败: {str(e)}")
        root.destroy()


if __name__ == "__main__":
    main()