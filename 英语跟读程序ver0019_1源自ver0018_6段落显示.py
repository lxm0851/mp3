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
import whisper
import pyaudio
import sys

import hashlib
import random
import requests

from text_to_subtitle_ver0010 import WhisperSubtitleGenerator

import shutil
from collections import deque


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


class SubtitleGeneratorWindow:
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title("字幕生成器")
        self.window.geometry("600x800")

        self.original_app_id = ''
        self.original_app_key = ''

        # 百度翻译API配置
        self.api_frame = ttk.LabelFrame(self.window, text="百度翻译API配置")
        self.api_frame.pack(fill="x", padx=10, pady=5)

        # APP ID 输入框
        ttk.Label(self.api_frame, text="APP ID:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.app_id_entry = ttk.Entry(self.api_frame)
        self.app_id_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')

        self.app_id_entry.bind('<FocusOut>', lambda e: self.update_api_config())

        # API Key 输入框
        ttk.Label(self.api_frame, text="API Key:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.app_key_entry = ttk.Entry(self.api_frame)
        self.app_key_entry.grid(row=1, column=1, padx=5, pady=5, sticky='ew')

        self.app_key_entry.bind('<FocusOut>', lambda e: self.update_api_config())

        # 按钮框架（保存和解锁按钮）
        self.api_button_frame = ttk.Frame(self.api_frame)
        self.api_button_frame.grid(row=2, column=0, columnspan=5, pady=5, sticky='e')

        # 保存API配置按钮
        self.save_api_btn = ttk.Button(self.api_button_frame, text="保存API配置", command=self.save_api_config)
        self.save_api_btn.pack(side="right", padx=5)

        # 解锁按钮，绑定到 unlock_entry 方法
        self.unlock_api_btn = ttk.Button(
            self.api_button_frame,
            text="解锁输入框",
            command=lambda: self.unlock_all_entries([self.app_id_entry, self.app_key_entry])
        )
        self.unlock_api_btn.pack(side="right", padx=5)

        # 路径选择
        self.path_frame = ttk.LabelFrame(self.window, text="路径设置")
        self.path_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(self.path_frame, text="音频文件夹:").grid(row=0, column=0, padx=5, pady=5)
        self.audio_path_var = tk.StringVar()
        self.audio_path_entry = ttk.Entry(self.path_frame, textvariable=self.audio_path_var)
        self.audio_path_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(self.path_frame, text="选择", command=self.select_audio_path).grid(row=0, column=2, padx=5, pady=5)

        ttk.Label(self.path_frame, text="输出文件夹:").grid(row=1, column=0, padx=5, pady=5)
        self.output_path_var = tk.StringVar()
        self.output_path_entry = ttk.Entry(self.path_frame, textvariable=self.output_path_var)
        self.output_path_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(self.path_frame, text="选择", command=self.select_output_path).grid(row=1, column=2, padx=5, pady=5)

        # 进度显示
        self.progress_frame = ttk.LabelFrame(self.window, text="生成进度")
        self.progress_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.progress_text = tk.Text(self.progress_frame, height=10)
        self.progress_text.pack(fill="both", expand=True, padx=5, pady=5)

        self.progress_bar = ttk.Progressbar(self.progress_frame, mode='determinate')
        self.progress_bar.pack(fill="x", padx=5, pady=5)

        # 控制按钮
        self.button_frame = ttk.Frame(self.window)
        self.button_frame.pack(fill="x", padx=10, pady=5)

        self.generate_btn = ttk.Button(self.button_frame, text="开始生成", command=self.start_generate)
        self.generate_btn.pack(side="right", padx=5)

        self.stop_btn = ttk.Button(self.button_frame, text="停止生成", command=self.stop_generate, state='disabled')
        self.stop_btn.pack(side="right", padx=5)

        self.setup_logging()
        self.load_api_config()
        self.generator = WhisperSubtitleGenerator()

        self.create_context_menus()
        self.bind_shortcuts()

        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.is_generating = False

    def create_context_menus(self):
        """为所有输入框创建右键菜单"""
        entries = [
            self.app_id_entry,
            self.app_key_entry,
            self.audio_path_entry,  # 使用 entry
            self.output_path_entry  # 使用 entry
        ]

        for entry in entries:
            if isinstance(entry, (tk.Entry, ttk.Entry)):
                menu = tk.Menu(self.window, tearoff=0)
                menu.add_command(label="剪切", command=lambda e=entry: self.cut_text(e))
                menu.add_command(label="复制", command=lambda e=entry: self.copy_text(e))
                menu.add_command(label="粘贴", command=lambda e=entry: self.paste_text(e))
                menu.add_separator()
                menu.add_command(label="全选", command=lambda e=entry: self.select_all(e))

                entry.bind("<Button-3>", lambda e, m=menu: self.show_context_menu(e, m))
            else:
                logging.warning(f"尝试创建上下文菜单到非Entry对象: {entry}")

    def bind_shortcuts(self):
        """绑定快捷键"""
        entries = [
            self.app_id_entry,
            self.app_key_entry,
            self.audio_path_entry,
            self.output_path_entry
        ]

        for entry in entries:
            if isinstance(entry, (tk.Entry, ttk.Entry)):
                # 检查焦点
                def focus_check(widget, callback):
                    if widget == widget.winfo_toplevel().focus_get():
                        callback(widget)

                # Windows/Linux 快捷键
                entry.bind('<Control-a>', lambda e: focus_check(e.widget, self.select_all))
                entry.bind('<Control-A>', lambda e: focus_check(e.widget, self.select_all))
                entry.bind('<Control-c>', lambda e: focus_check(e.widget, self.copy_text))
                entry.bind('<Control-C>', lambda e: focus_check(e.widget, self.copy_text))
                entry.bind('<Control-v>', lambda e: focus_check(e.widget, self.paste_text))
                entry.bind('<Control-V>', lambda e: focus_check(e.widget, self.paste_text))
                entry.bind('<Control-x>', lambda e: focus_check(e.widget, self.cut_text))
                entry.bind('<Control-X>', lambda e: focus_check(e.widget, self.cut_text))

                # Mac 快捷键
                entry.bind('<Command-a>', lambda e: focus_check(e.widget, self.select_all))
                entry.bind('<Command-A>', lambda e: focus_check(e.widget, self.select_all))
                entry.bind('<Command-c>', lambda e: focus_check(e.widget, self.copy_text))
                entry.bind('<Command-C>', lambda e: focus_check(e.widget, self.copy_text))
                entry.bind('<Command-v>', lambda e: focus_check(e.widget, self.paste_text))
                entry.bind('<Command-V>', lambda e: focus_check(e.widget, self.paste_text))
                entry.bind('<Command-x>', lambda e: focus_check(e.widget, self.cut_text))
                entry.bind('<Command-X>', lambda e: focus_check(e.widget, self.cut_text))
            else:
                logging.warning(f"尝试绑定快捷键到非Entry对象: {entry}")

    def show_context_menu(self, event, menu):
        """显示右键菜单"""
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def cut_text(self, entry):
        """剪切文本"""
        try:
            entry.event_generate("<<Cut>>")
        except Exception as e:
            logging.error(f"剪切操作失败: {str(e)}")
            messagebox.showerror("错误", f"剪切操作失败: {str(e)}")

    def copy_text(self, entry):
        """复制文本"""
        try:
            entry.event_generate("<<Copy>>")
        except Exception as e:
            logging.error(f"复制操作失败: {str(e)}")
            messagebox.showerror("错误", f"复制操作失败: {str(e)}")

    def paste_text(self, entry):
        """粘贴文本，包含防抖机制和锁定提示"""
        try:
            # 防抖机制：检查最近一次粘贴时间
            current_time = time.time()
            if hasattr(entry, 'last_paste_time'):
                if current_time - entry.last_paste_time < 0.5:  # 0.5秒内禁止重复粘贴
                    logging.warning(f"粘贴操作过于频繁，忽略本次操作: {entry.winfo_name()}")
                    self.update_progress_text(f"粘贴操作过于频繁，忽略本次操作: {entry.winfo_name()}")
                    return
            entry.last_paste_time = current_time

            # 清空当前选中的文本
            try:
                start, end = entry.selection_range()
                if start != end:
                    entry.delete(start, end)
            except:
                pass

            # 获取剪贴板内容并清理不可见字符
            clipboard_content = entry.clipboard_get().strip()
            clipboard_content = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', clipboard_content)

            # 打印粘贴前的值进行调试
            logging.debug(f"粘贴前的 entry 值: {repr(entry.get())}, 长度: {len(entry.get())}")
            logging.debug(f"粘贴的 clipboard 内容: {repr(clipboard_content)}, 长度: {len(clipboard_content)}")

            # 清空输入框内容，确保新内容替换旧内容
            entry.delete(0, 'end')

            # 执行粘贴操作
            entry.insert(0, clipboard_content)

            # 打印粘贴后的值进行调试
            logging.debug(f"粘贴后的 entry 值: {repr(entry.get())}, 长度: {len(entry.get())}")

            # 锁定输入框内容，防止意外修改
            entry.config(state='readonly')
            entry.locked = True  # 添加标志位

            # 更新进度文本，记录粘贴操作
            self.update_progress_text(f"已粘贴到输入框: {entry.winfo_name()}")

            # 弹出提示框，告知用户输入框已锁定
            messagebox.showinfo(
                "提示",
                f"输入框 {entry.winfo_name()} 已锁定，防止意外修改。\n点击'解锁'按钮可重新编辑。"
            )

        except tk.TclError as e:
            logging.error(f"粘贴操作失败: 剪贴板为空或不可访问 - {str(e)}")
            messagebox.showerror("错误", "粘贴失败: 剪贴板为空或不可访问")
            self.update_progress_text(f"粘贴失败: 剪贴板为空或不可访问 - {str(e)}")
        except Exception as e:
            logging.error(f"粘贴操作失败: {str(e)}")
            messagebox.showerror("错误", f"粘贴操作失败: {str(e)}")
            self.update_progress_text(f"粘贴失败: {str(e)}")

    def select_all(self, entry):
        """全选文本"""
        try:
            entry.select_range(0, 'end')
            entry.icursor('end')  # 将光标移到末尾
        except Exception as e:
            logging.error(f"全选操作失败: {str(e)}")
            messagebox.showerror("错误", f"全选操作失败: {str(e)}")

    def setup_logging(self):
        """配置日志记录"""
        log_dir = os.path.join(os.path.expanduser('~'), '.audio_player', 'logs')
        os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(log_dir, 'subtitle_generator.log')),
                logging.StreamHandler()
            ]
        )

    def update_progress_text(self, message):
        """更新进度文本，添加时间戳"""
        timestamp = time.strftime("%H:%M:%S")
        self.progress_text.insert('end', f"[{timestamp}] {message}\n")
        self.progress_text.see('end')
        self.window.update()

    def update_progress_bar(self, current, total):
        """更新进度条"""
        self.progress_bar['value'] = (current / total) * 100
        self.window.update()

    def on_closing(self):
        """处理窗口关闭"""
        if self.is_generating:
            if not messagebox.askyesno("确认", "正在生成字幕，确定要退出吗？"):
                return
        self.window.destroy()

    def clear_progress(self):
        """清除进度信息"""
        if messagebox.askyesno("确认", "确定要清除进度信息吗？"):
            self.progress_text.delete(1.0, 'end')
            self.progress_bar['value'] = 0

    def load_api_config(self):
        """加载API配置时添加确认覆盖功能，并清理不可见字符"""
        config_file = os.path.join(os.path.expanduser('~'), '.audio_player', 'baidu_api_config.json')
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                # 获取配置中的 app_id 和 app_key，并清理不可见字符
                app_id = config.get('app_id', '').strip()
                app_key = config.get('app_key', '').strip()

                # 清理所有不可见字符，包括换行符、制表符、不可打印字符等
                app_id = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', app_id)
                app_key = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', app_key)

                # 存储原始值
                self.original_app_id = app_id
                self.original_app_key = app_key

                # 打印日志时显示完整值（保持不变）
                print('加载的 app_id:', repr(app_id), f'长度: {len(app_id)}')
                print('加载的 app_key:', repr(app_key), f'长度: {len(app_key)}')

                # 如果输入框中已有内容，询问是否覆盖
                current_app_id = self.app_id_entry.get().strip()
                current_app_key = self.app_key_entry.get().strip()
                if current_app_id or current_app_key:
                    if not messagebox.askyesno("确认覆盖", "输入框中已有API配置，是否用保存的配置覆盖？"):
                        self.update_progress_text("已取消覆盖API配置")
                        return

                # 创建用于前端显示的隐藏版本
                def mask_sensitive(text):
                    if len(text) <= 6:  # 如果长度小于等于6，不隐藏
                        return text
                    return f"{text[:3]}{'*' * (len(text) - 6)}{text[-3:]}"

                display_app_id = mask_sensitive(app_id)
                display_app_key = mask_sensitive(app_key)

                # 清空现有内容
                self.app_id_entry.delete(0, 'end')
                self.app_key_entry.delete(0, 'end')

                # 插入隐藏后的值用于前端显示
                self.app_id_entry.insert(0, display_app_id)
                self.app_key_entry.insert(0, display_app_key)

                # 打印插入后的值（显示实际插入的隐藏值）
                print('插入后的 app_id:', repr(self.app_id_entry.get()), f'长度: {len(self.app_id_entry.get())}')
                print('插入后的 app_key:', repr(self.app_key_entry.get()), f'长度: {len(self.app_key_entry.get())}')

                self.update_progress_text("API配置已加载")
            else:
                # 如果没有配置文件，也初始化原始值为空
                self.original_app_id = ''
                self.original_app_key = ''
                self.update_progress_text("未找到API配置文件，使用空配置")
        except json.JSONDecodeError as e:
            self.original_app_id = ''
            self.original_app_key = ''
            messagebox.showerror("错误", f"API配置文件格式错误: {str(e)}")
            self.update_progress_text(f"加载API配置失败: 配置文件格式错误")
        except Exception as e:
            self.original_app_id = ''
            self.original_app_key = ''
            messagebox.showerror("错误", f"加载API配置失败: {str(e)}")
            self.update_progress_text(f"加载API配置失败: {str(e)}")

    # 添加保存配置的方法
    def save_api_config(self):
        """保存API配置，始终使用原始值"""
        config_file = os.path.join(os.path.expanduser('~'), '.audio_player', 'baidu_api_config.json')
        try:
            # 确保配置目录存在
            os.makedirs(os.path.dirname(config_file), exist_ok=True)

            # 获取输入框中的值，仅用于检查是否需要更新
            display_app_id = self.app_id_entry.get().strip()
            display_app_key = self.app_key_entry.get().strip()

            # 检查输入框中的值是否是隐藏格式（包含***）
            def is_masked(text):
                return '***' in text

            # 如果输入框中的值不是隐藏格式，更新原始值
            if not is_masked(display_app_id):
                self.original_app_id = display_app_id
                logging.info(f"保存前更新 APP ID: {repr(self.original_app_id)}")

            if not is_masked(display_app_key):
                self.original_app_key = display_app_key
                logging.info(f"保存前更新 API Key: {repr(self.original_app_key)}")

            # 检查原始值是否为空
            if not self.original_app_id or not self.original_app_key:
                logging.error("保存API配置失败: APP ID 或 API Key 不能为空")
                messagebox.showerror("错误", "APP ID 和 API Key 不能为空")
                self.update_progress_text("保存API配置失败: APP ID 和 API Key 不能为空")
                return

            # 打印要保存的原始值进行调试
            logging.info(f"保存的 app_id: {repr(self.original_app_id)}")
            logging.info(f"保存的 app_key: {repr(self.original_app_key)}")
            print(f"保存的 app_id: {repr(self.original_app_id)}")
            print(f"保存的 app_key: {repr(self.original_app_key)}")

            # 保存配置，使用原始值
            config = {
                'app_id': self.original_app_id,
                'app_key': self.original_app_key
            }

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            # 更新输入框显示为隐藏格式
            def mask_sensitive(text):
                if len(text) <= 6:
                    return text
                return f"{text[:3]}{'*' * (len(text) - 6)}{text[-3:]}"

            self.app_id_entry.delete(0, 'end')
            self.app_id_entry.insert(0, mask_sensitive(self.original_app_id))
            self.app_key_entry.delete(0, 'end')
            self.app_key_entry.insert(0, mask_sensitive(self.original_app_key))

            logging.info("API配置保存成功，输入框已更新为隐藏格式")
            self.update_progress_text("API配置已保存")
        except Exception as e:
            logging.error(f"保存API配置失败: {str(e)}")
            messagebox.showerror("错误", f"保存API配置失败: {str(e)}")
            self.update_progress_text(f"保存API配置失败: {str(e)}")

    def unlock_all_entries(self, entries):
        current_time = time.time()
        if hasattr(self, 'last_unlock_time'):
            if current_time - self.last_unlock_time < 0.5:
                logging.warning("解锁操作过于频繁，忽略本次操作")
                self.update_progress_text("解锁操作过于频繁，忽略本次操作")
                return
        self.last_unlock_time = current_time
        try:
            for entry in entries:
                self.unlock_entry(entry)
        except Exception as e:
            logging.error(f"批量解锁输入框失败: {str(e)}")
            messagebox.showerror("错误", f"批量解锁输入框失败: {str(e)}")
            self.update_progress_text(f"批量解锁输入框失败: {str(e)}")

    def unlock_entry(self, entry):
        """解锁指定的输入框，恢复可编辑状态，并在成功解锁后弹出提示"""
        try:
            if hasattr(entry, 'locked') and entry.locked:
                entry.config(state='normal')
                entry.locked = False
                self.update_progress_text(f"输入框 {entry.winfo_name()} 已解锁")
                logging.info(f"输入框 {entry.winfo_name()} 已解锁")
                # 弹出提示框，告知用户输入框已解锁
                messagebox.showinfo(
                    "提示",
                    f"输入框 {entry.winfo_name()} 已解锁，您现在可以编辑内容。"
                )
            else:
                self.update_progress_text(f"输入框 {entry.winfo_name()} 未锁定，无需解锁")
                logging.info(f"输入框 {entry.winfo_name()} 未锁定，无需解锁")
                # 弹出提示框，告知用户输入框未锁定
                messagebox.showinfo(
                    "提示",
                    f"输入框 {entry.winfo_name()} 未锁定，无需解锁。"
                )
        except Exception as e:
            logging.error(f"解锁输入框失败: {str(e)}")
            messagebox.showerror("错误", f"解锁输入框失败: {str(e)}")
            self.update_progress_text(f"解锁输入框失败: {str(e)}")

    def select_audio_path(self):
        path = filedialog.askdirectory(title="选择音频文件夹")
        if path:
            if os.access(path, os.R_OK):
                self.audio_path_var.set(path)
                self.update_progress_text(f"已选择音频文件夹: {path}")
            if not self.output_path_var.get():
                self.output_path_var.set(os.path.join(path, "字幕文件"))

    def select_output_path(self):
        path = filedialog.askdirectory(title="选择输出文件夹")
        if path:
            self.output_path_var.set(path)

    @safe_call
    def start_generate(self):
        # 验证API配置
        if not self.validate_api_config():
            return

        # 验证输入
        audio_path = self.audio_path_entry.get().strip()
        if not audio_path:
            messagebox.showerror("错误", "请选择音频文件夹")
            return

        output_path = self.output_path_entry.get().strip()
        if not output_path:
            messagebox.showerror("错误", "请选择输出文件夹")
            return

        if self.is_generating:
            messagebox.showwarning("警告", "正在处理中，请等待当前任务完成")
            return

        self.is_generating = True
        self.generate_btn.config(state='disabled')

        # 自动解锁
        self.unlock_all_entries([self.app_id_entry, self.app_key_entry])

        # 保存API配置_取消，由按钮保存
        # self.save_api_config()

        # 创建输出文件夹
        os.makedirs(output_path, exist_ok=True)

        # 获取所有音频文件
        audio_files = []
        for root, _, files in os.walk(audio_path):
            for file in files:
                if file.lower().endswith(('.mp3', '.wav')):
                    audio_files.append(os.path.join(root, file))

        if not audio_files:
            messagebox.showerror("错误", "未找到音频文件")
            return

        # 更新进度条配置
        self.progress_bar['maximum'] = len(audio_files)
        self.progress_bar['value'] = 0

        def process_files():
            try:
                total_files = len(audio_files)
                success_count = 0

                for i, audio_file in enumerate(audio_files, 1):
                    try:
                        output_file = os.path.join(
                            output_path,
                            os.path.splitext(os.path.basename(audio_file))[0] + '.srt'
                        )

                        self.update_progress_text(f"处理文件 ({i}/{total_files}): {os.path.basename(audio_file)}")

                        # 生成字幕
                        self.generator.generate_srt(
                            audio_path=audio_file,
                            output_path=output_file
                        )

                        success_count += 1
                        self.update_progress_bar(i, total_files)
                        self.update_progress_text(f"成功生成字幕: {os.path.basename(output_file)}")

                    except Exception as e:
                        self.update_progress_text(f"处理文件失败: {os.path.basename(audio_file)} - 错误: {str(e)}")
                        logging.error(f"处理文件 {audio_file} 失败: {str(e)}")
                        continue

                self.update_progress_text(
                    f"处理完成: 成功 {success_count}/{total_files} 个文件, "
                    f"失败 {total_files - success_count} 个文件"
                )
                messagebox.showinfo("完成", "字幕生成任务已完成")

            except Exception as e:
                self.update_progress_text(f"处理过程中发生错误: {str(e)}")
                logging.error(f"生成字幕过程中发生错误: {str(e)}")
                messagebox.showerror("错误", "字幕生成失败，请查看日志")
            finally:
                self.is_generating = False
                self.generate_btn.config(state='normal')

        threading.Thread(target=process_files, daemon=True).start()

    def validate_api_config(self):
        """验证API配置是否有效"""
        # 使用原始值进行验证
        app_id = self.original_app_id
        app_key = self.original_app_key

        # 检查原始值是否为空
        if not app_id or not app_key:
            logging.error("API配置验证失败: APP ID 或 API Key 为空")
            messagebox.showerror("错误", "APP ID 和 API Key 不能为空")
            self.update_progress_text("API配置验证失败: APP ID 和 API Key 不能为空")
            return False

        try:
            # 打印用于验证的原始值，方便调试
            logging.info(f"开始验证API配置 - app_id: {repr(app_id)}, app_key: {repr(app_key)}")
            print(f"验证时使用的 app_id: {repr(app_id)}")
            print(f"验证时使用的 app_key: {repr(app_key)}")

            # 设置API配置到generator
            self.generator.set_api_config(app_id, app_key)

            # 进行测试翻译
            test_text = "Hello"
            logging.info(f"执行测试翻译，测试文本: {test_text}")
            result = self.generator.test_translation(test_text)

            if result:
                logging.info("API配置验证成功")
                self.update_progress_text("API配置验证成功")
                return True
            else:
                logging.error("API配置验证失败: 测试翻译返回空结果")
                messagebox.showerror("错误", "API配置无效，请检查APP ID和API Key")
                self.update_progress_text("API配置验证失败: 测试翻译返回空结果")
                return False

        except Exception as e:
            # 捕获并记录详细的错误信息
            error_msg = f"API配置验证失败: {str(e)}"
            logging.error(error_msg)
            print(error_msg)
            messagebox.showerror("错误", error_msg)
            self.update_progress_text(error_msg)
            return False

    # 如果用户手动修改了输入框，需要更新原始值
    def update_api_config(self):
        """更新API配置，当用户修改输入框内容时"""
        display_app_id = self.app_id_entry.get().strip()
        display_app_key = self.app_key_entry.get().strip()

        # 检查输入框中的值是否是隐藏格式（包含***）
        def is_masked(text):
            return '***' in text

        # 如果两个输入框都是隐藏格式，保持原始值不变
        if is_masked(display_app_id) and is_masked(display_app_key):
            logging.info("API配置未更改（输入框值为隐藏格式，保持原始值）")
            self.update_progress_text("API配置未更改（使用原始值）")
            return

        # 检查并更新 APP ID
        if not is_masked(display_app_id):
            self.original_app_id = display_app_id
            logging.info(f"更新 APP ID: {repr(self.original_app_id)}")

        # 检查并更新 API Key
        if not is_masked(display_app_key):
            self.original_app_key = display_app_key
            logging.info(f"更新 API Key: {repr(self.original_app_key)}")

        self.update_progress_text("API配置已更新")
        logging.info(f"当前原始值 - app_id: {repr(self.original_app_id)}, app_key: {repr(self.original_app_key)}")

    def test_translation(self, text):
        """测试翻译API配置是否有效"""
        try:
            # 生成签名
            salt = str(random.randint(32768, 65536))
            sign = self.app_id + text + salt + self.app_key
            sign = hashlib.md5(sign.encode()).hexdigest()

            # 构建请求
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            payload = {
                'q': text,
                'from': 'en',
                'to': 'zh',
                'appid': self.app_id,
                'salt': salt,
                'sign': sign
            }

            # 发送请求
            response = requests.post(self.api_url, headers=headers, data=payload)
            result = response.json()

            # 检查响应
            if 'trans_result' in result:
                return True
            else:
                return False

        except Exception as e:
            logging.error(f"测试翻译API失败: {e}")
            return False

    def stop_generate(self):
        """停止生成字幕"""
        self.is_generating = False
        self.generate_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.update_progress_text("已停止生成字幕")


