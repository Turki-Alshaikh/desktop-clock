import ctypes
import ctypes.wintypes
import math
import sys
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QPoint, QSettings
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QAction
from PyQt6.QtWidgets import QApplication, QWidget, QMenu

# =====================================================================
# ثوابت Win32
# =====================================================================
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_BORDER = 0x00800000
WS_THICKFRAME = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020

# DWM attributes (Windows 11)
DWMWA_BORDER_COLOR = 34
DWMWA_COLOR_NONE = 0xFFFFFFFE
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_DONOTROUND = 1


def _safe(fn, *args, label=""):
    """تنفيذ آمن مع طباعة الخطأ بدل إسقاط التطبيق."""
    try:
        return fn(*args)
    except Exception as e:
        print(f"[warn] {label}: {e}")
        return None


def strip_window_chrome(hwnd: int) -> None:
    """إزالة كل أشكال الإطار/الحدود على مستوى ويندوز (10 + 11)."""
    user32 = ctypes.windll.user32

    # --- 1. إزالة أنماط الإطار القديمة (Win10 وبعض حالات Win11) ---
    style = _safe(user32.GetWindowLongW, hwnd, GWL_STYLE, label="GetWindowLong")
    if style is not None:
        new_style = style & ~(WS_BORDER | WS_THICKFRAME)
        _safe(user32.SetWindowLongW, hwnd, GWL_STYLE, new_style,
              label="SetWindowLong")

    # --- 2. إخفاء الأيقونة من شريط المهام ---
    ex = _safe(user32.GetWindowLongW, hwnd, GWL_EXSTYLE, label="GetWindowLong ex")
    if ex is not None:
        new_ex = (ex & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
        _safe(user32.SetWindowLongW, hwnd, GWL_EXSTYLE, new_ex,
              label="SetWindowLong ex")

    # --- 3. إعلام ويندوز أن الأنماط تغيّرت ليُعيد رسم الإطار ---
    _safe(user32.SetWindowPos, hwnd, 0, 0, 0, 0, 0,
          SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
          label="SetWindowPos")

    # --- 4. إزالة إطار DWM (Windows 11) ---
    dwmapi = ctypes.windll.dwmapi
    border = ctypes.c_uint(DWMWA_COLOR_NONE)
    _safe(dwmapi.DwmSetWindowAttribute,
          hwnd, DWMWA_BORDER_COLOR,
          ctypes.byref(border), ctypes.sizeof(border),
          label="DWM border color")

    # --- 5. منع الزوايا الدائرية (Windows 11) ---
    corner = ctypes.c_uint(DWMWCP_DONOTROUND)
    _safe(dwmapi.DwmSetWindowAttribute,
          hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
          ctypes.byref(corner), ctypes.sizeof(corner),
          label="DWM corner pref")


# =====================================================================
# الساعة
# =====================================================================
class DesktopClock(QWidget):
    def __init__(self):
        super().__init__()

        # ✅ بدون WindowStaysOnBottomHint (كان يخفي النافذة تحت Progman)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # الحجم والموقع
        self.settings = QSettings("MyDesktop", "ClassicClock")
        size = int(self.settings.value("size", 220))
        self.setFixedSize(size, size)

        saved_pos = self.settings.value("pos")
        if (isinstance(saved_pos, QPoint)
                and QApplication.primaryScreen()
                    .availableGeometry().contains(saved_pos)):
            self.move(saved_pos)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(screen.center() - self.rect().center())

        self._drag_pos = None

        # المظهر
        self.show_seconds = True
        self.color_main = QColor(255, 255, 255, 245)
        self.color_accent = QColor(255, 200, 120, 255)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(50)

    # -----------------------------------------------------------------
    # تطبيق إزالة الحدود بمجرد ظهور النافذة
    # -----------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32":
            strip_window_chrome(int(self.winId()))

    # -----------------------------------------------------------------
    # الرسم
    # -----------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # مسح كامل → شفافية تامة
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        w, h = self.width(), self.height()
        side = min(w, h)
        margin = side * 0.06
        rect = QRectF(margin, margin, side - 2 * margin, side - 2 * margin)
        center = rect.center()
        R = rect.width() / 2
        unit = max(1.0, R / 70)

        now = datetime.now()
        hour_angle = (now.hour % 12 + now.minute / 60) * 30
        minute_angle = (now.minute + now.second / 60) * 6
        second_angle = (now.second + now.microsecond / 1_000_000) * 6

        # علامات الساعات
        for i in range(12):
            ang = math.radians(i * 30 - 90)
            x2 = center.x() + R * 0.96 * math.cos(ang)
            y2 = center.y() + R * 0.96 * math.sin(ang)
            if i % 3 == 0:
                x1 = center.x() + R * 0.86 * math.cos(ang)
                y1 = center.y() + R * 0.86 * math.sin(ang)
                p.setPen(QPen(self.color_main, unit * 1.1,
                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            else:
                x1 = center.x() + R * 0.90 * math.cos(ang)
                y1 = center.y() + R * 0.90 * math.sin(ang)
                p.setPen(QPen(QColor(255, 255, 255, 140), unit * 0.7,
                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # عقرب الساعات
        p.save()
        p.translate(center)
        p.rotate(hour_angle)
        p.setPen(QPen(self.color_main, unit * 2.2,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(0, R * 0.08), QPointF(0, -R * 0.48))
        p.restore()

        # عقرب الدقائق
        p.save()
        p.translate(center)
        p.rotate(minute_angle)
        p.setPen(QPen(self.color_main, unit * 1.5,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(0, R * 0.08), QPointF(0, -R * 0.72))
        p.restore()

        # عقرب الثواني
        if self.show_seconds:
            p.save()
            p.translate(center)
            p.rotate(second_angle)
            p.setPen(QPen(self.color_accent, unit * 0.8,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(0, R * 0.18), QPointF(0, -R * 0.85))
            p.restore()

        # نقطة المركز
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self.color_accent))
        p.drawEllipse(center, unit * 2.0, unit * 2.0)
        p.setBrush(QBrush(self.color_main))
        p.drawEllipse(center, unit * 0.85, unit * 0.85)

    # -----------------------------------------------------------------
    # تغيير الحجم بعجلة الفأرة
    # -----------------------------------------------------------------
    def wheelEvent(self, event):
        step = 15 if event.angleDelta().y() > 0 else -15
        new_size = max(120, min(600, self.width() + step))
        if new_size != self.width():
            self._resize_keeping_center(new_size)

    def _resize_keeping_center(self, new_size):
        old_center = self.geometry().center()
        self.setFixedSize(new_size, new_size)
        r = self.rect()
        r.moveCenter(old_center)
        self.move(r.topLeft())
        self.settings.setValue("size", new_size)
        self.settings.setValue("pos", self.pos())
        self.update()

    # -----------------------------------------------------------------
    # السحب بالفأرة
    # -----------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (event.globalPosition().toPoint()
                              - self.frameGeometry().topLeft())
            event.accept()

    def mouseMoveEvent(self, event):
        if (event.buttons() == Qt.MouseButton.LeftButton
                and self._drag_pos is not None):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_pos is not None:
            self.settings.setValue("pos", self.pos())
        self._drag_pos = None

    # -----------------------------------------------------------------
    # قائمة الزر الأيمن
    # -----------------------------------------------------------------
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1a1a; color: #eee;
                    border: 1px solid #333; border-radius: 8px;
                    padding: 6px; font-size: 12px; }
            QMenu::item { padding: 6px 22px; border-radius: 4px; }
            QMenu::item:selected { background-color: #2f2f2f; }
        """)
        sec_action = QAction("إظهار الثواني", self, checkable=True)
        sec_action.setChecked(self.show_seconds)
        sec_action.triggered.connect(self._toggle_seconds)
        menu.addAction(sec_action)

        size_menu = menu.addMenu("الحجم")
        for name, value in [("صغير", 150), ("متوسط", 220),
                            ("كبير", 320), ("ضخم", 450)]:
            act = QAction(name, self)
            act.triggered.connect(
                lambda _, v=value: self._resize_keeping_center(v))
            size_menu.addAction(act)

        menu.addSeparator()
        close_action = QAction("إغلاق", self)
        close_action.triggered.connect(QApplication.quit)
        menu.addAction(close_action)
        menu.exec(event.globalPos())

    def _toggle_seconds(self, checked):
        self.show_seconds = checked
        self.update()


# =====================================================================
# نقطة الدخول
# =====================================================================
def main():
    # صيد أي استثناء صامت
    def _hook(exc_type, exc_val, exc_tb):
        import traceback
        traceback.print_exception(exc_type, exc_val, exc_tb)
        sys.__excepthook__(exc_type, exc_val, exc_tb)
    sys.excepthook = _hook

    app = QApplication(sys.argv)
    clock = DesktopClock()
    clock.show()
    print("✓ الساعة تعمل الآن. اضغط Win+D لرؤيتها.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()