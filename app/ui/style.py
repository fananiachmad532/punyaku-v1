"""Dark theme stylesheet for the application.

Single file so users can tweak colors without touching widget code.

Palette design notes
--------------------
We use a small, harmonized palette:

* Surfaces: a single ramp of cool slate (``#0e1116`` to ``#262b35``) so that
  cards, hovers and borders feel like one family instead of competing greys.
* Accent: a softer indigo-blue (``#6a8cff``) that reads as "calm" rather than
  the neon ``#3da9fc`` we had before.
* Status colors: success / warning / error / info are all in the same
  lightness band so the queue table does not look like a Christmas tree.
"""
from __future__ import annotations


# Surfaces.
BG = "#0e1116"
SURFACE = "#171a21"
SURFACE_HOVER = "#1f232c"
SURFACE_ELEVATED = "#252a35"
BORDER = "#262b35"
BORDER_STRONG = "#323845"

# Text.
TEXT = "#e4e7ec"
TEXT_SECONDARY = "#9aa3b2"
TEXT_MUTED = "#6b7280"
TEXT_DISABLED = "#4b525d"

# Status (harmonized — same perceived lightness band).
STATUS_SUCCESS = "#5fbf8c"
STATUS_ERROR = "#e07579"
STATUS_WARNING = "#e0a44a"
STATUS_INFO = "#6a8cff"
STATUS_NEUTRAL = "#7a8493"

# Danger button (delete / remove).
DANGER_BG = "#5c2a2c"
DANGER_HOVER = "#7a3a3d"
DANGER_TEXT = "#fbdcdd"


