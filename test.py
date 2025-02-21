class SubtitleGeneratorWindow:
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title("字幕生成器")
        self.window.geometry("600x400")

        # 百度翻译API配置
        self.api_frame = ttk.LabelFrame(self.window, text="百度翻译API配置 (支持 Ctrl+V 粘贴)")
        self.api_frame.pack(fill="x", padx=10, pady=5)

        # APP ID 输入框和标签
        ttk.Label(self.api_frame, text="APP ID:").grid(row=0, column=0, padx=5, pady=5)
        self.app_id_entry = ttk.Entry(self.api_frame)
        self.app_id_entry.grid(row=0, column=1, padx=5, pady=5)

        # API Key 输入框和标签
        ttk.Label(self.api_frame, text="API Key:").grid(row=1, column=0, padx=5, pady=5)
        self.api_key_entry = ttk.Entry(self.api_frame)
        self.api_key_entry.grid(row=1, column=1, padx=5, pady=5)

        # 绑定复制粘贴事件到输入框
        self.bind_copy_paste(self.app_id_entry)
        self.bind_copy_paste(self.api_key_entry)

        # ... 其他代码保持不变 ...

    def bind_copy_paste(self, entry):
        """绑定复制粘贴事件到输入框"""
        # Windows/Linux
        entry.bind('<Control-v>', lambda e: self.paste_text(e))
        entry.bind('<Control-V>', lambda e: self.paste_text(e))
        entry.bind('<Control-c>', lambda e: self.copy_text(e))
        entry.bind('<Control-C>', lambda e: self.copy_text(e))
        # Mac
        entry.bind('<Command-v>', lambda e: self.paste_text(e))
        entry.bind('<Command-V>', lambda e: self.paste_text(e))
        entry.bind('<Command-c>', lambda e: self.copy_text(e))
        entry.bind('<Command-C>', lambda e: self.copy_text(e))

    def paste_text(self, event):
        """处理粘贴事件"""
        try:
            # 获取剪贴板内容
            clipboard_text = self.window.clipboard_get()
            # 获取当前输入框
            entry = event.widget
            # 如果有选中的文本，先删除
            try:
                start = entry.selection_range()[0]
                end = entry.selection_range()[1]
                entry.delete(start, end)
            except:
                pass
            # 在光标位置插入剪贴板内容
            entry.insert('insert', clipboard_text)
            return 'break'  # 阻止默认行为
        except Exception as e:
            print(f"粘贴失败: {e}")

    def copy_text(self, event):
        """处理复制事件"""
        try:
            # 获取当前输入框
            entry = event.widget
            # 获取选中的文本
            try:
                selection = entry.selection_get()
                # 复制到剪贴板
                self.window.clipboard_clear()
                self.window.clipboard_append(selection)
            except:
                pass
            return 'break'  # 阻止默认行为
        except Exception as e:
            print(f"复制失败: {e}")