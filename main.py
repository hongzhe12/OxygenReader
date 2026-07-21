import sys
import os
import json
import ctypes
import fitz
import keyboard
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QDialog,
    QVBoxLayout,
    QPushButton,
    QFileDialog,
    QLabel,
    QLineEdit,
    QHBoxLayout,
    QMessageBox,
    QListWidget,
    QListWidgetItem,
    QColorDialog,
    QSpinBox,
    QGridLayout,
    QSystemTrayIcon,
    QMenu,
    QStyle,
    QCheckBox,
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QFont, QIcon, QKeySequence, QAction


# --- 资源路径处理 ---
def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


# --- 配置区域 ---
APP_DATA_DIR = os.path.join(os.environ["APPDATA"], "OxygenReaderData")
if not os.path.exists(APP_DATA_DIR):
    os.makedirs(APP_DATA_DIR)

HISTORY_FILE = os.path.join(APP_DATA_DIR, "bookshelf.json")
CONFIG_FILE = os.path.join(APP_DATA_DIR, "config.json")


class GlobalSignal(QObject):
    toggle_signal = Signal()
    next_signal = Signal()
    prev_signal = Signal()
    update_style_signal = Signal()


class ConfigManager:
    def __init__(self):
        self.config = {
            "window_title": "二氧化碳阅读器",
            "font_size": 24,
            "text_color": "#505050",
            "bg_color": "#00000000",
            "key_next": "down",
            "key_prev": "up",
            "key_toggle": "F3",
            "focus_anchor": True,
        }
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.config.update(saved)
            except:
                pass

    def save(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)


class BookShelf:
    def __init__(self):
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except:
                self.data = {}

    def save(self):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def update_progress(self, filepath, line_index):
        if filepath:
            self.data.pop(filepath, None)
            self.data[filepath] = line_index
            self.save()

    def get_progress(self, filepath):
        return self.data.get(filepath, 0)

    def get_recent_books(self):
        return list(self.data.keys())


class HotkeyLineEdit(QLineEdit):
    def __init__(self, default_text="", parent=None):
        super().__init__(default_text, parent)
        self.setPlaceholderText("点击并按下按键...")
        self.setReadOnly(True)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self.setText("")
            return
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return
        modifiers = event.modifiers()
        keys = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            keys.append("ctrl")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            keys.append("shift")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            keys.append("alt")
        key_text = QKeySequence(key).toString().lower()
        if key_text == "return":
            key_text = "enter"
        if key_text == "pgup":
            key_text = "page up"
        if key_text == "pgdown":
            key_text = "page down"
        if key_text == "left":
            key_text = "left"
        if key_text == "right":
            key_text = "right"
        if key_text == "up":
            key_text = "up"
        if key_text == "down":
            key_text = "down"
        if key_text:
            keys.append(key_text)
        self.setText("+".join(keys))


