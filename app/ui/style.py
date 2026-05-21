"""Dark theme stylesheet for the application.

Single file so users can tweak colors without touching widget code.
"""
from __future__ import annotations


def dark_stylesheet(accent: str = "#3da9fc") -> str:
    return f"""
    * {{
        font-family: 'Segoe UI', 'Inter', 'Noto Sans', Arial, sans-serif;
        font-size: 13px;
        color: #e6e8eb;
    }}
    QMainWindow, QWidget {{
        background-color: #14171c;
    }}
    QFrame#card {{
        background-color: #1c2129;
        border: 1px solid #232a35;
        border-radius: 12px;
    }}
    QPushButton {{
        background-color: #232a35;
        border: 1px solid #2a3340;
        border-radius: 8px;
        padding: 7px 14px;
        color: #e6e8eb;
    }}
    QPushButton:hover {{
        background-color: #2a3340;
    }}
    QPushButton:disabled {{
        color: #6f7785;
        background-color: #1c2129;
    }}
    QPushButton#primary {{
        background-color: {accent};
        color: #0c0f13;
        font-weight: 600;
        border: none;
    }}
    QPushButton#primary:hover {{
        background-color: #62b8ff;
    }}
    QPushButton#danger {{
        background-color: #6b1f1f;
        color: #ffd8d8;
        border: none;
    }}
    QPushButton#danger:hover {{
        background-color: #a32f2f;
    }}
    QPlainTextEdit, QTextEdit, QLineEdit, QComboBox, QSpinBox {{
        background-color: #11141a;
        border: 1px solid #232a35;
        border-radius: 8px;
        padding: 6px 8px;
        selection-background-color: {accent};
        selection-color: #0c0f13;
    }}
    QTableWidget {{
        background-color: #11141a;
        gridline-color: #232a35;
        border: 1px solid #232a35;
        border-radius: 10px;
        selection-background-color: #243043;
        selection-color: #ffffff;
    }}
    QHeaderView::section {{
        background-color: #1c2129;
        color: #b8c0cc;
        border: none;
        padding: 8px 10px;
        font-weight: 600;
    }}
    QProgressBar {{
        background-color: #11141a;
        border: 1px solid #232a35;
        border-radius: 6px;
        text-align: center;
        color: #e6e8eb;
        min-height: 14px;
    }}
    QProgressBar::chunk {{
        background-color: {accent};
        border-radius: 6px;
    }}
    QLabel#statTitle {{
        color: #8b95a5;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    QLabel#statValue {{
        color: #ffffff;
        font-size: 22px;
        font-weight: 700;
    }}
    QStatusBar {{
        background-color: #11141a;
        color: #8b95a5;
    }}
    QToolTip {{
        background-color: #1c2129;
        color: #e6e8eb;
        border: 1px solid #2a3340;
        padding: 4px 8px;
    }}
    QScrollBar:vertical {{
        background: #11141a;
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: #2a3340;
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #3a4555;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    """
