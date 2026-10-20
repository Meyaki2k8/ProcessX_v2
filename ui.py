import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from collections import OrderedDict
from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QFileInfo,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QIcon,
    QImage,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QResizeEvent,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFileIconProvider,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_DIR,
    IO_PRIORITY_NAMES,
    PRIORITY_MAP,
    I18N,
    export_rules_to_file,
    get_setting,
    import_rules_from_file,
    is_critical_process,
    load_rules,
    save_rules,
    set_setting,
    tr,
    translate_val,
    validate_rules,
)
from core import (
    CPU_COUNT,
    CPU_TOPOLOGY,
    RuleWatcher,
    add_to_startup,
    apply_all_rules,
    apply_all_rules_async,
    apply_dwm_glass,
    collect_proc_snapshot,
    delete_rule,
    find_exe_path,
    find_rule_for_process,
    format_affinity_str,
    get_proc_exe,
    get_running_pids,
    is_in_startup,
    kill_process,
    list_power_plans,
    normalize_exe_path,
    remove_from_startup,
    save_and_apply_rule,
    set_dwm_corner_preference,
    trim_process_memory,
    WM_PROCESSX_SHOW_NAME,
)

WM_PROCESSX_SHOW = ctypes.windll.user32.RegisterWindowMessageW(WM_PROCESSX_SHOW_NAME)


def _log_error(context: str, exc: Exception | None = None):
    try:
        log_path = APP_DIR / "processx.log"
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[{now}] [ERROR in {context}]\n")
            if exc is not None:
                traceback.print_exception(type(exc), exc, exc.__traceback__, file=f)
            else:
                f.write(f"{context}\n")
    except Exception:
        pass


# ── Color Palette (Modern Deep Obsidian & Electric Blue) ─────────────────────
# Primary Background: Deep Obsidian Black
BG_OBSIDIAN = "#090A0F"
BG_OBSIDIAN_TRANSLUCENT = "rgba(9, 10, 15, 0.82)"

# Surface Containers (Obsidian table & card surfaces)
SURFACE_CARD = "#0F1117"
SURFACE_GLASS = "rgba(15, 17, 23, 0.70)"
SURFACE_GLASS_HOVER = "rgba(22, 26, 36, 0.85)"
SURFACE_GLASS_ACTIVE = "rgba(30, 36, 50, 0.90)"

# Specular 1px Borders
BORDER_SUBTLE = "rgba(255, 255, 255, 0.08)"
BORDER_HOVER = "rgba(255, 255, 255, 0.16)"
BORDER_TOOLBAR = "rgba(255, 255, 255, 0.06)"

# Electric Blue / Cobalt Blue Accents
ACCENT_BLUE = "#3B82F6"
ACCENT_BLUE_DARK = "#2563EB"
ACCENT_BLUE_HOVER = "#60A5FA"
ACCENT_BLUE_DIM = "rgba(59, 130, 246, 0.12)"
BORDER_BLUE = "rgba(59, 130, 246, 0.30)"
BORDER_BLUE_FOCUS = "rgba(59, 130, 246, 0.55)"
TEXT_BLUE = "#60A5FA"
ROW_HOVER_SELECTION = "rgba(37, 99, 235, 0.15)"

# Backward-compatibility aliases for existing module imports
ACCENT_EMERALD = ACCENT_BLUE
ACCENT_EMERALD_HOVER = ACCENT_BLUE_HOVER
ACCENT_EMERALD_DIM = ACCENT_BLUE_DIM
ACCENT_CYAN = ACCENT_BLUE
ACCENT_CYAN_HOVER = ACCENT_BLUE_HOVER
ACCENT_CYAN_DIM = ACCENT_BLUE_DIM
BORDER_ACTIVE = BORDER_BLUE
BORDER_CYAN = BORDER_BLUE

# Text Hierarchy
TEXT_PRIMARY = "#F1F5F9"
TEXT_SECONDARY = "#94A3B8"
TEXT_MUTED = "#475569"

# Functional / State Colors
COLOR_RUNNING = "#3B82F6"
COLOR_WAITING = "#64748B"
COLOR_DANGER = "#F43F5E"
COLOR_DANGER_HOVER = "#FB7185"
COLOR_WARNING = "#F59E0B"
COLOR_INFO = "#38BDF8"

# ── Typography ───────────────────────────────────────────────────────────────
FONT_FAMILY_UI = '"Segoe UI Variable Text", "Segoe UI", "Inter", -apple-system, sans-serif'
FONT_FAMILY_MONO = '"Cascadia Code", "JetBrains Mono", "Consolas", monospace'