class ReaderWindow(QWidget):
    def __init__(self, bookshelf, config_mgr, comm):
        super().__init__()
        self.bookshelf = bookshelf
        self.cfg = config_mgr
        self.comm = comm
        self.current_file = None
        self.is_focus_mode = False

        icon_path = resource_path("logo.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        self.text_label = QLabel("按 F3 唤醒")
        layout.addWidget(self.text_label)
        self.setLayout(layout)
        self.content_lines = []
        self.current_index = 0
        self.drag_pos = None
        self.apply_style()

    def reset_focus(self):
        if self.cfg.config.get("focus_anchor", True):
            self.is_focus_mode = True
        else:
            self.is_focus_mode = False

    def apply_style(self):
        c = self.cfg.config
        bg = (
            c["bg_color"]
            if c["bg_color"] != "#00000000" and c["bg_color"] != "transparent"
            else "transparent"
        )
        self.setStyleSheet(f"QWidget {{ background-color: {bg}; }}")
        font = QFont("Microsoft YaHei", int(c["font_size"]))
        self.text_label.setFont(font)

        if not self.is_focus_mode:
            self.text_label.setStyleSheet(
                f"color: {c['text_color']}; background-color: transparent;"
            )

        self.adjustSize()

    def load_book(self, path):
        if not os.path.exists(path):
            return
        self.current_file = path
        try:
            doc = fitz.open(path)
            text = "".join([page.get_text() for page in doc])
            self.content_lines = [l.strip() for l in text.split("\n") if l.strip()]
            doc.close()
            idx = self.bookshelf.get_progress(path)
            self.current_index = idx if idx < len(self.content_lines) else 0
        except Exception as e:
            self.text_label.setText(f"Err: {e}")

    def show_line(self):
        txt = (
            self.content_lines[self.current_index]
            if 0 <= self.current_index < len(self.content_lines)
            else "--- End ---"
        )
        self.text_label.setText(txt)
        c = self.cfg.config
        self.text_label.setStyleSheet(
            f"color: {c['text_color']}; background-color: transparent;"
        )
        self.is_focus_mode = False
        self.adjustSize()
        self.bookshelf.update_progress(self.current_file, self.current_index)

    def next_line(self):
        if self.current_file:
            self.current_index += 1
            self.show_line()

    def prev_line(self):
        if self.current_file and self.current_index > 0:
            self.current_index -= 1
            self.show_line()

    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())
            if msg.message == 0x0084:  # WM_NCHITTEST
                return True, 2  # HTCAPTION → 整个窗口当作标题栏拖动
        return super().nativeEvent(eventType, message)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide()