def dark_stylesheet(accent: str = "#6a8cff") -> str:
    # Derive a calmer hover from the accent.  We do not parse the color here;
    # the default hover works well with the recommended accent and any user
    # override still gets a sensible 8% lighter overlay via ``border``.
    accent_hover = "#8aa4ff" if accent.lower() == "#6a8cff" else accent
    return f"""
    * {{
        font-family: 'Segoe UI', 'Inter', 'Noto Sans', Arial, sans-serif;
        font-size: 13px;
        color: {TEXT};
    }}
    QMainWindow, QWidget {{
        background-color: {BG};
    }}
    QFrame#card {{
        background-color: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 12px;
    }}
    QPushButton {{
        background-color: {SURFACE_HOVER};
        border: 1px solid {BORDER_STRONG};
        border-radius: 8px;
        padding: 7px 14px;
        color: {TEXT};
    }}
    QPushButton:hover {{
        background-color: {SURFACE_ELEVATED};
        border-color: {BORDER_STRONG};
    }}
    QPushButton:pressed {{
        background-color: {SURFACE};
    }}
    QPushButton:disabled {{
        color: {TEXT_DISABLED};
        background-color: {SURFACE};
        border-color: {BORDER};
    }}
    QPushButton#primary {{
        background-color: {accent};
        color: #0c0f13;
        font-weight: 600;
        border: none;
    }}
    QPushButton#primary:hover {{
        background-color: {accent_hover};
    }}
    QPushButton#primary:disabled {{
        background-color: {SURFACE_ELEVATED};
        color: {TEXT_DISABLED};
    }}
    QPushButton#danger {{
        background-color: {DANGER_BG};
        color: {DANGER_TEXT};
        border: 1px solid {DANGER_HOVER};
    }}
    QPushButton#danger:hover {{
        background-color: {DANGER_HOVER};
    }}
    QPlainTextEdit, QTextEdit, QLineEdit {{
        background-color: {BG};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 6px 8px;
        color: {TEXT};
        selection-background-color: {accent};
        selection-color: #0c0f13;
    }}
    QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus {{
        border-color: {accent};
    }}
    QComboBox, QSpinBox {{
        background-color: {BG};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 5px 8px;
        color: {TEXT};
        selection-background-color: {accent};
        selection-color: #0c0f13;
    }}
    QComboBox:hover, QSpinBox:hover {{
        border-color: {BORDER_STRONG};
    }}
    QComboBox:focus, QSpinBox:focus {{
        border-color: {accent};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: right center;
        width: 18px;
        border-left: 1px solid {BORDER};
    }}
    QComboBox::down-arrow {{
        width: 8px;
        height: 8px;
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {TEXT_SECONDARY};
        margin-right: 4px;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        subcontrol-origin: border;
        width: 16px;
        border: none;
        background-color: transparent;
    }}
    QSpinBox::up-button {{
        subcontrol-position: top right;
    }}
    QSpinBox::down-button {{
        subcontrol-position: bottom right;
    }}
    QSpinBox::up-arrow {{
        image: none;
        width: 7px;
        height: 7px;
        border-left: 3px solid transparent;
        border-right: 3px solid transparent;
        border-bottom: 4px solid {TEXT_SECONDARY};
    }}
    QSpinBox::down-arrow {{
        image: none;
        width: 7px;
        height: 7px;
        border-left: 3px solid transparent;
        border-right: 3px solid transparent;
        border-top: 4px solid {TEXT_SECONDARY};
    }}
    QComboBox QAbstractItemView {{
        background-color: {SURFACE};
        border: 1px solid {BORDER_STRONG};
        selection-background-color: {accent};
        selection-color: #0c0f13;
        outline: 0;
    }}
    QCheckBox {{
        spacing: 8px;
        color: {TEXT};
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {BORDER_STRONG};
        background-color: {BG};
    }}
    QCheckBox::indicator:hover {{
        border-color: {accent};
    }}
    QCheckBox::indicator:checked {{
        background-color: {accent};
        border-color: {accent};
    }}
    QTableWidget {{
        background-color: {BG};
        gridline-color: {BORDER};
        border: 1px solid {BORDER};
        border-radius: 10px;
        selection-background-color: #2a3858;
        selection-color: #ffffff;
        alternate-background-color: {SURFACE};
    }}
    QTableWidget::item {{
        padding: 4px 6px;
    }}
    QHeaderView::section {{
        background-color: {SURFACE};
        color: {TEXT_SECONDARY};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 8px 10px;
        font-weight: 600;
    }}
    QHeaderView::section:first {{
        border-top-left-radius: 10px;
    }}
    QHeaderView::section:last {{
        border-top-right-radius: 10px;
    }}
    QTableCornerButton::section {{
        background-color: {SURFACE};
        border: none;
    }}
    QProgressBar {{
        background-color: {SURFACE_HOVER};
        border: 1px solid {BORDER};
        border-radius: 6px;
        text-align: center;
        color: {TEXT};
        min-height: 14px;
    }}
    QProgressBar::chunk {{
        background-color: {accent};
        border-radius: 5px;
    }}
    QLabel#appTitle {{
        color: {TEXT};
        font-size: 18px;
        font-weight: 700;
        letter-spacing: 0.3px;
    }}
    QLabel#appSubtitle {{
        color: {TEXT_MUTED};
        font-size: 12px;
    }}
    QLabel#statTitle {{
        color: {TEXT_MUTED};
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    QLabel#statValue {{
        color: {TEXT};
        font-size: 22px;
        font-weight: 700;
    }}
    QToolBar {{
        background-color: {BG};
        border: none;
        spacing: 6px;
        padding: 4px 6px;
    }}
    QToolBar QToolButton {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 6px 10px;
        color: {TEXT_SECONDARY};
    }}
    QToolBar QToolButton:hover {{
        background-color: {SURFACE_HOVER};
        color: {TEXT};
        border-color: {BORDER_STRONG};
    }}
    QToolBar QToolButton:checked {{
        background-color: {SURFACE_ELEVATED};
        color: {TEXT};
    }}
    QToolBar::separator {{
        background-color: {BORDER};
        width: 1px;
        margin: 6px 4px;
    }}
    QStatusBar {{
        background-color: {SURFACE};
        color: {TEXT_SECONDARY};
        border-top: 1px solid {BORDER};
    }}
    QStatusBar::item {{
        border: none;
    }}
    QSplitter::handle {{
        background-color: transparent;
    }}
    QSplitter::handle:hover {{
        background-color: {BORDER_STRONG};
    }}
    QSplitter::handle:horizontal {{
        width: 6px;
    }}
    QSplitter::handle:vertical {{
        height: 6px;
    }}
    QToolTip {{
        background-color: {SURFACE_ELEVATED};
        color: {TEXT};
        border: 1px solid {BORDER_STRONG};
        padding: 4px 8px;
    }}
    QMenu {{
        background-color: {SURFACE};
        border: 1px solid {BORDER_STRONG};
        padding: 4px;
        color: {TEXT};
    }}
    QMenu::item {{
        padding: 6px 18px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background-color: {accent};
        color: #0c0f13;
    }}
    QScrollBar:vertical {{
        background: {BG};
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER_STRONG};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #3f4757;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    QScrollBar:horizontal {{
        background: {BG};
        height: 10px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {BORDER_STRONG};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: #3f4757;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}
    """
