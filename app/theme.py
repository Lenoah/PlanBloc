"""Couleurs et feuille de style Qt (QSS)."""
from PySide6.QtGui import QColor, QPalette

BG = "#eef2f6"
DARK = "#1f2d3d"
ACCENT = "#2563eb"
GREEN = "#22a55a"
INK = "#1c2733"
MUTED = "#5b6b7c"
LINE = "#dfe5ec"
LINE_SOFT = "#edf1f5"
LINE_DAY = "#cfd8e3"
GAUGE_LEFT = "#f5c518"
GAUGE_DONE = "#b8c1cc"

STATUS = {
    "ok": {"border": "#22a55a", "ink": "#1d7a43", "bg": "#e6f7ec"},
    "orange": {"border": "#f08c00", "ink": "#a15c00", "bg": "#fff4e2"},
    "rouge": {"border": "#e03131", "ink": "#b42323", "bg": "#ffe9ea"},
    "incomplet": {"border": "#8a98a8", "ink": "#4a5a6b", "bg": "#f1f4f8"},
}

# (fond pastel, couleur franche) par activité
PALETTE = [
    ("#dbe8fb", "#2563eb"), ("#dcf5e3", "#16a34a"), ("#ece2fb", "#7c3aed"), ("#d5f3f0", "#0d9488"),
    ("#fce4ef", "#db2777"), ("#e0e7ff", "#4f46e5"), ("#fde8d7", "#c2410c"), ("#e6ecf2", "#475569"),
]
DAY_TINTS = [
    ("#dbe8fb", "#3b82f6"), ("#dcf5e3", "#22a55a"), ("#fdf0cf", "#f5b400"), ("#ece2fb", "#8b5cf6"),
    ("#fde0e1", "#e5383b"), ("#d5f3f0", "#0d9488"), ("#e6ecf2", "#475569"),
]


def tint(hex_color: str, amount: float = 0.82) -> str:
    c = QColor(hex_color)
    mix = lambda v: round(v + (255 - v) * amount)
    return QColor(mix(c.red()), mix(c.green()), mix(c.blue())).name()


def light_palette() -> QPalette:
    p = QPalette()
    R = QPalette.ColorRole
    for role, color in ((R.Window, BG), (R.WindowText, INK), (R.Base, "#ffffff"), (R.AlternateBase, "#f6f8fb"),
                        (R.Text, INK), (R.Button, "#ffffff"), (R.ButtonText, INK), (R.Highlight, ACCENT),
                        (R.HighlightedText, "#ffffff"), (R.ToolTipBase, DARK), (R.ToolTipText, "#ffffff"),
                        (R.PlaceholderText, "#8a98a8")):
        p.setColor(role, QColor(color))
    return p


QSS = """
QWidget#Root { background: #eef2f6; }
QToolTip { background: #1f2d3d; color: #ffffff; border: none; padding: 6px 8px; }

#TopBar { background: #1f2d3d; }
#TopBar QLabel#Logo { background: #2563eb; color: #ffffff; border-radius: 7px; font-size: 17px; font-weight: 700; }
#TopBar QLabel#Brand { color: #ffffff; font-size: 15px; font-weight: 600; }
#TopBar QPushButton[tab="true"] { color: #dfe7f0; background: transparent; border: none; border-radius: 7px;
    padding: 8px 14px; font-size: 14px; }
#TopBar QPushButton[tab="true"]:hover { background: #2b3c50; }
#TopBar QPushButton[tab="true"]:checked { background: #2563eb; color: #ffffff; font-weight: 600; }
#TopBar QPushButton#ExportBtn { color: #ffffff; background: transparent; border: 1px solid #3d5168;
    border-radius: 7px; padding: 7px 14px; }
#TopBar QPushButton#ExportBtn:hover { background: #2b3c50; }
QLabel#Badge { background: #e03131; color: #ffffff; border-radius: 9px; padding: 1px 7px; font-size: 11px; font-weight: 700; }

#ContextBar { background: #ffffff; border-bottom: 1px solid #dfe5ec; }
#Card { background: #ffffff; border: 1px solid #dfe5ec; border-radius: 10px; }
#Rail { background: #f6f8fb; border-right: 1px solid #dfe5ec; }
#Rail[dropHover="true"] { background: #fff4e2; border: 2px solid #f08c00; }
#Transparent { background: transparent; }
QScrollArea { background: transparent; border: none; }
#ActCard { background: #ffffff; border: 1px solid #dfe5ec; border-radius: 8px; }
#ActCard:hover { border: 1px solid #b5c2d1; }
QLabel#Info { background: #fff6e5; border: 1px solid #f7d79a; border-radius: 7px; color: #7a4b00; padding: 10px 12px; }
#DlgFooter { background: #fafbfd; border-top: 1px solid #edf1f5; }
QDialog { background: #ffffff; }

QComboBox, QLineEdit, QDateEdit, QSpinBox { background: #ffffff; border: 1px solid #d5dce5; border-radius: 6px;
    padding: 5px 8px; min-height: 22px; }
QComboBox:focus, QLineEdit:focus, QDateEdit:focus, QSpinBox:focus { border: 1px solid #2563eb; }
QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #d5dce5; selection-background-color: #dbe8fb;
    selection-color: #1c2733; outline: none; }

QPushButton { background: #ffffff; border: 1px solid #d5dce5; border-radius: 7px; padding: 7px 14px; color: #1c2733; }
QPushButton:hover { background: #f3f6fa; }
QPushButton:pressed { background: #e6ebf2; }
QPushButton:disabled { color: #a8b3bf; }
QPushButton[variant="primary"] { background: #2563eb; color: #ffffff; border: none; font-weight: 600; }
QPushButton[variant="primary"]:hover { background: #1d4ed8; }
QPushButton[variant="primary"]:pressed { background: #1e40af; }
QPushButton[variant="success"] { background: #22a55a; color: #ffffff; border: none; font-weight: 600; }
QPushButton[variant="success"]:hover { background: #1b8f4c; }
QPushButton[variant="danger"] { background: #ffffff; color: #c92a2a; border: 1px solid #f1b0b2; }
QPushButton[variant="danger"]:hover { background: #fff1f1; }
QPushButton[variant="dashed"] { background: transparent; color: #2563eb; border: 1px dashed #b5c2d1; font-weight: 600; padding: 9px; }
QPushButton[variant="dashed"]:hover { background: #eaf1fd; }
QPushButton[chip="true"] { background: #eef2f6; border: none; border-radius: 14px; padding: 6px 12px; font-weight: 500; }
QPushButton[chip="true"]:hover { background: #e2e8f0; }
QPushButton[chip="true"]:checked { background: #2563eb; color: #ffffff; }

#WeekNav { background: #ffffff; border: 1px solid #d5dce5; border-radius: 7px; }
#WeekNav QPushButton { border: none; border-radius: 0; background: transparent; font-size: 17px; padding: 1px 0; }
#WeekNav QPushButton:hover { background: #f3f6fa; }
#WeekNav QLabel { border-left: 1px solid #e3e8ee; border-right: 1px solid #e3e8ee; padding: 5px 14px; font-weight: 500; }

QTableWidget { background: #ffffff; border: 1px solid #dfe5ec; border-radius: 10px; }
QTableWidget::item { border-bottom: 1px solid #edf1f5; padding-left: 8px; }
QHeaderView::section { background: #f6f8fb; border: none; border-bottom: 1px solid #e3e8ee; padding: 9px 8px;
    font-weight: 600; color: #4a5a6b; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #c3cdd8; border-radius: 5px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #c3cdd8; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""
