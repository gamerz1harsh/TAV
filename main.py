"""Native desktop launcher for Riverton."""
from __future__ import annotations

import sys
import threading
from functools import partial
from typing import Any

from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QScrollArea, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from game_engine import GameEngine, GameRuleError, LOCATIONS, ORIGINS, SAVE_FILE
from game_features import filter_memories
from llm_service import get_dynamic_year_options, generate_starting_scenario, load_llm_settings, save_llm_settings
from character_creation import enumerate_eras, build_character_template
from dev_console import DevConsole
import game_config

# Generation timeout in seconds
GENERATION_TIMEOUT_SECONDS = 60


class GenerationWorker(QObject):
    """Signal-based bridge for thread-safe UI updates after generation completes."""
    finished = Signal(object, object, object, object)  # template, origin_id, start_year, generated
    error = Signal(str)

    def __init__(self, template: dict, origin_id: str, start_year: int) -> None:
        super().__init__()
        self.template = template
        self.origin_id = origin_id
        self.start_year = start_year

    def run(self) -> None:
        try:
            generated = generate_starting_scenario(self.template)
            self.finished.emit(self.template, self.origin_id, self.start_year, generated)
        except Exception as e:
            error_msg = str(e) if str(e) else "Unknown error during LLM generation"
            self.error.emit(error_msg)


APP_STYLE = """
/* Dark modern theme for Riverton */
QWidget {
    background: #0d1117;
    color: #c9d1d9;
    font-family: 'Segoe UI', -apple-system, sans-serif;
    font-size: 13px;
}
QWidget#central {
    background: #0d1117;
}

/* Headers */
QLabel#eyebrow {
    color: #58a6ff;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}
QLabel#title {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 40px;
    font-weight: 700;
    color: #f0f6fc;
}
QLabel#subtitle {
    color: #8b949e;
    font-size: 13px;
    font-weight: 500;
}

/* Cards & Groups */
QFrame.card, QGroupBox {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
}
QFrame.card:hover {
    border-color: #58a6ff;
}
QGroupBox {
    margin-top: 14px;
    padding: 20px 14px 14px 14px;
    font-weight: 700;
    color: #f0f6fc;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #58a6ff;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}

/* Buttons */
QPushButton {
    background: #238636;
    color: #ffffff;
    border: 1px solid #2ea043;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover {
    background: #2ea043;
    border-color: #3fb950;
}
QPushButton:pressed {
    background: #1a7a2e;
}
QPushButton:disabled {
    background: #21262d;
    color: #484f58;
    border-color: #30363d;
}

/* Location buttons */
QPushButton.location {
    background: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 14px;
}
QPushButton.location:hover {
    background: #30363d;
    border-color: #58a6ff;
    color: #f0f6fc;
}
QPushButton.location:checked {
    background: #1f6feb;
    color: #ffffff;
    border-color: #58a6ff;
}

/* Origin buttons */
QPushButton.origin {
    background: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 16px;
    text-align: left;
    font-size: 12px;
}
QPushButton.origin:hover {
    background: #1c2128;
    border-color: #58a6ff;
}
QPushButton.origin:checked {
    border: 2px solid #58a6ff;
    background: #1c2128;
}

/* Quiet buttons */
QPushButton.quiet {
    background: transparent;
    color: #8b949e;
    border: 1px solid #30363d;
}
QPushButton.quiet:hover {
    color: #f0f6fc;
    border-color: #58a6ff;
}

/* Text inputs */
QLineEdit {
    background: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: #58a6ff;
}
QLineEdit::placeholder {
    color: #484f58;
}

/* Text edit / journal */
QTextEdit {
    background: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px;
    font-size: 12px;
}

/* Combo box */
QComboBox {
    background: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}
QComboBox:hover {
    border-color: #58a6ff;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #8b949e;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
    selection-background-color: #1f6feb;
}

/* Checkboxes */
QCheckBox {
    color: #c9d1d9;
    font-size: 12px;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #30363d;
    border-radius: 3px;
    background: #0d1117;
}
QCheckBox::indicator:checked {
    background: #1f6feb;
    border-color: #58a6ff;
}

/* Scroll areas */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: #161b22;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #484f58;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Progress bars */
QProgressBar {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    text-align: center;
    color: #8b949e;
    font-size: 11px;
}
QProgressBar::chunk {
    background: #238636;
    border-radius: 5px;
}

/* Menu bar */
QMenuBar {
    background: #161b22;
    color: #8b949e;
    border-bottom: 1px solid #30363d;
    padding: 2px;
}
QMenuBar::item {
    padding: 6px 12px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background: #30363d;
    color: #f0f6fc;
}
QMenu {
    background: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 8px 32px 8px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: #1f6feb;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background: #30363d;
    margin: 4px 8px;
}

/* Status bar */
QStatusBar {
    background: #161b22;
    color: #8b949e;
    border-top: 1px solid #30363d;
    font-size: 11px;
}
QStatusBar::item {
    border: none;
}

/* Dialog styling */
QDialog {
    background: #0d1117;
}
QDialog QLabel {
    color: #c9d1d9;
}
QDialogButtonBox QPushButton {
    min-width: 80px;
}
"""


class RivertonWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.engine = GameEngine()
        self.setWindowTitle("Riverton - Year One")
        self.resize(1120, 780)
        self.setMinimumSize(900, 620)

        # Build dev console first
        self._dev_console = DevConsole(self)
        self._dev_console.setVisible(True)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._dev_console)

        # Wire up game engine logging to dev console
        self.engine.set_log_callback(self._on_engine_log)

        # Log startup
        self._dev_console.info("Riverton application starting", "System")

        self._build_menu_bar()
        self._build_pages()
        self.statusBar().showMessage("Choose an origin to begin a new story.")

    def _on_engine_log(self, level: str, message: str, source: str) -> None:
        """Callback from the game engine for logging."""
        self._dev_console.log(level, message, source)
        if hasattr(self, 'dev_log_display'):
            color = "#8b949e"
            if level == "ERROR": color = "#f85149"
            elif level == "WARNING": color = "#d29922"
            elif level == "INFO": color = "#58a6ff"
            self.dev_log_display.append(f'<span style="color: {color}">[{level}] {message}</span>')
            # Scroll to bottom
            self.dev_log_display.verticalScrollBar().setValue(self.dev_log_display.verticalScrollBar().maximum())

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        # Settings menu
        settings_menu = menu_bar.addMenu("Settings")
        llm_action = QAction("LLM settings…", self)
        llm_action.triggered.connect(self._open_llm_settings_dialog)
        settings_menu.addAction(llm_action)

        # View menu
        view_menu = menu_bar.addMenu("View")
        self._toggle_console_action = QAction("Dev Console", self)
        self._toggle_console_action.setCheckable(True)
        self._toggle_console_action.setChecked(True)
        self._toggle_console_action.setShortcut(QKeySequence("Ctrl+`"))
        self._toggle_console_action.triggered.connect(self._toggle_dev_console)
        view_menu.addAction(self._toggle_console_action)

    def _toggle_dev_console(self, checked: bool) -> None:
        """Toggle the dev console visibility."""
        self._dev_console.setVisible(checked)

    def _build_pages(self) -> None:
        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)
        self.setup_page = self._build_setup_page()
        self.creation_page = self._build_creation_page()
        self.generating_overlay = self._build_generating_overlay()
        self.game_page = self._build_game_page()
        self.pages.addWidget(self.setup_page)
        self.pages.addWidget(self.creation_page)
        self.pages.addWidget(self.generating_overlay)
        self.pages.addWidget(self.game_page)

    def _build_setup_page(self) -> QWidget:
        # Start / loading screen with New Game and Continue options
        page = QWidget()
        page.setObjectName("central")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(120, 80, 120, 80)
        layout.setSpacing(20)

        # Decorative top accent line
        accent = QFrame()
        accent.setFixedHeight(3)
        accent.setFixedWidth(80)
        accent.setStyleSheet("background: #58a6ff; border-radius: 2px;")
        layout.addWidget(accent, alignment=Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Riverton")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("A small-town life simulator")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(24)

        new_btn = QPushButton("New Game")
        new_btn.setFixedHeight(54)
        new_btn.setMinimumWidth(280)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(lambda: self.pages.setCurrentWidget(self.creation_page))
        layout.addWidget(new_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        if SAVE_FILE.exists():
            cont_btn = QPushButton("Continue Game")
            cont_btn.setFixedHeight(44)
            cont_btn.setMinimumWidth(280)
            cont_btn.setObjectName("quiet")
            cont_btn.setProperty("class", "quiet")
            cont_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cont_btn.clicked.connect(self._continue_game)
            layout.addWidget(cont_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()

        # Version label
        version = QLabel("v1.0.0")
        version.setStyleSheet("color: #30363d; font-size: 10px;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        return page

    def _build_game_page(self) -> QWidget:
        """Refined game page layout: Header (age circle + stats), Chronicle (left), Sidebar (right), Dev Log (bottom)."""
        page = QWidget()
        page.setObjectName("central")
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # ===== 1. HEADER: Age Circle + Name + Stats =====
        header_frame = QFrame()
        header_frame.setObjectName("card")
        header_frame.setStyleSheet("""
            QFrame#card {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 10px;
                padding: 4px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(16)

        # Age Circle (perfectly circular)
        self.age_circle = QLabel("25")
        self.age_circle.setFixedSize(64, 64)
        self.age_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.age_circle.setStyleSheet("""
            QLabel {
                border: 2px solid #58a6ff;
                border-radius: 32px;
                font-size: 22px;
                font-weight: 700;
                color: #58a6ff;
                background: #0d1117;
            }
        """)
        header_layout.addWidget(self.age_circle)

        # Name and stats column
        name_stats_col = QVBoxLayout()
        name_stats_col.setSpacing(4)

        self.game_title = QLabel("Player Name")
        self.game_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #f0f6fc;")
        name_stats_col.addWidget(self.game_title)

        # Engine stats row (Energy, Money, Skill, Reputation)
        self.engine_stats_layout = QHBoxLayout()
        self.engine_stats_layout.setSpacing(12)
        self.engine_stat_labels = {}
        for stat_key in ["energy", "money", "skill", "reputation"]:
            lbl = QLabel(f"{stat_key.capitalize()}: 0")
            lbl.setStyleSheet("color: #8b949e; font-size: 12px; font-weight: 500;")
            self.engine_stat_labels[stat_key] = lbl
            self.engine_stats_layout.addWidget(lbl)
        name_stats_col.addLayout(self.engine_stats_layout)

        # UI stats row (Happiness, Health, Smarts, Looks) - small progress bars
        self.ui_stats_widget = QWidget()
        self.ui_stats_layout = QHBoxLayout(self.ui_stats_widget)
        self.ui_stats_layout.setContentsMargins(0, 0, 0, 0)
        self.ui_stats_layout.setSpacing(8)
        self.ui_stat_bars = {}
        ui_stat_colors = {
            "happiness": "#f0c000",
            "health": "#3fb950",
            "smarts": "#58a6ff",
            "looks": "#bc8cff",
        }
        for stat_key, color in ui_stat_colors.items():
            bar_container = QWidget()
            bar_container.setFixedWidth(100)
            bar_layout = QVBoxLayout(bar_container)
            bar_layout.setContentsMargins(0, 0, 0, 0)
            bar_layout.setSpacing(1)
            label = QLabel(f"{stat_key.capitalize()}: 50")
            label.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 600;")
            bar_layout.addWidget(label)
            # Progress bar background
            bg = QFrame()
            bg.setFixedHeight(4)
            bg.setStyleSheet("background: #21262d; border-radius: 2px;")
            fill = QFrame()
            fill.setFixedHeight(4)
            fill.setStyleSheet(f"background: {color}; border-radius: 2px;")
            fill.setFixedWidth(50)  # 50% default
            # Stack fill on top of bg using a container
            bar_container2 = QWidget()
            bar_container2.setFixedHeight(4)
            bar2_layout = QVBoxLayout(bar_container2)
            bar2_layout.setContentsMargins(0, 0, 0, 0)
            bar2_layout.setSpacing(0)
            bar2_layout.addWidget(bg)
            bar2_layout.addWidget(fill)
            bar_layout.addWidget(bar_container2)
            self.ui_stat_bars[stat_key] = {"label": label, "fill": fill, "bg": bg}
            self.ui_stats_layout.addWidget(bar_container)
        self.ui_stats_widget.setVisible(False)  # Hidden until game starts
        name_stats_col.addWidget(self.ui_stats_widget)

        header_layout.addLayout(name_stats_col, 1)
        header_layout.addStretch()

        # Action points badge
        self.actions_badge = QLabel("Actions: 3")
        self.actions_badge.setStyleSheet("""
            QLabel {
                background: #1f6feb;
                color: #ffffff;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 12px;
                border-radius: 10px;
            }
        """)
        header_layout.addWidget(self.actions_badge)

        main_layout.addWidget(header_frame)

        # ===== 2. MAIN CONTENT: Chronicle (Left) + Sidebar (Right) =====
        content_area = QHBoxLayout()
        content_area.setSpacing(10)

        # --- Left Panel: Chronicle View (Scrollable) ---
        self.chronicle_scroll = QScrollArea()
        self.chronicle_scroll.setWidgetResizable(True)
        self.chronicle_scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #30363d;
                border-radius: 8px;
                background: #161b22;
            }
        """)
        chronicle_container = QWidget()
        self.chronicle_layout = QVBoxLayout(chronicle_container)
        self.chronicle_layout.setContentsMargins(16, 12, 16, 12)
        self.chronicle_layout.setSpacing(6)

        # Chronicle title
        chronicle_title = QLabel("CHRONICLE")
        chronicle_title.setObjectName("eyebrow")
        chronicle_title.setStyleSheet("color: #58a6ff; font-size: 10px; font-weight: 700; letter-spacing: 1.5px;")
        self.chronicle_layout.addWidget(chronicle_title)

        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #30363d;")
        self.chronicle_layout.addWidget(sep)

        # Year entries will be added here dynamically
        self.year_entries_container = QVBoxLayout()
        self.year_entries_container.setSpacing(8)
        self.chronicle_layout.addLayout(self.year_entries_container)
        self.chronicle_layout.addStretch()

        self.chronicle_scroll.setWidget(chronicle_container)

        # Advance Year section (below chronicle in left column)
        left_column = QVBoxLayout()
        left_column.setSpacing(6)
        left_column.addWidget(self.chronicle_scroll, 1)

        # Advance Year button area
        advance_frame = QFrame()
        advance_frame.setObjectName("card")
        advance_frame.setStyleSheet("""
            QFrame#card {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        advance_layout = QVBoxLayout(advance_frame)
        advance_layout.setContentsMargins(8, 6, 8, 6)
        advance_layout.setSpacing(4)
        advance_label = QLabel("Advance Year")
        advance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        advance_label.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600; letter-spacing: 1px;")
        advance_layout.addWidget(advance_label)

        self.advance_year_btn = QPushButton("+")
        self.advance_year_btn.setFixedSize(48, 48)
        self.advance_year_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.advance_year_btn.setStyleSheet("""
            QPushButton {
                background: #238636;
                color: #ffffff;
                border: 2px solid #2ea043;
                border-radius: 24px;
                font-size: 24px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #2ea043;
                border-color: #3fb950;
            }
            QPushButton:pressed {
                background: #1a7a2e;
            }
        """)
        self.advance_year_btn.clicked.connect(self._open_decision_dialog)
        advance_layout.addWidget(self.advance_year_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        left_column.addWidget(advance_frame)

        # --- Right Panel: Sidebar (Map + NPCs + Actions) ---
        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFixedWidth(280)
        self.sidebar_scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #30363d;
                border-radius: 8px;
                background: #161b22;
            }
        """)
        sidebar_container = QWidget()
        self.sidebar_layout = QVBoxLayout(sidebar_container)
        self.sidebar_layout.setContentsMargins(12, 12, 12, 12)
        self.sidebar_layout.setSpacing(10)

        # Map Section
        map_label = QLabel("MAP")
        map_label.setObjectName("eyebrow")
        map_label.setStyleSheet("color: #58a6ff; font-size: 10px; font-weight: 700; letter-spacing: 1.5px;")
        self.sidebar_layout.addWidget(map_label)

        self.map_grid = QGridLayout()
        self.map_grid.setSpacing(6)
        self.map_buttons = {}
        self.sidebar_layout.addLayout(self.map_grid)

        # Separator
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: #30363d;")
        self.sidebar_layout.addWidget(sep2)

        # People Here Section
        people_label = QLabel("PEOPLE HERE")
        people_label.setObjectName("eyebrow")
        people_label.setStyleSheet("color: #58a6ff; font-size: 10px; font-weight: 700; letter-spacing: 1.5px;")
        self.sidebar_layout.addWidget(people_label)

        self.npcs_container = QVBoxLayout()
        self.npcs_container.setSpacing(6)
        self.sidebar_layout.addLayout(self.npcs_container)

        self.sidebar_layout.addStretch()

        self.sidebar_scroll.setWidget(sidebar_container)

        content_area.addLayout(left_column, 1)
        content_area.addWidget(self.sidebar_scroll, 0)

        main_layout.addLayout(content_area, 1)

        # ===== 3. BOTTOM: Dev Log Footer =====
        dev_log_frame = QFrame()
        dev_log_frame.setObjectName("card")
        dev_log_frame.setStyleSheet("""
            QFrame#card {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 2px;
            }
        """)
        dev_log_layout = QVBoxLayout(dev_log_frame)
        dev_log_layout.setContentsMargins(8, 4, 8, 4)
        dev_log_layout.setSpacing(2)

        dev_log_header = QHBoxLayout()
        dev_log_title = QLabel("DEV LOG")
        dev_log_title.setObjectName("eyebrow")
        dev_log_title.setStyleSheet("color: #8b949e; font-size: 9px; font-weight: 700; letter-spacing: 1.5px;")
        dev_log_header.addWidget(dev_log_title)
        dev_log_header.addStretch()
        dev_log_layout.addLayout(dev_log_header)

        self.dev_log_display = QTextEdit()
        self.dev_log_display.setReadOnly(True)
        self.dev_log_display.setFixedHeight(80)
        self.dev_log_display.setStyleSheet("""
            QTextEdit {
                background: #0d1117;
                color: #8b949e;
                border: 1px solid #21262d;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        dev_log_layout.addWidget(self.dev_log_display)

        main_layout.addWidget(dev_log_frame)

        return page

    def _build_creation_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("central")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(52, 24, 52, 24)
        layout.setSpacing(12)

        header = QLabel("Create Your Character")
        header.setObjectName("title")
        header.setStyleSheet("font-size: 36px;")
        layout.addWidget(header)

        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Your name")
        self.name_input.setMaxLength(32)
        form.addRow("Name", self.name_input)

        self.era_input = QLineEdit(enumerate_eras()[0])
        self.era_input.setPlaceholderText(f"Era ({', '.join(enumerate_eras())})")
        form.addRow("Era", self.era_input)

        self.age_input = QLineEdit("")
        self.age_input.setPlaceholderText("Age (optional)")
        form.addRow("Age", self.age_input)

        self.start_year_box = QComboBox()
        self.start_year_box.addItems(["1", "2"])
        form.addRow("Start year", self.start_year_box)

        self.llm_box = QCheckBox("Generate starting scenario, map, and NPCs using local LLM")
        self.llm_box.setChecked(False)
        form.addRow("Use LLM", self.llm_box)

        layout.addLayout(form)

        origin_label = QLabel("ORIGIN")
        origin_label.setObjectName("eyebrow")
        layout.addWidget(origin_label)
        self.origin_group = QButtonGroup(self)
        self.origin_group.setExclusive(True)
        origin_grid = QGridLayout()
        origin_grid.setHorizontalSpacing(12)
        origin_grid.setVerticalSpacing(12)
        for index, origin in enumerate(ORIGINS):
            button = QPushButton(f"{origin['tag']}\n\n{origin['name']}\n{origin['description']}")
            button.setObjectName("origin")
            button.setProperty("class", "origin")
            button.setCheckable(True)
            button.setMinimumHeight(120)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("origin_id", origin["id"])
            self.origin_group.addButton(button)
            origin_grid.addWidget(button, index // 2, index % 2)
            if index == 0:
                button.setChecked(True)
        layout.addLayout(origin_grid)

        controls = QHBoxLayout()
        generate = QPushButton("Generate")
        generate.setCursor(Qt.CursorShape.PointingHandCursor)
        generate.clicked.connect(lambda: self._on_generate_clicked())
        controls.addWidget(generate)
        begin = QPushButton("Begin without generation")
        begin.setCursor(Qt.CursorShape.PointingHandCursor)
        begin.clicked.connect(lambda: self._apply_character_template(None, self.name_input.text(), self.era_input.text(), self.age_input.text(), int(self.start_year_box.currentText()), False))
        controls.addWidget(begin)
        back = QPushButton("Back")
        back.setObjectName("quiet")
        back.setProperty("class", "quiet")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(lambda: self.pages.setCurrentWidget(self.setup_page))
        controls.addWidget(back)
        controls.addStretch()
        layout.addLayout(controls)
        return page

    def _build_generating_overlay(self) -> QWidget:
        """A subtle generating overlay instead of a full loading screen."""
        page = QWidget()
        page.setObjectName("central")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(52, 44, 52, 44)
        layout.setSpacing(16)

        layout.addStretch()

        # Spinner style animation (CSS-based)
        spinner = QLabel("⟳")
        spinner.setStyleSheet("""
            font-size: 48px;
            color: #58a6ff;
            background: transparent;
        """)
        spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(spinner)

        self.generating_label = QLabel("Generating your story…")
        self.generating_label.setStyleSheet("""
            font-size: 18px;
            color: #8b949e;
            font-weight: 500;
            background: transparent;
        """)
        self.generating_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.generating_label)

        self.generating_detail = QLabel("Creating scenario, NPCs, and locations")
        self.generating_detail.setStyleSheet("""
            font-size: 12px;
            color: #484f58;
            background: transparent;
        """)
        self.generating_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.generating_detail)

        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setFixedWidth(280)
        bar.setFixedHeight(6)
        layout.addWidget(bar, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        return page

    def _start_new_game(self) -> None:
        button = self.origin_group.checkedButton()
        origin_id = button.property("origin_id") if button else ""
        try:
            state = self.engine.new_game(self.name_input.text(), origin_id)
        except GameRuleError as error:
            self._error(str(error))
            return
        self._dev_console.info(f"New game started: {self.name_input.text()} ({origin_id})", "Game")
        self.pages.setCurrentWidget(self.game_page)
        self._render(state)

    def _continue_game(self) -> None:
        # Check for per-game folders first
        saved_games = game_config.list_games()
        if saved_games:
            selected = self._choose_game_dialog(saved_games)
            if selected is None:
                return
            try:
                game_folder = game_config.GAMES_DIR / selected["folder"]
                state = self.engine.load_game(game_folder=game_folder)
            except GameRuleError as error:
                self._error(str(error))
                return
            self._dev_console.info(f"Continuing saved game: {selected['player_name']}", "Game")
            self.pages.setCurrentWidget(self.game_page)
            self._render(state)
            return

        # Fallback: legacy save file
        try:
            state = self.engine.load_game()
        except GameRuleError as error:
            self._error(str(error))
            return
        self._dev_console.info("Continuing saved game", "Game")
        self.pages.setCurrentWidget(self.game_page)
        self._render(state)

    def _choose_game_dialog(self, saved_games: list[dict]) -> QDialog | None:
        """Show a dialog to pick which saved game to continue."""
        if len(saved_games) == 1:
            self._dev_console.info(f"Found 1 saved game: {saved_games[0]['player_name']}", "Game")
            return saved_games[0]

        dialog = QDialog(self)
        dialog.setWindowTitle("Continue Game")
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)

        title = QLabel("Select a saved game")
        title.setStyleSheet("font-family: Georgia; font-size: 20px; font-weight: 700; color: #f0f6fc;")
        layout.addWidget(title)

        for game in saved_games:
            if not game.get("has_save"):
                continue
            btn = QPushButton(f"{game['player_name']}\nCreated: {game['created']}")
            btn.setMinimumHeight(60)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: #21262d;
                    color: #c9d1d9;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 10px 14px;
                    font-size: 12px;
                    text-align: left;
                }
                QPushButton:hover {
                    background: #30363d;
                    border-color: #58a6ff;
                }
            """)
            btn.clicked.connect(lambda _, g=game: (dialog.accept(), setattr(dialog, "_selected_game", g)))
            layout.addWidget(btn)

        cancel = QPushButton("Cancel")
        cancel.setObjectName("quiet")
        cancel.setProperty("class", "quiet")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(dialog.reject)
        layout.addWidget(cancel)

        # If no games have saves, return the first one
        dialog._selected_game = saved_games[0] if saved_games and saved_games[0].get("has_save") else None
        dialog.exec()
        return getattr(dialog, "_selected_game", None)

    def _show_setup(self) -> None:
        self.name_input.clear()
        self.pages.setCurrentWidget(self.setup_page)
        self.name_input.setFocus()
        self.statusBar().showMessage("Choose an origin to begin a new story.")

    def _apply_character_template(self, dialog: QDialog | None, name: str, era: str, age_text: str, start_year: int = 1, use_llm: bool = False) -> None:
        try:
            age = int(age_text) if age_text.strip() else None
        except ValueError:
            age = None
        template = build_character_template(name=name or self.name_input.text() or "Player", era=era or "modern", age=age)
        button = self.origin_group.checkedButton()
        origin_id = button.property("origin_id") if button else ""
        if use_llm:
            self._start_generation(template, origin_id, start_year)
            if dialog is not None:
                dialog.accept()
            return

        try:
            state = self.engine.new_game(template["player"]["name"], origin_id)
        except GameRuleError as error:
            self._error(str(error))
            return
        player = self.engine.state["player"]
        tpl_player = template["player"]
        player["era"] = tpl_player.get("era")
        player["age"] = tpl_player.get("age")
        player["stats"] = tpl_player.get("stats", player.get("stats", {}))
        player["ui_stats"] = tpl_player.get("ui_stats", {})
        try:
            self.engine.state["year"] = int(start_year)
        except Exception:
            pass
        try:
            self.engine._save()
        except Exception:
            pass
        if dialog is not None:
            dialog.accept()
        self._dev_console.info(f"Character created: {template['player']['name']}", "Game")
        self.pages.setCurrentWidget(self.game_page)
        self._render(self.engine.public_state())

    def _on_generate_clicked(self) -> None:
        try:
            age = int(self.age_input.text()) if self.age_input.text().strip() else None
        except ValueError:
            age = None
        template = build_character_template(name=self.name_input.text() or "Player", era=self.era_input.text() or "modern", age=age)
        btn = self.origin_group.checkedButton()
        origin_id = btn.property("origin_id") if btn else ""
        start_year = int(self.start_year_box.currentText())
        self._start_generation(template, origin_id, start_year)

    def _start_generation(self, template: dict[str, Any], origin_id: str, start_year: int) -> None:
        self._dev_console.info("Starting LLM generation...", "LLM")
        self.generating_detail.setText("Creating scenario, NPCs, and locations")
        self.pages.setCurrentWidget(self.generating_overlay)
        self._generation_timer = None
        self._generation_worker = None

        self._generation_timer = QTimer(self)
        self._generation_timer.setSingleShot(True)
        self._generation_timer.timeout.connect(self._on_generation_timeout)
        self._generation_timer.start(GENERATION_TIMEOUT_SECONDS * 1000)

        self._generation_worker = GenerationWorker(template, origin_id, start_year)
        self._generation_worker.finished.connect(self._on_generation_complete)
        self._generation_worker.error.connect(self._on_generation_error)

        thread = threading.Thread(target=self._generation_worker.run, daemon=True)
        thread.start()

    def _on_generation_timeout(self) -> None:
        self._generation_timer = None
        self._generation_worker = None
        self._dev_console.warn(f"Generation timed out after {GENERATION_TIMEOUT_SECONDS}s", "LLM")
        self.pages.setCurrentWidget(self.game_page)
        self._error(
            f"Generation is taking longer than {GENERATION_TIMEOUT_SECONDS} seconds. "
            "The LLM may not be responding. Please check your LM Studio / LLM endpoint "
            "status in Settings → LLM settings, and try again."
        )

    def _on_generation_error(self, error_msg: str) -> None:
        if self._generation_timer:
            self._generation_timer.stop()
            self._generation_timer = None
        self._generation_worker = None
        self._dev_console.error(f"Generation failed: {error_msg}", "LLM")
        self.pages.setCurrentWidget(self.game_page)
        self._error(f"Generation failed: {error_msg}\n\nPlease check that your LLM endpoint is running at the URL configured in Settings → LLM settings, and that the model is loaded.")

    def _on_generation_complete(self, template: dict[str, Any], origin_id: str, start_year: int, generated: dict[str, Any]) -> None:
        if self._generation_timer:
            self._generation_timer.stop()
            self._generation_timer = None
        self._generation_worker = None
        self._dev_console.info("Generation completed successfully", "LLM")

        dynamic_locations = None
        dynamic_npcs = None
        starting_scenario = ""
        starting_map = {}
        if generated:
            map_data = generated.get("map", {})
            if isinstance(map_data, dict):
                locs = map_data.get("locations", {})
                if isinstance(locs, dict) and locs:
                    dynamic_locations = locs
                starting_map = map_data
            starting_scenario = generated.get("scenario", "")
            gen_npcs = generated.get("npcs", [])
            if isinstance(gen_npcs, list) and gen_npcs:
                dynamic_npcs = gen_npcs

        try:
            state = self.engine.new_game(
                template["player"]["name"],
                origin_id,
                dynamic_locations=dynamic_locations,
                dynamic_npcs=dynamic_npcs,
                generated=generated,
            )
        except GameRuleError as error:
            self._error(f"Game Rule Error on load: {str(error)}")
            return

        try:
            player = self.engine.state["player"]
            tpl_player = template["player"]
            player["era"] = tpl_player.get("era")
            player["age"] = tpl_player.get("age")
            existing_stats = player.get("stats", {})
            player["stats"].update(tpl_player.get("stats", {}))
            self.engine.state["ui_stats"] = tpl_player.get("ui_stats", {})
            self.engine.state["starting_scenario"] = starting_scenario
            self.engine.state["starting_map"] = starting_map
        except Exception as e:
            self._error(f"Error updating player state from generation result: {e}")

        try:
            self.engine.state["year"] = int(start_year)
        except Exception:
            pass

        if starting_scenario:
            self.engine._memory(starting_scenario, tags=["starting_scenario"], importance=5)

        try:
            self.engine._save()
        except Exception as e:
            print(f"Warning: Failed to save game state after generation: {e}")

        self.pages.setCurrentWidget(self.game_page)
        try:
            self._render(self.engine.public_state())
        except Exception as e:
            self._error(f"Critical Error during final render: {e}")

    def _preview_generated_scenario(self, name: str, era: str, age_text: str, use_llm: bool) -> None:
        try:
            age = int(age_text) if age_text.strip() else None
        except ValueError:
            age = None
        template = build_character_template(name=name or self.name_input.text() or "Player", era=era or "modern", age=age)
        if not use_llm:
            QMessageBox.information(self, "Preview", "LLM preview is disabled. Check 'Use LLM' to enable generation.")
            return
        try:
            generated = generate_starting_scenario(template)
            npcs = generated.get("npcs", [])
            summary = generated.get("scenario", "(no summary)")
            msg = f"Scenario:\n{summary}\n\nNPCs:\n" + "\n".join(f"- {n.get('name')} ({n.get('role')}) @ {n.get('location')}" for n in npcs[:6])
            QMessageBox.information(self, "Generated preview", msg)
        except Exception:
            QMessageBox.warning(self, "Preview", "Could not generate preview from LLM.")

    def _run_action(self, method, *args) -> None:
        try:
            self._render(method(*args))
        except GameRuleError as error:
            self._error(str(error))

    def _render(self, state: dict) -> None:
        """Render the full game UI from the engine state."""
        player = state.get("player", {})
        stats = player.get("stats", {})
        age = player.get("age", 25)
        self.age_circle.setText(str(age))
        self.game_title.setText(player.get("name", "Unknown"))
        
        # Update engine stats (Energy, Money, Skill, Reputation)
        for stat_key in ["energy", "money", "skill", "reputation"]:
            lbl = self.engine_stat_labels.get(stat_key)
            if lbl:
                val = stats.get(stat_key, 0)
                if stat_key == "money":
                    lbl.setText(f"Money: ${val}")
                else:
                    lbl.setText(f"{stat_key.capitalize()}: {val}")
        
        # Update UI stats (Happiness, Health, Smarts, Looks) with progress bars
        player_ui_stats = player.get("ui_stats", {})
        if player_ui_stats:
            self.ui_stats_widget.setVisible(True)
            for stat_key, bar_data in self.ui_stat_bars.items():
                val = player_ui_stats.get(stat_key, 50)
                val = max(0, min(100, val))
                bar_data["label"].setText(f"{stat_key.capitalize()}: {val}")
                bar_data["fill"].setFixedWidth(int(val * 0.64))  # 64px max width for 100 value
        else:
            self.ui_stats_widget.setVisible(False)
        
        # Update actions badge
        actions = state.get("actions_remaining", 0)
        self.actions_badge.setText(f"Actions: {actions}")
        if actions <= 0:
            self.actions_badge.setStyleSheet("""
                QLabel {
                    background: #da3633;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 4px 12px;
                    border-radius: 10px;
                }
            """)
        else:
            self.actions_badge.setStyleSheet("""
                QLabel {
                    background: #1f6feb;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 4px 12px;
                    border-radius: 10px;
                }
            """)
        
        # Update status bar
        season = state.get("season", "Spring")
        year = state.get("year", 1)
        location = state.get("player", {}).get("location", "apartment")
        loc_name = state.get("all_locations", {}).get(location, location)
        self.statusBar().showMessage(f"📍 {loc_name}  |  {season}  |  Year {year}")
        
        # Render chronicle and sidebar
        self._render_year_progression(state)
        self._render_map_and_features(state)

    def _render_year_progression(self, state: dict) -> None:
        """Render the chronicle view with years grouped and memory entries."""
        self._clear_layout(self.year_entries_container)
        
        memories = state.get("memories", [])
        current_year = state.get("year", 1)
        
        # Group memories by year (using structured memory store if available)
        # For now, distribute memories across years evenly
        year_memories: dict[int, list[str]] = {}
        for y in range(1, current_year + 1):
            year_memories[y] = []
        
        if memories:
            # Distribute memories across years (last memories = most recent year)
            mems_per_year = max(1, len(memories) // current_year)
            for i, mem in enumerate(memories):
                text = mem if isinstance(mem, str) else mem.get("text", "...")
                year_idx = min(i // mems_per_year, current_year - 1)
                year_memories[year_idx + 1].append(text)
        
        # Render each year
        for y in range(1, current_year + 1):
            # Year header
            year_header = QWidget()
            year_header_layout = QHBoxLayout(year_header)
            year_header_layout.setContentsMargins(0, 0, 0, 0)
            year_header_layout.setSpacing(8)
            
            year_label = QLabel(f"Year {y}")
            year_label.setStyleSheet("""
                font-size: 16px;
                font-weight: 700;
                color: #58a6ff;
                padding: 4px 0;
            """)
            year_header_layout.addWidget(year_label)
            
            # Year separator line
            year_line = QFrame()
            year_line.setFixedHeight(1)
            year_line.setStyleSheet("background: #30363d;")
            year_header_layout.addWidget(year_line, 1)
            
            self.year_entries_container.addWidget(year_header)
            
            # Memory entries for this year
            mems = year_memories.get(y, [])
            if not mems:
                # Placeholder for empty year
                empty_label = QLabel("No memories recorded yet...")
                empty_label.setStyleSheet("""
                    color: #484f58;
                    font-size: 12px;
                    font-style: italic;
                    padding-left: 12px;
                    padding-bottom: 4px;
                """)
                self.year_entries_container.addWidget(empty_label)
            else:
                for mem_text in mems:
                    mem_entry = QFrame()
                    mem_entry.setStyleSheet("""
                        QFrame {
                            background: #0d1117;
                            border: 1px solid #21262d;
                            border-radius: 4px;
                            padding: 6px 10px;
                            margin-left: 8px;
                        }
                    """)
                    mem_layout = QVBoxLayout(mem_entry)
                    mem_layout.setContentsMargins(8, 4, 8, 4)
                    mem_layout.setSpacing(2)
                    
                    mem_label = QLabel(mem_text)
                    mem_label.setWordWrap(True)
                    mem_label.setStyleSheet("color: #c9d1d9; font-size: 12px; background: transparent; border: none;")
                    mem_layout.addWidget(mem_label)
                    
                    self.year_entries_container.addWidget(mem_entry)
        
        # Scroll to bottom to show latest entries
        QTimer.singleShot(50, lambda: self.chronicle_scroll.verticalScrollBar().setValue(
            self.chronicle_scroll.verticalScrollBar().maximum()
        ))

    def _render_map_and_features(self, state: dict) -> None:
        """Render the sidebar with map buttons and NPC list."""
        # Clear map grid and NPCs container (keep the fixed section headers)
        self._clear_layout(self.map_grid)
        self._clear_layout(self.npcs_container)
        
        current_loc = state["player"]["location"]
        all_locations = state.get("all_locations", LOCATIONS)
        
        # 1. MAP - location buttons in a grid
        self.map_buttons.clear()
        col_count = 2
        for i, (loc_id, loc_name) in enumerate(all_locations.items()):
            btn = QPushButton(loc_name)
            btn.setCheckable(True)
            btn.setChecked(loc_id == current_loc)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: #21262d;
                    color: #c9d1d9;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 8px 10px;
                    font-size: 11px;
                    font-weight: 600;
                    text-align: center;
                }
                QPushButton:hover {
                    background: #30363d;
                    border-color: #58a6ff;
                    color: #f0f6fc;
                }
                QPushButton:checked {
                    background: #1f6feb;
                    color: #ffffff;
                    border-color: #58a6ff;
                }
            """)
            btn.clicked.connect(partial(self._run_action, self.engine.travel, loc_id))
            self.map_buttons[loc_id] = btn
            self.map_grid.addWidget(btn, i // col_count, i % col_count)
        
        # 2. PEOPLE HERE - NPC list at current location
        npcs = state.get("npcs", [])
        here = [npc for npc in npcs if npc.get("location") == current_loc]
        
        if not here:
            empty_npc = QLabel("No one is here right now.")
            empty_npc.setStyleSheet("color: #484f58; font-size: 11px; font-style: italic; padding: 4px 0;")
            self.npcs_container.addWidget(empty_npc)
        else:
            for npc in here:
                npc_card = QFrame()
                npc_card.setObjectName("npc_card")
                npc_card.setStyleSheet("""
                    QFrame#npc_card {
                        background: #0d1117;
                        border: 1px solid #21262d;
                        border-radius: 6px;
                        padding: 8px;
                        margin: 0;
                    }
                    QFrame#npc_card:hover {
                        border-color: #30363d;
                    }
                """)
                npc_layout = QVBoxLayout(npc_card)
                npc_layout.setContentsMargins(8, 6, 8, 6)
                npc_layout.setSpacing(4)
                
                # NPC name and role
                name_lbl = QLabel(f"<b>{npc['name']}</b>  <span style='color:#8b949e;font-size:10px;'>{npc.get('role', '')}</span>")
                name_lbl.setStyleSheet("font-size: 12px; background: transparent;")
                name_lbl.setTextFormat(Qt.TextFormat.RichText)
                npc_layout.addWidget(name_lbl)
                
                # Relationship indicators
                rel_text = f"Trust: {npc.get('trust', 0)} | Affinity: {npc.get('affinity', 0)}"
                rel_lbl = QLabel(rel_text)
                rel_lbl.setStyleSheet("color: #484f58; font-size: 10px; background: transparent;")
                npc_layout.addWidget(rel_lbl)
                
                # Action buttons row
                action_row = QHBoxLayout()
                action_row.setSpacing(4)
                for act in ["talk", "help", "work"]:
                    ab = QPushButton(act.capitalize())
                    ab.setFixedHeight(24)
                    ab.setCursor(Qt.CursorShape.PointingHandCursor)
                    ab.setStyleSheet("""
                        QPushButton {
                            background: #21262d;
                            color: #c9d1d9;
                            border: 1px solid #30363d;
                            border-radius: 4px;
                            padding: 2px 8px;
                            font-size: 10px;
                            font-weight: 600;
                        }
                        QPushButton:hover {
                            background: #30363d;
                            border-color: #58a6ff;
                        }
                        QPushButton:pressed {
                            background: #1f6feb;
                        }
                    """)
                    ab.clicked.connect(partial(self._run_action, self.engine.interact, npc["id"], act))
                    action_row.addWidget(ab)
                action_row.addStretch()
                npc_layout.addLayout(action_row)
                
                self.npcs_container.addWidget(npc_card)

    def _open_decision_dialog(self) -> None:
        try:
            state = self.engine.public_state()
        except GameRuleError as error:
            self._error(str(error))
            return
        dialog = QDialog(self)
        dialog.setMinimumWidth(560)
        dialog.setWindowTitle("Riverton")
        layout = QVBoxLayout(dialog)
        if state["completed"]:
            dialog.setWindowTitle("Year complete")
            title = QLabel(state["outcome"]["title"])
            title.setStyleSheet("font-family: Georgia; font-size: 22px; font-weight: 700; color: #f0f6fc;")
            body = QLabel(state["outcome"]["text"])
            body.setStyleSheet("color: #8b949e;")
            body.setWordWrap(True)
            button = QPushButton("Play a different life")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda: (dialog.accept(), self._show_setup()))
            layout.addWidget(title)
            layout.addWidget(body)
            layout.addSpacing(12)
            layout.addWidget(button)
            dialog.exec()
            return
        random_event = state["active_random_event"]
        event = random_event or state["event"]
        is_random = random_event is not None
        if not is_random and state["actions_remaining"] > 0:
            self._error("Use all seasonal actions before opening the next decision.")
            return
        dialog.setWindowTitle("A moment between seasons" if is_random else "New Year")
        eyebrow = QLabel("RANDOM EVENT" if is_random else "NEW YEAR DECISION")
        eyebrow.setObjectName("eyebrow")
        title = QLabel(event["title"])
        title.setStyleSheet("font-family: Georgia; font-size: 25px; font-weight: 700; color: #f0f6fc;")
        body = QLabel(event["text"])
        body.setWordWrap(True)
        body.setStyleSheet("color: #8b949e;")
        choices = QVBoxLayout()
        method = self.engine.choose_random if is_random else self.engine.choose_main
        for choice in event["choices"]:
            button = QPushButton(f"{choice['label']}\n{choice.get('text', 'Choose this response.')}")
            button.setMinimumHeight(66)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(partial(self._choose_from_dialog, dialog, method, choice["id"]))
            choices.addWidget(button)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addSpacing(8)
        layout.addLayout(choices)
        dialog.exec()

    def _choose_from_dialog(self, dialog: QDialog, method, choice_id: str) -> None:
        try:
            state = method(choice_id)
        except GameRuleError as error:
            self._error(str(error))
            return
        dialog.accept()
        self._render(state)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                RivertonWindow._clear_layout(item.layout())

    def _open_llm_settings_dialog(self) -> None:
        settings = load_llm_settings()
        dialog = QDialog(self)
        dialog.setWindowTitle("LLM settings")
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        base_url_input = QLineEdit(settings.get("base_url", "http://127.0.0.1:1234/v1"))
        base_url_input.setStyleSheet("""
            QLineEdit { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
            border-radius: 4px; padding: 6px 10px; }
            QLineEdit:focus { border-color: #58a6ff; }
        """)
        model_input = QLineEdit(settings.get("model", "local-model"))
        model_input.setStyleSheet("""
            QLineEdit { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
            border-radius: 4px; padding: 6px 10px; }
            QLineEdit:focus { border-color: #58a6ff; }
        """)
        enabled_box = QCheckBox("Use local LLM for seasonal choices")
        enabled_box.setChecked(bool(settings.get("enabled", True)))
        form.addRow("Base URL", base_url_input)
        form.addRow("Model", model_input)
        form.addRow("", enabled_box)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(lambda: self._save_llm_settings(dialog, base_url_input.text(), model_input.text(), enabled_box.isChecked()))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _save_llm_settings(self, dialog: QDialog, base_url: str, model: str, enabled: bool) -> None:
        payload = {"base_url": base_url.strip() or "http://127.0.0.1:1234/v1", "model": model.strip() or "local-model", "enabled": enabled}
        save_llm_settings(payload)
        dialog.accept()
        self.statusBar().showMessage("LLM settings saved. Riverton will use them for future season choices.", 5000)
        self._test_llm_connection(payload)

    def _test_llm_connection(self, settings: dict) -> None:
        try:
            options = get_dynamic_year_options({"player": {"location": "cafe", "stats": {"energy": 2, "money": 1, "skill": 1, "reputation": 1}}, "npcs": [{"id": "priya", "trust": 2, "affinity": 1}, {"id": "sam", "trust": 1, "affinity": 0}], "flags": {"cafe_shift": True}}, base_url=settings.get("base_url"), model=settings.get("model"), enabled=settings.get("enabled", True))
        except Exception:
            options = []
        if options:
            QMessageBox.information(self, "LLM connection", "Connection looks good. Riverton can request seasonal options from LM Studio.")
            self._dev_console.info("LLM connection test: successful", "LLM")
        else:
            QMessageBox.warning(self, "LLM connection", "The app could not reach LM Studio. It will fall back to built-in options until the endpoint is available.")
            self._dev_console.warn("LLM connection test: failed", "LLM")

    def _error(self, message: str) -> None:
        self.statusBar().showMessage(message, 5000)
        self._dev_console.error(message, "UI")
        QMessageBox.warning(self, "Riverton", message)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    window = RivertonWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
