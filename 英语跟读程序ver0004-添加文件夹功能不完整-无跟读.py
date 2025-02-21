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


class AudioPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("音频播放器")
        self.root.geometry("1000x600")

        # 初始化pygame混音器
        pygame.mixer.init()

        # 初始化变量
        self.folders = {}  # 存储文件夹及其音频文件
        self.current_playlist = []  # 当前播放列表
        self.current_index = 0  # 当前播放索引
        self.play_mode = "sequential"  # 播放模式
        self.settings_file = "player_settings.json"
        self.is_playing = False

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

    def play_current_track(self):
        """播放当前曲目"""
        if not self.current_playlist or self.current_index >= len(self.current_playlist):
            return

        try:
            pygame.mixer.music.load(self.current_playlist[self.current_index])
            pygame.mixer.music.play()
            self.is_playing = True
            self.play_button.config(text="暂停")
            self.update_info_label()
        except Exception as e:
            messagebox.showerror("错误", f"播放失败: {str(e)}")

    def play_pause(self):
        """播放/暂停功能"""
        # 如果正在播放,则停止播放
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.play_button.config(text="播放")
            return

        # 获取当前选中项
        selection = self.folder_tree.selection()
        if selection:
            item = selection[0]
            parent = self.folder_tree.parent(item)

            # 如果是文件节点
            if parent and parent in self.folders:
                file_name = self.folder_tree.item(item)['text']
                folder_files = self.folders[parent]['files']

                # 查找对应的文件路径
                for idx, file_path in enumerate(folder_files):
                    if os.path.basename(file_path) == file_name:
                        # 更新播放列表和索引
                        self.current_playlist = folder_files
                        self.current_index = idx
                        # 开始播放
                        self.play_current_track()
                        return

        # 如果没有选中文件但存在播放列表,继续播放当前歌曲
        if self.current_playlist and not self.is_playing:
            pygame.mixer.music.unpause()
            self.is_playing = True
            self.play_button.config(text="暂停")

    def stop(self):
        """停止播放并重置状态"""
        pygame.mixer.music.stop()
        self.is_playing = False
        self.play_button.config(text="播放")
        self.info_label.config(text="未播放")

    def previous_track(self):
        """播放上一曲"""
        if not self.current_playlist:
            return
        self.current_index = (self.current_index - 1) % len(self.current_playlist)
        self.play_current_track()

    def next_track(self):
        """播放下一曲"""
        if not self.current_playlist:
            return
        self.current_index = (self.current_index + 1) % len(self.current_playlist)
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

    def check_end_of_track(self):
        """检查当前曲目是否播放完毕，处理自动播放"""
        if self.is_playing and not pygame.mixer.music.get_busy():
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

        # 定期检查
        self.root.after(1000, self.check_end_of_track)

    def on_closing(self):
        """关闭窗口时的处理"""
        self.save_settings()
        pygame.mixer.quit()
        self.root.destroy()

    def start(self):
        """启动播放器"""
        # 恢复文件夹树形结构
        self.restore_folder_tree()
        # 开始检查播放状态
        self.check_end_of_track()
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