def get_ui_font(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Return configured modern sans-serif QFont."""
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Inter", "sans-serif"])
    font.setPointSize(size)
    font.setWeight(weight)
    return font


def get_mono_font(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Return tabular monospace QFont for metrics, PIDs, and counters."""
    font = QFont()
    font.setFamilies(["Cascadia Code", "Consolas", "JetBrains Mono", "monospace"])
    font.setPointSize(size)
    font.setWeight(weight)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


# ── Global QSS Stylesheet ───────────────────────────────────────────────────
GLOBAL_STYLESHEET = f"""
/* ── Global Defaults ─────────────────────────────────────────────────────── */
QWidget {{
    color: {TEXT_PRIMARY};
    font-family: {FONT_FAMILY_UI};
    font-size: 13px;
    outline: none;
}}

QWidget:disabled {{
    color: {TEXT_MUTED};
}}

/* ── Main Window & Outer Containers ───────────────────────────────────────── */
QMainWindow {{
    background: transparent;
    border: none;
}}

#RootFrame, #MainContainer {{
    background: transparent;
    border: none;
}}

#ContentWidget {{
    background: transparent;
    border: none;
}}

#GlassCard {{
    background-color: {SURFACE_CARD};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
    background-clip: padding-box;
}}

#GlassCard:hover {{
    border: 1px solid {BORDER_HOVER};
}}

/* Toolbar frame: static subtle border with NO hover border change */
#ActionToolbar {{
    background-color: {SURFACE_CARD};
    border: 1px solid {BORDER_TOOLBAR};
    border-radius: 8px;
    background-clip: padding-box;
}}

/* ── Custom Title Bar ─────────────────────────────────────────────────────── */
#TitleBar {{
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {BORDER_SUBTLE};
}}

#TitleLabel {{
    font-size: 14px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    letter-spacing: 0.5px;
}}

#VersionBadge {{
    background-color: {ACCENT_BLUE_DIM};
    color: {TEXT_BLUE};
    border: 1px solid {BORDER_BLUE};
    border-radius: 6px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 600;
    max-height: 20px;
}}

/* Window Controls: 32x28px uniform boxes, optically centered */
#TitleBtn, #TitleBtnClose {{
    background-color: transparent;
    border: none;
    border-radius: 6px;
    color: {TEXT_SECONDARY};
    font-size: 12px;
    font-weight: 600;
    padding: 0px;
    text-align: center;
    min-width: 32px;
    max-width: 32px;
    min-height: 28px;
    max-height: 28px;
}}

#TitleBtn:hover {{
    background-color: rgba(255, 255, 255, 0.08);
    color: {TEXT_PRIMARY};
}}

#TitleBtn:pressed {{
    background-color: rgba(255, 255, 255, 0.14);
}}

#TitleBtnClose:hover {{
    background-color: {COLOR_DANGER};
    color: #FFFFFF;
}}

#TitleBtnClose:pressed {{
    background-color: #BE123C;
    color: #FFFFFF;
}}

/* Language Toggle Segmented Pill */
#LangToggleContainer {{
    background-color: rgba(15, 17, 23, 0.75);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    padding: 2px;
    max-height: 28px;
}}

.LangToggleBtn {{
    border: none;
    border-radius: 4px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 700;
    color: {TEXT_SECONDARY};
    background-color: transparent;
    min-height: 22px;
    max-height: 22px;
}}

.LangToggleBtn:hover {{
    color: {TEXT_PRIMARY};
}}

.LangToggleBtn[active="true"] {{
    background-color: {ACCENT_BLUE_DARK};
    color: #FFFFFF;
}}

/* ── Search Bar & Inputs ──────────────────────────────────────────────────── */
QLineEdit {{
    background-color: rgba(14, 16, 22, 0.75);
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 6px;
    background-clip: padding-box;
    padding: 6px 12px;
    color: {TEXT_PRIMARY};
    font-size: 13px;
    selection-background-color: rgba(59, 130, 246, 0.28);
    selection-color: #FFFFFF;
}}

QLineEdit:hover {{
    border: 1px solid {BORDER_HOVER};
}}

QLineEdit:focus {{
    border: 1px solid {ACCENT_BLUE};
    background-color: rgba(18, 21, 29, 0.95);
}}

/* ── Buttons ──────────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {SURFACE_GLASS};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 6px;
    background-clip: padding-box;
    color: {TEXT_PRIMARY};
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {SURFACE_GLASS_HOVER};
    border: 1px solid {BORDER_HOVER};
    color: #FFFFFF;
}}

QPushButton:pressed {{
    background-color: {SURFACE_GLASS_ACTIVE};
    border: 1px solid {BORDER_BLUE};
}}

QPushButton:disabled {{
    background-color: rgba(16, 18, 24, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.03);
    color: {TEXT_MUTED};
}}

/* Primary Action Button (Solid Electric Blue) */
QPushButton#AccentBtn {{
    background-color: {ACCENT_BLUE_DARK};
    border: 1px solid {ACCENT_BLUE_DARK};
    border-radius: 6px;
    background-clip: padding-box;
    color: #FFFFFF;
    font-weight: 700;
}}

QPushButton#AccentBtn:hover {{
    background-color: {ACCENT_BLUE};
    border: 1px solid {ACCENT_BLUE};
    color: #FFFFFF;
}}

QPushButton#AccentBtn:pressed {{
    background-color: #1D4ED8;
    border: 1px solid #1D4ED8;
}}

/* Subtle Accent Button ("Profiles" / CyanBtn) */
QPushButton#CyanBtn, QPushButton#SubtleAccentBtn {{
    background-color: {ACCENT_BLUE_DIM};
    border: 1px solid {BORDER_BLUE};
    border-radius: 6px;
    background-clip: padding-box;
    color: {TEXT_BLUE};
    font-weight: 600;
}}

QPushButton#CyanBtn:hover, QPushButton#SubtleAccentBtn:hover {{
    background-color: rgba(59, 130, 246, 0.22);
    border: 1px solid rgba(59, 130, 246, 0.50);
    color: #93C5FD;
}}

/* Danger Button */
QPushButton#DangerBtn {{
    background-color: rgba(244, 63, 94, 0.14);
    border: 1px solid rgba(244, 63, 94, 0.35);
    border-radius: 6px;
    background-clip: padding-box;
    color: {COLOR_DANGER};
    font-weight: 600;
}}

QPushButton#DangerBtn:hover {{
    background-color: {COLOR_DANGER};
    border: 1px solid {COLOR_DANGER};
    color: #FFFFFF;
}}

/* ── Tree & Table Views ───────────────────────────────────────────────────── */
/* ── Tree Views (Process Tree) ────────────────────────────────────────────── */
QTreeWidget, QTreeView, QTreeWidget::viewport, QTreeView::viewport {{
    background-color: {SURFACE_CARD};
    background: {SURFACE_CARD};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
    background-clip: padding-box;
    padding: 2px;
    outline: none;
    alternate-background-color: transparent;
    selection-background-color: transparent;
    selection-color: {TEXT_PRIMARY};
    show-decoration-selected: 0;
}}

/* For QTreeWidget/QTreeView, ProcessRowDelegate has exclusive authority over
   row background fill, hover, selection, left indicator bar, and guide lines.
   Explicitly clear item background, borders, and hover/selection pseudo-states
   in QSS to completely eliminate visual fighting, double painting, and ghosting. */
QTreeWidget::item, QTreeView::item {{
    height: 32px;
    border: none;
    margin: 0px;
    padding: 2px 4px;
    border-radius: 0px;
    background: transparent;
    background-color: transparent;
    outline: none;
}}

QTreeWidget::item:hover, QTreeView::item:hover {{
    background: transparent;
    background-color: transparent;
    border: none;
    outline: none;
}}

QTreeWidget::item:selected, QTreeView::item:selected {{
    background: transparent;
    background-color: transparent;
    border: none;
    outline: none;
}}

QTreeWidget::item:focus, QTreeView::item:focus {{
    background: transparent;
    background-color: transparent;
    border: none;
    outline: none;
}}

/* ── Table Views (Rules & Profiles) ───────────────────────────────────────── */
QTableWidget, QTableView, QTableWidget::viewport, QTableView::viewport,
QAbstractItemView, QAbstractItemView::viewport {{
    background-color: {SURFACE_CARD};
    background: {SURFACE_CARD};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
    background-clip: padding-box;
    padding: 2px;
    outline: none;
    alternate-background-color: transparent;
    selection-background-color: {ROW_HOVER_SELECTION};
    selection-color: #FFFFFF;
    show-decoration-selected: 1;
}}

QTableWidget::item, QTableView::item {{
    height: 32px;
    border: none;
    margin: 0px;
    padding: 2px 4px;
    border-radius: 0px;
}}

/* Left column rounded corners + indicator bar */
QTableWidget::item:first, QTableView::item:first {{
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
}}

/* Right column rounded corners */
QTableWidget::item:last, QTableView::item:last {{
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}}

QTableWidget::item:hover, QTableView::item:hover {{
    background-color: rgba(37, 99, 235, 0.10);
    color: #F1F5F9;
}}

QTableWidget::item:hover:first, QTableView::item:hover:first {{
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
    border-left: 3px solid {ACCENT_BLUE};
}}

QTableWidget::item:hover:last, QTableView::item:hover:last {{
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}}

QTableWidget::item:selected, QTableView::item:selected {{
    background-color: rgba(37, 99, 235, 0.18);
    color: #FFFFFF;
}}

QTableWidget::item:selected:first, QTableView::item:selected:first {{
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
    border-left: 3px solid {ACCENT_BLUE};
}}

QTableWidget::item:selected:last, QTableView::item:selected:last {{
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}}


/* Header View */
QHeaderView::section {{
    background-color: rgba(12, 14, 19, 0.85);
    color: {TEXT_SECONDARY};
    padding: 6px 10px;
    border: none;
    border-bottom: 1px solid {BORDER_SUBTLE};
    border-right: 1px solid rgba(255, 255, 255, 0.03);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

QHeaderView::section:hover {{
    background-color: rgba(22, 26, 36, 0.9);
    color: {TEXT_PRIMARY};
}}

/* Tree Branch Indicators */
QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {{
    image: none;
}}

QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings {{
    image: none;
}}

/* ── Minimalist Dark Scrollbars ───────────────────────────────────────────── */
QScrollBar:vertical {{
    background-color: transparent;
    width: 8px;
    margin: 4px 2px 4px 2px;
}}

QScrollBar::handle:vertical {{
    background-color: rgba(255, 255, 255, 0.15);
    border-radius: 4px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: rgba(255, 255, 255, 0.30);
}}

QScrollBar::handle:vertical:pressed {{
    background-color: {ACCENT_BLUE_DARK};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background-color: transparent;
}}

QScrollBar:horizontal {{
    background-color: transparent;
    height: 8px;
    margin: 2px 4px 2px 4px;
}}

QScrollBar::handle:horizontal {{
    background-color: rgba(255, 255, 255, 0.15);
    border-radius: 4px;
    min-width: 24px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: rgba(255, 255, 255, 0.30);
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background-color: transparent;
}}

/* Table & Tree scrollbar tracks on solid surface */
QTreeWidget QScrollBar:vertical, QTableWidget QScrollBar:vertical,
QTreeWidget QScrollBar:horizontal, QTableWidget QScrollBar:horizontal {{
    background-color: {SURFACE_CARD};
}}

QTreeWidget QScrollBar::add-page:vertical, QTreeWidget QScrollBar::sub-page:vertical,
QTableWidget QScrollBar::add-page:vertical, QTableWidget QScrollBar::sub-page:vertical,
QTreeWidget QScrollBar::add-page:horizontal, QTreeWidget QScrollBar::sub-page:horizontal,
QTableWidget QScrollBar::add-page:horizontal, QTableWidget QScrollBar::sub-page:horizontal {{
    background-color: {SURFACE_CARD};
}}

/* ── Editor Dialog Scroll Area ────────────────────────────────────────────── */
#EditorScrollArea, #EditorScrollViewport, #EditorScrollContainer {{
    background-color: {BG_OBSIDIAN};
    border: none;
}}

#EditorScrollArea QScrollBar:vertical {{
    background-color: {BG_OBSIDIAN};
    width: 8px;
    margin: 4px 2px 4px 2px;
}}

#EditorScrollArea QScrollBar::add-page:vertical,
#EditorScrollArea QScrollBar::sub-page:vertical {{
    background-color: {BG_OBSIDIAN};
}}

#EditorScrollArea QScrollBar:horizontal {{
    height: 0px;
    background-color: transparent;
}}

/* ── Combobox ─────────────────────────────────────────────────────────────── */
QComboBox {{
    background-color: rgba(16, 19, 26, 0.85);
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 6px;
    background-clip: padding-box;
    padding: 6px 32px 6px 12px;
    color: {TEXT_PRIMARY};
    font-size: 12px;
    font-weight: 500;
}}

QComboBox:hover {{
    border: 1px solid {BORDER_HOVER};
}}

QComboBox:focus:on {{
    border: 1px solid {ACCENT_BLUE};
}}

QComboBox:focus:!on {{
    border: 1px solid {BORDER_HOVER};
}}

NoScrollComboBox, CrispComboBox {{
    background: transparent;
    border: none;
    outline: none;
    padding: 0px;
}}

NoScrollComboBox:focus, CrispComboBox:focus {{
    border: none;
    outline: none;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border: none;
}}

QComboBox QAbstractItemView {{
    background-color: #12151D;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 6px;
    background-clip: padding-box;
    color: {TEXT_PRIMARY};
    selection-background-color: transparent;
    selection-color: #FFFFFF;
    padding: 4px;
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    min-height: 28px;
    padding: 4px 10px;
    border: none;
    border-left: none;
    border-radius: 4px;
    color: {TEXT_PRIMARY};
    background-color: transparent;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: rgba(37, 99, 235, 0.15);
    color: #FFFFFF;
    border: none;
    border-left: none;
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: rgba(37, 99, 235, 0.25);
    color: #FFFFFF;
    border: none;
    border-left: none;
}}

/* ── Radio & CheckBoxes ───────────────────────────────────────────────────── */
QRadioButton, QCheckBox {{
    background: transparent;
    color: {TEXT_PRIMARY};
    spacing: 8px;
    font-size: 12px;
}}

QRadioButton::indicator, QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background-color: rgba(14, 16, 22, 0.8);
    border-radius: 4px;
}}

QRadioButton::indicator {{
    border-radius: 8px;
}}

QRadioButton::indicator:hover, QCheckBox::indicator:hover {{
    border-color: {ACCENT_BLUE};
}}

QRadioButton::indicator:checked, QCheckBox::indicator:checked {{
    background-color: {ACCENT_BLUE_DARK};
    border-color: {ACCENT_BLUE};
}}

/* ── Context Menu (QMenu) ─────────────────────────────────────────────────── */
QMenu {{
    background-color: rgba(14, 16, 23, 0.96);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 6px;
}}

QMenu::item {{
    padding: 6px 20px 6px 12px;
    border-radius: 4px;
    color: {TEXT_PRIMARY};
    font-size: 12px;
}}

QMenu::item:selected {{
    background-color: rgba(37, 99, 235, 0.25);
    color: #FFFFFF;
}}

QMenu::separator {{
    height: 1px;
    background-color: {BORDER_SUBTLE};
    margin: 4px 6px;
}}

/* ── ToolTips ─────────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: rgba(12, 14, 18, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 5px 9px;
    font-size: 11px;
}}

/* ── Status Bar ───────────────────────────────────────────────────────────── */
#StatusBar {{
    background-color: transparent;
    border-top: 1px solid {BORDER_SUBTLE};
    padding: 4px 12px;
    color: {TEXT_SECONDARY};
    font-size: 11px;
}}
"""


# ── Native Windows Icon Resolution (QFileIconProvider via Windows Shell Engine) ─
ASSETS_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"
ICO_PATH = ASSETS_DIR / "Meyaki.ico"

_app_icon = None
_icon_pix_cache: dict[int, QPixmap] = {}
_exe_icon_cache: dict[str, QIcon] = {}
_generic_exe_icon: QIcon | None = None
_icon_provider: QFileIconProvider | None = None
_icon_lock = threading.Lock()


def get_app_icon() -> QIcon:
    """ProcessX application branding icon (Meyaki.ico). For app window & tray only."""
    global _app_icon
    if _app_icon is None:
        if ICO_PATH.exists():
            _app_icon = QIcon(str(ICO_PATH))
        else:
            _app_icon = QIcon()
    return _app_icon


def get_app_pixmap(size: int = 24) -> QPixmap:
    if size not in _icon_pix_cache:
        pix = get_app_icon().pixmap(size, size)
        _icon_pix_cache[size] = pix
    return _icon_pix_cache[size]


get_meyaki_qicon = get_app_icon
get_meyaki_pixmap = get_app_pixmap


def _get_icon_provider() -> QFileIconProvider:
    global _icon_provider
    if _icon_provider is None:
        _icon_provider = QFileIconProvider()
    return _icon_provider


def get_generic_exe_icon(size: int = 16) -> QIcon:
    """
    Returns the Windows OS native generic application icon dynamically.
    Uses QFileIconProvider with dummy.exe (matching Task Manager and Process Lasso).
    Never falls back to Meyaki.ico.
    """
    global _generic_exe_icon
    if _generic_exe_icon is None or _generic_exe_icon.isNull():
        provider = _get_icon_provider()
        ico = provider.icon(QFileInfo("dummy.exe"))
        if ico and not ico.isNull():
            _generic_exe_icon = ico
        else:
            return QIcon()
    return _generic_exe_icon


def resolve_process_icon(name: str, exe_path: str = None, size: int = 16) -> QIcon:
    """
    Robust 100% dynamic process icon resolver matching Process Lasso and Task Manager:
    1. If a valid executable file exists at exe_path, extract its authentic native icon via QFileIconProvider.
    2. Fallback to Windows OS native generic executable icon (dummy.exe) for pseudo-processes
       without real files (System Idle Process, System, Registry, Memory Compression, Secure System, etc.)
       or inaccessible processes.
    Aggressively caches by path and name fallback to prevent GDI/handle leaks and disk churn.
    Never falls back to Meyaki.ico.
    """
    key = ""
    if exe_path:
        key = os.path.normcase(os.path.abspath(exe_path)) if os.path.isabs(exe_path) else os.path.normcase(exe_path)
    elif name:
        key = f"proc_name:{name.lower()}"

    if key:
        with _icon_lock:
            if key in _exe_icon_cache:
                cached = _exe_icon_cache[key]
                if not cached.isNull():
                    return cached
                _exe_icon_cache.pop(key, None)

    if exe_path and os.path.isfile(key):
        try:
            provider = _get_icon_provider()
            ico = provider.icon(QFileInfo(key))
            if ico and not ico.isNull():
                with _icon_lock:
                    _exe_icon_cache[key] = ico
                    if len(_exe_icon_cache) > 2048:
                        _exe_icon_cache.pop(next(iter(_exe_icon_cache)))
                return ico
        except Exception:
            pass

    # Fallback to generic exe icon and cache it so we do not hit disk/provider repeatedly
    gen_ico = get_generic_exe_icon(size=size)
    if key and gen_ico and not gen_ico.isNull():
        with _icon_lock:
            _exe_icon_cache[key] = gen_ico
    return gen_ico



def make_btn(
    text: str,
    parent=None,
    obj_name: str = "",
    on_click=None,
    width: int = None,
    cursor=None,
) -> QPushButton:
    """Helper to create a styled QPushButton with common attributes."""
    btn = QPushButton(text, parent)
    if obj_name:
        btn.setObjectName(obj_name)
    if width is not None:
        btn.setFixedWidth(width)
    if cursor is not None:
        btn.setCursor(cursor)
    if on_click is not None:
        btn.clicked.connect(on_click)
    return btn


def make_action_row(
    *buttons: QWidget,
    leading_widgets: list[QWidget] | None = None,
    stretch_middle: bool = True,
) -> QHBoxLayout:
    """Helper to assemble dialog bottom action rows with consistent spacing and stretch."""
    row = QHBoxLayout()
    if leading_widgets:
        for w in leading_widgets:
            row.addWidget(w)
    if stretch_middle:
        row.addStretch()
    for b in buttons:
        row.addWidget(b)
    return row


# Vector Window Controls
class WindowControlButton(QPushButton):
    def __init__(self, btn_type: str, parent=None):
        super().__init__(parent)
        self.btn_type = btn_type
        self._is_maximized = False
        self.setFixedSize(34, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_maximized(self, is_max: bool):
        if self._is_maximized != is_max:
            self._is_maximized = is_max
            self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        is_hover = self.underMouse()
        is_down = self.isDown()

        if self.btn_type == "close":
            if is_down:
                painter.fillRect(self.rect(), QColor("#BE123C"))
            elif is_hover:
                painter.fillRect(self.rect(), QColor("#E11D48"))
        else:
            if is_down:
                painter.fillRect(self.rect(), QColor(255, 255, 255, 30))
            elif is_hover:
                painter.fillRect(self.rect(), QColor(255, 255, 255, 18))

        pen_color = QColor("#FFFFFF") if (is_hover or is_down) else QColor("#CBD5E1")
        pen = QPen(pen_color, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        cx = round(self.width() / 2.0)
        cy = round(self.height() / 2.0)

        if self.btn_type == "min":
            painter.drawLine(QPointF(cx - 5.0, cy), QPointF(cx + 5.0, cy))
        elif self.btn_type == "max":
            if self._is_maximized:
                path = QPainterPath()
                path.moveTo(cx - 1.5, cy - 4.5)
                path.lineTo(cx + 4.5, cy - 4.5)
                path.lineTo(cx + 4.5, cy + 1.5)
                path.lineTo(cx + 1.5, cy + 1.5)
                painter.drawPath(path)
                painter.drawRect(QRectF(cx - 4.5, cy - 1.5, 6.0, 6.0))
            else:
                painter.drawRect(QRectF(cx - 4.5, cy - 4.5, 9.0, 9.0))
        elif self.btn_type == "close":
            painter.drawLine(QPointF(cx - 4.5, cy - 4.5), QPointF(cx + 4.5, cy + 4.5))
            painter.drawLine(QPointF(cx - 4.5, cy + 4.5), QPointF(cx + 4.5, cy - 4.5))

class CrispRadioButton(QRadioButton):
    """
    Crisp vector radio button with antialiased indicators:
    - 16px geometric circle drawn with sub-pixel precision on QRectF(1.5, (height - 16) / 2.0, 16.0, 16.0)
    - Smooth inner dot when selected
    - Accurate sizeHint: indicator_diameter (18px) + spacing (8px) + text_width + extra_padding (12px)
    - Zero label clipping and zero background bleeding
    """
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(QFont("Segoe UI Variable Text", 11))
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        font = self.font()
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(self.text()) if self.text() else 0
        w = 18 + 8 + text_w + 14
        h = max(28, fm.height() + 8)
        return QSize(w, h)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        is_checked = self.isChecked()
        is_hover = self.underMouse()
        h = float(self.height())

        # Exact 16x16 geometric circle on QRectF(1.5, (height - 16.0) / 2.0, 16.0, 16.0)
        ind_rect = QRectF(1.5, (h - 16.0) / 2.0, 16.0, 16.0)

        # Outer circle
        if is_checked:
            pen = QPen(QColor(ACCENT_BLUE), 1.0)
            brush = QBrush(QColor("#0F172A"))
        elif is_hover:
            pen = QPen(QColor("#60A5FA"), 1.0)
            brush = QBrush(QColor("#1E293B"))
        else:
            pen = QPen(QColor("#475569"), 1.0)
            brush = QBrush(QColor("#1E293B"))

        painter.setPen(pen)
        painter.setBrush(brush)
        painter.drawEllipse(ind_rect)

        # Inner dot when checked
        if is_checked:
            dot_center = ind_rect.center()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#3B82F6")))
            painter.drawEllipse(dot_center, 4.0, 4.0)

            # Center white dot for crisp contrast
            painter.setBrush(QBrush(QColor("#FFFFFF")))
            painter.drawEllipse(dot_center, 1.8, 1.8)

        # Text label — transparent background, never clips text
        text = self.text()
        if text:
            text_x = 18.0 + 8.0
            avail_w = max(0.0, float(self.width()) - text_x)
            text_rect = QRectF(text_x, 0.0, avail_w, h)
            font = self.font()
            font.setBold(is_checked)
            painter.setFont(font)
            painter.setPen(QColor("#FFFFFF") if is_checked else QColor("#E2E8F0"))
            painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)


# ── Crisp Vector Checkbox ────────────────────────────────────────────────────
class CrispCheckBox(QCheckBox):
    """
    Crisp vector checkbox with antialiased indicators:
    - 16px rounded square (4px radius) on sub-pixel grid
    - Solid #2563EB fill when checked with sharp white checkmark (✓) inside
    - #1E293B fill with #475569 border when unchecked
    - Accurate sizeHint preventing text truncation
    """
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(QFont("Segoe UI Variable Text", 11))
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        font = self.font()
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(self.text()) if self.text() else 0
        w = 18 + 8 + text_w + 14
        h = max(28, fm.height() + 8)
        return QSize(w, h)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        is_checked = self.isChecked()
        is_hover = self.underMouse()
        h = float(self.height())

        ind_rect = QRectF(1.5, (h - 16.0) / 2.0, 16.0, 16.0)
        radius = 4.0

        if is_checked:
            painter.setPen(QPen(QColor(ACCENT_BLUE), 1.0))
            painter.setBrush(QBrush(QColor(ACCENT_BLUE_DARK)))
            painter.drawRoundedRect(ind_rect, radius, radius)

            # Sharp crisp vector checkmark (✓)
            path = QPainterPath()
            rx = ind_rect.left()
            ry = ind_rect.top()
            path.moveTo(rx + 3.5, ry + 8.0)
            path.lineTo(rx + 6.5, ry + 11.5)
            path.lineTo(rx + 12.5, ry + 4.5)

            check_pen = QPen(QColor("#FFFFFF"), 1.8)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.strokePath(path, check_pen)

        else:
            border_color = QColor("#60A5FA") if is_hover else QColor("#475569")
            painter.setPen(QPen(border_color, 1.0))
            painter.setBrush(QBrush(QColor("#1E293B")))
            painter.drawRoundedRect(ind_rect, radius, radius)

        # Text label
        text = self.text()
        if text:
            text_x = 18.0 + 8.0
            avail_w = max(0.0, float(self.width()) - text_x)
            text_rect = QRectF(text_x, 0.0, avail_w, h)
            font = self.font()
            font.setBold(is_checked)
            painter.setFont(font)
            painter.setPen(QColor("#FFFFFF") if is_checked else QColor("#E2E8F0"))
            painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)


# ── NoScroll / Crisp Vector ComboBox ──────────────────────────────────────────
class NoScrollComboBox(QComboBox):
    """
    Seamless rounded combobox with clean vector chevron-down (⌄) icon on the right.
    Sub-pixel anti-aliased 1px border and 6px border-radius matching the design system.
    ElideNone popup view preventing text truncation.
    Filters mouse wheel events to prevent accidental item switching and unwanted focus glow when closed.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setMinimumWidth(260)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._clicked_focus = False
        self.setFont(QFont("Segoe UI Variable Text", 10))

        # Ensure popup view does not elide text and has sufficient width
        popup_view = self.view()
        if popup_view:
            popup_view.setTextElideMode(Qt.TextElideMode.ElideNone)
            popup_view.setMinimumWidth(260)

    def mousePressEvent(self, event):
        self._clicked_focus = True
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        self._clicked_focus = False
        super().focusOutEvent(event)

    def sizeHint(self) -> QSize:
        font = self.font()
        fm = QFontMetrics(font)
        max_w = 0
        for i in range(self.count()):
            max_w = max(max_w, fm.horizontalAdvance(self.itemText(i)))
        w = max(260, max_w + 44)
        return QSize(w, 34)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def wheelEvent(self, event):
        # Only allow wheel interaction if the popup dropdown list is open and visible
        if self.view() and self.view().isVisible():
            super().wheelEvent(event)
        else:
            # Prevent acquiring or retaining focus border when scrolling past
            if not self._clicked_focus:
                self.clearFocus()
            event.ignore()  # Pass the wheel scroll event to the parent scroll area

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        is_hover = self.underMouse()
        is_open = self.view().isVisible() if self.view() else False
        has_active_focus = (self.hasFocus() and self._clicked_focus)

        # Background rounded rectangle: half-pixel offset for dead-center 1px border
        border_col = QColor(ACCENT_BLUE) if (is_open or has_active_focus) else (QColor(255, 255, 255, 41) if is_hover else QColor(255, 255, 255, 20))
        bg_col = QColor("#12151D") if is_hover else QColor("#0E1016")

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(border_col, 1.0))
        painter.setBrush(QBrush(bg_col))
        painter.drawRoundedRect(rect, 6.0, 6.0)

        # Selected item text
        text = self.currentText()
        if text:
            text_rect = QRectF(12.0, 0.0, max(0.0, float(self.width()) - 36.0), float(self.height()))
            painter.setFont(self.font())
            painter.setPen(QColor(TEXT_PRIMARY))
            painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)

        # Clean vector chevron-down icon (⌄)
        cx = float(self.width()) - 16.0
        cy = float(self.height()) / 2.0
        chevron = QPainterPath()
        chevron.moveTo(cx - 4.5, cy - 2.0)
        chevron.lineTo(cx, cy + 2.5)
        chevron.lineTo(cx + 4.5, cy - 2.0)

        chev_pen = QPen(QColor("#FFFFFF") if is_hover else QColor("#94A3B8"), 1.5)
        chev_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        chev_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(chevron, chev_pen)


class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._thumb_position = 1.0 if checked else 0.0
        self.setFixedSize(46, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim = QPropertyAnimation(self, b"thumb_position", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool, animated: bool = True):
        if self._checked != checked:
            self._checked = checked
            if animated:
                self._anim.stop()
                self._anim.setStartValue(self._thumb_position)
                self._anim.setEndValue(1.0 if checked else 0.0)
                self._anim.start()
            else:
                self._thumb_position = 1.0 if checked else 0.0
                self.update()
            self.toggled.emit(self._checked)

    def get_thumb_position(self) -> float:
        return self._thumb_position

    def set_thumb_position(self, pos: float):
        self._thumb_position = pos
        self.update()

    thumb_position = pyqtProperty(float, get_thumb_position, set_thumb_position)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
            event.accept()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = float(self.width())
        height = float(self.height())
        radius = height / 2.0

        # Background track color interpolation
        if self._checked:
            track_color = QColor(ACCENT_BLUE_DARK)
            border_color = QColor(ACCENT_BLUE)
        else:
            track_color = QColor(30, 41, 59)
            border_color = QColor(71, 85, 105)

        track_rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(border_color, 1.0))
        painter.setBrush(QBrush(track_color))
        painter.drawRoundedRect(track_rect, radius, radius)

        # Thumb circle
        thumb_size = height - 8.0
        min_x = 4.0
        max_x = width - thumb_size - 4.0
        thumb_x = min_x + (max_x - min_x) * self._thumb_position
        thumb_y = 4.0

        thumb_rect = QRectF(thumb_x, thumb_y, thumb_size, thumb_size)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.drawEllipse(thumb_rect)


# ── Modern Segmented Control Container ───────────────────────────────────────
class SegmentedControl(QFrame):
    """
    Modern iOS/macOS dark glass segmented tab button bar:
    - Container: Obsidian background #0E1117, 1px border rgba(255, 255, 255, 0.08), border-radius 9px, padding 4px.
    - Segment buttons: #94A3B8 text, font-size 12px, font-weight 600, border-radius 7px.
    - Active segment: Solid #2563EB with electric blue border #3B82F6, bright #FFFFFF bold text.
    - Smooth interactive transitions with mutual exclusion via QButtonGroup.
    """
    valueChanged = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SegmentedControl")
        self.setStyleSheet("""
            QFrame#SegmentedControl {
                background-color: #0E1117;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 9px;
                padding: 4px;
            }
            QPushButton.segmented-btn {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 7px;
                color: #94A3B8;
                font-size: 12px;
                font-weight: 600;
                padding: 7px 14px;
                min-height: 28px;
            }
            QPushButton.segmented-btn:hover:!checked {
                background-color: rgba(255, 255, 255, 0.06);
                color: #F1F5F9;
            }
            QPushButton.segmented-btn:checked {
                background-color: #2563EB;
                border: 1px solid #3B82F6;
                color: #FFFFFF;
                font-weight: 700;
            }
        """)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(5)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = []  # list of tuples: (canonical_key, QPushButton, value)
        self._group.buttonClicked.connect(self._on_button_clicked)

    def add_segment(self, label: str, value, key: str = "") -> QPushButton:
        btn = QPushButton(label, self)
        btn.setProperty("class", "segmented-btn")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._group.addButton(btn)
        self._layout.addWidget(btn)
        c_key = key or (str(value) if value is not None else label)
        self._buttons.append((c_key, btn, value))
        return btn

    def _on_button_clicked(self, clicked_btn):
        for key, btn, val in self._buttons:
            if btn == clicked_btn:
                self.valueChanged.emit(val)
                break

    def set_value(self, target_val):
        for key, btn, val in self._buttons:
            if val == target_val or str(val).lower() == str(target_val).lower() or key == target_val:
                btn.setChecked(True)
                return
        if self._buttons:
            self._buttons[0][1].setChecked(True)

    def get_value(self):
        checked_btn = self._group.checkedButton()
        for key, btn, val in self._buttons:
            if btn == checked_btn:
                return val
        return None

    def get_selected_key(self) -> str:
        checked_btn = self._group.checkedButton()
        for key, btn, val in self._buttons:
            if btn == checked_btn:
                return key
        return ""

    def update_segment_label(self, key: str, new_label: str):
        for k, btn, val in self._buttons:
            if k == key:
                btn.setText(new_label)
                break

    update_label = update_segment_label


# ── Interactive CPU Core Chip Button ─────────────────────────────────────────
class CoreChip(QPushButton):
    """
    Compact CPU core chip toggle button:
    - Clickable toggle button (height: 36px, border-radius: 7px).
    - Enabled/Selected: Background rgba(37, 99, 235, 0.20), border 1px solid #3B82F6, text #60A5FA with ✓ indicator.
    - Disabled/Excluded: Background #0E1117, border 1px solid rgba(255, 255, 255, 0.06), text #64748B.
    """
    def __init__(self, core_index: int, parent=None):
        super().__init__(parent)
        self.core_index = core_index
        self.setCheckable(True)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("""
            QPushButton {
                background-color: #0E1117;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 7px;
                color: #64748B;
                font-size: 12px;
                font-weight: 600;
                padding: 2px 10px;
            }
            QPushButton:hover:!checked {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.12);
                color: #94A3B8;
            }
            QPushButton:checked {
                background-color: rgba(37, 99, 235, 0.20);
                border: 1px solid #3B82F6;
                color: #60A5FA;
                font-weight: 700;
            }
            QPushButton:checked:hover {
                background-color: rgba(37, 99, 235, 0.28);
                border: 1px solid #60A5FA;
                color: #93C5FD;
            }
        """)
        self._update_text()
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool):
        self._update_text()

    def _update_text(self):
        prefix = "✓ CPU" if self.isChecked() else "CPU"
        self.setText(f"{prefix} {self.core_index}")

    _sync_text = _update_text


# Window Containers
class RootFrame(QFrame):
    def __init__(self, parent=None, radius: float = 8.0):
        super().__init__(parent)
        self.setObjectName("RootFrame")
        self.radius = radius
        self.is_maximized = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.is_maximized:
            painter.fillRect(self.rect(), QColor(BG_OBSIDIAN))
        else:
            rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
            path = QPainterPath()
            path.addRoundedRect(rect, self.radius, self.radius)
            painter.fillPath(path, QColor(BG_OBSIDIAN))
            painter.strokePath(path, QPen(QColor(255, 255, 255, 20), 1.0))


class DialogTitleBar(QWidget):
    """
    Custom dark titlebar for frameless dialogs.
    Features Meyaki icon, title label, and crisp vector close button with drag support.
    """
    def __init__(self, parent_dialog: QDialog, title: str = ""):
        super().__init__(parent_dialog)
        self.dialog = parent_dialog
        self.setObjectName("DialogTitleBar")
        self.setFixedHeight(40)
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 8, 4)
        layout.setSpacing(8)

        # Icon with high-DPI crisp rendering
        self.icon_label = QLabel(self)
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        phys_size = int(round(20 * dpr))
        pix = get_app_icon().pixmap(phys_size, phys_size)
        pix.setDevicePixelRatio(dpr)
        self.icon_label.setPixmap(pix)
        self.icon_label.setFixedSize(20, 20)
        layout.addWidget(self.icon_label)

        # Title
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("DialogTitleLabel")
        self.title_label.setFont(get_ui_font(10, weight=600))
        self.title_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: 600; font-size: 13px;")
        layout.addWidget(self.title_label)

        layout.addStretch()

        # Vector close button
        self.btn_close = WindowControlButton("close", self)
        self.btn_close.clicked.connect(self.dialog.reject)
        layout.addWidget(self.btn_close)

    def set_title(self, title: str):
        self.title_label.setText(title)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.dialog.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.dialog.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class FramelessDialog(QDialog):
    """
    Base frameless dialog with custom dark title bar and rounded corners.
    """
    def __init__(self, parent=None, title: str = ""):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Root Frame
        self.root_frame = RootFrame(self, radius=8.0)
        self.root_frame.setStyleSheet(
            f"#DialogTitleBar {{"
            f"    background: transparent;"
            f"    border: none;"
            f"    border-bottom: 1px solid {BORDER_SUBTLE};"
            f"}}"
        )

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(self.root_frame)

        frame_layout = QVBoxLayout(self.root_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        # Title bar
        self.dialog_title_bar = DialogTitleBar(self, title=title)
        self.title_bar = self.dialog_title_bar
        self.btn_close = self.dialog_title_bar.btn_close
        frame_layout.addWidget(self.dialog_title_bar)
        if title:
            super().setWindowTitle(title)

        # Body Container
        self.body_widget = QWidget(self.root_frame)
        self.body_widget.setObjectName("DialogBody")
        self.body_layout = QVBoxLayout(self.body_widget)
        self.body_layout.setContentsMargins(18, 14, 18, 16)
        self.body_layout.setSpacing(12)
        frame_layout.addWidget(self.body_widget, 1)

    def setWindowTitle(self, title: str):
        super().setWindowTitle(title)
        if hasattr(self, "dialog_title_bar"):
            self.dialog_title_bar.set_title(title)

    def showEvent(self, event):
        super().showEvent(event)
        hwnd = int(self.winId())
        apply_dwm_glass(hwnd, backdrop_type=3, dark=True, rounded=True)


class LanguageToggle(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LangToggleContainer")
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.btn_en = QPushButton("EN", self)
        self.btn_en.setProperty("class", "LangToggleBtn")
        self.btn_en.setFixedSize(28, 22)
        self.btn_en.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_en.clicked.connect(lambda: I18N.set_language("en"))
        layout.addWidget(self.btn_en)

        self.btn_vi = QPushButton("VI", self)
        self.btn_vi.setProperty("class", "LangToggleBtn")
        self.btn_vi.setFixedSize(28, 22)
        self.btn_vi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_vi.clicked.connect(lambda: I18N.set_language("vi"))
        layout.addWidget(self.btn_vi)

        self.update_active(I18N.current_language)
        I18N.language_changed.connect(self.update_active)

    def update_active(self, lang: str):
        is_vi = (lang == "vi")
        self.btn_vi.setProperty("active", "true" if is_vi else "false")
        self.btn_en.setProperty("active", "false" if is_vi else "true")
        self.btn_vi.style().unpolish(self.btn_vi)
        self.btn_vi.style().polish(self.btn_vi)
        self.btn_en.style().unpolish(self.btn_en)
        self.btn_en.style().polish(self.btn_en)
        self.btn_vi.update()
        self.btn_en.update()

    def sync_active(self, lang: str):
        self.update_active(lang)


class CustomTitleBar(QWidget):
    search_changed = pyqtSignal(str)

    def __init__(self, parent_window, title: str = "ProcessX", version: str = "v2.0"):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.setObjectName("TitleBar")
        self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 8, 4)
        layout.setSpacing(10)

        # ── Left: Meyaki Icon + Title + Compact Version Badge
        self.icon_label = QLabel(self)
        self.icon_label.setPixmap(get_app_pixmap(24))
        self.icon_label.setFixedSize(24, 24)
        layout.addWidget(self.icon_label)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("TitleLabel")
        layout.addWidget(self.title_label)

        self.version_badge = QLabel(version, self)
        self.version_badge.setObjectName("VersionBadge")
        self.version_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_badge.setFixedHeight(20)
        layout.addWidget(self.version_badge)

        layout.addSpacing(12)

        # ── Center: Search Bar
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText(tr("search_placeholder"))
        self.search_input.setFixedWidth(290)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.search_changed.emit)
        layout.addWidget(self.search_input)

        layout.addStretch()

        # ── Right: Language Switcher UI (Immediately left of window controls)
        self.lang_toggle = LanguageToggle(self)
        layout.addWidget(self.lang_toggle)

        layout.addSpacing(6)

        # ── Right: Window Controls (Uniform 34x28px, crisp 1.5px vector geometry)
        self.btn_min = WindowControlButton("min", self)
        self.btn_min.setObjectName("TitleBtn")
        self.btn_min.setToolTip(tr("tooltip_minimize"))
        layout.addWidget(self.btn_min)

        self.btn_max = WindowControlButton("max", self)
        self.btn_max.setObjectName("TitleBtn")
        self.btn_max.setToolTip(tr("tooltip_maximize"))
        layout.addWidget(self.btn_max)

        self.btn_close = WindowControlButton("close", self)
        self.btn_close.setObjectName("TitleBtnClose")
        self.btn_close.setToolTip(tr("tooltip_close"))
        layout.addWidget(self.btn_close)

        if self.parent_window:
            self.btn_min.clicked.connect(self.parent_window.showMinimized)
            if hasattr(self.parent_window, "toggle_maximize"):
                self.btn_max.clicked.connect(self.parent_window.toggle_maximize)
            else:
                self.btn_max.clicked.connect(self.parent_window.showMaximized)
            self.btn_close.clicked.connect(self.parent_window.close)

            if hasattr(self.parent_window, "window_maximized_changed"):
                self.parent_window.window_maximized_changed.connect(self.update_max_button)

        I18N.language_changed.connect(self.retranslate_ui)

    def retranslate_ui(self, lang: str = ""):
        self.search_input.setPlaceholderText(tr("search_placeholder"))
        self.btn_min.setToolTip(tr("tooltip_minimize"))
        is_max = self.parent_window.isMaximized() if self.parent_window else False
        self.btn_max.setToolTip(tr("tooltip_restore") if is_max else tr("tooltip_maximize"))
        self.btn_close.setToolTip(tr("tooltip_close"))

    def update_max_button(self, is_maximized: bool):
        self.btn_max.set_maximized(is_maximized)
        self.btn_max.setToolTip(tr("tooltip_restore") if is_maximized else tr("tooltip_maximize"))

    def set_maximized(self, is_maximized: bool):
        self.update_max_button(is_maximized)

    def update_max_state(self, is_max: bool):
        self.update_max_button(is_max)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            if child in (self, self.title_label, self.icon_label, self.version_badge):
                self.parent_window.start_drag()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            if child in (self, self.title_label, self.icon_label, self.version_badge):
                self.parent_window.toggle_maximize()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)


class ActionToolbar(QFrame):
    open_profiles_clicked = pyqtSignal()
    add_rule_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    open_profiles = open_profiles_clicked
    add_rule = add_rule_clicked
    open_settings = settings_clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ActionToolbar")

        self._active_rules = 0
        self._total_rules = 0
        self._proc_groups = 0
        self._is_watcher_active = True
        self._watcher_text = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # ── Left: Primary Action Buttons
        self.btn_profiles = QPushButton(tr("btn_profiles"), self)
        self.btn_profiles.setObjectName("SubtleAccentBtn")
        self.btn_profiles.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.btn_profiles.setToolTip(tr("tooltip_profiles"))
        self.btn_profiles.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_profiles.clicked.connect(self.open_profiles_clicked.emit)
        layout.addWidget(self.btn_profiles)

        self.btn_add = QPushButton(tr("btn_add_profile"), self)
        self.btn_add.setObjectName("AccentBtn")
        self.btn_add.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.btn_add.setToolTip(tr("tooltip_add_profile"))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self.add_rule_clicked.emit)
        layout.addWidget(self.btn_add)

        self.btn_settings = QPushButton(tr("btn_settings"), self)
        self.btn_settings.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.btn_settings.setToolTip(tr("tooltip_settings"))
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self.btn_settings)

        layout.addStretch()

        # ── Right: Live Indicators
        self.metric_rules = QLabel("Profiles: 0", self)
        self.metric_rules.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 500;")
        layout.addWidget(self.metric_rules)

        sep = QLabel("•", self)
        sep.setStyleSheet(f"color: {TEXT_MUTED};")
        layout.addWidget(sep)

        self.metric_procs = QLabel(f"{tr('metric_procs')} 0", self)
        self.metric_procs.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 500;")
        layout.addWidget(self.metric_procs)

        sep2 = QLabel("•", self)
        sep2.setStyleSheet(f"color: {TEXT_MUTED};")
        layout.addWidget(sep2)

        # Watcher pulse indicator (Electric blue tint pill)
        self.watcher_badge = QLabel(f"● {tr('watcher_active')}", self)
        self.watcher_badge.setStyleSheet(
            f"color: {TEXT_BLUE}; font-size: 11px; font-weight: 700; "
            f"background-color: {ACCENT_BLUE_DIM}; border: 1px solid {BORDER_BLUE}; "
            f"padding: 3px 8px; border-radius: 6px;"
        )
        layout.addWidget(self.watcher_badge)

        I18N.language_changed.connect(self.retranslate_ui)

    def retranslate_ui(self, lang: str = ""):
        self.btn_profiles.setText(tr("btn_profiles"))
        self.btn_profiles.setToolTip(tr("tooltip_profiles"))

        self.btn_add.setText(tr("btn_add_profile"))
        self.btn_add.setToolTip(tr("tooltip_add_profile"))

        self.btn_settings.setText(tr("btn_settings"))
        self.btn_settings.setToolTip(tr("tooltip_settings"))

        self.update_metrics(self._active_rules, self._total_rules, self._proc_groups)
        self.set_watcher_status(self._is_watcher_active, self._watcher_text)

    def sync_i18n(self):
        self.retranslate_ui()

    def update_metrics(self, active_rules: int, total_rules: int, proc_groups: int):
        self._total_rules = max(0, total_rules)
        self._active_rules = min(max(0, active_rules), self._total_rules)
        self._proc_groups = max(0, proc_groups)
        self.metric_rules.setText(f"{tr('metric_profiles')} <b style='color: {ACCENT_BLUE};'>{self._active_rules}</b> / {self._total_rules}")
        self.metric_procs.setText(f"{tr('metric_procs')} <b style='color: {TEXT_PRIMARY};'>{self._proc_groups}</b>")

    def set_watcher_status(self, is_active: bool, text: str = None):
        self._is_watcher_active = is_active
        self._watcher_text = text
        display_text = text if text else (tr("watcher_active") if is_active else tr("watcher_idle"))
        if is_active:
            self.watcher_badge.setText(f"● {display_text}")
            self.watcher_badge.setStyleSheet(
                f"color: {TEXT_BLUE}; font-size: 11px; font-weight: 700; "
                f"background-color: {ACCENT_BLUE_DIM}; border: 1px solid {BORDER_BLUE}; "
                f"padding: 3px 8px; border-radius: 6px;"
            )
        else:
            self.watcher_badge.setText(f"○ {display_text}")
            self.watcher_badge.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; "
                f"background-color: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08); "
                f"padding: 3px 8px; border-radius: 6px;"
            )

# Process Tree View & Delegate
class ProcessRowDelegate(QStyledItemDelegate):
    """
    Renders:
    1. Base solid background fill (SURFACE_CARD / #0F1117) ensuring zero ghosting or double paint.
    2. Continuous seamless row highlight (hover and selection) across column boundaries.
    3. Process Lasso-style subtle, crisp tree branch guide lines in column 0.
    """
    def __init__(self, tree: QTreeWidget):
        super().__init__(tree)
        self.tree = tree

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        col = index.column()
        total_cols = self.tree.columnCount()
        rect = QRectF(option.rect)

        hovered_item = getattr(self.tree, "hovered_item", None)
        item = self.tree.itemFromIndex(index) if (col == 0 or hovered_item is not None) else None
        is_hovered = (item is not None and item == hovered_item)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

        # For col 0, align left edge flush with section 0 in viewport coordinates
        if col == 0:
            header_x = float(self.tree.header().sectionViewportPosition(0))
            rect.setLeft(header_x)

        # ── 1. Clear Cell Background with Base Surface Color (#0F1117)
        base_bg = QColor(SURFACE_CARD)
        painter.fillRect(rect, base_bg)

        # ── 2. Row Hover & Selection Overlays
        if is_hovered or is_selected:
            if is_selected and is_hovered:
                alpha = 56
            elif is_selected:
                alpha = 46
            else:
                alpha = 26
            bg_color = QColor(37, 99, 235, alpha)

            painter.setBrush(bg_color)
            painter.setPen(Qt.PenStyle.NoPen)
            radius = 6.0

            if col == 0:
                # Rounded left edge
                path = QPainterPath()
                path.moveTo(rect.right(), rect.top())
                path.lineTo(rect.left() + radius, rect.top())
                path.quadTo(rect.left(), rect.top(), rect.left(), rect.top() + radius)
                path.lineTo(rect.left(), rect.bottom() - radius)
                path.quadTo(rect.left(), rect.bottom(), rect.left() + radius, rect.bottom())
                path.lineTo(rect.right(), rect.bottom())
                path.closeSubpath()
                painter.drawPath(path)

                # Left indicator bar (3px ACCENT_BLUE conforming to highlight radius)
                painter.save()
                painter.setClipPath(path)
                painter.fillRect(QRectF(rect.left(), rect.top(), 3.0, rect.height()), QColor(ACCENT_BLUE))
                painter.restore()

            elif col == total_cols - 1:
                # Rounded right edge
                path = QPainterPath()
                path.moveTo(rect.left(), rect.top())
                path.lineTo(rect.right() - radius, rect.top())
                path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + radius)
                path.lineTo(rect.right(), rect.bottom() - radius)
                path.quadTo(rect.right(), rect.bottom(), rect.right() - radius, rect.bottom())
                path.lineTo(rect.left(), rect.bottom())
                path.closeSubpath()
                painter.drawPath(path)

            else:
                painter.fillRect(rect, bg_color)

        # ── 3. Process Lasso Tree Guide Lines (Col 0)
        if col == 0 and item:
            depth = 0
            curr = item.parent()
            ancestors = []
            while curr:
                ancestors.append(curr)
                curr = curr.parent()
            depth = len(ancestors)

            if depth > 0:
                indent_step = float(self.tree.indentation())
                left_start = rect.left() + 10.0
                line_pen = QPen(QColor(148, 163, 184, 52), 1.0)
                painter.setPen(line_pen)

                # Vertical ancestor continuation lines
                for a_idx, anc in enumerate(reversed(ancestors[:-1])):
                    p_anc = anc.parent()
                    if p_anc and (p_anc.indexOfChild(anc) < p_anc.childCount() - 1):
                        x_pos = left_start + a_idx * indent_step + indent_step / 2.0
                        painter.drawLine(QPointF(x_pos, rect.top()), QPointF(x_pos, rect.bottom()))

                # Direct parent connector line
                direct_x = left_start + (depth - 1) * indent_step + indent_step / 2.0
                y_mid = rect.center().y()
                parent_item = item.parent()
                has_next_sibling = parent_item and (parent_item.indexOfChild(item) < parent_item.childCount() - 1)

                y_end = rect.bottom() if has_next_sibling else y_mid
                painter.drawLine(QPointF(direct_x, rect.top()), QPointF(direct_x, y_end))

                # Horizontal connector to the child node
                painter.drawLine(QPointF(direct_x, y_mid), QPointF(direct_x + indent_step * 0.7, y_mid))

        painter.restore()

        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.StateFlag.State_Selected
        opt.state &= ~QStyle.StateFlag.State_MouseOver

        super().paint(painter, opt, index)


class ProcessTreeWidget(QTreeWidget):
    edit_rule_requested = pyqtSignal(str, int, str)   # exe_name, pid, exe_path
    refresh_requested = pyqtSignal()
    scroll_state_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(8)
        self._update_header_labels()

        self.setAnimated(False)
        self.setAlternatingRowColors(False)
        self.setRootIsDecorated(False)
        self.setIndentation(18)
        self.setIconSize(QSize(16, 16))
        self.setUniformRowHeights(True)
        self.setSortingEnabled(False)
        self.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # 1. Pixel-based scrolling
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.viewport().setStyleSheet(f"background-color: {SURFACE_CARD}; background: {SURFACE_CARD};")
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(SURFACE_CARD))
        pal.setColor(QPalette.ColorRole.Window, QColor(SURFACE_CARD))
        self.setPalette(pal)
        self.viewport().setPalette(pal)
        self.viewport().setAutoFillBackground(True)

        self.hovered_item: QTreeWidgetItem | None = None
        self._last_wheel_time: float = 0.0
        self.is_scrolling = False

        v_bar = self.verticalScrollBar()
        v_bar.setSingleStep(32)
        v_bar.valueChanged.connect(self._on_vscroll_changed)

        self.row_delegate = ProcessRowDelegate(self)
        self.setItemDelegate(self.row_delegate)

        # Fonts
        self.ui_font = get_ui_font(10)
        self.bold_ui_font = get_ui_font(10, QFont.Weight.Bold)
        self.mono_font = get_mono_font(9, QFont.Weight.Medium)
        self.setFont(self.ui_font)

        # Header adjustments
        header = self.header()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col_idx in range(1, 8):
            header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

        self.setColumnWidth(1, 75)   # PID
        self.setColumnWidth(2, 80)   # CPU
        self.setColumnWidth(3, 95)   # RAM
        self.setColumnWidth(4, 140)  # CPU Priority (sufficient width for Vietnamese text)
        self.setColumnWidth(5, 115)  # I/O Priority (sufficient width for Vietnamese text)
        self.setColumnWidth(6, 125)  # CPU Sets
        self.setColumnWidth(7, 100)  # Profile Status

        self._icon_cache: OrderedDict[str, QIcon] = OrderedDict()
        self._items_by_pid: dict[int, QTreeWidgetItem] = {}
        self._filter_text = ""
        self._explicitly_collapsed_pids: set[int] = set()

        self.itemDoubleClicked.connect(self._on_double_click)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.itemCollapsed.connect(self._on_item_collapsed)
        self.itemExpanded.connect(self._on_item_expanded)

        I18N.language_changed.connect(self.retranslate_ui)

    def _update_header_labels(self):
        self.setHeaderLabels([
            tr("col_proc_name"),
            tr("col_pid"),
            tr("col_cpu"),
            tr("col_ram"),
            tr("col_cpu_pri"),
            tr("col_io_pri"),
            tr("col_cpu_sets"),
            tr("col_profile"),
        ])

    def retranslate_ui(self, lang: str = ""):
        self._update_header_labels()
        self.refresh_requested.emit()
        self.viewport().update()

    def paintEvent(self, event: QPaintEvent):
        """Paint solid dark background across entire viewport so empty rows are never light gray."""
        painter = QPainter(self.viewport())
        painter.fillRect(event.rect(), QColor(SURFACE_CARD))
        painter.end()
        super().paintEvent(event)

    def updateGeometries(self):
        super().updateGeometries()
        if self.topLevelItemCount() > 0:
            first_item = self.topLevelItem(0)
            h = self.visualItemRect(first_item).height()
            if h > 0 and self.verticalScrollBar().singleStep() != h:
                self.verticalScrollBar().setSingleStep(h)

    def _update_hover_from_cursor(self) -> bool:
        if not self.isVisible():
            return False

        vp = self.viewport()
        vp_pos = vp.mapFromGlobal(QCursor.pos())

        if vp.rect().contains(vp_pos):
            target_item = self.itemAt(vp_pos)
        else:
            target_item = None

        if target_item != self.hovered_item:
            self.hovered_item = target_item
            vp.update()
            return True
        return False

    def _on_vscroll_changed(self, val: int = 0):
        self.is_scrolling = True
        self.scroll_state_changed.emit(True)
        QTimer.singleShot(150, self._stop_scroll)
        self._update_hover_from_cursor()

    def _stop_scroll(self):
        self.is_scrolling = False
        self.scroll_state_changed.emit(False)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self._update_hover_from_cursor()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.hovered_item is not None:
            self.hovered_item = None
            self.viewport().update()

    def wheelEvent(self, event):
        self._last_wheel_time = time.monotonic()
        super().wheelEvent(event)
        self._update_hover_from_cursor()

    def drawBranches(self, painter, rect, index):
        pass

    def _on_item_collapsed(self, item: QTreeWidgetItem):
        pid = item.data(1, Qt.ItemDataRole.UserRole)
        if isinstance(pid, int):
            self._explicitly_collapsed_pids.add(pid)

    def _on_item_expanded(self, item: QTreeWidgetItem):
        pid = item.data(1, Qt.ItemDataRole.UserRole)
        if isinstance(pid, int):
            self._explicitly_collapsed_pids.discard(pid)

    def get_process_icon(self, name: str, exe_path: str = None) -> QIcon:
        clean_path = (exe_path or "").strip()
        if clean_path and os.path.isfile(clean_path):
            cache_id = os.path.normcase(os.path.abspath(clean_path))
        else:
            cache_id = "__generic__"

        if cache_id in self._icon_cache:
            cached = self._icon_cache[cache_id]
            if not cached.isNull():
                self._icon_cache.move_to_end(cache_id)
                return cached
            self._icon_cache.pop(cache_id, None)

        icon = resolve_process_icon(name, clean_path, 16)
        if icon and not icon.isNull():
            self._icon_cache[cache_id] = icon
            if len(self._icon_cache) > 2048:
                self._icon_cache.popitem(last=False)
            return icon
        return get_generic_exe_icon(16)

    def update_snapshot(self, snapshot: list[dict]):
        try:
            vbar = self.verticalScrollBar()
            top_item = None
            top_offset = 0
            scroll_val = vbar.value()
            user_scrolled_recently = (time.monotonic() - getattr(self, "_last_wheel_time", 0.0) < 0.3)
            if scroll_val > 0 and not user_scrolled_recently:
                top_item = self.itemAt(0, 0)
                if top_item:
                    top_offset = self.visualItemRect(top_item).top()

            incoming_pids = set()
            node_map = {}

            def register_nodes(nodes):
                for n in nodes:
                    p_id = n["pid"]
                    incoming_pids.add(p_id)
                    node_map[p_id] = n
                    children = n.get("children", [])
                    if children:
                        register_nodes(children)

            register_nodes(snapshot)

            existing_pids = set(self._items_by_pid.keys())
            dead_pids = existing_pids - incoming_pids
            for d_pid in dead_pids:
                dead_item = self._items_by_pid.pop(d_pid, None)
                if dead_item:
                    if self.hovered_item == dead_item:
                        self.hovered_item = None
                    dead_item.takeChildren()
                    p = dead_item.parent()
                    if p:
                        p.removeChild(dead_item)
                    else:
                        idx = self.indexOfTopLevelItem(dead_item)
                        if idx >= 0:
                            self.takeTopLevelItem(idx)

            filter_q = self._filter_text.strip().lower()
            blue_color = QColor(ACCENT_BLUE)
            secondary_color = QColor(TEXT_SECONDARY)
            muted_color = QColor(TEXT_MUTED)
            primary_color = QColor(TEXT_PRIMARY)

            def matches_filter(node: dict) -> bool:
                if not filter_q:
                    return True
                if filter_q in node.get("name", "").lower():
                    return True
                if filter_q in str(node.get("pid", "")):
                    return True
                if filter_q in (node.get("exe_path") or "").lower():
                    return True
                for svc in node.get("services", []):
                    if filter_q in svc.lower():
                        return True
                for child in node.get("children", []):
                    if matches_filter(child):
                        return True
                return False

            def sync_node(node: dict, parent_item: QTreeWidgetItem | None, index_in_parent: int):
                pid = node["pid"]
                name = node["name"]
                exe_path = node.get("exe_path") or ""
                has_rule = node.get("has_rule", False)
                children = node.get("children", [])
                child_count = len(children)
                services = node.get("services", [])
                is_sys = node.get("is_system", False)

                display_name = name
                if services:
                    if len(services) == 1:
                        display_name = f"{name}  [{services[0]}]"
                    elif len(services) <= 2:
                        display_name = f"{name}  [{', '.join(services)}]"
                    else:
                        display_name = f"{name}  [{services[0]} +{len(services)-1} svcs]"

                if child_count > 0:
                    display_name += f" ({child_count})"

                rule_badge = tr("rule_active") if has_rule else tr("rule_none")

                item = self._items_by_pid.get(pid)
                if item is not None:
                    try:
                        _ = item.parent()
                    except RuntimeError:
                        item = None
                        self._items_by_pid.pop(pid, None)

                is_new = (item is None)

                if is_new:
                    item = QTreeWidgetItem()
                    self._items_by_pid[pid] = item
                    item.setData(0, Qt.ItemDataRole.UserRole, name)
                    item.setData(1, Qt.ItemDataRole.UserRole, pid)
                    item.setData(2, Qt.ItemDataRole.UserRole, exe_path)
                    item.setData(3, Qt.ItemDataRole.UserRole, is_sys)
                    item.setIcon(0, self.get_process_icon(name, exe_path))

                    for c_idx in (1, 2, 3):
                        item.setFont(c_idx, self.mono_font)
                        item.setTextAlignment(c_idx, Qt.AlignmentFlag.AlignCenter)
                    for c_idx in (4, 5, 6, 7):
                        item.setTextAlignment(c_idx, Qt.AlignmentFlag.AlignCenter)

                    if parent_item:
                        parent_item.insertChild(index_in_parent, item)
                    else:
                        self.insertTopLevelItem(index_in_parent, item)
                else:
                    curr_parent = item.parent()
                    curr_tree = item.treeWidget()
                    if curr_parent != parent_item or (parent_item is None and curr_tree != self):
                        if curr_parent:
                            curr_parent.removeChild(item)
                        elif curr_tree == self:
                            old_idx = self.indexOfTopLevelItem(item)
                            if old_idx >= 0:
                                self.takeTopLevelItem(old_idx)
                        if parent_item:
                            parent_item.insertChild(index_in_parent, item)
                        else:
                            self.insertTopLevelItem(index_in_parent, item)

                    old_path = item.data(2, Qt.ItemDataRole.UserRole)
                    if old_path != exe_path or item.icon(0).isNull():
                        item.setData(2, Qt.ItemDataRole.UserRole, exe_path)
                        item.setIcon(0, self.get_process_icon(name, exe_path))

                if item.text(0) != display_name:
                    item.setText(0, display_name)
                if item.text(1) != str(pid):
                    item.setText(1, str(pid))
                if item.text(2) != node["cpu_str"]:
                    item.setText(2, node["cpu_str"])
                if item.text(3) != node["ram_str"]:
                    item.setText(3, node["ram_str"])
                pri_disp = tr("val_none") if node["pri_str"] in ("None", "Not Specified") else translate_val(node["pri_str"], "cpu")
                io_disp = tr("val_none") if node["io_str"] in ("None", "Not Specified") else translate_val(node["io_str"], "io")
                aff_disp = tr("val_none") if node["aff_str"] in ("None", "Not Specified") else translate_val(node["aff_str"])
                if item.text(4) != pri_disp:
                    item.setText(4, pri_disp)
                if item.text(5) != io_disp:
                    item.setText(5, io_disp)
                if item.text(6) != aff_disp:
                    item.setText(6, aff_disp)
                if item.text(7) != rule_badge:
                    item.setText(7, rule_badge)

                if has_rule:
                    if item.foreground(0).color() != blue_color:
                        item.setForeground(0, blue_color)
                    if item.foreground(7).color() != blue_color:
                        item.setForeground(7, blue_color)
                    if item.font(7) != self.bold_ui_font:
                        item.setFont(7, self.bold_ui_font)
                else:
                    if item.foreground(7).color() != muted_color:
                        item.setForeground(7, muted_color)
                    if is_sys:
                        if item.foreground(0).color() != secondary_color:
                            item.setForeground(0, secondary_color)
                        if item.font(0) != self.ui_font:
                            item.setFont(0, self.ui_font)
                    else:
                        if item.foreground(0).color() != primary_color:
                            item.setForeground(0, primary_color)
                        if item.font(0) != self.bold_ui_font:
                            item.setFont(0, self.bold_ui_font)

                if child_count > 0:
                    should_expand = pid not in self._explicitly_collapsed_pids
                    if item.isExpanded() != should_expand:
                        item.setExpanded(should_expand)

                if filter_q:
                    should_hide = not matches_filter(node)
                    if item.isHidden() != should_hide:
                        item.setHidden(should_hide)
                elif item.isHidden():
                    item.setHidden(False)

                for c_idx, child_node in enumerate(children):
                    sync_node(child_node, item, c_idx)

            for r_idx, root_node in enumerate(snapshot):
                sync_node(root_node, None, r_idx)

            if top_item and top_item.treeWidget() == self:
                new_top = self.visualItemRect(top_item).top()
                diff = new_top - top_offset
                if diff != 0:
                    vbar.setValue(vbar.value() + diff)

            self._update_hover_from_cursor()
        except Exception as e:
            _log_error("ProcessTreeWidget.update_snapshot", e)

    def set_filter(self, query: str):
        self._filter_text = query

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            curr = self.currentIndex()
            if curr.isValid():
                item = self.itemFromIndex(curr)
                if item:
                    exe_name = item.data(0, Qt.ItemDataRole.UserRole)
                    pid = item.data(1, Qt.ItemDataRole.UserRole)
                    exe_path = item.data(2, Qt.ItemDataRole.UserRole)
                    if exe_name:
                        self.edit_rule_requested.emit(exe_name, pid or 0, exe_path or "")
                        event.accept()
                        return
        super().keyPressEvent(event)

    def _on_double_click(self, item: QTreeWidgetItem, column: int = 0):
        if not item:
            return
        exe_name = item.data(0, Qt.ItemDataRole.UserRole) or ""
        pid = item.data(1, Qt.ItemDataRole.UserRole) or 0
        exe_path = item.data(2, Qt.ItemDataRole.UserRole) or ""
        if exe_name:
            self.edit_rule_requested.emit(exe_name, pid or 0, exe_path or "")

    def _show_context_menu(self, pos: QPoint):
        item = self.itemAt(pos)
        if not item:
            return

        exe_name = item.data(0, Qt.ItemDataRole.UserRole) or ""
        pid = item.data(1, Qt.ItemDataRole.UserRole) or 0
        exe_path = item.data(2, Qt.ItemDataRole.UserRole) or ""

        menu = QMenu(self)

        act_edit = menu.addAction(tr("menu_edit_profile", name=exe_name))
        act_edit.triggered.connect(lambda: self.edit_rule_requested.emit(exe_name, pid, exe_path))

        menu.addSeparator()

        act_open_folder = menu.addAction(tr("menu_open_explorer"))
        act_open_folder.setEnabled(bool(exe_path and os.path.exists(exe_path)))
        act_open_folder.triggered.connect(lambda: self._open_in_explorer(exe_path))

        act_copy_path = menu.addAction(tr("menu_copy_path"))
        act_copy_path.setEnabled(bool(exe_path))
        act_copy_path.triggered.connect(lambda: QApplication.clipboard().setText(exe_path))

        # Trim Memory: preserved from Clean
        act_trim = menu.addAction(tr("menu_trim_mem"))
        act_trim.setEnabled(bool(pid))
        act_trim.triggered.connect(lambda: self._trim_mem(pid))

        menu.addSeparator()

        act_kill = menu.addAction(tr("menu_kill_proc"))
        is_crit = is_critical_process(exe_name, pid, exe_path)
        if is_crit:
            act_kill.setEnabled(False)
            act_kill.setText(f"{tr('menu_kill_proc')} (Protected)")
        else:
            act_kill.triggered.connect(lambda: self._confirm_kill_process(exe_name, pid))

        menu.exec(QCursor.pos())

    def _on_context_menu(self, pos: QPoint):
        self._show_context_menu(pos)

    def _trim_mem(self, pid: int):
        if pid:
            trim_process_memory(pid)
            self.refresh_requested.emit()

    def _open_in_explorer(self, exe_path: str):
        if exe_path and os.path.exists(exe_path):
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                subprocess.Popen(["explorer", f"/select,{os.path.normpath(exe_path)}"], creationflags=flags)
            except Exception as e:
                QMessageBox.warning(self, tr("error_title"), tr("error_open_folder", err=e))

    def _confirm_kill_process(self, exe_name: str, pid: int):
        if is_critical_process(exe_name, pid):
            QMessageBox.warning(
                self,
                tr("error_title"),
                f"Cannot terminate protected system process: {exe_name} (PID: {pid})"
            )
            return

        target = f"PID {pid}" if pid else f"all {exe_name}"
        ret = QMessageBox.question(
            self,
            tr("confirm_kill_title"),
            tr("confirm_kill_msg", target=target),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            try:
                if pid:
                    if not kill_process(pid):
                        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, creationflags=flags)
                else:
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                    subprocess.run(["taskkill", "/F", "/IM", exe_name], capture_output=True, creationflags=flags)
                self.refresh_requested.emit()
            except Exception as e:
                QMessageBox.warning(self, tr("error_title"), tr("error_kill_proc", err=e))

# Dialogs
SECTION_HEADER_STYLE = "font-size: 13px; font-weight: 700; color: #F8FAFC; letter-spacing: 0.5px;"
SECTION_DESC_STYLE = f"font-size: 12px; color: {TEXT_SECONDARY}; line-height: 1.4;"
PRESET_BTN_STYLE = f"""
QPushButton {{
    background-color: #0E1117;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 7px;
    color: {TEXT_SECONDARY};
    font-size: 12px;
    font-weight: 600;
    padding: 5px 14px;
    min-height: 28px;
}}
QPushButton:hover {{
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.16);
    color: #FFFFFF;
}}
QPushButton:pressed {{
    background-color: rgba(37, 99, 235, 0.20);
    border: 1px solid #3B82F6;
    color: #60A5FA;
}}
"""
GHOST_BTN_STYLE = f"""
QPushButton {{
    background-color: transparent;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 7px;
    color: {TEXT_SECONDARY};
    font-size: 13px;
    font-weight: 600;
    padding: 6px 16px;
}}
QPushButton:hover {{
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.20);
    color: #FFFFFF;
}}
QPushButton:pressed {{
    background-color: rgba(255, 255, 255, 0.08);
}}
"""

PRI_CONFIG = [
    ("None", "pri_none"),
    ("Idle", "pri_idle"),
    ("Below Normal", "pri_below_normal"),
    ("Normal", "pri_normal"),
    ("Above Normal", "pri_above_normal"),
    ("High", "pri_high"),
    ("Realtime", "pri_realtime"),
]

IO_CONFIG = [
    (-1, "io_none"),
    (0, "io_very_low"),
    (1, "io_low"),
    (2, "io_normal"),
    (3, "io_high"),
]

MEM_CONFIG = [
    (-1, "mem_none"),
    (1, "mem_very_low"),
    (2, "mem_low"),
    (3, "mem_medium"),
    (4, "mem_below_normal"),
    (5, "mem_normal"),
]


class AddRuleDialog(FramelessDialog):
    """
    Frameless modal dialog to input or browse for an EXE file to create a profile.
    """
    def __init__(self, parent=None):
        super().__init__(parent, title=tr("add_dlg_title"))
        self.result_exe = None
        self.result_path = None

        self.setFixedSize(480, 220)

        self._build_ui()
        I18N.language_changed.connect(self.retranslate_ui)

    def _build_ui(self):
        root_layout = self.body_layout
        root_layout.setContentsMargins(18, 10, 18, 16)
        root_layout.setSpacing(12)

        self.lbl_title = QLabel(tr("add_dlg_label"), self)
        self.lbl_title.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY};")
        root_layout.addWidget(self.lbl_title)
        self.lbl_label = self.lbl_title

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.entry = QLineEdit(self)
        self.entry.setPlaceholderText(tr("add_dlg_placeholder"))
        self.entry.returnPressed.connect(self._on_ok)
        input_row.addWidget(self.entry, 1)

        self.btn_browse = QPushButton(tr("add_dlg_browse"), self)
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self._browse_file)
        input_row.addWidget(self.btn_browse)

        root_layout.addLayout(input_row)

        self.path_lbl = QLabel("", self)
        self.path_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        root_layout.addWidget(self.path_lbl)

        root_layout.addStretch()

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)
        btn_bar.addStretch()

        self.btn_cancel = QPushButton(tr("add_dlg_cancel"), self)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        btn_bar.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton(tr("add_dlg_continue"), self)
        self.btn_ok.setObjectName("AccentBtn")
        self.btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ok.clicked.connect(self._on_ok)
        btn_bar.addWidget(self.btn_ok)

        root_layout.addLayout(btn_bar)

    def retranslate_ui(self, lang: str):
        self.setWindowTitle(tr("add_dlg_title"))
        self.lbl_title.setText(tr("add_dlg_label"))
        self.entry.setPlaceholderText(tr("add_dlg_placeholder"))
        self.btn_browse.setText(tr("add_dlg_browse"))
        self.btn_cancel.setText(tr("add_dlg_cancel"))
        self.btn_ok.setText(tr("add_dlg_continue"))
        if self.result_path:
            self.path_lbl.setText(tr("add_dlg_path_prefix", path=self.result_path))

    sync_i18n = retranslate_ui

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("add_dlg_file_dialog_title"), "", tr("add_dlg_file_filter")
        )
        if path:
            self.result_path = path
            exe_name = os.path.basename(path)
            self.entry.setText(exe_name)
            self.path_lbl.setText(tr("add_dlg_path_prefix", path=path))

    _browse = _browse_file

    def _on_ok(self):
        val = self.entry.text().strip()
        if not val:
            QMessageBox.warning(self, tr("error_title"), tr("add_dlg_err_empty"))
            return
        if not val.lower().endswith(".exe"):
            val += ".exe"
        self.result_exe = val
        self.accept()

    _accept_file = _on_ok


class SettingsDialog(FramelessDialog):
    """
    Modern glassmorphic settings modal dialog.
    """
    settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, title=tr("settings_title"))
        self.parent_app = parent
        self.setMinimumSize(620, 410)
        self.resize(620, 410)

        self._build_ui()
        I18N.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui(I18N.current_language)

    def showEvent(self, event):
        super().showEvent(event)
        self.retranslate_ui(I18N.current_language)

    def _build_ui(self):
        root_layout = self.body_layout
        root_layout.setContentsMargins(20, 10, 20, 18)
        root_layout.setSpacing(12)

        # ── General Settings Container Card
        card = QFrame(self)
        card.setObjectName("GlassCard")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(18, 16, 18, 16)
        c_layout.setSpacing(16)

        # Section Heading
        self.lbl_sec_general = QLabel(tr("settings_sec_general"), card)
        self.lbl_sec_general.setStyleSheet("font-size: 11px; font-weight: 700; color: #94A3B8; letter-spacing: 0.5px;")
        c_layout.addWidget(self.lbl_sec_general)

        # 1. Run on Startup
        row_startup = QHBoxLayout()
        row_startup.setSpacing(14)

        info_startup = QVBoxLayout()
        info_startup.setSpacing(2)
        self.lbl_startup_title = QLabel(tr("settings_startup_label"), card)
        self.lbl_startup_title.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY};")
        info_startup.addWidget(self.lbl_startup_title)

        self.lbl_startup_desc = QLabel(tr("settings_startup_desc"), card)
        self.lbl_startup_desc.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        self.lbl_startup_desc.setWordWrap(True)
        info_startup.addWidget(self.lbl_startup_desc)
        row_startup.addLayout(info_startup, 1)

        self.toggle_startup = ToggleSwitch(checked=is_in_startup(), parent=card)
        self.toggle_startup.toggled.connect(self._on_startup_toggled)
        row_startup.addWidget(self.toggle_startup)
        c_layout.addLayout(row_startup)

        # Separator
        sep1 = QFrame(card)
        sep1.setFixedHeight(1)
        sep1.setStyleSheet(f"background-color: {BORDER_SUBTLE};")
        c_layout.addWidget(sep1)

        # 2. Minimize to Tray on Close
        row_tray = QHBoxLayout()
        row_tray.setSpacing(14)

        info_tray = QVBoxLayout()
        info_tray.setSpacing(2)
        self.lbl_tray_title = QLabel(tr("settings_tray_label"), card)
        self.lbl_tray_title.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY};")
        info_tray.addWidget(self.lbl_tray_title)

        self.lbl_tray_desc = QLabel(tr("settings_tray_desc"), card)
        self.lbl_tray_desc.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        self.lbl_tray_desc.setWordWrap(True)
        info_tray.addWidget(self.lbl_tray_desc)
        row_tray.addLayout(info_tray, 1)

        curr_tray = bool(get_setting("minimize_to_tray", True))
        self.toggle_tray = ToggleSwitch(checked=curr_tray, parent=card)
        self.toggle_tray.toggled.connect(self._on_tray_toggled)
        row_tray.addWidget(self.toggle_tray)
        c_layout.addLayout(row_tray)

        # Separator
        sep2 = QFrame(card)
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background-color: {BORDER_SUBTLE};")
        c_layout.addWidget(sep2)

        # 3. Interface Language
        row_lang = QHBoxLayout()
        row_lang.setSpacing(14)

        info_lang = QVBoxLayout()
        info_lang.setSpacing(2)
        self.lbl_lang_title = QLabel(tr("settings_lang_label"), card)
        self.lbl_lang_title.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY};")
        info_lang.addWidget(self.lbl_lang_title)

        self.lbl_lang_desc = QLabel(tr("settings_lang_desc"), card)
        self.lbl_lang_desc.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        self.lbl_lang_desc.setWordWrap(True)
        info_lang.addWidget(self.lbl_lang_desc)
        row_lang.addLayout(info_lang, 1)

        self.combo_lang = NoScrollComboBox(card)
        self.combo_lang.setMinimumWidth(260)
        self.combo_lang.view().setMinimumWidth(260)
        self.combo_lang.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        self.combo_lang.addItem("Tiếng Việt (VI)", "vi")
        self.combo_lang.addItem("English (EN)", "en")
        curr_lang = I18N.current_language
        self.combo_lang.setCurrentIndex(1 if curr_lang == "en" else 0)
        self.combo_lang.currentIndexChanged.connect(self._on_lang_changed)
        row_lang.addWidget(self.combo_lang)
        c_layout.addLayout(row_lang)

        root_layout.addWidget(card)

        # Status feedback label
        self.lbl_status = QLabel("", self)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {ACCENT_BLUE};")
        root_layout.addWidget(self.lbl_status)

        # ── Bottom Action Bar
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        self.btn_close = QPushButton(tr("settings_btn_close"), self)
        self.btn_close.setObjectName("AccentBtn")
        self.btn_close.setFixedWidth(100)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        btn_bar.addWidget(self.btn_close)

        root_layout.addLayout(btn_bar)

    def _on_startup_toggled(self, checked: bool):
        if checked:
            ok, msg = add_to_startup()
            set_setting("run_on_startup", True)
            self.lbl_status.setText(msg or tr("settings_status_saved"))
        else:
            ok, msg = remove_from_startup()
            set_setting("run_on_startup", False)
            self.lbl_status.setText(tr("settings_status_saved"))
        self.settings_changed.emit()

    def _on_tray_toggled(self, checked: bool):
        set_setting("minimize_to_tray", checked)
        self.lbl_status.setText(tr("settings_status_saved"))
        self.settings_changed.emit()

    def _on_lang_changed(self, index: int):
        lang = self.combo_lang.itemData(index)
        if lang:
            I18N.set_language(lang)
            self.lbl_status.setText(tr("settings_status_saved"))
            self.settings_changed.emit()

    def retranslate_ui(self, lang: str = None):
        if not lang:
            lang = I18N.current_language
        self.setWindowTitle(tr("settings_title"))
        self.lbl_sec_general.setText(tr("settings_sec_general"))
        self.lbl_startup_title.setText(tr("settings_startup_label"))
        self.lbl_startup_desc.setText(tr("settings_startup_desc"))
        self.lbl_tray_title.setText(tr("settings_tray_label"))
        self.lbl_tray_desc.setText(tr("settings_tray_desc"))
        self.lbl_lang_title.setText(tr("settings_lang_label"))
        self.lbl_lang_desc.setText(tr("settings_lang_desc"))
        self.btn_close.setText(tr("settings_btn_close"))
        if self.lbl_status.text():
            self.lbl_status.setText(tr("settings_status_saved"))

        # Sync language combo without triggering event
        self.combo_lang.blockSignals(True)
        self.combo_lang.setCurrentIndex(1 if lang == "en" else 0)
        self.combo_lang.blockSignals(False)

    sync_i18n = retranslate_ui


class ProfilesManagerDialog(FramelessDialog):
    """
    Profiles Management window with table view, search filter, import, export, delete, and edit.
    """
    rules_modified = pyqtSignal()

    def __init__(self, parent, rules: dict):
        super().__init__(parent, title=tr("pm_title"))
        self.parent_app = parent
        self.rules = rules

        self.setMinimumSize(880, 500)
        self.resize(960, 540)

        self._build_ui()
        self.populate_table()

        I18N.language_changed.connect(self.retranslate_ui)

    def _build_ui(self):
        root_layout = self.body_layout
        root_layout.setContentsMargins(18, 10, 18, 16)
        root_layout.setSpacing(12)

        # ── Top Bar: Search Filter & Add
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText(tr("pm_search_placeholder"))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.search_input, 1)
        self.search = self.search_input

        self.btn_add = QPushButton(tr("btn_add_profile"), self)
        self.btn_add.setObjectName("AccentBtn")
        self.btn_add.clicked.connect(self._add_rule)
        top_bar.addWidget(self.btn_add)

        root_layout.addLayout(top_bar)

        # ── Profiles Table
        self.table = QTableWidget(self)
        self.table.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.table.viewport().setStyleSheet(f"background-color: {SURFACE_CARD}; background: {SURFACE_CARD};")
        t_pal = self.table.palette()
        t_pal.setColor(QPalette.ColorRole.Base, QColor(SURFACE_CARD))
        t_pal.setColor(QPalette.ColorRole.Window, QColor(SURFACE_CARD))
        self.table.setPalette(t_pal)
        self.table.viewport().setPalette(t_pal)
        self.table.setColumnCount(6)
        self._update_table_headers()
        self.table.setIconSize(QSize(16, 16))
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)

        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 160)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 110)

        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        root_layout.addWidget(self.table, 1)

        # ── Bottom Action Toolbar
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        self.btn_import = QPushButton(tr("pm_btn_import"), self)
        self.btn_import.clicked.connect(self._import_profiles)
        btn_bar.addWidget(self.btn_import)

        self.btn_export = QPushButton(tr("pm_btn_export"), self)
        self.btn_export.clicked.connect(self._export_profiles)
        btn_bar.addWidget(self.btn_export)

        self.btn_delete = QPushButton(tr("pm_btn_delete"), self)
        self.btn_delete.setObjectName("DangerBtn")
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_bar.addWidget(self.btn_delete)
        self.btn_del = self.btn_delete

        btn_bar.addStretch()

        self.btn_close = QPushButton(tr("pm_btn_close"), self)
        self.btn_close.clicked.connect(self.close)
        btn_bar.addWidget(self.btn_close)

        root_layout.addLayout(btn_bar)

    def _update_table_headers(self):
        self.table.setHorizontalHeaderLabels([
            tr("pm_col_exe"),
            tr("pm_col_cpu_pri"),
            tr("pm_col_io_pri"),
            tr("pm_col_cpu_sets"),
            tr("pm_col_power_plan"),
            tr("pm_col_status")
        ])

    _sync_headers = _update_table_headers

    def retranslate_ui(self, lang: str = None):
        self.setWindowTitle(tr("pm_title"))
        self.search_input.setPlaceholderText(tr("pm_search_placeholder"))
        self.btn_add.setText(tr("btn_add_profile"))
        self.btn_import.setText(tr("pm_btn_import"))
        self.btn_export.setText(tr("pm_btn_export"))
        self.btn_delete.setText(tr("pm_btn_delete"))
        self.btn_close.setText(tr("pm_btn_close"))
        self._update_table_headers()
        self.populate_table()

    sync_i18n = retranslate_ui

    def populate_table(self):
        running = get_running_pids(self.rules)
        plan_name_by_guid = {guid.lower(): name for name, guid, _active in list_power_plans()}

        query = self.search_input.text().strip().lower()

        rows = []
        for rk, rule in self.rules.items():
            exe_name = rule.get("name") or os.path.basename(rule.get("exe_path") or rk)
            disp_label = exe_name
            if rule.get("exe_path"):
                disp_label = f"{exe_name} ({rule['exe_path']})"

            if query and query not in disp_label.lower():
                continue

            aff = rule.get("affinity", None)
            if aff is None or aff == "None":
                aff_str = tr("val_none")
            else:
                aff_str = translate_val(format_affinity_str(aff))

            if "io_priority" in rule and rule["io_priority"] not in (None, "None", -1):
                try:
                    io_raw = IO_PRIORITY_NAMES[int(rule["io_priority"])]
                    io_name = translate_val(io_raw, "io")
                except Exception:
                    io_name = tr("val_none")
            else:
                io_name = tr("val_none")

            pri = rule.get("priority")
            pri_name = translate_val(pri, "cpu") if pri and pri not in ("None", None) else tr("val_none")

            pp_guid = rule.get("power_plan")
            pp_name = plan_name_by_guid.get(pp_guid.lower(), pp_guid) if pp_guid else tr("val_none")
            is_running = (rk in running)
            status = tr("pm_status_running") if is_running else tr("pm_status_stopped")

            rows.append((rk, exe_name, disp_label, pri_name, io_name, aff_str, pp_name, status, is_running))

        rows.sort(key=lambda x: x[1].lower())

        self.table.clearSpans()
        blue_color = QColor(ACCENT_BLUE)
        muted_color = QColor(COLOR_WAITING)
        mono_font = get_mono_font(9)

        if not rows:
            self.table.setRowCount(1)
            msg = tr("pm_empty_not_found") if query else tr("pm_empty_no_profiles")
            empty_item = QTableWidgetItem(msg)
            empty_item.setForeground(muted_color)
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(0, 0, empty_item)
            self.table.setSpan(0, 0, 1, 6)
            return

        self.table.setRowCount(len(rows))

        for row_idx, (rk, exe_name, disp_label, pri, io_name, aff_str, pp_name, status, is_running) in enumerate(rows):
            item_name = QTableWidgetItem(disp_label)
            item_name.setData(Qt.ItemDataRole.UserRole, rk)
            item_name.setIcon(resolve_process_icon(exe_name, self.rules.get(rk, {}).get("exe_path"), 16))
            self.table.setItem(row_idx, 0, item_name)

            item_pri = QTableWidgetItem(pri)
            item_pri.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 1, item_pri)

            item_io = QTableWidgetItem(io_name)
            item_io.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 2, item_io)

            item_aff = QTableWidgetItem(aff_str)
            item_aff.setFont(mono_font)
            item_aff.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 3, item_aff)

            item_pp = QTableWidgetItem(pp_name)
            item_pp.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 4, item_pp)

            item_status = QTableWidgetItem(status)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_status.setForeground(blue_color if is_running else muted_color)
            self.table.setItem(row_idx, 5, item_status)

    populate = populate_table

    def _on_search_changed(self):
        self.populate_table()

    def _on_item_double_clicked(self, item: QTableWidgetItem):
        row = item.row()
        rk_item = self.table.item(row, 0)
        if not rk_item:
            return
        rk = rk_item.data(Qt.ItemDataRole.UserRole)
        if rk and rk in self.rules:
            r = self.rules[rk]
            exe_name = r.get("name") or os.path.basename(r.get("exe_path") or rk)
            dlg = RuleEditorDialog(
                self, proc_name=exe_name, rules=self.rules,
                rule_key=rk, path_hint=r.get("exe_path")
            )
            dlg.rule_saved.connect(self._on_rule_updated)
            dlg.rule_deleted.connect(self._on_rule_updated)
            dlg.exec()

    _on_double_click = _on_item_double_clicked

    def _on_rule_updated(self):
        self.rules = load_rules()
        self.populate_table()
        self.rules_modified.emit()

    _on_modified = _on_rule_updated

    def _add_rule(self):
        dlg = AddRuleDialog(self)
        if dlg.exec() and dlg.result_exe:
            ed = RuleEditorDialog(self, proc_name=dlg.result_exe, rules=self.rules, path_hint=dlg.result_path)
            ed.rule_saved.connect(self._on_rule_updated)
            ed.exec()

    def _delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return

        rk_item = self.table.item(row, 0)
        rk = rk_item.data(Qt.ItemDataRole.UserRole)
        rule_to_del = self.rules.get(rk)
        exe_name = rule_to_del.get("name") if rule_to_del else os.path.basename(rk)

        ret = QMessageBox.question(
            self,
            tr("pm_confirm_delete_title"),
            tr("pm_confirm_delete_msg", exe=exe_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            delete_rule(self.rules, rk)
            self.rules = load_rules()
            self.populate_table()
            self.rules_modified.emit()

    def _export_profiles(self):
        if not self.rules:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("pm_btn_export"), "processx_rules.json", "JSON Files (*.json);;All Files (*.*)"
        )
        if not path:
            return

        try:
            export_rules_to_file(path, self.rules)
            QMessageBox.information(self, tr("pm_export_success_title"), tr("pm_export_success_msg", count=len(self.rules), path=path))
        except Exception as e:
            QMessageBox.critical(self, tr("error_title"), f"{e}")

    _export = _export_profiles

    def _import_profiles(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("pm_btn_import"), "", "JSON Files (*.json);;All Files (*.*)"
        )
        if not path:
            return

        try:
            cleaned, warnings = import_rules_from_file(path, self.rules)
        except Exception as e:
            QMessageBox.critical(self, tr("error_title"), f"{e}")
            return

        overlap = sorted(set(cleaned) & set(self.rules))
        if overlap:
            sample = ", ".join(overlap[:5]) + (", ..." if len(overlap) > 5 else "")
            ret = QMessageBox.question(
                self,
                tr("pm_btn_import"),
                f"{len(overlap)} profiles already exist and will be overwritten:\n\n{sample}\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        self.rules.update(cleaned)
        save_rules(self.rules)
        self.populate_table()
        self.rules_modified.emit()

        QMessageBox.information(self, tr("pm_import_success_title"), tr("pm_import_success_msg", count=len(cleaned)))

    _import = _import_profiles


class RuleEditorDialog(FramelessDialog):
    """
    State-of-the-art glassmorphic modal dialog for process optimization:
    - Pure single-language strings (zero bilingual overflow)
    - Modern iOS/macOS segmented control bars (CPU, I/O, Memory Priority)
    - Responsive CPU Core Matrix chip grid with physical-only preset
    - Power Plan switching with NoScrollComboBox
    - Clean 5-section architecture with balanced layout
    """
    rule_saved = pyqtSignal()
    rule_deleted = pyqtSignal()

    def __init__(self, parent, proc_name: str, rules: dict,
                 pid: int = None, path_hint: str = None, rule_key: str = None):
        super().__init__(parent, title=tr("ed_title", name=proc_name))
        self.parent_app = parent
        self.proc_name = proc_name
        self.rules = rules
        self.pid = pid
        self.path_hint = path_hint
        self.rule_key = rule_key

        # Resolve existing rule
        self.existing = {}
        if self.rule_key and self.rule_key in self.rules:
            self.existing = self.rules[self.rule_key]
            if not self.path_hint:
                self.path_hint = self.existing.get("exe_path")
        else:
            rk, r = find_rule_for_process(self.pid, self.rules, name=self.proc_name, exe_path=self.path_hint)
            if r:
                self.existing = r
                self.rule_key = rk
                if not self.path_hint:
                    self.path_hint = self.existing.get("exe_path")
            elif proc_name.lower() in self.rules:
                self.existing = self.rules[proc_name.lower()]
                self.rule_key = proc_name.lower()
                if not self.path_hint:
                    self.path_hint = self.existing.get("exe_path")

        # Responsive geometry: dynamically adapts to screen resolution and DPI scale
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        target_w = min(940, max(840, int(avail.width() * 0.70)))
        target_h = min(860, max(720, int(avail.height() * 0.88)))
        min_w = min(800, avail.width() - 40)
        min_h = min(640, avail.height() - 60)
        self.setMinimumSize(min_w, min_h)
        self.resize(target_w, target_h)
        # Center on screen
        cx = avail.x() + (avail.width() - target_w) // 2
        cy = avail.y() + (avail.height() - target_h) // 2
        self.move(max(avail.x(), cx), max(avail.y(), cy))

        self._build_ui()
        I18N.language_changed.connect(self.retranslate_ui)

    def _build_ui(self):
        root_layout = self.body_layout
        root_layout.setContentsMargins(18, 8, 18, 16)
        root_layout.setSpacing(12)

        # ── Header Card (High-res Process Icon, Name, PID, Executable Path) ──
        header_card = QFrame(self)
        header_card.setObjectName("GlassCard")
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(16, 12, 16, 12)
        h_layout.setSpacing(14)

        self.icon_lbl = QLabel(header_card)
        self.icon_lbl.setFixedSize(40, 40)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_process_icon()
        h_layout.addWidget(self.icon_lbl)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        name_lbl = QLabel(self.proc_name, header_card)
        name_lbl.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY};")
        name_row.addWidget(name_lbl)

        if self.rule_key and self.rule_key in self.rules:
            active_badge = QLabel("● Active Profile", header_card)
            active_badge.setStyleSheet(
                "background-color: rgba(59, 130, 246, 0.15); "
                "color: #60A5FA; "
                "border: 1px solid rgba(59, 130, 246, 0.35); "
                "border-radius: 4px; "
                "padding: 1px 6px; "
                "font-size: 11px; "
                "font-weight: 600;"
            )
            name_row.addWidget(active_badge)
        name_row.addStretch()
        info_layout.addLayout(name_row)

        details = []
        if self.pid:
            details.append(f"{tr('ed_pid_label')} {self.pid}")
        if self.path_hint:
            details.append(f"{tr('ed_path_label')} {self.path_hint}")
        self.desc_lbl = QLabel("  |  ".join(details) if details else self.proc_name, header_card)
        self.desc_lbl.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY};")
        self.desc_lbl.setWordWrap(True)
        info_layout.addWidget(self.desc_lbl)

        h_layout.addLayout(info_layout, 1)
        root_layout.addWidget(header_card)

        # ── Scroll Area for Configuration Sections ───────────────────────────
        scroll = QScrollArea(self)
        self.scroll = scroll
        scroll.setObjectName("EditorScrollArea")
        scroll.viewport().setObjectName("EditorScrollViewport")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        container = QWidget()
        container.setObjectName("EditorScrollContainer")
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(0, 4, 6, 8)
        c_layout.setSpacing(10)

        # ── 1. CPU Priority Card (Segmented Control) ─────────────────────────
        pri_card = QFrame(container)
        pri_card.setObjectName("GlassCard")
        pri_layout = QVBoxLayout(pri_card)
        pri_layout.setContentsMargins(14, 12, 14, 12)
        pri_layout.setSpacing(8)

        self.lbl_pri = QLabel(tr("ed_sec_cpu_pri"), pri_card)
        self.lbl_pri.setStyleSheet(SECTION_HEADER_STYLE)
        pri_layout.addWidget(self.lbl_pri)

        self.pri_seg = SegmentedControl(pri_card)
        for pri_name, tr_key in PRI_CONFIG:
            self.pri_seg.add_segment(tr(tr_key), pri_name, key=pri_name)
        saved_pri = self.existing.get("priority", "None")
        if not saved_pri:
            saved_pri = "None"
        self.pri_seg.set_value(saved_pri)
        pri_layout.addWidget(self.pri_seg)
        c_layout.addWidget(pri_card)

        # ── 2. I/O Priority Card (Segmented Control) ─────────────────────────
        io_card = QFrame(container)
        io_card.setObjectName("GlassCard")
        io_layout = QVBoxLayout(io_card)
        io_layout.setContentsMargins(14, 12, 14, 12)
        io_layout.setSpacing(8)

        self.lbl_io = QLabel(tr("ed_sec_io_pri"), io_card)
        self.lbl_io.setStyleSheet(SECTION_HEADER_STYLE)
        io_layout.addWidget(self.lbl_io)

        self.io_seg = SegmentedControl(io_card)
        for io_lvl, tr_key in IO_CONFIG:
            self.io_seg.add_segment(tr(tr_key), io_lvl, key=str(io_lvl))
        saved_io = self.existing.get("io_priority", -1)
        if saved_io is None:
            saved_io = -1
        self.io_seg.set_value(saved_io)
        io_layout.addWidget(self.io_seg)
        c_layout.addWidget(io_card)

        # ── 3. Memory Priority Card (Segmented Control) ──────────────────────
        mem_card = QFrame(container)
        mem_card.setObjectName("GlassCard")
        mem_layout = QVBoxLayout(mem_card)
        mem_layout.setContentsMargins(14, 12, 14, 12)
        mem_layout.setSpacing(8)

        self.lbl_mem = QLabel(tr("ed_sec_mem_pri"), mem_card)
        self.lbl_mem.setStyleSheet(SECTION_HEADER_STYLE)
        mem_layout.addWidget(self.lbl_mem)

        self.mem_seg = SegmentedControl(mem_card)
        for mem_lvl, tr_key in MEM_CONFIG:
            self.mem_seg.add_segment(tr(tr_key), mem_lvl, key=str(mem_lvl))
        saved_mem = self.existing.get("memory_priority", -1)
        if saved_mem is None:
            saved_mem = -1
        self.mem_seg.set_value(saved_mem)
        mem_layout.addWidget(self.mem_seg)
        c_layout.addWidget(mem_card)

        # ── 4. CPU Sets / CPU Affinity Card (Interactive Core Matrix) ────────
        cpu_card = QFrame(container)
        cpu_card.setObjectName("GlassCard")
        cpu_layout = QVBoxLayout(cpu_card)
        cpu_layout.setContentsMargins(14, 12, 14, 12)
        cpu_layout.setSpacing(10)

        cpu_header = QHBoxLayout()
        cpu_header.setSpacing(8)
        self.lbl_cpu = QLabel(tr("ed_sec_cpu_sets", core_count=CPU_COUNT), cpu_card)
        self.lbl_cpu.setStyleSheet(SECTION_HEADER_STYLE)
        cpu_header.addWidget(self.lbl_cpu)
        cpu_header.addStretch()

        # Presets: None (First), All, Physical Only
        self.btn_none = QPushButton(tr("aff_none"), cpu_card)
        self.btn_none.setStyleSheet(PRESET_BTN_STYLE)
        self.btn_none.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_none.clicked.connect(self._select_none_cpus)
        cpu_header.addWidget(self.btn_none)

        self.btn_all = QPushButton(tr("ed_btn_all_cores"), cpu_card)
        self.btn_all.setStyleSheet(PRESET_BTN_STYLE)
        self.btn_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_all.clicked.connect(self._select_all_cpus)
        cpu_header.addWidget(self.btn_all)

        self.btn_physical = QPushButton(tr("ed_btn_physical_cores"), cpu_card)
        self.btn_physical.setStyleSheet(PRESET_BTN_STYLE)
        self.btn_physical.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_physical.setToolTip("Selects even logical cores (0, 2, 4...) to bypass SMT threads for gaming")
        self.btn_physical.clicked.connect(self._select_physical_cpus)
        cpu_header.addWidget(self.btn_physical)

        cpu_layout.addLayout(cpu_header)

        # Interactive CPU Core Chips Grid
        has_cpu_sets = bool(CPU_TOPOLOGY.get("global_to_cpu_set_id"))
        self.cpu_chips = []
        if not has_cpu_sets:
            lbl_none = QLabel("CPU Sets not available on this system architecture", cpu_card)
            lbl_none.setStyleSheet(f"color: {TEXT_MUTED}; font-style: italic;")
            cpu_layout.addWidget(lbl_none)
        else:
            saved_aff = self.existing.get("affinity", None)
            if saved_aff is None or saved_aff == "None":
                saved_aff = []

            grid = QGridLayout()
            grid.setSpacing(6)
            # Responsive columns adapting to CPU core count (e.g. 4, 8, 16, 32, 64)
            if CPU_COUNT >= 16:
                cols = 8
            elif CPU_COUNT >= 12:
                cols = 6
            elif CPU_COUNT >= 8:
                cols = 4
            else:
                cols = max(1, CPU_COUNT)
            for i in range(CPU_COUNT):
                chip = CoreChip(i, cpu_card)
                chip.setChecked(i in saved_aff)
                grid.addWidget(chip, i // cols, i % cols)
                self.cpu_chips.append(chip)
            cpu_layout.addLayout(grid)

        self.chips = self.cpu_chips
        c_layout.addWidget(cpu_card)

        # ── 5. Power Plan Card ───────────────────────────────────────────────
        pp_card = QFrame(container)
        pp_card.setObjectName("GlassCard")
        pp_layout = QVBoxLayout(pp_card)
        pp_layout.setContentsMargins(14, 12, 14, 12)
        pp_layout.setSpacing(8)

        self.lbl_pp = QLabel(tr("ed_sec_power_plan"), pp_card)
        self.lbl_pp.setStyleSheet(SECTION_HEADER_STYLE)
        pp_layout.addWidget(self.lbl_pp)

        self.pp_combo = NoScrollComboBox(pp_card)
        self.pp_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        self.pp_combo.addItem(tr("ed_power_plan_default"), None)

        saved_pp = self.existing.get("power_plan")
        selected_idx = 0
        for name, guid, _active in list_power_plans():
            self.pp_combo.addItem(name, guid)
            if saved_pp and guid and guid.lower() == saved_pp.lower():
                selected_idx = self.pp_combo.count() - 1

        self.pp_combo.setCurrentIndex(selected_idx)
        pp_layout.addWidget(self.pp_combo)
        c_layout.addWidget(pp_card)

        scroll.setWidget(container)
        root_layout.addWidget(scroll, 1)

        # ── Live Status Result Label ─────────────────────────────────────────
        self.result_lbl = QLabel("", self)
        self.result_lbl.setStyleSheet(f"color: {ACCENT_BLUE}; font-weight: 600; font-size: 12px;")
        self.result_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root_layout.addWidget(self.result_lbl)

        # ── Bottom Action Footer ─────────────────────────────────────────────
        FOOTER_BTN_HEIGHT = 34
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        self.btn_reset = QPushButton(tr("ed_btn_reset_defaults"), self)
        self.btn_reset.setStyleSheet(GHOST_BTN_STYLE)
        self.btn_reset.setFixedHeight(FOOTER_BTN_HEIGHT)
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.clicked.connect(self._reset_defaults)
        btn_bar.addWidget(self.btn_reset)

        if self.rule_key and self.rule_key in self.rules:
            self.btn_del = QPushButton(tr("ed_btn_delete"), self)
            self.btn_del.setObjectName("DangerBtn")
            self.btn_del.setFixedHeight(FOOTER_BTN_HEIGHT)
            self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_del.clicked.connect(self._delete_rule)
            btn_bar.addWidget(self.btn_del)

        btn_bar.addStretch()

        self.btn_cancel = QPushButton(tr("ed_btn_cancel"), self)
        self.btn_cancel.setStyleSheet(GHOST_BTN_STYLE)
        self.btn_cancel.setFixedHeight(FOOTER_BTN_HEIGHT)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.close)
        btn_bar.addWidget(self.btn_cancel)

        self.btn_save = QPushButton(tr("ed_btn_save"), self)
        self.btn_save.setObjectName("AccentBtn")
        self.btn_save.setFixedHeight(FOOTER_BTN_HEIGHT)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._save_and_apply)
        btn_bar.addWidget(self.btn_save)

        root_layout.addLayout(btn_bar)

    def _load_process_icon(self):
        """Load crisp high-resolution process executable icon (32x32 / 48x48) with SmoothPixmapTransform."""
        exe_path = self.path_hint or find_exe_path(self.proc_name)
        ico = resolve_process_icon(self.proc_name, exe_path, 48)
        pix = ico.pixmap(48, 48) if (ico and not ico.isNull()) else None

        if not pix or pix.isNull():
            pix = get_generic_exe_icon(48).pixmap(40, 40)

        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        phys = int(round(40 * dpr))
        scaled_pix = pix.scaled(
            phys, phys,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        scaled_pix.setDevicePixelRatio(dpr)
        self.icon_lbl.setPixmap(scaled_pix)

    def showEvent(self, event):
        super().showEvent(event)
        # Ensure scroll area starts flush at the top so Section 1 header is clearly visible
        if hasattr(self, "scroll") and self.scroll:
            self.scroll.verticalScrollBar().setValue(0)
            QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(0) if hasattr(self, "scroll") and self.scroll else None)
        if hasattr(self, "btn_save") and self.btn_save:
            self.btn_save.setFocus()

    def retranslate_ui(self, lang: str):
        """Reactive live translation update across all cards, segments, and buttons."""
        self.setWindowTitle(tr("ed_title", name=self.proc_name))
        details = []
        if self.pid:
            details.append(f"{tr('ed_pid_label')} {self.pid}")
        if self.path_hint:
            details.append(f"{tr('ed_path_label')} {self.path_hint}")
        self.desc_lbl.setText("  |  ".join(details) if details else self.proc_name)

        # 1. CPU Priority
        self.lbl_pri.setText(tr("ed_sec_cpu_pri"))
        for pri_name, tr_key in PRI_CONFIG:
            self.pri_seg.update_segment_label(pri_name, tr(tr_key))

        # 2. I/O Priority
        self.lbl_io.setText(tr("ed_sec_io_pri"))
        for io_lvl, tr_key in IO_CONFIG:
            self.io_seg.update_segment_label(str(io_lvl), tr(tr_key))

        # 3. Memory Priority
        self.lbl_mem.setText(tr("ed_sec_mem_pri"))
        for mem_lvl, tr_key in MEM_CONFIG:
            self.mem_seg.update_segment_label(str(mem_lvl), tr(tr_key))

        # 4. CPU Sets / Affinity
        self.lbl_cpu.setText(tr("ed_sec_cpu_sets", core_count=CPU_COUNT))
        self.btn_none.setText(tr("aff_none"))
        self.btn_all.setText(tr("ed_btn_all_cores"))
        self.btn_physical.setText(tr("ed_btn_physical_cores"))

        # 5. Power Plan
        self.lbl_pp.setText(tr("ed_sec_power_plan"))
        self.pp_combo.setItemText(0, tr("ed_power_plan_default"))

        # Actions
        self.btn_reset.setText(tr("ed_btn_reset_defaults"))
        if hasattr(self, "btn_del"):
            self.btn_del.setText(tr("ed_btn_delete"))
        self.btn_cancel.setText(tr("ed_btn_cancel"))
        self.btn_save.setText(tr("ed_btn_save"))

    sync_i18n = retranslate_ui

    def _select_all_cpus(self):
        for chip in self.cpu_chips:
            chip.setChecked(True)

    def _select_none_cpus(self):
        for chip in self.cpu_chips:
            chip.setChecked(False)

    def _select_physical_cpus(self):
        """Bypass Hyper-Threading / SMT logical sibling threads by selecting even core indices 0, 2, 4..."""
        for chip in self.cpu_chips:
            chip.setChecked(chip.core_index % 2 == 0)

    _select_physical_cores = _select_physical_cpus

    def _reset_defaults(self):
        """Reset all parameters to None / system default baseline."""
        self.pri_seg.set_value("None")
        self.io_seg.set_value(-1)
        self.mem_seg.set_value(-1)
        self._select_none_cpus()
        self.pp_combo.setCurrentIndex(0)
        self.result_lbl.setText(tr("ed_status_reset"))

    def _save_and_apply(self):
        # 1. CPU Sets Affinity (If None/no cores selected, ignore/not enforce)
        has_cpu_sets = bool(CPU_TOPOLOGY.get("global_to_cpu_set_id"))
        if has_cpu_sets and self.cpu_chips:
            aff = [chip.core_index for chip in self.cpu_chips if chip.isChecked()]
            if not aff:
                aff = None
        else:
            aff = self.existing.get("affinity", None)
            if aff in ([], "None"):
                aff = None

        # 2. CPU Priority
        selected_pri = self.pri_seg.get_value()
        if selected_pri in ("None", None):
            selected_pri = None

        # 3. I/O Priority
        selected_io = self.io_seg.get_value()
        if selected_io in (-1, None, "None"):
            selected_io = None

        # 4. Memory Priority
        selected_mem = self.mem_seg.get_value()
        if selected_mem in (-1, None, "None"):
            selected_mem = None

        # Build rule definition
        rule = {
            "name": self.proc_name,
            "priority": selected_pri,
            "io_priority": selected_io,
            "memory_priority": selected_mem,
            "affinity": aff,
        }

        if self.path_hint and os.path.isfile(self.path_hint):
            rule["exe_path"] = self.path_hint

        pp_guid = self.pp_combo.currentData()
        if pp_guid:
            rule["power_plan"] = pp_guid

        target_key = self.rule_key or self.proc_name
        instance_ct, any_failed, all_msgs = save_and_apply_rule(
            self.rules, target_key, rule,
            pid=self.pid, path_hint=self.path_hint, auto_apply=True
        )

        self.rule_saved.emit()
        self.accept()

    _save_profile = _save_and_apply

    def _delete_rule(self):
        confirm = QMessageBox.question(
            self,
            tr("ed_confirm_delete_title"),
            tr("ed_confirm_delete_msg", name=self.proc_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        target_key = self.rule_key or self.proc_name
        delete_rule(self.rules, target_key)
        self.rule_deleted.emit()
        self.close()

    _delete_profile = _delete_rule


# Background Worker Thread
class ProcessSnapshotWorker(QThread):
    snapshot_ready = pyqtSignal(list)

    def __init__(self, rules_supplier, parent=None):
        super().__init__(parent)
        self.rules_supplier = rules_supplier

    def run(self):
        try:
            snapshot = collect_proc_snapshot(self.rules_supplier())
            self.snapshot_ready.emit(snapshot)
        except Exception as e:
            _log_error("ProcessSnapshotWorker.run", e)


class _WatcherBridge(QObject):
    """Thread-safe signal dispatcher from background RuleWatcher thread to Qt Main UI thread."""
    status_changed = pyqtSignal(str)
    refresh_requested = pyqtSignal()


# Main Window
class ProcessX(QMainWindow):
    window_maximized_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("QMainWindow { background: transparent; border: none; }")

        self.rules = load_rules()
        self._quitting = False
        self._refreshing = False

        self.setWindowTitle("ProcessX v2.0")
        self.setMinimumSize(780, 480)
        self.resize(980, 600)

        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move((geo.width() - self.width()) // 2, (geo.height() - self.height()) // 2)

        self.root_frame = RootFrame(self, radius=8.0)
        self.root_frame.setMouseTracking(True)
        self.setMouseTracking(True)
        self.setCentralWidget(self.root_frame)
        self.root_layout = QVBoxLayout(self.root_frame)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self, title="ProcessX", version="v2.0")
        self.title_bar.search_changed.connect(self._on_search)
        self.root_layout.addWidget(self.title_bar)

        content = QWidget(self.root_frame)
        content.setObjectName("ContentWidget")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(12, 10, 12, 6)
        cl.setSpacing(8)

        self.toolbar = ActionToolbar(content)
        self.toolbar.open_profiles.connect(self._open_profiles)
        self.toolbar.add_rule.connect(self._open_add_rule)
        self.toolbar.open_settings.connect(self._open_settings)
        cl.addWidget(self.toolbar)

        self.tree = ProcessTreeWidget(content)
        self.tree.edit_rule_requested.connect(self._open_editor)
        self.tree.refresh_requested.connect(self.trigger_refresh)
        cl.addWidget(self.tree, 1)

        self.status_bar = QLabel(tr("status_watcher_running"), content)
        self.status_bar.setObjectName("StatusBar")
        cl.addWidget(self.status_bar)
        self.root_layout.addWidget(content, 1)

        # System Tray
        self._setup_tray()

        # Snapshot Worker
        self.worker = ProcessSnapshotWorker(lambda: self.rules, self)
        self.worker.snapshot_ready.connect(self._on_snapshot_ready)
        self.worker.finished.connect(self._on_worker_finished)

        # Thread-safe Watcher Bridge
        self._watcher_bridge = _WatcherBridge(self)
        self._watcher_bridge.status_changed.connect(self._on_watcher_status)
        self._watcher_bridge.refresh_requested.connect(self.trigger_refresh)

        # Watcher
        self.watcher = RuleWatcher(
            lambda: self.rules,
            status_cb=self._watcher_bridge.status_changed.emit,
            refresh_cb=self._watcher_bridge.refresh_requested.emit,
        )
        self.watcher.start()

        # UI Refresh Timer: fixed 2000ms
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(2000)
        self.refresh_timer.timeout.connect(self.trigger_refresh)
        self.refresh_timer.start()

        I18N.language_changed.connect(self._retranslate_ui)
        self._apply_state_styling(False)
        self.trigger_refresh()

    def _on_watcher_status(self, msg: str):
        if hasattr(self, "status_bar"):
            self.status_bar.setText(msg)
        is_active = ("active" in msg.lower() or "monitoring" in msg.lower() or "running" in msg.lower())
        if hasattr(self, "toolbar"):
            self.toolbar.set_watcher_status(is_active, msg)

    def _retranslate_ui(self, lang: str = ""):
        if hasattr(self, "status_bar"):
            self.status_bar.setText(tr("status_watcher_running"))
        if hasattr(self, "tray_act_show"):
            self.tray_act_show.setText(tr("tray_open"))
            self.tray_act_profiles.setText(tr("tray_profiles"))
            if hasattr(self, "tray_act_settings"):
                self.tray_act_settings.setText(tr("btn_settings"))
            self.tray_act_refresh.setText(tr("tray_refresh"))
            self.tray_act_quit.setText(tr("tray_quit"))

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(get_app_icon(), self)
        self.tray.setToolTip("ProcessX v2.0")
        self.tray_menu = QMenu()
        self.tray_act_show = self.tray_menu.addAction(tr("tray_open"), self.show_and_activate)
        self.tray_act_profiles = self.tray_menu.addAction(tr("tray_profiles"), self._open_profiles)
        self.tray_act_settings = self.tray_menu.addAction(tr("btn_settings"), self._open_settings)
        self.tray_act_refresh = self.tray_menu.addAction(tr("tray_refresh"), self.trigger_refresh)
        self.tray_menu.addSeparator()
        self.tray_act_quit = self.tray_menu.addAction(tr("tray_quit"), self.quit_app)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_and_activate()

    def show_and_activate(self):
        now = time.monotonic()
        if now - getattr(self, "_last_show_activate_time", 0.0) < 0.2:
            return
        self._last_show_activate_time = now

        hwnd = int(self.winId()) if hasattr(self, "winId") else 0
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        self.show()
        self.activateWindow()
        self.raise_()
        self.watcher.set_active_mode(True)
        if not self.refresh_timer.isActive():
            self.refresh_timer.start()
        self.trigger_refresh()

    def nativeEvent(self, event_type, message):
        try:
            if event_type == b"windows_generic_MSG":
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_PROCESSX_SHOW:
                    self.show_and_activate()
                    return True, 0
        except Exception as e:
            _log_error("ProcessX.nativeEvent", e)
        return False, 0

    def showEvent(self, event):
        super().showEvent(event)
        is_max = self.isMaximized()
        apply_dwm_glass(int(self.winId()), backdrop_type=3, dark=True, rounded=not is_max)
        self._apply_state_styling(is_max)
        if is_max:
            self._ensure_maximized_geometry()
        self.watcher.set_active_mode(True)
        if not self.refresh_timer.isActive():
            self.refresh_timer.start()
        self.trigger_refresh()

    def _ensure_maximized_geometry(self):
        screen = self.screen()
        if screen:
            avail_geo = screen.availableGeometry()
            if self.geometry() != avail_geo:
                self.setGeometry(avail_geo)

    def _apply_state_styling(self, is_max: bool):
        self.root_frame.is_maximized = is_max
        self.root_frame.update()
        hwnd = int(self.winId()) if self.isVisible() else 0
        if hwnd and sys.platform == "win32":
            set_dwm_corner_preference(hwnd, rounded=not is_max)
        if hasattr(self, "title_bar") and self.title_bar:
            self.title_bar.update_max_button(is_max)
            self.title_bar.setStyleSheet(
                "#TitleBar {"
                "    background-color: transparent;"
                f"    border-bottom: 1px solid {BORDER_SUBTLE};"
                "}"
            )

    def closeEvent(self, event):
        if get_setting("minimize_to_tray", True) and hasattr(self, "tray") and self.tray.isVisible() and not self._quitting:
            self.hide()
            self.refresh_timer.stop()
            self.watcher.set_active_mode(False)
            event.ignore()
        else:
            self.quit_app()
            event.accept()

    def quit_app(self):
        self._quitting = True
        self.refresh_timer.stop()
        self.watcher.stop()
        if hasattr(self, "tray"):
            self.tray.hide()
        QApplication.quit()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            is_max = self.isMaximized()
            if is_max:
                self._ensure_maximized_geometry()
            self._apply_state_styling(is_max)
            self.window_maximized_changed.emit(is_max)
            if self.isMinimized():
                self.refresh_timer.stop()
                self.watcher.set_active_mode(False)
            elif self.isVisible():
                self.watcher.set_active_mode(True)
                if not self.refresh_timer.isActive():
                    self.refresh_timer.start()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        is_max = self.isMaximized()
        if is_max:
            self._ensure_maximized_geometry()
            if not self.root_frame.is_maximized:
                self._apply_state_styling(True)
        else:
            if self.root_frame.is_maximized:
                self._apply_state_styling(False)

    def start_drag(self):
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                user32.ReleaseCapture()
                user32.SendMessageW(int(self.winId()), 0x00A1, 2, 0)  # WM_NCLBUTTONDOWN, HTCAPTION
            except Exception:
                pass

    def _get_resize_direction(self, pos: QPoint) -> str | None:
        if self.isMaximized():
            return None
        bw = 6
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        left, right = x <= bw, x >= w - bw
        top, bottom = y <= bw, y >= h - bw
        if top and left: return "top_left"
        if top and right: return "top_right"
        if bottom and left: return "bottom_left"
        if bottom and right: return "bottom_right"
        if left: return "left"
        if right: return "right"
        if top: return "top"
        if bottom: return "bottom"
        return None

    def _set_resize_cursor(self, direction: str | None):
        if direction in ("top_left", "bottom_right"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif direction in ("top_right", "bottom_left"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif direction in ("left", "right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif direction in ("top", "bottom"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()

    def _start_resize(self, direction: str):
        resize_codes = {"left": 1, "right": 2, "top": 3, "top_left": 4, "top_right": 5, "bottom": 6, "bottom_left": 7, "bottom_right": 8}
        if sys.platform == "win32" and direction in resize_codes:
            try:
                user32 = ctypes.windll.user32
                user32.ReleaseCapture()
                user32.SendMessageW(int(self.winId()), 0x0112, 0xF000 + resize_codes[direction], 0)  # WM_SYSCOMMAND, SC_SIZE
            except Exception:
                pass

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.isMaximized():
            direction = self._get_resize_direction(event.position().toPoint())
            self._set_resize_cursor(direction)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and not self.isMaximized():
            direction = self._get_resize_direction(event.position().toPoint())
            if direction:
                self._start_resize(direction)
                event.accept()
                return
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        self.unsetCursor()
        super().leaveEvent(event)

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self._apply_state_styling(False)
            self.window_maximized_changed.emit(False)
        else:
            self.showMaximized()
            self._ensure_maximized_geometry()
            self._apply_state_styling(True)
            self.window_maximized_changed.emit(True)

    def trigger_refresh(self):
        if self._quitting or not self.isVisible() or self._refreshing or self.tree.is_scrolling:
            return
        self._refreshing = True
        self.worker.start()

    def _on_worker_finished(self):
        self._refreshing = False

    def _on_snapshot_ready(self, snapshot: list):
        try:
            if self._quitting:
                return
            self.tree.update_snapshot(snapshot)
            self.rules = load_rules()
            running = get_running_pids(self.rules)
            active_cnt = min(len(running), len(self.rules))
            self.toolbar.update_metrics(active_cnt, len(self.rules), len(snapshot))
        except Exception as e:
            _log_error("ProcessX._on_snapshot_ready", e)

    def _on_rules_changed(self):
        self.rules = load_rules()
        self.trigger_refresh()

    def _on_search(self, text: str):
        self.tree.set_filter(text)
        self.trigger_refresh()

    def _open_profiles(self):
        dlg = ProfilesManagerDialog(self, self.rules)
        dlg.rules_modified.connect(self._on_rules_changed)
        dlg.exec()

    def _open_add_rule(self):
        dlg = AddRuleDialog(self)
        if dlg.exec() and dlg.result_exe:
            ed = RuleEditorDialog(self, proc_name=dlg.result_exe, rules=self.rules, path_hint=dlg.result_path)
            ed.rule_saved.connect(self._on_rules_changed)
            ed.exec()

    def _open_editor(self, name: str, pid: int = 0, path: str = ""):
        ed = RuleEditorDialog(self, proc_name=name, rules=self.rules, pid=pid or None, path_hint=path or None)
        ed.rule_saved.connect(self._on_rules_changed)
        ed.rule_deleted.connect(self._on_rules_changed)
        ed.exec()

    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.settings_changed.connect(self.trigger_refresh)
        dlg.exec()

    def mainloop(self):
        if "--startup" not in sys.argv:
            self.show()
        return QApplication.instance().exec()

# Entry Helper
def run_app():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_STYLESHEET)
    app.setWindowIcon(get_app_icon())
    win = ProcessX()
    return win.mainloop()