class WhisperFollowReading:
    def __init__(self, model_size="tiny"):
        self.whisper_model = whisper.load_model(model_size)
        self.is_recording = False
        self.recording_thread = None
        self._stop_recognition = False  # 停止标志

        self.frames = []
        self.sample_rate = 44100

        # 创建临时文件目录
        self.temp_dir = os.path.join(os.path.expanduser('~'), '.audio_player', 'temp')
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

        # 使用临时目录中的固定文件名
        self.playback_file = os.path.join(self.temp_dir, "temp_playback.wav")
        self.transcribe_file = os.path.join(self.temp_dir, "temp_transcribe.wav")

        self.audio_queue = []
        self.last_audio_time = 0
        self.min_wait_time = 5
        self.silence_threshold = 3  # 允许的静音间隔
        self.recognition_queue = []
        self.is_processing = False

    def save_audio_files(self):
        """改进的音频文件保存功能"""
        try:
            # 确保临时目录存在
            if not os.path.exists(self.temp_dir):
                os.makedirs(self.temp_dir)

            # 尝试释放可能占用的文件句柄
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except Exception as e:
                logging.warning(f"无法卸载音频: {e}")

            # 删除可能存在的旧文件
            for file in [self.playback_file, self.transcribe_file]:
                try:
                    if os.path.exists(file):
                        os.remove(file)
                except Exception as e:
                    logging.warning(f"删除旧文件失败: {e}")

            if not self.frames:
                logging.warning("没有录音数据")
                return None, None

            # 保存用于播放的音频
            try:
                self._save_wave_file(self.playback_file, self.frames)
            except Exception as e:
                logging.error(f"保存播放音频失败: {e}")
                return None, None

            # 保存用于转写的音频
            try:
                self._save_wave_file(self.transcribe_file, self.frames)
            except Exception as e:
                logging.error(f"保存转写音频失败: {e}")
                if os.path.exists(self.playback_file):
                    try:
                        os.remove(self.playback_file)
                    except:
                        pass
                return None, None

            # 验证文件是否成功创建
            if not os.path.exists(self.playback_file) or not os.path.exists(self.transcribe_file):
                logging.error("文件保存失败")
                return None, None

            return self.playback_file, self.transcribe_file

        except Exception as e:
            logging.error(f"保存音频文件失败: {e}")
            self.cleanup_temp_files()
            return None, None

    def _save_wave_file(self, file_path, frames):
        """改进的 WAV 文件保存功能"""
        wave_file = None
        try:
            wave_file = wave.open(file_path, "wb")
            wave_file.setnchannels(1)
            wave_file.setsampwidth(2)
            wave_file.setframerate(self.sample_rate)
            wave_file.writeframes(b''.join(frames))
        except Exception as e:
            logging.error(f"保存WAV文件失败: {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            raise
        finally:
            if wave_file is not None:
                try:
                    wave_file.close()
                except AttributeError:
                    # 若由于内部原因导致close出现AttributeError，则忽略该错误
                    pass
                except Exception as e:
                    logging.warning(f"关闭WAV文件时出现警告: {e}")

    def recognize_speech(self, audio_file):
        """改进的语音识别功能"""
        try:
            # 检查停止标志
            if self._stop_recognition:
                logging.info("语音识别已停止，不执行")
                return None

            if not os.path.exists(audio_file):
                logging.error(f"音频文件不存在: {audio_file}")
                return None

            if os.path.getsize(audio_file) < 1024:
                logging.warning("音频文件过小")
                return None

            print('开始WhisperFollowReading内的语音识别')
            # 使用 Whisper 进行识别，移除可能导致tensor维度不匹配的参数
            result = self.whisper_model.transcribe(
                audio_file,
                task="translate",
                language="en",
                beam_size=1,  # 降低beam_size
                word_timestamps=False  # 关闭词级时间戳
            )

            return {
                'en_text': result.get("text", "").strip(),
                'cn_text': result.get("translation", "").strip() if "translation" in result else "",
                'segments': result.get("segments", []),
                'confidence': result.get("confidence", 0)
            }

        except Exception as e:
            logging.error(f"语音识别错误: {e}")
            return None

    def start_recording(self):
        """改进的录音功能"""
        self.is_recording = True  # 设置录音状态标志
        self.frames = []  # 用于存储录音数据的列表
        self.last_audio_time = time.time()  # 记录最后检测到声音的时间

        def record_audio():
            p = None  # PyAudio实例
            stream = None  # 音频流对象
            try:
                # 初始化PyAudio
                p = pyaudio.PyAudio()
                # 打开音频流
                stream = p.open(
                    format=pyaudio.paInt16,  # 16位格式
                    channels=2,  # 单声道
                    rate=self.sample_rate,  # 采样率(通常是16000Hz)
                    input=True,  # 设置为输入流
                    frames_per_buffer=4096  # 缓冲区大小
                )

                while self.is_recording:
                    # 读取音频数据
                    data = stream.read(1024)
                    # 检测是否有声音（通过检查音频振幅）
                    if any(abs(int.from_bytes(data[i:i + 2], 'little', signed=True)) > 500
                           for i in range(0, len(data), 2)):
                        self.last_audio_time = time.time()  # 更新最后音频时间
                    self.frames.append(data)  # 保存录音数据

                    # 检查静音时长，超过阈值则停止录音
                    if time.time() - self.last_audio_time > self.silence_threshold:
                        self.is_recording = False
                        print('已停止录音')
                        break

            except Exception as e:
                logging.error(f"录音错误: {e}")
                messagebox.showerror("录音错误", f"录音失败: {str(e)}")
            finally:
                if stream:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except Exception as e:
                        logging.error(f"停止音频流失败: {e}")
                if p:
                    try:
                        p.terminate()
                    except Exception as e:
                        logging.error(f"关闭PyAudio失败: {e}")

        self.recording_thread = threading.Thread(target=record_audio)
        self.recording_thread.start()

    def stop_recording(self):
        """改进的停止录音功能"""
        try:
            if not self.is_recording:
                return self.frames

            self.is_recording = False
            # 假设有录音停止逻辑
            self.is_playing_or_recording = False
            self.has_moved = False
            if self.recording_thread:
                self.recording_thread.join(timeout=1.0)  # 设置超时以避免死锁
                self.recording_thread = None

            return self.frames
        except Exception as e:
            logging.error(f"停止录音失败: {e}")
            return []
        finally:
            # 确保重置录音状态
            self.is_recording = False
            if not self.frames:
                self.frames = []

    def cleanup_temp_files(self):
        """清理临时文件"""
        for file in [self.playback_file, self.transcribe_file]:
            try:
                if os.path.exists(file):
                    os.remove(file)
            except Exception as e:
                logging.warning(f"清理临时文件失败: {e}")

    def __del__(self):
        """析构函数中确保清理临时文件"""
        self.cleanup_temp_files()


class AudioPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("音频播放器")
        self.root.geometry("1000x800")

        # 音频引擎初始化
        pygame.mixer.pre_init(44100, -16, 2, 4096)  # 增加缓冲区大小
        pygame.init()
        pygame.mixer.init()

        # 简单直接地设置音量为50
        self._volume = 50
        pygame.mixer.music.set_volume(0.5)

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

        # 播放控制相关变量
        self._playback = {
            'speed': 1.0,
            'volume': 0.5,  # 设置默认音量为50%
            'volume_fade': None,
            'time_offset': 0,
            'last_position': 0
        }

        self.current_position = 0

        self.follow_reader = WhisperFollowReading()

        # 初始化whisper模型
        print("正在加载Whisper模型...")
        self.whisper_model = whisper.load_model("base")
        print("模型加载完成！")

        # 初始化额外的mixer通道
        pygame.mixer.set_num_channels(8)  # 设置更多的音频通道

        self._recognition_thread = None  # 识别线程引用
        self._last_switch_time = time.time()

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
            self.no_record_mode = False
            self.no_playback_mode = False
            self.no_record_var = tk.BooleanVar(value=False)
            self.no_playback_var = tk.BooleanVar(value=False)

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
            self._playback_delay_timer = None  # 新增播放延迟定时器

            # 新增段落切换锁，防止多次快速点击导致混乱
            self._segment_switch_queue = deque()  # 切换队列
            self._segment_switch_lock = False
            self._target_segment = None  # 跟踪目标段落

            self.is_playing_or_recording = False  # 是否正在播放句子、录音或播放录音
            self.has_moved = False  # 是否已经执行过切换操作

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
            self.file_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="文件", menu=self.file_menu)
            self.file_menu.add_command(label="添加文件夹", command=self.add_folder)
            self.file_menu.add_command(label="导入播放列表", command=self.import_playlist)
            self.file_menu.add_command(label="导出播放列表", command=self.export_playlist)
            self.file_menu.add_separator()
            self.file_menu.add_command(label="退出", command=self.on_closing)  # 使用 on_closing

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
            tools_menu.add_command(label="字幕生成", command=self.show_subtitle_generator)  # 新增
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

    def show_subtitle_generator(self):
        """显示字幕生成窗口"""
        SubtitleGeneratorWindow(self.root)

    def create_widgets(self):
        """创建界面组件"""
        style = ttk.Style()

        # 主背景色使用温暖的浅米色
        main_bg = '#FFF5E6'  # 浅米色背景
        secondary_bg = '#FFF8F0'  # 次要背景色
        text_color = '#2C3E50'  # 深蓝灰色文字
        accent_color = '#E67E22'  # 温暖的橙色作为强调色

        # 配置ttk主题
        style.theme_use('clam')  # 使用clam主题,这样可以自定义颜色

        # 基础样式配置
        style.configure('TFrame', background=main_bg)
        style.configure('TLabelframe', background=main_bg)
        style.configure('TLabelframe.Label',
                        background=main_bg,
                        foreground=text_color,
                        font=('Microsoft YaHei UI', 10))

        # 在create_widgets函数中,修改按钮颜色和语速控制布局

        # 修改按钮颜色为更淡的橙红色
        accent_color = '#FF9966'  # 更淡的橙红色
        hover_color = '#FFB088'  # 鼠标悬停时的颜色
        pressed_color = '#FF7744'  # 按下时的颜色

        # 按钮样式配置
        style.configure('TButton',
                        font=('Microsoft YaHei UI', 9),
                        background=accent_color,
                        foreground=text_color,
                        borderwidth=1,
                        padding=5)

        style.map('TButton',
                  background=[('active', hover_color),
                              ('pressed', pressed_color)],
                  foreground=[('active', text_color),
                              ('pressed', '#FFFFFF')])

        # 菜单样式
        self.root.option_add('*Menu.background', secondary_bg)
        self.root.option_add('*Menu.foreground', text_color)
        self.root.option_add('*Menu.activeBackground', accent_color)
        self.root.option_add('*Menu.activeForeground', '#FFFFFF')
        self.root.option_add('*Menu.font', ('Microsoft YaHei UI', 9))

        # 标签样式
        style.configure('TLabel',
                        background=main_bg,
                        foreground=text_color,
                        font=('Microsoft YaHei UI', 10))

        # 进度条样式
        style.configure('Horizontal.TScale',
                        background=main_bg,
                        troughcolor='#FFE0B2',
                        slidercolor=accent_color)

        # 树形视图样式
        style.configure('Treeview',
                        background=secondary_bg,
                        fieldbackground=secondary_bg,
                        foreground=text_color,
                        font=('Microsoft YaHei UI', 9))
        style.map('Treeview',
                  background=[('selected', accent_color)],
                  foreground=[('selected', '#FFFFFF')])

        style.configure('Treeview.Heading',
                        background='#FFE0B2',
                        foreground=text_color,
                        font=('Microsoft YaHei UI', 9, 'bold'))

        # 文本框样式
        self.root.option_add('*Text.background', secondary_bg)
        self.root.option_add('*Text.foreground', text_color)
        self.root.option_add('*Text.selectBackground', accent_color)
        self.root.option_add('*Text.selectForeground', '#FFFFFF')
        self.root.option_add('*Text.font', ('Microsoft YaHei UI', 10))

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
        self.control_frame = ttk.Frame(main_frame)  # 修复：将 control_frame 保存为实例变量
        self.control_frame.pack(side="right", fill="both", padx=5)

        # 文件操作按钮
        file_frame = ttk.LabelFrame(self.control_frame, text="文件操作")  # 修复：使用 self.control_frame
        file_frame.pack(fill="x", pady=5)

        ttk.Button(file_frame, text="添加文件夹",
                   command=self.add_folder).pack(side="left", padx=5)
        ttk.Button(file_frame, text="移除选中文件夹",
                   command=self.remove_selected_folder).pack(side="left", padx=5)
        ttk.Button(file_frame, text="播放选中文件夹",
                   command=self.play_selected_folder).pack(side="left", padx=5)

        # 播放模式选择
        mode_frame = ttk.LabelFrame(self.control_frame, text="播放模式")  # 修复：使用 self.control_frame
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
        control_buttons = ttk.Frame(self.control_frame)  # 修复：使用 self.control_frame
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
        volume_frame = ttk.LabelFrame(self.control_frame, text="音量控制")  # 修复：使用 self.control_frame
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
        self.info_label = ttk.Label(self.control_frame, text="未播放")  # 修复：使用 self.control_frame
        self.info_label.pack(pady=5)

        # 添加跟读控制区域
        self.follow_frame = ttk.LabelFrame(self.control_frame, text="跟读控制")  # 修复：保存为实例变量
        self.follow_frame.pack(fill="x", pady=5)

        # 在 follow_frame 中创建一个横向按钮框架
        button_frame = ttk.Frame(self.follow_frame)
        button_frame.pack(fill="x", pady=5)

        # 字幕编辑按钮和跟读按钮水平放置
        self.edit_subtitle_btn = ttk.Button(
            button_frame,  # 改为使用 button_frame
            text="预览/修改字幕",
            command=self.edit_current_subtitles
        )
        self.edit_subtitle_btn.pack(side="left", padx=5)  # 使用 side="left"

        self.follow_button = ttk.Button(
            button_frame,  # 改为使用 button_frame
            text="开始跟读",
            command=self.toggle_follow_reading
        )
        self.follow_button.pack(side="left", padx=5)  # 使用 side="left"

        # 在跟读控制区域添加字幕偏移控制
        offset_frame = ttk.Frame(self.follow_frame)
        offset_frame.pack(fill="x", pady=5)
        ttk.Label(offset_frame, text="字幕偏移:").pack(side="left")
        ttk.Button(offset_frame, text="-0.5s",
                   command=lambda: self.adjust_subtitle_offset(-500)).pack(side="left")
        ttk.Button(offset_frame, text="+0.5s",
                   command=lambda: self.adjust_subtitle_offset(500)).pack(side="left")

        # 修改语速控制布局
        speed_frame = ttk.LabelFrame(self.follow_frame, text="语速控制")
        speed_frame.pack(fill="x", pady=5)

        # 语速滑动条
        speed_scale_frame = ttk.Frame(speed_frame)
        speed_scale_frame.pack(fill="x", pady=2)
        ttk.Label(speed_scale_frame, text="语速:").pack(side="left", padx=5)
        self.speed_scale = ttk.Scale(speed_scale_frame, from_=0.5, to=2.0,
                                     orient="horizontal",
                                     command=self.on_speed_change)
        self.speed_scale.set(1.0)
        self.speed_scale.pack(side="left", fill="x", expand=True, padx=10)

        # 语速微调按钮
        speed_adjust_frame = ttk.Frame(speed_scale_frame)
        speed_adjust_frame.pack(side="right", padx=5)
        ttk.Button(speed_adjust_frame, text="-0.1", width=5,
                   command=lambda: self.adjust_speed(-0.1)).pack(side="left", padx=2)
        ttk.Button(speed_adjust_frame, text="+0.1", width=5,
                   command=lambda: self.adjust_speed(0.1)).pack(side="left", padx=2)

        # 预设速度按钮 - 新的一行
        preset_frame = ttk.Frame(speed_frame)
        preset_frame.pack(fill="x", pady=2)
        ttk.Label(preset_frame, text="预设:").pack(side="left", padx=5)
        for speed in self.player_config['speed_presets']:
            ttk.Button(preset_frame, text=f"{speed}x", width=5,
                       command=lambda s=speed: self.set_playback_speed(s)).pack(side="left", padx=2)

        # 跟读文本显示区域
        text_frame = ttk.LabelFrame(self.control_frame, text="跟读结果")  # 修复：使用 self.control_frame
        text_frame.pack(fill="both", expand=True, pady=5)

        self.follow_text = tk.Text(text_frame, height=9, width=40)
        self.follow_text.pack(pady=5, padx=5, fill="both", expand=True)

        # 字幕样式配置
        self.follow_text.tag_configure('en', foreground='blue', font=('Consolas', 10))
        self.follow_text.tag_configure('cn', foreground='green', font=('Microsoft YaHei', 10))
        self.follow_text.tag_configure('time', foreground='gray')

        # 在创建 follow_text 后添加更多文本样式
        self.follow_text.tag_configure('prompt', foreground='purple')
        self.follow_text.tag_configure('recognized', foreground='blue', font=('Consolas', 10))
        self.follow_text.tag_configure('title', foreground='green', font=('Arial', 10, 'bold'))
        self.follow_text.tag_configure('error', foreground='red')

        # 播放进度控制
        progress_frame = ttk.LabelFrame(self.control_frame, text="播放进度")  # 修复：使用 self.control_frame
        progress_frame.pack(fill="x", pady=5)

        # 快进快退按钮和进度条框架
        progress_control_frame = ttk.Frame(progress_frame)
        progress_control_frame.pack(fill="x", padx=5)

        self.create_follow_control_buttons()

        # 后退2秒
        ttk.Button(progress_control_frame, text="◀◀", width=3,
                   command=lambda: self.seek_relative(-2)).pack(side="left", padx=2)

        # 进度条
        self.progress_scale = ttk.Scale(progress_control_frame, from_=0, to=100,
                                        orient="horizontal")  # 移除 command 参数 避免实时调用 seek_absolute
        self.progress_scale.pack(side="left", fill="x", expand=True, padx=5)

        # 进度条事件绑定  统一拖动逻辑。
        self.progress_scale.bind("<Button-1>", self.on_progress_press)
        self.progress_scale.bind("<ButtonRelease-1>", self.on_progress_release)

        # 前进2秒
        ttk.Button(progress_control_frame, text="▶▶", width=3,
                   command=lambda: self.seek_relative(2)).pack(side="left", padx=2)

        # 时间显示框架
        time_frame = ttk.Frame(progress_frame)
        time_frame.pack(fill="x", padx=5)

        # 当前时间/总时间
        self.time_label = ttk.Label(time_frame, text="00:00 / 00:00")
        self.time_label.pack(side="right", padx=5)

        # 添加波形显示
        wave_frame = ttk.LabelFrame(self.control_frame, text="音频波形")  # 修复：使用 self.control_frame
        wave_frame.pack(fill="x", pady=5)
        self.wave_canvas = tk.Canvas(wave_frame, height=60, bg='white')
        self.wave_canvas.pack(fill="x", padx=5)

        # 添加播放列表功能按钮
        playlist_frame = ttk.Frame(self.control_frame)  # 修复：使用 self.control_frame
        playlist_frame.pack(fill="x", pady=5)
        ttk.Button(playlist_frame, text="导出列表",
                   command=self.export_playlist).pack(side="left", padx=2)
        ttk.Button(playlist_frame, text="导入列表",
                   command=self.import_playlist).pack(side="left", padx=2)
        ttk.Button(playlist_frame, text="收藏",
                   command=self.toggle_favorite).pack(side="left", padx=2)

        # 修改文本标签样式
        self.follow_text.tag_configure('en',
                                       foreground='#2980B9',
                                       font=('Microsoft YaHei UI', 11))
        self.follow_text.tag_configure('cn',
                                       foreground='#16A085',
                                       font=('Microsoft YaHei UI', 10))
        self.follow_text.tag_configure('time',
                                       foreground='#7F8C8D',
                                       font=('Microsoft YaHei UI', 9))
        self.follow_text.tag_configure('prompt',
                                       foreground='#8E44AD',
                                       font=('Microsoft YaHei UI', 10))
        self.follow_text.tag_configure('recognized',
                                       foreground='#2980B9',
                                       font=('Microsoft YaHei UI', 11))
        self.follow_text.tag_configure('title',
                                       foreground=accent_color,
                                       font=('Microsoft YaHei UI', 11, 'bold'))
        self.follow_text.tag_configure('error',
                                       foreground='#C0392B',
                                       font=('Microsoft YaHei UI', 10))

        # 修改波形显示画布背景
        if hasattr(self, 'wave_canvas'):
            self.wave_canvas.configure(bg=secondary_bg)

        # 修改状态栏样式
        self.status_bar.configure(
            background=main_bg,
            foreground=text_color,
            font=('Microsoft YaHei UI', 9)
        )

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

    def check_follow_status(self, wait_time):
        """检查跟读状态"""
        try:
            if not self.is_following:
                return

            # 停止录音
            self.follow_reader.stop_recording()
            audio_data = self.follow_reader.get_audio_data()
            if audio_data:
                # 识别录音
                recognized_text = self.follow_reader.recognize_audio(audio_data)
                self.follow_text.insert('end', f"\n识别结果: {recognized_text}\n", 'result')
                self.follow_text.see('end')

                # 检查“不播放录音模式”
                if hasattr(self, 'no_playback_mode') and self.no_playback_mode:
                    self.follow_text.insert('end', "\n不播放录音模式，跳过播放...\n", 'prompt')
                    self.follow_text.see('end')
                else:
                    # 播放录音
                    self.follow_reader.play_recording(audio_data)
                    self.follow_text.insert('end', "\n正在播放录音...\n", 'prompt')
                    self.follow_text.see('end')

            self.toggle_navigation_buttons(True)
            self.continue_after_playback()

        except Exception as e:
            logging.error(f"检查跟读状态失败: {e}")
            self.update_status("检查跟读状态失败", 'error')
            self.toggle_navigation_buttons(True)
            self.continue_after_playback()

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

    def process_follow_reading(self):
        """完整的录音处理流程"""
        try:
            # 1. 停止录音并获取数据
            frames = self.follow_reader.stop_recording()
            self.toggle_navigation_buttons(True)  # 录音结束，启用导航按钮

            if not frames:
                logging.warning("没有录音数据")
                self.continue_after_playback()
                return

            # 2. 保存音频文件
            playback_file, transcribe_file = self.follow_reader.save_audio_files()
            if not playback_file or not transcribe_file:
                logging.error("保存音频文件失败")
                self.continue_after_playback()
                return

            # 3. 显示原文
            current_subtitle = self.subtitles[self.current_segment]
            reference_text = current_subtitle.get('en_text', '')
            self.follow_text.delete('1.0', 'end')

            # 4. 播放录音（如果启用）
            if not self.no_playback_mode and os.path.exists(playback_file):
                pygame.mixer.music.load(playback_file)
                pygame.mixer.music.play()

            # 5. 异步处理语音识别
            def handle_recognition():
                try:
                    recognition = self.follow_reader.recognize_speech(transcribe_file)
                    if recognition:
                        # 6. 更新识别结果
                        self.root.after(0, lambda: self._update_recognition_result(
                            recognition, reference_text, playback_file, transcribe_file))
                    else:
                        logging.error("语音识别返回空结果")
                        self.root.after(0, lambda: self.cleanup_and_continue(
                            playback_file, transcribe_file))
                except Exception as e:
                    logging.error(f"处理语音识别失败: {e}")
                    self.root.after(0, lambda: self.cleanup_and_continue(
                        playback_file, transcribe_file))

            # 保存线程引用
            self.recognition_thread = threading.Thread(target=handle_recognition)
            self.recognition_thread.daemon = True
            self.recognition_thread.start()

        except Exception as e:
            logging.error(f"处理录音失败: {e}")
            self.toggle_navigation_buttons(True)  # 确保在出错时也启用导航按钮
            self.continue_after_playback()

    def _update_recognition_result(self, recognition, reference_text, playback_file, transcribe_file):
        """更新识别结果到界面"""
        try:
            self.follow_text.insert('end', "\n=== 跟读结果 ===\n", 'title')
            recognized_text = recognition.get('en_text', '')
            self.follow_text.insert('end', f"您说的是: {recognized_text}\n", 'recognized')

            if recognition.get('cn_text'):
                self.follow_text.insert('end', f"翻译: {recognition['cn_text']}\n", 'cn')

            similarity = self.calculate_improved_similarity(reference_text, recognized_text)
            feedback = self.get_feedback(similarity)

            self.follow_text.insert('end', f"\n准确度评分: {similarity:.1f}%\n", 'score')
            self.follow_text.insert('end', f"{feedback}\n", 'feedback')
            self.follow_text.see('end')

            # 确保音频播放完成后继续
            self.root.after(2000, lambda: self.cleanup_and_continue(playback_file, transcribe_file))

        except Exception as e:
            logging.error(f"更新识别结果失败: {e}")
            self.cleanup_and_continue(playback_file, transcribe_file)

    def cleanup_and_continue(self, playback_file, transcribe_file):
        """修复的文件清理功能"""
        try:
            # 先停止播放避免文件占用
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()

            # 等待一小段时间确保文件释放
            time.sleep(0.1)

            # 确保文件存在再删除
            if playback_file and os.path.exists(playback_file):
                try:
                    os.remove(playback_file)
                except Exception as e:
                    logging.warning(f"清理播放文件失败: {e}")

            if transcribe_file and os.path.exists(transcribe_file):
                try:
                    os.remove(transcribe_file)
                except Exception as e:
                    logging.warning(f"清理转写文件失败: {e}")

        except Exception as e:
            logging.error(f"清理临时文件失败: {e}")
        finally:
            # 无论清理是否成功都继续下一步
            self.continue_after_playback()

    def continue_after_playback(self):
        """回放结束后继续播放"""
        try:
            if self._segment_switch_queue:
                self._process_switch_queue()
                return

            next_segment = self.current_segment + 1
            if next_segment < self.total_segments:
                self.follow_text.insert('end', "\n=== 准备下一段 ===\n", 'prompt')
                self.current_segment = next_segment
                self.play_segment()
                return

            self.current_loop += 1
            if self.current_loop < self.max_follow_loops:
                self.current_segment = 0
                self.follow_text.insert('end', f"\n开始第 {self.current_loop + 1} 轮跟读\n", 'title')
                self.play_segment()
                return

            play_mode = self.mode_var.get()
            if play_mode == "loop_one":
                self.current_loop = 0
                self.current_segment = 0
                self.follow_text.insert('end', "\n重新开始跟读当前音频\n", 'title')
                self.play_segment()
            elif self.current_index < len(self.current_playlist) - 1:
                self.current_index += 1
                self.current_loop = 0
                self.current_segment = 0
                self.follow_text.insert('end', f"\n开始跟读下一个音频文件\n", 'title')
                self.start_follow_reading()
            elif play_mode == "loop_all":
                self.current_index = 0
                self.current_loop = 0
                self.current_segment = 0
                self.follow_text.insert('end', "\n重新开始跟读播放列表\n", 'title')
                self.start_follow_reading()
            else:
                self.stop_follow_reading()

        except Exception as e:
            logging.error(f"继续播放失败: {e}")
            self.update_status("继续播放失败", 'error')

    def stop_follow_reading(self):
        """改进的停止跟读功能"""
        if not self.is_following:  # 避免重复调用
            return

        try:
            self.is_following = False
            self.follow_button.config(text="开始跟读")

            # 清理音频资源前先停止所有播放
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()

            # 等待一小段时间确保资源释放
            time.sleep(0.2)

            # 清理其他资源
            self._cleanup_audio_resources()

            # 重置状态
            self.is_playing = False
            self.is_playing_or_recording = False
            self.has_moved = False
            self._retry_count = 0
            self.current_segment = 0

            self.follow_text.insert('end', "跟读已停止\n")
            self.follow_text.see('end')

            # 延迟后再启动普通播放
            self.root.after(500, self._resume_normal_playback)

            self.update_status("跟读已停止", 'info')

        except Exception as e:
            logging.error(f"停止跟读失败: {e}")
            self.update_status("停止跟读失败", 'error')

    def _resume_normal_playback(self):
        """改进的恢复普通播放功能"""
        try:
            if not self.current_playlist:
                return

            # 完全清理资源
            self._cleanup_audio_resources()

            # 重新加载并播放
            current_file = self.current_playlist[self.current_index]
            try:
                # 预加载音频
                pygame.mixer.music.load(current_file)
                time.sleep(0.1)  # 等待加载完成

                # 设置音量
                pygame.mixer.music.set_volume(self._volume / 100.0)

                # 从当前进度开始播放（秒）
                pygame.mixer.music.play(start=self.current_position)
                self.is_playing = True
                self.play_button.config(text="暂停")
                logging.info(f"恢复播放，当前进度: {self.format_time(self.current_position)}")  # 添加日志

                # 立即更新字幕（将秒转换为毫秒）
                if self.subtitles:
                    current_pos_ms = self.current_position * 1000  # 转换为毫秒
                    subtitle = self._find_subtitle_optimized(current_pos_ms)
                    if subtitle:
                        self._update_subtitle_display(subtitle)

                # 更新显示
                self.update_info_label()
                total_length = self.get_current_audio_length()
                logging.info(f"音频总长度: {self.format_time(total_length)}")  # 添加日志
                if total_length > 0:
                    progress = (self.current_position / total_length) * 100
                    self.progress_scale.set(progress)
                self.time_label.config(
                    text=f"{self.format_time(self.current_position)} / {self.format_time(total_length)}")

                # 启动进度更新
                if not self.is_seeking:
                    self.update_timer = self.root.after(500, self.update_progress)

            except Exception as e:
                logging.error(f"加载音频失败: {e}")
                self.update_status("加载音频失败", 'error')
                self.is_playing = False  # 重置播放状态
                self.play_button.config(text="播放")  # 更新按钮状态

        except Exception as e:
            logging.error(f"恢复普通播放失败: {e}")
            self.update_status("恢复普通播放失败", 'error')
            self.is_playing = False  # 重置播放状态
            self.play_button.config(text="播放")  # 更新按钮状态

    def calculate_improved_similarity(self, text1, text2):
        """改进的文本相似度计算"""
        try:
            # 文本预处理
            def preprocess(text):
                # 转小写，去除标点
                text = re.sub(r'[^\w\s]', '', text.lower())
                # 分词
                return text.split()

            words1 = preprocess(text1)
            words2 = preprocess(text2)

            if not words1 or not words2:
                return 0

            # 计算词级别匹配
            matches = 0
            total_words = len(words1)

            for w1 in words1:
                if w1 in words2:
                    matches += 1

            # 考虑词序
            order_bonus = 0
            for i in range(len(words1) - 1):
                if i < len(words2) - 1:
                    if words1[i] == words2[i] and words1[i + 1] == words2[i + 1]:
                        order_bonus += 0.5

            # 计算最终得分
            base_score = (matches / total_words) * 100
            final_score = min(100, base_score + order_bonus)

            return final_score

        except Exception as e:
            logging.error(f"计算相似度失败: {e}")
            return 0

    def get_feedback(self, similarity):
        """根据相似度生成更详细的反馈"""
        if (similarity >= 90):
            return "★★★★★ 太棒了！发音非常准确！"
        elif (similarity >= 80):
            return "★★★★☆ 非常好！继续保持！"
        elif (similarity >= 70):
            return "★★★☆☆ 不错！还可以更好！"
        elif (similarity >= 60):
            return "★★☆☆☆ 基本正确，需要多练习"
        elif (similarity >= 50):
            return "★☆☆☆☆ 继续努力，重点注意发音"
        else:
            return "☆☆☆☆☆ 加油，建议多听多练"

    def show_about(self):
        """显示关于信息"""
        try:
            about_window = tk.Toplevel(self.root)
            about_window.title("关于")
            about_window.geometry("300x200")

            about_label = ttk.Label(about_window,
                                    text="""英语语感听说助手\n版本: 1.0\n作者: 林溪木\n日期: 2025-02-01""",
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

    def _serialize_folder_data(self):
        """序列化文件夹数据，处理不可序列化的内容"""
        serializable_folders = {}
        for folder_id, folder_info in self.folders.items():
            serializable_folders[str(folder_id)] = {
                'path': folder_info['path'],
                'files': list(folder_info['files']),  # 确保是列表
                'expanded': bool(folder_info['expanded'])  # 确保是布尔值
            }
        return serializable_folders

    def _deserialize_folder_data(self, data):
        """反序列化文件夹数据"""
        folders = {}
        for folder_id, folder_info in data.items():
            folders[folder_id] = {
                'path': str(folder_info['path']),
                'files': list(folder_info['files']),
                'expanded': bool(folder_info['expanded'])
            }
        return folders

    def _encode_json_safe(self, obj):
        """安全的JSON编码处理"""
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, bytes):
            return obj.decode('utf-8')
        return str(obj)

    def save_settings(self):
        """改进的设置保存功能，确保文件夹持久化"""
        try:
            settings = {
                'folders': {},  # 用于存储处理后的文件夹数据
                'volume': self._volume,
                'speed': self.speed_scale.get(),
                'subtitle_offset': self._playback.get('time_offset', 0),
                'loop_count': self.loop_count.get(),
                'play_mode': self.mode_var.get()
            }

            # 遍历 self.folders，将每个文件夹的信息序列化
            for tree_id, folder_info in self.folders.items():
                folder_path = folder_info['path']
                settings['folders'][folder_path] = {  # 使用文件夹路径作为键
                    'path': folder_path,
                    'files': folder_info['files'],
                    'expanded': folder_info['expanded']
                }

            # 保存到文件
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)

            self.update_status("设置已保存", 'success')
            return True

        except Exception as e:
            self.update_status(f"保存设置失败: {str(e)}", 'error')
            return False

    def load_settings(self):
        """改进的设置加载功能，确保文件夹正确恢复"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)

                # 清空当前树形视图
                for item in self.folder_tree.get_children():
                    self.folder_tree.delete(item)

                # 重置文件夹字典
                self.folders = {}

                # 加载文件夹信息
                loaded_folders = settings.get('folders', {})
                for folder_path, folder_data in loaded_folders.items():
                    if os.path.exists(folder_path):  # 检查文件夹是否存在
                        folder_name = os.path.basename(folder_path)
                        # 创建树形视图节点
                        tree_id = self.folder_tree.insert(
                            "", "end",
                            text=folder_name,
                            values=(f"{len(folder_data['files'])}个文件",)
                        )

                        # 保存到文件夹字典
                        self.folders[tree_id] = {
                            'path': folder_path,
                            'files': folder_data['files'],
                            'expanded': folder_data['expanded']
                        }

                        # 如果之前是展开状态，重新展开
                        if folder_data['expanded']:
                            self.expand_folder(tree_id)

                # 恢复其他设置
                self.volume = settings.get('volume', 50)
                self.speed_scale.set(settings.get('speed', 1.0))
                self._playback['time_offset'] = settings.get('subtitle_offset', 0)
                self.loop_count.set(settings.get('loop_count', 1))
                self.mode_var.set(settings.get('play_mode', 'sequential'))

                self.update_status("设置已加载", 'success')
                return True

        except Exception as e:
            self.update_status(f"加载设置失败: {str(e)}", 'error')
            return False

    def delete_settings(self):
        """删除设置文件"""
        try:
            if messagebox.askyesno("确认", "确定要删除所有设置文件吗？"):
                files_to_delete = [
                    self.settings_file,
                    self.state_file,
                    self.history_file,
                    self.favorites_file
                ]

                for file in files_to_delete:
                    if os.path.exists(file):
                        os.remove(file)

                self.update_status("所有设置文件已删除", 'success')
                messagebox.showinfo("成功", "设置已删除，程序将重新启动")
                self.root.after(1000, self.restart_application)
        except Exception as e:
            self.update_status(f"删除设置失败: {str(e)}", 'error')

    def restart_application(self):
        """重启应用程序"""
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def clean_settings(self):
        """清理设置文件"""
        try:
            if os.path.exists(self.settings_file):
                os.remove(self.settings_file)
                self.update_status("设置文件已删除", 'success')
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
                self.update_status("状态文件已删除", 'success')
            return True
        except Exception as e:
            self.update_status(f"清理设置失败: {str(e)}", 'error')
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

            # 显示段落信息
            self.follow_text.insert('end',
                                    f"当前段落: {self.current_segment + 1}/{len(self.subtitles)}\n", 'title')

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
                    # 解析序号
                    index = int(lines[0])

                    # 解析时间轴
                    time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', lines[1])
                    if not time_match:
                        continue

                    start_time = self.parse_srt_time(time_match.group(1))
                    end_time = self.parse_srt_time(time_match.group(2))

                    # 分离中英文
                    remaining_lines = lines[2:]
                    en_text = []
                    cn_text = []

                    for line in remaining_lines:
                        if line.startswith('英文：'):
                            en_text.append(line.replace('英文：', '').strip())
                        elif line.startswith('中文：'):
                            cn_text.append(line.replace('中文：', '').strip())
                        elif re.search(r'[\u4e00-\u9fff]', line):
                            cn_text.append(line.strip())
                        else:
                            en_text.append(line.strip())

                    self.subtitles.append({
                        'index': index,
                        'start_time': start_time,
                        'end_time': end_time,
                        'en_text': ' '.join(en_text),
                        'cn_text': ' '.join(cn_text)
                    })

            return True if self.subtitles else False

        except Exception as e:
            logging.error(f"加载字幕失败: {e}")
            return False

    def parse_srt_time(self, time_string):
        """解析 SRT 时间格式"""
        try:
            hours, mins, rest = time_string.split(':')
            seconds, milliseconds = rest.split(',')

            total_ms = (int(hours) * 3600 * 1000 +
                        int(mins) * 60 * 1000 +
                        int(seconds) * 1000 +
                        int(milliseconds))
            return total_ms

        except Exception as e:
            print(f"解析时间失败: {e}")
            return 0

    def handle_playback_ended(self):
        """改进的播放结束处理"""
        try:
            print("进入 handle_playback_ended")  # 调试输出
            # 如果正在跟读模式
            if self.is_following:
                if self.current_segment >= self.total_segments:
                    self.current_loop += 1
                    if self.current_loop < self.loop_count.get():
                        # 继续当前文件的下一轮跟读
                        self.current_segment = 0
                        self.follow_text.insert('end', f"\n重新跟读第 {self.current_loop + 1} 次\n")
                        self.play_segment()
                    else:
                        # 切换到下一个文件或结束跟读
                        if self.current_index < len(self.current_playlist) - 1:
                            self.current_index += 1
                            self.current_loop = 0
                            self.current_segment = 0
                            self.start_follow_reading()
                        else:
                            self.stop_follow_reading()
                            # 恢复普通播放模式
                            self.current_index = 0
                            self.current_loop = 0
                            self.play_current_track()
                return

            # 普通模式处理
            max_loops = self.loop_count.get()
            print('普通模式单次播放完成:', self.current_loop, max_loops)

            current_file = os.path.basename(self.current_playlist[self.current_index])
            if self.current_loop < max_loops - 1:
                print(f"继续循环播放当前曲目，下一循环={self.current_loop + 1}")  # 调试输出
                self.current_loop += 1
                pygame.mixer.music.load(self.current_playlist[self.current_index])
                pygame.mixer.music.play()
                self.info_label.config(text=f"当前播放: {current_file} ({self.current_loop + 1}/{max_loops})")
                self.check_playback_status()
                return

            # 当前曲目已循环完毕，重置循环计数，根据播放模式播放下一曲
            self.current_loop = 0
            play_mode = self.mode_var.get()
            print(f"播放模式: {play_mode}")  # 调试输出

            if play_mode == "sequential":
                if self.current_index < len(self.current_playlist) - 1:
                    self.next_track()  # 播放下一曲
                else:
                    self.stop()  # 停止播放
            elif play_mode == "loop_one":
                self.play_current_track()  # 循环播放当前曲目
            elif play_mode == "loop_all":
                if self.current_index < len(self.current_playlist) - 1:
                    self.next_track()  # 播放下一曲
                else:
                    # 列表循环，回到列表开头
                    self.current_index = 0
                    self.next_track()
        except Exception as e:
            self.update_status(f"处理播放结束失败: {str(e)}", 'error')

    def start_playback_delay(self):
        """启动播放延迟"""
        if not self.is_paused_for_delay:  # 避免重复启动
            self.is_paused_for_delay = True
            self.update_status("播放完毕，暂停10秒...", 'info')
            self.playback_delay_timer = self.root.after(10000, self.continue_playback_after_delay)  # 10秒延迟

    def continue_playback_after_delay(self):
        """延迟后继续播放"""
        self.is_paused_for_delay = False
        play_mode = self.mode_var.get()
        if play_mode in ["sequential", "loop_all"]:
            self.next_track()

    def _schedule_next_track(self):
        """调度下一曲播放"""
        if not self.is_paused_for_delay:
            self.is_paused_for_delay = True
            self.update_status("播放完毕，等待3秒...", 'info')
            self._playback_delay_timer = self.root.after(3000, self._play_next_after_delay)

    def _play_next_after_delay(self):
        """延迟后播放下一曲"""
        self.is_paused_for_delay = False
        self.current_index += 1
        if self.current_index >= len(self.current_playlist):
            if self.mode_var.get() == "loop_all":
                self.current_index = 0
            else:
                self.stop()
                return
        self.play_current_track()

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
            # 获取当前播放位置（秒）
            current_pos = self.get_accurate_position()  # 返回秒
            self._playback['speed'] = float(speed)

            # 重新加载并调整播放位置
            if self.is_playing and self.current_playlist:
                current_file = self.current_playlist[self.current_index]
                pygame.mixer.music.load(current_file)
                pygame.mixer.music.play(start=current_pos)  # current_pos 单位是秒
                self.current_position = current_pos  # 更新当前进度（秒）
                logging.info(f"设置播放速度: {speed}，当前进度: {self.format_time(current_pos)}")

                # 更新字幕（将秒转换为毫秒）
                if self.subtitles:
                    current_pos_ms = current_pos * 1000  # 转换为毫秒
                    subtitle = self._find_subtitle_optimized(current_pos_ms)
                    if subtitle:
                        self._update_subtitle_display(subtitle)

                # 更新进度条和时间显示
                total_length = self.get_current_audio_length()
                if total_length > 0:
                    progress = (current_pos / total_length) * 100
                    self.progress_scale.set(progress)
                self.time_label.config(text=f"{self.format_time(current_pos)} / {self.format_time(total_length)}")

                # 启动进度更新
                if not self.is_seeking:
                    self.update_timer = self.root.after(500, self.update_progress)

        except Exception as e:
            logging.error(f"设置播放速度失败: {e}")
            self.update_status(f"设置播放速度失败: {str(e)}", 'error')

    def get_accurate_position(self):
        """改进的精确播放位置获取功能"""
        try:
            # 如果未在播放，返回当前进度（秒）
            if not self.is_playing:
                last_position = self.current_position  # 单位：秒
                logging.info(f"未播放，返回当前进度: {self.format_time(last_position)}")
                return last_position

            # 获取当前播放位置（毫秒）
            pos_ms = pygame.mixer.music.get_pos()
            if pos_ms < 0:
                last_position = self.current_position  # 单位：秒
                logging.info(f"播放位置无效，返回当前进度: {self.format_time(last_position)}")
                return last_position

            # 将播放位置（毫秒）转换为秒
            current_pos = pos_ms / 1000.0  # 单位：秒
            adjusted_pos = current_pos * self._playback['speed']  # 调整速度
            self.current_position = adjusted_pos  # 更新当前进度（秒）
            logging.info(f"获取播放位置: {self.format_time(adjusted_pos)}")
            return adjusted_pos

        except Exception as e:
            logging.error(f"获取播放位置失败: {e}")
            last_position = self.current_position  # 单位：秒
            logging.info(f"获取失败，返回当前进度: {self.format_time(last_position)}")
            return last_position

    def check_playback_status(self):
        """改进的播放状态检查，降低检查频率"""
        try:
            if self.is_playing and not self.is_paused_for_delay:
                is_busy = pygame.mixer.music.get_busy()

                if not is_busy:
                    # 增加额外的延迟检查以确保真正播放结束
                    time.sleep(0.2)  # 增加延迟时间
                    if not pygame.mixer.music.get_busy():
                        print("检测到播放结束，准备切换下一曲")  # 调试输出
                        self.handle_playback_ended()
                else:
                    # 进一步降低检查频率到2秒
                    self.root.after(2000, self.check_playback_status)

        except Exception as e:
            logging.error(f"检查播放状态失败: {e}")

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
                'last_playlist': self.current_playlist,
                'last_index': self.current_index,
                'last_position': self._playback.get('last_position', 0),
                'loop_count': self.loop_count.get(),
                'play_mode': self.mode_var.get(),
                'favorites': list(self.favorites),
                'no_record_mode': self.no_record_mode,  # 保存不录音模式状态
                'no_playback_mode': self.no_playback_mode,  # 保存不播放模式状态
                'stats': {
                    'total_play_time': self.stats['total_play_time'],
                    'played_files': list(self.stats['played_files']),
                    'last_played': self.stats['last_played']
                }
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

                    # 恢复上次播放列表和索引
                    last_playlist = state.get('last_playlist', [])
                    last_index = state.get('last_index', 0)
                    if last_playlist and 0 <= last_index < len(last_playlist):
                        self.current_playlist = last_playlist
                        self.current_index = last_index

                    # 恢复模式状态
                    self.no_record_mode = state.get('no_record_mode', False)
                    self.no_playback_mode = state.get('no_playback_mode', False)

                    # 如果有对应的UI组件，更新其状态
                    if hasattr(self, 'no_record_var'):
                        self.no_record_var.set(self.no_record_mode)
                    if hasattr(self, 'no_playback_var'):
                        self.no_playback_var.set(self.no_playback_mode)

                    return True
        except Exception as e:
            self.update_status(f"加载状态失败: {str(e)}", 'error')
        return False

    def on_closing(self):
        """改进的关闭处理,确保清理临时文件"""
        try:
            # 停止所有播放
            if hasattr(self, 'is_playing') and self.is_playing:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()

            # 取消所有定时器
            if self.update_timer:
                self.root.after_cancel(self.update_timer)
            if self._status_timer:
                self.root.after_cancel(self._status_timer)
            if self._auto_save_timer:
                self.root.after_cancel(self._auto_save_timer)
            if self._playback_delay_timer:
                self.root.after_cancel(self._playback_delay_timer)

            # 清理临时文件
            if hasattr(self, 'follow_reader'):
                self.follow_reader.cleanup_temp_files()

            # 保存最终状态
            self.save_player_state()
            self.save_settings()

            # 记录关闭事件
            logging.info("播放器正常关闭")

        except Exception as e:
            logging.error(f"关闭时发生错误: {e}")
        finally:
            pygame.mixer.quit()
            self.root.destroy()

    def start(self):
        """启动播放器"""
        # 恢复文件夹树形结构
        # self.restore_folder_tree() #  移动到 load_settings 之后
        # 开始主循环
        self.root.mainloop()

    def restore_folder_tree(self):
        try:
            # # 清空现有树
            # for item in self.folder_tree.get_children():
            #     self.folder_tree.delete(item)
            #
            # # 重新创建树节点，更新每个文件夹的 node_id
            # for folder_key, folder_info in self.folders.items():
            #     folder_path = folder_info['path']
            #     folder_name = os.path.basename(folder_path)
            #     tree_id = self.folder_tree.insert("", "end",
            #                                       text=folder_name,
            #                                       values=(f"{len(folder_info['files'])}个文件",))
            #     folder_info['node_id'] = tree_id
            #
            #     # 如果之前是展开状态，则重新展开
            #     if folder_info.get('expanded', False):
            #         self.expand_folder(tree_id)

            self.update_status("文件夹结构已恢复", 'info')
        except Exception as e:
            self.update_status(f"恢复文件夹结构失败: {str(e)}", 'error')

    def setup_logging(self):
        """修复日志系统设置"""
        try:
            # 设置日志文件路径
            log_file = os.path.join(self.logs_dir, f'player_{time.strftime("%Y%m%d")}.log')

            # 修正日志格式
            logging.basicConfig(
                filename=log_file,
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',  # 修改 levellevel 为 levelname
                datefmt='%Y-%m-%d %H:%M:%S'
            )

            # 添加控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.WARNING)
            formatter = logging.Formatter('%(levelname)s: %(message)s')  # 修改此处的格式
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

    def toggle_follow_reading(self):
        """改进的跟读切换功能"""
        try:
            if not self.is_following:
                self.is_following = True
                self.follow_button.config(text="停止跟读")
                self.start_follow_reading()  # 调用跟读开始处理
                self.update_status("跟读模式已开启", 'info')
            else:
                self.stop_follow_reading()
        except Exception as e:
            self.update_status(f"切换跟读失败: {str(e)}", 'error')

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
            if self.current_segment == 1:
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

        """恢复普通播放模式"""
        try:
            if not self.is_following and self.current_playlist:
                self.play_current_track()
        except Exception as e:
            logging.error(f"恢复普通播放失败: {e}")

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

            if (has_subtitles and self.subtitles):
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

    def pause_for_follow(self):
        """改进的跟读暂停功能"""
        if self.is_following:
            try:
                # 暂停播放并停止进度更新
                pygame.mixer.music.pause()
                self.is_playing = False
                self.is_playing_or_recording = False
                self.has_moved = False
                if hasattr(self, 'update_timer') and self.update_timer:
                    self.root.after_cancel(self.update_timer)
                    self.update_timer = None
                self.update_status("已暂停，准备跟读", 'info')
                self.play_button.config(text="播放")

                current_subtitle = self.subtitles[self.current_segment]
                reference_text = current_subtitle.get('en_text', '')

                # # 显示原文（确保字幕显示）
                # self.follow_text.delete('1.0', 'end')
                # self.follow_text.insert('end', "\n=== 原文 ===\n", 'title')
                # self.follow_text.insert('end', f"{reference_text}\n", 'en')
                # self.follow_text.see('end')

                # 禁用导航按钮，准备录音
                self.toggle_navigation_buttons(False)

                # 检查“不录音模式”和“不播放录音模式”
                if hasattr(self, 'no_recording_mode') and self.no_recording_mode:
                    # 不录音模式：跳过录音，直接继续播放
                    self.follow_text.insert('end', "\n不录音模式，跳过录音...\n", 'prompt')
                    self.follow_text.see('end')
                    self.toggle_navigation_buttons(True)
                    self.continue_after_playback()
                    return
                else:
                    # 正常录音模式
                    self.follow_text.insert('end', "\n请开始跟读...\n", 'prompt')
                    self.follow_text.see('end')
                    self.follow_reader.start_recording()

                    # 计算等待时间：原文持续时间的1倍，但不少于3秒
                    wait_time = max(
                        3000,
                        min(8000, int((current_subtitle['end_time'] - current_subtitle['start_time']) * 1.0))
                    )

                    self.root.after(wait_time, lambda: self.check_follow_status(wait_time))

            except Exception as e:
                logging.error(f"准备跟读失败: {e}")
                self.toggle_navigation_buttons(True)
                self.continue_after_playback()

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

    def play_selected_folder(self):
        """改进的播放选中文件夹功能"""
        try:
            selection = self.folder_tree.selection()
            if not selection:
                self.update_status("请先选择一个文件夹", 'warning')
                return

            folder_id = selection[0]

            # 检查是否需要清理
            if (folder_id not in self.folders) and messagebox.askyesno("无效文件夹", "检测到文件夹引用错误，需要清理后重新添加，是否现在清理？"):
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

                # 取消进度更新定时器
                if hasattr(self, 'update_timer') and self.update_timer:
                    self.root.after_cancel(self.update_timer)
                    self.update_timer = None
            else:
                if not pygame.mixer.music.get_busy():  # 检查是否有音频在播放
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
                if not self.is_seeking:
                    self.update_progress()
        except Exception as e:
            self.update_status(f"播放/暂停失败: {str(e)}", 'error')

    def _load_and_play_track(self, index):
        """统一的曲目加载和播放处理"""
        try:
            self.current_index = index
            self.current_segment = 0
            self.current_loop = 0

            # 加载字幕
            current_file = self.current_playlist[index]
            self.load_subtitles(current_file)

            # 更新显示
            self._update_tree_selection()

            # 开始播放
            if self.is_following:
                self.play_segment()
            else:
                self.play_current_track()

        except Exception as e:
            self.update_status(f"加载曲目失败: {str(e)}", 'error')

    def previous_track(self):
        """改进的上一曲功能"""
        if not self.current_playlist:
            return

        new_index = (self.current_index - 1) % len(self.current_playlist)
        self._load_and_play_track(new_index)

    def next_track(self):
        """改进的下一曲功能"""
        if not self.current_playlist:
            return

        new_index = (self.current_index + 1) % len(self.current_playlist)
        self._load_and_play_track(new_index)

    @safe_call
    def stop(self):
        """停止播放并重置状态"""
        try:
            pygame.mixer.music.stop()
            self.is_playing = False
            self.is_paused_for_delay = False  # 重置暂停延迟状态
            self.is_playing_or_recording = False
            self.has_moved = False

            # 清理所有定时器
            for timer_attr in ['update_timer', '_playback_delay_timer']:
                if hasattr(self, timer_attr):
                    timer = getattr(self, timer_attr)
                    if timer:
                        self.root.after_cancel(timer)
                        setattr(self, timer_attr, None)

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
        if not hasattr(self, 'current_playlist') or not self.current_playlist:
            return

        try:
            # 如果不是正在拖动，直接返回
            if not self.is_seeking:
                return

            # 取消现有的进度更新定时器
            if hasattr(self, 'update_timer') and self.update_timer:
                self.root.after_cancel(self.update_timer)
                self.update_timer = None

            total_length = self.get_current_audio_length()
            seek_pos = (float(value) / 100.0) * total_length  # seek_pos 单位是秒

            # 重新加载并播放到指定位置
            current_file = self.current_playlist[self.current_index]
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play(start=seek_pos)

            # 更新当前进度（秒）
            self.current_position = seek_pos
            self.last_seek_position = seek_pos  # 记录跳转后的起始位置

            # 立即更新字幕（将秒转换为毫秒）
            if self.subtitles:
                current_pos_ms = seek_pos * 1000  # 转换为毫秒
                subtitle = self._find_subtitle_optimized(current_pos_ms)
                if subtitle:
                    self._update_subtitle_display(subtitle)

            # 更新时间显示
            current_time = self.format_time(seek_pos)
            total_time = self.format_time(total_length)
            self.time_label.config(text=f"{current_time} / {total_time}")

            # 更新进度条
            self.progress_scale.set(value)

            # 更新状态
            self.update_status(f"跳转到: {current_time}", 'info')
            logging.info(f"拖动进度条到: {seek_pos} 秒，字幕时间: {current_pos_ms} 毫秒")

        except Exception as e:
            self.update_status(f"定位失败: {str(e)}", 'error')
            logging.error(f"定位失败: {e}")
        finally:
            # 清除 seeking 标志并延迟恢复进度更新
            self.is_seeking = False
            self.root.after(1000, self._resume_progress_update)

    # 未记录跳转后的起始位置，导致 update_progress 覆盖新位置。
    def seek_relative(self, seconds):
        """相对定位（快进/快退）"""
        if not self.is_playing or not self.current_playlist:
            return

        try:
            # 设置 seeking 标志
            self.is_seeking = True

            # 取消现有的进度更新定时器
            if hasattr(self, 'update_timer') and self.update_timer:
                self.root.after_cancel(self.update_timer)
                self.update_timer = None

            if self.is_following:
                # 跟读模式：按段落跳转
                if seconds > 0:  # 快进
                    if self.current_segment < len(self.subtitles) - 1:
                        self.current_segment += 1
                    else:
                        logging.info("已经是最后一段")
                        return
                else:  # 快退
                    if self.current_segment > 0:
                        self.current_segment -= 1
                    else:
                        logging.info("已经是第一段")
                        return

                subtitle = self.subtitles[self.current_segment]
                new_pos = float(subtitle['start_time']) / 1000.0  # 转换为秒
            else:
                # 普通模式：按时间跳转
                new_pos = max(0, self.current_position + seconds)
                total_length = self.get_current_audio_length()
                new_pos = min(new_pos, total_length)  # 确保不超过总长度

            # 重新加载并播放
            current_file = self.current_playlist[self.current_index]
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play(start=new_pos)

            # 更新当前进度（秒）
            self.current_position = new_pos
            self.last_seek_position = new_pos  # 记录跳转后的起始位置

            # 立即更新字幕（将秒转换为毫秒）
            if self.subtitles:
                current_pos_ms = new_pos * 1000  # 转换为毫秒
                subtitle = self._find_subtitle_optimized(current_pos_ms)
                if subtitle:
                    self._update_subtitle_display(subtitle)

            # 更新显示
            total_length = self.get_current_audio_length()
            if total_length > 0:
                progress = (new_pos / total_length) * 100
                self.progress_scale.set(progress)
            self.time_label.config(text=f"{self.format_time(new_pos)} / {self.format_time(total_length)}")

            # 更新状态
            self.update_status(f"快进/快退到: {self.format_time(new_pos)}", 'info')
            logging.info(f"快进/快退到: {new_pos} 秒，字幕时间: {current_pos_ms} 毫秒")

        except Exception as e:
            self.update_status(f"快进快退失败: {str(e)}", 'error')
            logging.error(f"快进快退失败: {e}")
        finally:
            self.is_seeking = False
            self.root.after(1000, self._resume_progress_update)

    def _resume_progress_update(self):
        """恢复进度更新"""
        if self.is_playing and not self.is_seeking:
            self.update_progress()

    def _update_tree_selection(self):
        """改进的树形视图选中更新"""
        try:
            if not self.current_playlist or self.current_index >= len(self.current_playlist):
                return

            current_file = self.current_playlist[self.current_index]

            # 清除现有选择
            self.folder_tree.selection_remove(*self.folder_tree.selection())

            # 查找并选中当前文件
            for folder_id in self.folders:
                for child in self.folder_tree.get_children(folder_id):
                    if os.path.basename(current_file) == self.folder_tree.item(child)['text']:
                        self.folder_tree.selection_set(child)
                        self.folder_tree.see(child)
                        break
        except Exception as e:
            logging.error(f"更新树形选择失败: {e}")

    def play_current_track(self):
        """播放当前曲目"""
        try:
            current_file = self.current_playlist[self.current_index]
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play(start=self.current_position)
            self.is_playing = True
            logging.info(f"从 {self.format_time(self.current_position)} 开始播放")

            # 加载字幕
            self.load_subtitles(current_file)

            # 启动字幕更新（将秒转换为毫秒）
            if self.subtitles:
                current_pos_ms = self.current_position * 1000  # 转换为毫秒
                subtitle = self._find_subtitle_optimized(current_pos_ms)
                if subtitle:
                    self._update_subtitle_display(subtitle)

            self.update_info_label()
            self._update_tree_selection()
            logging.info("界面已更新")

            for timer in ['update_timer', '_check_timer', '_playback_delay_timer']:
                if hasattr(self, timer) and getattr(self, timer):
                    self.root.after_cancel(getattr(self, timer))
                    setattr(self, timer, None)
            logging.info("旧定时器已清理")

            total_length = self.get_current_audio_length()
            if total_length > 0:
                progress = (self.current_position / total_length) * 100
                self.progress_scale.set(progress)
            self.time_label.config(text=f"{self.format_time(self.current_position)} / {self.format_time(total_length)}")

            if not self.is_seeking:
                self.update_timer = self.root.after(500, self.update_progress)
            self.root.after(1000, lambda: self._start_playback_check())
            logging.info(f"播放开始，当前进度: {self.current_position} 秒")

        except Exception as e:
            self.update_status(f"播放失败: {str(e)}", 'error')

    def update_progress(self):
        """更新进度条和时间显示"""
        if not self.is_playing or self.is_seeking:
            return

        try:
            pos = pygame.mixer.music.get_pos()
            if pos > 0:
                relative_time = pos / 1000.0
                if hasattr(self, 'last_seek_position'):
                    self.current_position = self.last_seek_position + relative_time
                    delattr(self, 'last_seek_position')
                else:
                    if hasattr(self, 'last_update_time') and hasattr(self, 'last_position'):
                        time_diff = (time.time() - self.last_update_time)
                        self.current_position = self.last_position + time_diff
                    else:
                        self.current_position = relative_time

                self.last_position = self.current_position
                self.last_update_time = time.time()
            elif pos == -1:
                self.handle_playback_ended()
                return

            total_length = self.get_current_audio_length()
            if total_length > 0:
                progress = min(100, (self.current_position / total_length) * 100)
                if abs(progress - self.progress_scale.get()) > 0.5:
                    self.progress_scale.set(progress)

            self.time_label.config(text=f"{self.format_time(self.current_position)} / {self.format_time(total_length)}")

            # 更新字幕（普通模式和跟读模式）
            if self.subtitles:
                current_pos_ms = self.current_position * 1000
                subtitle = self._find_subtitle_optimized(current_pos_ms)
                if subtitle:
                    self._update_subtitle_display(subtitle)

            if self.is_playing and not self.is_seeking:
                self.update_timer = self.root.after(500, self.update_progress)
            logging.info(f"更新进度，当前进度: {self.current_position} 秒，pygame.get_pos: {pos} 毫秒")

        except Exception as e:
            logging.error(f"更新进度出错: {e}")
            if self.is_playing and not self.is_seeking:
                self.update_timer = self.root.after(500, self.update_progress)

    def _start_playback_check(self):
        """延迟启动播放状态检查"""
        if self.is_playing:
            self._check_timer = self.root.after(2000, self.check_playback_status)

    def on_progress_press(self, event):
        """进度条按下事件"""
        self.is_seeking = True
        # 取消进度更新定时器
        if hasattr(self, 'update_timer') and self.update_timer:
            self.root.after_cancel(self.update_timer)
            self.update_timer = None

    def on_progress_release(self, event):
        """进度条释放事件"""
        try:
            if self.current_playlist and self.is_playing:
                # 获取当前进度条位置
                pos = self.progress_scale.get()

                if self.is_following:
                    # 跟读模式：按段落跳转
                    total_length = self.get_current_audio_length()
                    seek_pos = (pos / 100.0) * total_length  # seek_pos 单位是秒
                    current_pos_ms = seek_pos * 1000  # 转换为毫秒
                    subtitle = self._find_subtitle_optimized(current_pos_ms)
                    if subtitle:
                        self.current_segment = self.subtitles.index(subtitle)
                        start_time = float(subtitle['start_time']) / 1000.0  # 转换为秒
                        self.seek_absolute((start_time / total_length) * 100)  # 跳转到段落开始
                    else:
                        logging.warning("未找到对应段落，保持当前进度")
                else:
                    # 普通模式：直接跳转
                    self.seek_absolute(pos)
        except Exception as e:
            self.update_status(f"进度调整失败: {str(e)}", 'error')
            logging.error(f"进度调整失败: {e}")
        finally:
            self.is_seeking = False
            self.root.after(1000, self._resume_progress_update)

    def edit_current_subtitles(self):
        """改进的字幕编辑功能"""
        try:
            if not self.current_playlist or self.current_index >= len(self.current_playlist):
                self.update_status("无可编辑的字幕文件", 'warning')
                return

            current_file = self.current_playlist[self.current_index]
            srt_path = os.path.splitext(current_file)[0] + '.srt'

            if not os.path.exists(srt_path):
                self.update_status("未找到字幕文件", 'warning')
                return

            # 检查文件权限
            if not os.access(srt_path, os.W_OK):
                self.update_status("没有字幕文件的写入权限", 'error')
                return

            # 暂停播放
            was_playing = self.is_playing
            if was_playing:
                self.play_pause()

            # 创建编辑窗口
            edit_window = tk.Toplevel(self.root)
            edit_window.title("字幕编辑")
            edit_window.geometry("800x600")

            # 创建文本编辑区
            edit_text = tk.Text(edit_window, wrap=tk.WORD)
            edit_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            # 加载字幕内容
            try:
                with open(srt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    edit_text.insert('1.0', content)
            except Exception as e:
                self.update_status(f"读取字幕文件失败: {str(e)}", 'error')
                edit_window.destroy()
                return

            def save_subtitles():
                try:
                    content = edit_text.get('1.0', tk.END)

                    # 创建备份文件
                    backup_path = srt_path + '.bak'
                    try:
                        import shutil
                        shutil.copy2(srt_path, backup_path)
                    except Exception as e:
                        logging.warning(f"创建备份文件失败: {e}")

                    # 保存新内容
                    with open(srt_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    self.update_status("字幕保存成功", 'success')

                    # 重新加载字幕
                    self.load_subtitles(current_file)

                    edit_window.destroy()

                except PermissionError:
                    self.update_status("保存失败：没有写入权限", 'error')
                except Exception as e:
                    self.update_status(f"保存字幕文件失败: {str(e)}", 'error')

            # 添加保存按钮
            btn_frame = ttk.Frame(edit_window)
            btn_frame.pack(fill='x', pady=5)

            ttk.Button(btn_frame, text="保存", command=save_subtitles).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="取消",
                       command=edit_window.destroy).pack(side='left', padx=5)

        except Exception as e:
            self.update_status(f"打开字幕编辑器失败: {str(e)}", 'error')

    def save_subtitles_to_file(self, srt_path, subtitles):
        """保存字幕到文件"""
        try:
            # 检查文件权限
            if not os.access(os.path.dirname(srt_path), os.W_OK):
                messagebox.showerror("错误", "没有写入权限，请检查文件权限设置")
                return False

            with open(srt_path, 'w', encoding='utf-8') as f:
                for i, sub in enumerate(subtitles, 1):
                    f.write(f"{i}\n")
                    f.write(f"{sub['time_str']}\n")
                    f.write(f"{sub['en_text']}\n")
                    if sub.get('cn_text'):
                        f.write(f"{sub['cn_text']}\n")
                    f.write("\n")

            return True
        except Exception as e:
            messagebox.showerror("保存失败", f"保存字幕文件失败: {str(e)}")
            return False

    def pause_follow_reading(self):
        """暂停跟读"""
        if self.is_following:
            self.follow_reader.stop_recording()
            self.is_following = False
            self.follow_button.config(text="继续跟读")

    def resume_follow_reading(self):
        """继续跟读"""
        if not self.is_following:
            self.is_following = True
            self.follow_button.config(text="停止跟读")
            self.follow_reader.start_recording()

    def skip_current_segment(self):
        """跳过当前段落"""
        if self.is_following:
            self.follow_reader.stop_recording()
            self.next_segment()

    def create_follow_control_buttons(self):
        """创建跟读控制按钮"""
        follow_control_frame = ttk.Frame(self.follow_frame)
        follow_control_frame.pack(fill="x", pady=5)

        # 创建自定义按钮样式
        style = ttk.Style()
        # 正常状态为橙色
        style.configure('NavButton.TButton',
                        background='#FFA500',  # 橙色
                        foreground='black',
                        borderwidth=1,
                        relief='raised')
        # 禁用状态为灰色
        style.map('NavButton.TButton',
                  background=[('disabled', '#E0E0E0')],
                  foreground=[('disabled', '#A0A0A0')])

        # 不录音模式
        self.no_record_var = tk.BooleanVar(value=self.no_record_mode)
        self.no_record_btn = ttk.Checkbutton(
            follow_control_frame,
            text="不录音模式",
            variable=self.no_record_var,
            command=self.toggle_recording_mode
        )
        self.no_record_btn.pack(side="left", padx=5)

        # 关闭跟读播放
        self.no_playback_var = tk.BooleanVar(value=self.no_playback_mode)
        self.no_playback_btn = ttk.Checkbutton(
            follow_control_frame,
            text="关闭跟读播放",
            variable=self.no_playback_var,
            command=self.toggle_playback_mode
        )
        self.no_playback_btn.pack(side="left", padx=5)

        # 导航按钮
        self.prev_segment_btn = ttk.Button(follow_control_frame, text="上一句", width=5,
                                           command=self.previous_segment, style='NavButton.TButton')
        self.prev_segment_btn.pack(side="left", padx=5)

        self.next_segment_btn = ttk.Button(follow_control_frame, text="下一句", width=5,
                                           command=self.next_segment, style='NavButton.TButton')
        self.next_segment_btn.pack(side="left", padx=5)

        self.repeat_segment_btn = ttk.Button(follow_control_frame, text="重复本句", width=8,
                                             command=self.repeat_current_segment, style='NavButton.TButton')
        self.repeat_segment_btn.pack(side="left", padx=5)

    def toggle_navigation_buttons(self, enable=True):
        """启用或禁用导航按钮"""
        state = "normal" if enable else "disabled"
        for btn in [self.prev_segment_btn, self.next_segment_btn, self.repeat_segment_btn]:
            btn.config(state=state)

    def toggle_recording_mode(self):
        """切换录音模式，并处理互斥逻辑"""
        self.no_record_mode = self.no_record_var.get()
        if self.no_record_mode:
            # 如果启用不录音模式，自动禁用不播放模式
            self.no_playback_var.set(False)
            self.no_playback_mode = False
            self.update_status("启用不录音模式，已自动禁用不播放模式", 'info')
        else:
            self.update_status("禁用不录音模式", 'info')

    def toggle_playback_mode(self):
        """切换跟读播放模式，并处理互斥逻辑"""
        self.no_playback_mode = self.no_playback_var.get()
        if self.no_playback_mode:
            # 如果启用不播放模式，自动禁用不录音模式
            self.no_record_var.set(False)
            self.no_record_mode = False
            self.update_status("启用不播放模式，已自动禁用不录音模式", 'info')
        else:
            self.update_status("禁用不播放模式", 'info')

    def _cleanup_audio_resources(self):
        """改进的音频资源清理功能"""
        try:
            # 设置停止标志
            self.follow_reader._stop_recognition = True

            # 先取消所有定时器
            for timer_attr in ['_follow_pause_timer', '_check_timer', '_recognition_timer']:
                if hasattr(self, timer_attr):
                    timer = getattr(self, timer_attr)
                    if timer:
                        self.root.after_cancel(timer)
                        setattr(self, timer_attr, None)

            # 停止播放
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()

            # 停止录音和语音识别
            if hasattr(self, 'follow_reader'):
                if self.follow_reader.is_recording:
                    print('准备停止之前的录音')
                    self.follow_reader.stop_recording()
                    time.sleep(0.2)
                # 停止正在进行的语音识别
                # 等待识别线程短暂时间
                if self._recognition_thread and self._recognition_thread.is_alive():
                    print('等待语音识别线程结束')
                    self._recognition_thread.join(timeout=1)  # 等待 1 秒
                    if self._recognition_thread.is_alive():
                        logging.warning("语音识别线程未能在超时时间内停止")
                self._recognition_thread = None

                # 删除资源文件
                for file_attr in ['playback_file', 'transcribe_file']:
                    if hasattr(self.follow_reader, file_attr):
                        file_path = getattr(self.follow_reader, file_attr)
                        if file_path and os.path.exists(file_path):
                            try:
                                # 尝试以独占模式打开文件，检查是否被占用
                                with open(file_path, 'a'):
                                    pass
                                os.remove(file_path)
                                logging.info(f"已删除音频文件: {file_path}")
                            except (IOError, OSError) as e:
                                logging.error(f"删除音频文件失败，可能被占用: {e}")

            # 重置播放状态
            self.is_playing = False
            self.is_playing_or_recording = False
            self.has_moved = False
            self._start_time = 0
            self._retry_count = 0
            if hasattr(self, '_segment_playing'):
                self._segment_playing = False

            # 等待资源释放
            time.sleep(0.1)  # 短暂等待确保资源完全释放

        except Exception as e:
            logging.error(f"清理音频资源失败: {e}")

    def load_audio_with_check(self, audio_file):
        """加载音频并检查是否成功"""
        try:
            start_load = time.time()
            pygame.mixer.music.load(audio_file)
            time.sleep(0.5)  # 等待加载完成
            logging.info(f"音频加载耗时: {time.time() - start_load:.2f}秒")
            return True
        except Exception as e:
            logging.error(f"加载音频失败: {e}")
            return False

    def _process_switch_queue(self):
        """处理切换队列中的操作"""
        if self._segment_switch_lock:
            # 如果锁未释放，等待锁释放后处理
            self.root.after(50, self._process_switch_queue)
            return

        if not self._segment_switch_queue:
            return

        # 清理队列，始终记录最新的操作
        last_operation = None
        last_segment_index = None
        while self._segment_switch_queue:
            operation, segment_index = self._segment_switch_queue.popleft()
            # 如果正在播放/录音，且已经移动过，则忽略 'previous' 和 'next' 操作
            if self.is_playing_or_recording and self.has_moved and operation in ['previous', 'next']:
                continue
            last_operation = operation
            last_segment_index = segment_index

        if last_operation == 'previous':
            self.previous_segment()
        elif last_operation == 'next':
            self.next_segment()
        elif last_operation == 'repeat':
            self.repeat_current_segment()
        elif last_operation == 'play':
            self.current_segment = last_segment_index
            self.play_segment()

    def play_segment(self):
        """改进的段落播放功能"""
        if not self.current_playlist:
            logging.error("播放列表为空")
            self.update_status("没有可播放的文件", 'error')
            self.stop_follow_reading()
            return

        if not self.subtitles:
            logging.warning("字幕数据为空，尝试重新加载")
            self._load_track_subtitles()
            if not self.subtitles:
                self.update_status("无法加载字幕", 'error')
                self.stop_follow_reading()
                return

        if self.current_segment >= len(self.subtitles):
            logging.error(f"段落索引越界: {self.current_segment} >= {len(self.subtitles)}")
            self.update_status("段落索引无效", 'error')
            self.stop_follow_reading()
            return

        try:
            start_cleanup = time.time()
            self._cleanup_audio_resources()
            time.sleep(0.5)
            logging.info(f"资源清理耗时: {time.time() - start_cleanup:.2f}秒")

            time.sleep(0.1)
            current_file = self.current_playlist[self.current_index]
            subtitle = self.subtitles[self.current_segment]

            logging.info(
                f"播放段落 - 文件: {os.path.basename(current_file)}, 段落: {self.current_segment + 1}/{len(self.subtitles)}")

            # 更新字幕显示（确保普通模式和跟读模式都显示）
            self.show_current_subtitle(subtitle)
            self.root.update()

            start_time = float(subtitle['start_time']) / 1000.0
            end_time = float(subtitle['end_time']) / 1000.0
            duration = end_time - start_time
            if duration < 1.0:
                duration = 1.0
                end_time = start_time + duration

            logging.info(f"播放段落 - 起止时间: {start_time}s -> {end_time}s")

            self.current_position = start_time
            logging.info(f"设置当前进度: {self.format_time(self.current_position)}")
            self._update_tree_selection()

            total_length = self.get_current_audio_length()
            logging.info(f"音频总长度: {self.format_time(total_length)}")
            progress = (start_time / total_length * 100) if total_length > 0 else 0
            self.progress_scale.set(progress)
            self.time_label.config(text=f"{self.format_time(start_time)} / {self.format_time(total_length)}")

            should_play_audio = True
            if should_play_audio:
                start_load = time.time()
                if not self.load_audio_with_check(current_file):
                    logging.error("音频加载失败")
                    self.update_status("加载音频失败", 'error')
                    self.is_playing = False
                    self.is_playing_or_recording = False
                    return
                logging.info(f"音频加载耗时: {time.time() - start_load:.2f}秒")

                pygame.mixer.music.set_volume(self._volume / 100.0)
                self._playback['speed'] = float(self.speed_scale.get())
                start_play = time.time()
                pygame.mixer.music.play(start=start_time)
                self.is_playing = True
                self.is_playing_or_recording = True
                self.has_moved = False
                logging.info(f"音频播放开始耗时: {time.time() - start_play:.2f}秒")

            if self.is_following:
                pause_time = int(duration * 1000)
                logging.info(f"设置音频播放时间: {pause_time}ms")
                if pause_time > 0 and self.is_following:
                    if hasattr(self, '_follow_pause_timer') and self._follow_pause_timer:
                        self.root.after_cancel(self._follow_pause_timer)
                    self._follow_pause_timer = self.root.after(pause_time, self.pause_for_follow)

            # 启动进度更新（仅在播放时）
            if self.is_playing and should_play_audio and not self.is_seeking:
                self.update_timer = self.root.after(500, self.update_progress)

            logging.info(f"段落播放开始 - 时间: {self.format_time(start_time)} -> {self.format_time(end_time)}")
            self.update_status(f"正在播放第 {self.current_segment + 1} 句", 'info')

        except Exception as e:
            logging.error(f"播放段落失败: {e}")
            self.update_status(f"播放段落失败: {str(e)}", 'error')
            self.is_playing = False
            self.is_playing_or_recording = False
            if hasattr(self, '_follow_pause_timer') and self._follow_pause_timer:
                self.root.after_cancel(self._follow_pause_timer)
        finally:
            # 在暂停或异常时，停止进度更新
            if not self.is_playing and hasattr(self, 'update_timer') and self.update_timer:
                self.root.after_cancel(self.update_timer)
                self.update_timer = None

    def previous_segment(self):
        """改进的播放上一句功能"""
        try:
            if hasattr(self, '_last_switch_time'):
                if time.time() - self._last_switch_time < 0.5:
                    return
            self._last_switch_time = time.time()

            if self.is_playing_or_recording and self.has_moved:
                self.update_status("当前状态下只能切换一次，请等待播放/录音结束", 'info')
                return

            if self._segment_switch_lock:
                self.update_status("正在处理切换，请稍候...", "info")
                return

            self._segment_switch_lock = True

            if not self.subtitles:
                self.update_status("没有字幕数据", 'warning')
                return

            if self.current_segment > 0:
                self._cleanup_audio_resources()
                self.current_segment -= 1
                self.follow_text.delete('1.0', 'end')
                self.follow_text.insert('end', f"准备播放第 {self.current_segment + 1}/{len(self.subtitles)} 段\n", 'prompt')
                self.follow_text.insert('end', "正在加载...\n", 'info')
                self.follow_text.see('end')
                self.root.update()
                self.update_status(f"切换到第{self.current_segment + 1}句", 'info')
                new_subtitle = self.subtitles[self.current_segment]
                new_pos = float(new_subtitle['start_time']) / 1000.0  # 转换为秒
                self.current_position = new_pos  # 修正单位为秒
                self.last_seek_position = new_pos  # 记录跳转位置
                self._target_segment = self.current_segment

                # 更新字幕显示
                self._update_subtitle_display(new_subtitle)

                # 更新进度条和时间显示
                total_length = self.get_current_audio_length()
                if total_length > 0:
                    progress = (new_pos / total_length) * 100
                    self.progress_scale.set(progress)
                self.time_label.config(text=f"{self.format_time(new_pos)} / {self.format_time(total_length)}")

                self._segment_switch_queue.clear()
                self._segment_switch_queue.append(('play', self._target_segment))
                self._process_switch_queue()

                if self.is_playing_or_recording:
                    self.has_moved = True
            else:
                self.update_status("已经是第一段", 'info')
                self._process_switch_queue()

        except Exception as e:
            logging.error(f"播放上一句失败: {e}")
            self.update_status("播放上一句失败", 'error')
        finally:
            self._segment_switch_lock = False

    def next_segment(self):
        """改进的播放下一句功能"""
        try:
            if hasattr(self, '_last_switch_time'):
                if time.time() - self._last_switch_time < 0.5:
                    return
            self._last_switch_time = time.time()

            if self.is_playing_or_recording and self.has_moved:
                self.update_status("当前状态下只能切换一次，请等待播放/录音结束", 'info')
                return

            if self._segment_switch_lock:
                self.update_status("正在处理切换，请稍候...", "info")
                return

            self._segment_switch_lock = True

            if not self.subtitles:
                self.update_status("没有字幕数据", 'warning')
                return

            if self.current_segment < len(self.subtitles) - 1:
                self._cleanup_audio_resources()
                self.current_segment += 1
                self.follow_text.delete('1.0', 'end')
                self.follow_text.insert('end', f"准备播放第 {self.current_segment + 1}/{len(self.subtitles)} 段\n", 'prompt')
                self.follow_text.insert('end', "正在加载...\n", 'info')
                self.follow_text.see('end')
                self.root.update()
                self.update_status(f"切换到第{self.current_segment + 1}句", 'info')
                new_subtitle = self.subtitles[self.current_segment]
                new_pos = float(new_subtitle['start_time']) / 1000.0  # 转换为秒
                self.current_position = new_pos  # 修正单位为秒
                self.last_seek_position = new_pos  # 记录跳转位置
                self._target_segment = self.current_segment

                # 更新字幕显示
                self._update_subtitle_display(new_subtitle)

                # 更新进度条和时间显示
                total_length = self.get_current_audio_length()
                if total_length > 0:
                    progress = (new_pos / total_length) * 100
                    self.progress_scale.set(progress)
                self.time_label.config(text=f"{self.format_time(new_pos)} / {self.format_time(total_length)}")

                self._segment_switch_queue.clear()
                self._segment_switch_queue.append(('play', self._target_segment))
                self._process_switch_queue()

                if self.is_playing_or_recording:
                    self.has_moved = True
            else:
                self.update_status("已经是最后一段", 'info')
                self._process_switch_queue()

        except Exception as e:
            logging.error(f"播放下一句失败: {e}")
            self.update_status("播放下一句失败", 'error')
        finally:
            self._segment_switch_lock = False

    def repeat_current_segment(self):
        """改进的重复当前句功能"""
        try:
            if hasattr(self, '_last_switch_time'):
                if time.time() - self._last_switch_time < 0.5:
                    return
            self._last_switch_time = time.time()

            if self._segment_switch_lock:
                self.update_status("正在处理切换，请稍候...", "info")
                return

            self._segment_switch_lock = True

            if not self.subtitles:
                self.update_status("没有字幕数据", 'warning')
                return

            if 0 <= self.current_segment < len(self.subtitles):
                self._cleanup_audio_resources()
                current_subtitle = self.subtitles[self.current_segment]
                current_pos = float(current_subtitle['start_time']) / 1000.0  # 转换为秒
                self.current_position = current_pos  # 修正单位为秒
                self.last_seek_position = current_pos  # 记录跳转位置
                self._target_segment = self.current_segment

                # 更新字幕显示
                self._update_subtitle_display(current_subtitle)

                # 更新进度条和时间显示
                total_length = self.get_current_audio_length()
                if total_length > 0:
                    progress = (current_pos / total_length) * 100
                    self.progress_scale.set(progress)
                self.time_label.config(text=f"{self.format_time(current_pos)} / {self.format_time(total_length)}")

                self._segment_switch_queue.clear()
                self._segment_switch_queue.append(('play', self._target_segment))
                self._process_switch_queue()
            else:
                self.update_status("当前段落索引无效", 'error')

        except Exception as e:
            logging.error(f"重复当前句失败: {e}")
            self.update_status("重复当前句失败", 'error')
        finally:
            self._segment_switch_lock = False

    def stop_playback(self):
        """停止播放并重置状态"""
        try:
            pygame.mixer.music.stop()
            self.is_playing = False
            self.is_playing_or_recording = False
            self.has_moved = False
            self.update_status("播放已停止", 'info')
        except Exception as e:
            logging.error(f"停止播放失败: {e}")
            self.update_status("停止播放失败", 'error')

    def toggle_follow_checking(self):
        self.check_follow_enabled = not getattr(self, 'check_follow_enabled', True)
        if not self.is_following and not self.follow_text.winfo_ismapped():
            logging.info("普通模式下确保字幕组件可见")
            self.follow_text.pack()  # 或其他显示方法
        self.update_status(
            f"跟读检测已{'启用' if self.check_follow_enabled else '禁用'}",
            'info'
        )

    def _load_track_subtitles(self):
        """加载当前曲目的字幕"""
        try:
            if self.current_playlist and 0 <= self.current_index < len(self.current_playlist):
                current_file = self.current_playlist[self.current_index]
                self.subtitles = []
                self.load_subtitles(current_file)
        except Exception as e:
            logging.error(f"加载字幕失败: {e}")


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