class SettingsDialog(QDialog):
    def __init__(self, cfg, comm, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.comm = comm
        self.setWindowTitle("设置")
        self.setFixedWidth(480)

        layout = QVBoxLayout(self)
        sg = QGridLayout()
        sg.setVerticalSpacing(6)
        sg.setHorizontalSpacing(6)

        sg.addWidget(QLabel("外观"), 0, 0, 1, 4)
        self.spin_font = QSpinBox()
        self.spin_font.setRange(8, 72)
        self.spin_font.setValue(int(self.cfg.config["font_size"]))
        self.spin_font.valueChanged.connect(self.save_appearance)
        sg.addWidget(QLabel("字号"), 1, 0)
        sg.addWidget(self.spin_font, 1, 1)

        self.btn_col_txt = QPushButton("文字色")
        self.btn_col_txt.clicked.connect(lambda: self.pick_color("text_color"))
        sg.addWidget(self.btn_col_txt, 1, 2)
        self.btn_col_bg = QPushButton("背景色")
        self.btn_col_bg.clicked.connect(lambda: self.pick_color("bg_color"))
        sg.addWidget(self.btn_col_bg, 1, 3)
        self.update_color_buttons()

        self.chk_focus = QCheckBox("聚焦引导")
        self.chk_focus.setChecked(self.cfg.config.get("focus_anchor", True))
        self.chk_focus.toggled.connect(self.toggle_focus)
        sg.addWidget(self.chk_focus, 1, 4)

        sep = QLabel("快捷键")
        sep.setStyleSheet("border-top: 1px solid #ccc; margin-top: 4px;")
        sg.addWidget(sep, 2, 0, 1, 5)

        self.inp_next = HotkeyLineEdit(self.cfg.config["key_next"])
        self.inp_next.textChanged.connect(self.apply_hotkey)
        sg.addWidget(QLabel("下一行"), 3, 0)
        sg.addWidget(self.inp_next, 3, 1)
        self.inp_prev = HotkeyLineEdit(self.cfg.config["key_prev"])
        self.inp_prev.textChanged.connect(self.apply_hotkey)
        sg.addWidget(QLabel("上一行"), 3, 2)
        sg.addWidget(self.inp_prev, 3, 3)
        self.inp_toggle = HotkeyLineEdit(self.cfg.config["key_toggle"])
        self.inp_toggle.textChanged.connect(self.apply_hotkey)
        sg.addWidget(QLabel("切换"), 3, 4)
        sg.addWidget(self.inp_toggle, 3, 5)

        btn_reset = QPushButton("恢复默认")
        btn_reset.setFixedHeight(22)
        btn_reset.setStyleSheet(
            "QPushButton { border: none; color: #888; text-decoration: underline; } QPushButton:hover { color: #333; }"
        )
        btn_reset.clicked.connect(self.reset_default_keys)
        sg.addWidget(btn_reset, 4, 5, Qt.AlignmentFlag.AlignRight)

        layout.addLayout(sg)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def update_color_buttons(self):
        c = self.cfg.config
        txt = c["text_color"]
        bg = c["bg_color"] if c["bg_color"] != "#00000000" else "#ffffff"
        self.btn_col_txt.setStyleSheet(f"background-color: {txt}; min-width: 40px;")
        self.btn_col_bg.setStyleSheet(f"background-color: {bg}; min-width: 40px;")

    def save_appearance(self):
        self.cfg.config["font_size"] = self.spin_font.value()
        self.cfg.save()
        self.comm.update_style_signal.emit()

    def apply_hotkey(self):
        self.cfg.config["key_next"] = self.inp_next.text()
        self.cfg.config["key_prev"] = self.inp_prev.text()
        self.cfg.config["key_toggle"] = self.inp_toggle.text()
        self.cfg.save()
        from_control = self.parent()
        if from_control and hasattr(from_control, "bind_keys"):
            from_control.bind_keys(silent=True)

    def toggle_focus(self, checked):
        self.cfg.config["focus_anchor"] = checked
        self.cfg.save()

    def reset_default_keys(self):
        self.inp_next.setText("down")
        self.inp_prev.setText("up")
        self.inp_toggle.setText("F3")
        self.apply_hotkey()
        QMessageBox.information(self, "提示", "快捷键已重置为默认设置！")

    def pick_color(self, key):
        col = QColorDialog.getColor()
        if col.isValid():
            if key == "bg_color":
                reply = QMessageBox.question(
                    self,
                    "背景",
                    "是否设为完全透明?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                self.cfg.config[key] = (
                    "#00000000"
                    if reply == QMessageBox.StandardButton.Yes
                    else col.name()
                )
            else:
                self.cfg.config[key] = col.name()
            self.cfg.save()
            self.update_color_buttons()
            self.comm.update_style_signal.emit()


class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = ConfigManager()

        icon_path = resource_path("logo.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setWindowTitle(self.cfg.config.get("window_title", "二氧化碳阅读器"))
        self.resize(600, 500)

        self.bookshelf = BookShelf()
        self.comm = GlobalSignal()
        self.reader = ReaderWindow(self.bookshelf, self.cfg, self.comm)

        self.comm.toggle_signal.connect(self.toggle_reader)
        self.comm.update_style_signal.connect(self.reader.apply_style)
        self.comm.next_signal.connect(self.reader.next_line)
        self.comm.prev_signal.connect(self.reader.prev_line)

        self.init_tray()
        self.init_ui()
        self.start_hooks()
        self.auto_resume()

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = resource_path("logo.ico")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            self.tray_icon.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            )

        tray_menu = QMenu()
        action_show = QAction("显示控制台", self)
        action_show.triggered.connect(self.showNormal)
        tray_menu.addAction(action_show)
        action_quit = QAction("退出", self)
        action_quit.triggered.connect(QApplication.quit)
        tray_menu.addAction(action_quit)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_click)
        self.tray_icon.show()

    def on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()
                self.activateWindow()

    def closeEvent(self, event):
        if self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage(
                "提示",
                "已缩略至系统托盘，右键托盘图标可退出。",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            event.ignore()
        else:
            event.accept()

    def init_ui(self):
        self.setAcceptDrops(True)
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # 顶栏
        top = QHBoxLayout()
        btn_imp = QPushButton("+ 导入")
        btn_imp.clicked.connect(self.import_book)
        top.addWidget(btn_imp)
        top.addStretch()
        btn_settings = QPushButton("⚙")
        btn_settings.setFixedWidth(32)
        btn_settings.setToolTip("设置")
        btn_settings.clicked.connect(self.open_settings)
        top.addWidget(btn_settings)
        layout.addLayout(top)

        # 书架标题 + 数量
        self.lbl_shelf_title = QLabel("书架")
        layout.addWidget(self.lbl_shelf_title)

        self.lbl_status = QLabel("拖入文件快速添加")
        self.lbl_status.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        self.list_books = QListWidget()
        self.list_books.itemDoubleClicked.connect(self.on_book_activated)
        layout.addWidget(self.list_books, 1)
        self.refresh_books()

        self.setLayout(layout)

    def auto_resume(self):
        recent = self.bookshelf.get_recent_books()
        if recent:
            last = recent[-1]
            self.reader.load_book(last)
            self.refresh_books()
            self.start_reading()

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self.comm, self)
        dlg.exec()

    def on_book_activated(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        self.reader.load_book(path)
        self.start_reading()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if any(
                path.lower().endswith(ext)
                for ext in (".txt", ".pdf", ".epub", ".mobi", ".azw3")
            ):
                self.reader.load_book(path)
                self.refresh_books()
                break

    def start_hooks(self):
        self.bind_keys(silent=True)

    def toggle_reader(self):
        if self.reader.isVisible():
            self.reader.hide()
        elif self.reader.current_file:
            self.reader.show()
            self.reader.activateWindow()

    def bind_keys(self, silent=False):
        keyboard.unhook_all()
        c = self.cfg.config
        try:
            keyboard.add_hotkey(
                c["key_next"],
                lambda: (
                    self.comm.next_signal.emit()
                    if self.reader.isVisible()
                    else keyboard.send(c["key_next"])
                ),
            )
            keyboard.add_hotkey(
                c["key_prev"],
                lambda: (
                    self.comm.prev_signal.emit()
                    if self.reader.isVisible()
                    else keyboard.send(c["key_prev"])
                ),
            )
            keyboard.add_hotkey(c["key_toggle"], self.comm.toggle_signal.emit)
            if not silent:
                QMessageBox.information(self, "成功", "快捷键已生效！")
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, "错误", f"快捷键冲突或格式错误: {e}")

    def import_book(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择", "", "Files (*.txt *.pdf *.epub *.mobi *.azw3)"
        )
        if path:
            self.reader.load_book(path)
            self.refresh_books()

    def start_reading(self):
        if self.reader.current_file:
            self.reader.reset_focus()
            self.reader.show_line()
            if self.cfg.config.get("focus_anchor", True):
                self.reader.adjustSize()
                screen = self.screen().geometry()
                size = self.reader.geometry()
                new_x = (screen.width() - size.width()) // 2
                new_y = (screen.height() - size.height()) // 2
                self.reader.move(new_x, new_y)
            else:
                self.reader.move(200, 200)

            self.reader.show()
            self.reader.activateWindow()
            self.hide()
            self.tray_icon.showMessage(
                "二氧化碳阅读器",
                "控制台已隐藏，文字已居中显示。",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
        else:
            QMessageBox.information(self, "提示", "请先导入书籍")

    def refresh_books(self):
        self.list_books.clear()
        books = self.bookshelf.get_recent_books()
        for k in books:
            line = self.bookshelf.get_progress(k)
            text = os.path.basename(k)
            if line > 0:
                text += f" — 第 {line} 行"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, k)
            self.list_books.addItem(item)
        self.lbl_shelf_title.setText(f"书架（{len(books)}）")
        self.lbl_status.setText(
            "拖入文件快速添加" if books else "尚无书籍，点击 + 导入 或拖入文件"
        )


if __name__ == "__main__":
    #  pyinstaller --noconfirm --onefile --windowed --icon "images/2352335.ico" --name "二氧化碳阅读器" "main.py"
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    panel = ControlPanel()
    panel.show()
    sys.exit(app.exec())
