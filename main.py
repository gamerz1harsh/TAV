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

from game_engine import GameEngine, GameRuleError, LOCATIONS, ORIGINS
from game_features import filter_memories
from llm_service import check_llm_connection, get_dynamic_year_options, generate_starting_scenario, load_llm_settings, save_llm_settings
from character_creation import enumerate_eras, build_character_template
from game_schema import get_menu_slots
from desktop.screens.creation_screen import CreationScreen
from desktop.screens.naruto_game_screen import NarutoGameScreen
from desktop.theme import APP_STYLE
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


class RivertonWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.engine = GameEngine()
        self.setWindowTitle("Anime Sim | Naruto World Pack")
        self.resize(1360, 860)
        self.setMinimumSize(1050, 680)

        # Build dev console first
        self._dev_console = DevConsole(self)
        self._dev_console.setVisible(False)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._dev_console)

        # Wire up game engine logging to dev console
        self.engine.set_log_callback(self._on_engine_log)

        # Log startup
        self._dev_console.info("Anime Sim application starting", "System")

        self._build_menu_bar()
        self._build_pages()
        self.statusBar().showMessage("Choose your village, family, chakra nature, and early strength.")

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

        # View menu
        view_menu = menu_bar.addMenu("View")
        self._toggle_console_action = QAction("Dev Console", self)
        self._toggle_console_action.setCheckable(True)
        self._toggle_console_action.setChecked(False)
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
        self.creation_page = CreationScreen()
        self.creation_page.generate_requested.connect(self._on_generate_clicked)
        self.creation_page.begin_requested.connect(self._on_begin_without_generation)
        self.creation_page.back_requested.connect(lambda: self.pages.setCurrentWidget(self.setup_page))
        self.generating_overlay = self._build_generating_overlay()
        self.game_page = self._build_game_page()
        self.pages.addWidget(self.setup_page)
        self.pages.addWidget(self.creation_page)
        self.pages.addWidget(self.generating_overlay)
        self.pages.addWidget(self.game_page)

    def _build_setup_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("central")
        page.setStyleSheet("""
            QWidget#central { background: #111820; color: #e7eee8; font-family: 'Bahnschrift', 'Yu Gothic UI', sans-serif; }
            QLabel#eyebrow { color: #63c6bb; font-size: 10px; font-weight: 800; letter-spacing: 3px; }
            QLabel#heroTitle { color: #e7eee8; font-size: 48px; font-weight: 900; }
            QLabel#muted { color: #99aaa5; font-size: 14px; }
            QFrame#hero { background: #1d2a32; border: 1px solid #34474c; border-radius: 18px; }
            QPushButton { background: #24343c; color: #e7eee8; border: 1px solid #34474c; border-radius: 9px; padding: 13px 20px; font-weight: 750; }
            QPushButton:hover { border-color: #63c6bb; }
            QPushButton#primary { background: #9fce91; color: #17231e; border-color: #9fce91; font-weight: 900; }
            QPushButton#primary:hover { background: #b4dca7; }
        """)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(56, 42, 56, 34)
        layout.setSpacing(20)
        layout.addStretch(1)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(38, 34, 38, 34)
        hero_layout.setSpacing(14)
        eyebrow = QLabel("WORLD PACK 01  /  NARUTO")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Anime Sim")
        title.setObjectName("heroTitle")
        subtitle = QLabel("A life simulator shaped by training, relationships, and the choices you make each year.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        hero_layout.addWidget(eyebrow)
        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)
        layout.addWidget(hero, alignment=Qt.AlignmentFlag.AlignHCenter)

        detail_row = QHBoxLayout()
        detail_row.setSpacing(12)
        for heading, detail in (
            ("GROW", "Train fundamentals and unlock focused paths."),
            ("CONNECT", "People remember how you treat them."),
            ("PROGRESS", "Earn techniques and advance through shinobi ranks."),
        ):
            card = QFrame()
            card.setObjectName("hero")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 15, 18, 15)
            card_layout.setSpacing(6)
            title_label = QLabel(heading)
            title_label.setObjectName("eyebrow")
            body = QLabel(detail)
            body.setObjectName("muted")
            body.setWordWrap(True)
            card_layout.addWidget(title_label)
            card_layout.addWidget(body)
            detail_row.addWidget(card, 1)
        layout.addLayout(detail_row)

        controls = QHBoxLayout()
        controls.addStretch()
        new_btn = QPushButton("Begin a New Life")
        new_btn.setObjectName("primary")
        new_btn.setMinimumWidth(260)
        new_btn.setMinimumHeight(48)
        new_btn.clicked.connect(lambda: self.pages.setCurrentWidget(self.creation_page))
        controls.addWidget(new_btn)
        if self._naruto_saved_games():
            cont_btn = QPushButton("Continue a Life")
            cont_btn.setMinimumHeight(48)
            cont_btn.clicked.connect(self._continue_game)
            controls.addWidget(cont_btn)
        controls.addStretch()
        layout.addLayout(controls)
        layout.addStretch(1)

        version = QLabel("SHINOBI LIFE  /  WORLD PACK 1.0")
        version.setObjectName("eyebrow")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        return page

    def _build_game_page(self) -> QWidget:
        """Build the pack-driven navigation rail and center workspace."""
        self.naruto_screen = NarutoGameScreen()
        self.naruto_screen.action_requested.connect(self._perform_world_action)
        self.naruto_screen.social_requested.connect(self._interact_with_world_npc)
        self.naruto_screen.travel_requested.connect(self._travel_world_location)
        self.naruto_screen.advance_year_requested.connect(self._advance_world_year)
        self.naruto_screen.save_requested.connect(self._save_world_game)
        self.naruto_screen.settings_requested.connect(self._open_llm_settings_dialog)
        self.naruto_screen.purchase_requested.connect(self._purchase_world_item)
        self.naruto_screen.apply_job_requested.connect(self._apply_for_world_job)
        self.naruto_screen.work_job_requested.connect(lambda: self._run_action(self.engine.work_world_job))
        return self.naruto_screen

    def _build_top_banner(self, parent_layout: QVBoxLayout) -> None:
        banner = QFrame()
        banner.setObjectName("card")
        banner.setStyleSheet("""
            QFrame#card {
                background: #171b23;
                border: 1px solid #2f3542;
                border-radius: 14px;
            }
        """)
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)
        banner_layout.setSpacing(12)

        self._brand_badge = QLabel("RIVERTON  CORPS REGISTRY")
        self._brand_badge.setStyleSheet("color: #f05a28; font-size: 15px; font-weight: 800; letter-spacing: 3px;")
        banner_layout.addWidget(self._brand_badge)

        banner_layout.addStretch()

        self.age_circle = QLabel("25")
        self.age_circle.setFixedSize(42, 42)
        self.age_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.age_circle.setStyleSheet("""
            QLabel {
                border: 2px solid #f05a28;
                border-radius: 21px;
                color: #f8f4e8;
                font-size: 18px;
                font-weight: 800;
                background: #0d1117;
            }
        """)
        banner_layout.addWidget(self.age_circle)

        self.game_title = QLabel("Player Name")
        self.game_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #f5efe3;")
        banner_layout.addWidget(self.game_title)

        self.actions_badge = QLabel("ACTIONS 3")
        self.actions_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.actions_badge.setStyleSheet("""
            QLabel {
                background: #f05a28;
                color: #11151c;
                font-size: 11px;
                font-weight: 800;
                padding: 7px 12px;
                border-radius: 12px;
                letter-spacing: 2px;
            }
        """)
        banner_layout.addWidget(self.actions_badge)

        parent_layout.addWidget(banner)

    def _build_dashboard_body(self, parent_layout: QVBoxLayout) -> None:
        content_area = QHBoxLayout()
        content_area.setSpacing(12)

        self.chronicle_scroll = QScrollArea()
        self.chronicle_scroll.setWidgetResizable(True)
        chronicle_container = QWidget()
        self.chronicle_layout = QVBoxLayout(chronicle_container)
        self.chronicle_layout.setContentsMargins(18, 16, 18, 16)
        self.chronicle_layout.setSpacing(10)

        self.chronicle_layout.addWidget(self._section_label("YOUR RECORD"))
        self.chronicle_layout.addWidget(self._divider())

        self.record_summary = QLabel("The night is long. Your story is unwritten.")
        self.record_summary.setWordWrap(True)
        self.record_summary.setStyleSheet("color: #b7aa95; font-family: Georgia; font-size: 14px; font-style: italic;")
        self.chronicle_layout.addWidget(self.record_summary)

        self.year_entries_container = QVBoxLayout()
        self.year_entries_container.setSpacing(12)
        self.chronicle_layout.addLayout(self.year_entries_container)
        self.chronicle_layout.addStretch()
        self.chronicle_scroll.setWidget(chronicle_container)

        left_column = QVBoxLayout()
        left_column.setSpacing(12)
        left_column.addWidget(self.chronicle_scroll, 1)

        right_panel = QVBoxLayout()
        right_panel.setSpacing(12)
        right_panel.addWidget(self._build_status_panel())
        right_panel.addWidget(self._build_profile_panel())
        right_panel.addWidget(self._build_operations_panel())
        right_panel.addStretch()

        right_scroll_wrap = QWidget()
        right_scroll_wrap.setLayout(right_panel)
        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setMinimumWidth(420)
        self.sidebar_scroll.setWidget(right_scroll_wrap)

        content_area.addWidget(self._wrap_panel(left_column), 2)
        content_area.addWidget(self._wrap_panel(QVBoxLayout(), self.sidebar_scroll), 1)
        parent_layout.addLayout(content_area, 1)

    def _build_bottom_action_bar(self, parent_layout: QVBoxLayout) -> None:
        bar = QFrame()
        bar.setObjectName("card")
        bar.setStyleSheet("""
            QFrame#card {
                background: #171b23;
                border: 1px solid #2f3542;
                border-radius: 14px;
            }
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        self.advance_year_btn = QPushButton("ADVANCE SIX MONTHS")
        self.advance_year_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.advance_year_btn.setMinimumHeight(52)
        self.advance_year_btn.setStyleSheet("""
            QPushButton {
                background: #11151c;
                color: #f05a28;
                border: 1px solid #f05a28;
                border-radius: 12px;
                font-size: 15px;
                font-weight: 900;
                letter-spacing: 2px;
            }
            QPushButton:hover {
                background: #1a1f29;
            }
        """)
        self.advance_year_btn.clicked.connect(self._open_decision_dialog)
        layout.addStretch()
        layout.addWidget(self.advance_year_btn, 2)
        layout.addStretch()
        parent_layout.addWidget(bar)

    def _build_dev_log(self, parent_layout: QVBoxLayout) -> None:
        self.dev_log_display = QTextEdit()
        self.dev_log_display.setReadOnly(True)
        self.dev_log_display.setFixedHeight(72)
        self.dev_log_display.setStyleSheet("""
            QTextEdit {
                background: #0b0e13;
                color: #8b949e;
                border: 1px solid #232a35;
                border-radius: 10px;
                padding: 6px 8px;
                font-size: 11px;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        parent_layout.addWidget(self.dev_log_display)

    def _build_status_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("card")
        panel.setStyleSheet("""
            QFrame#card {
                background: #171b23;
                border: 1px solid #2f3542;
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(self._section_label("STATUS"))
        header.addStretch()
        self.status_line = QLabel("UNPROVEN")
        self.status_line.setStyleSheet("color: #f8d27a; font-size: 11px; font-weight: 800; letter-spacing: 2px;")
        header.addWidget(self.status_line)
        layout.addLayout(header)

        self.engine_stats_layout = QHBoxLayout()
        self.engine_stats_layout.setSpacing(10)
        self.engine_stat_labels = {}
        for stat_key in ["energy", "money", "skill", "reputation"]:
            lbl = QLabel(f"{stat_key.upper()}: 0")
            lbl.setStyleSheet("color: #cfc7b7; font-size: 11px; font-weight: 700;")
            self.engine_stat_labels[stat_key] = lbl
            self.engine_stats_layout.addWidget(lbl)
        layout.addLayout(self.engine_stats_layout)

        self.ui_stats_widget = QWidget()
        self.ui_stats_layout = QVBoxLayout(self.ui_stats_widget)
        self.ui_stats_layout.setContentsMargins(0, 0, 0, 0)
        self.ui_stats_layout.setSpacing(9)
        self.ui_stat_bars = {}
        ui_stat_colors = {"health": "#e35d63", "happiness": "#b06ee3", "smarts": "#5a93f1", "strength": "#f17a45", "breath": "#61d7e6", "speed": "#5dd38a", "vitality": "#e5b65b", "mind": "#b8c7d9"}
        for stat_key, color in ui_stat_colors.items():
            row = QHBoxLayout()
            name = QLabel(stat_key.upper())
            name.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 700; letter-spacing: 2px;")
            bar_bg = QFrame()
            bar_bg.setFixedHeight(6)
            bar_bg.setStyleSheet("background: #232a35; border-radius: 3px;")
            bar_fill = QFrame(bar_bg)
            bar_fill.setFixedHeight(6)
            bar_fill.setStyleSheet(f"background: {color}; border-radius: 3px;")
            bar_fill.setFixedWidth(80)
            value = QLabel("0")
            value.setFixedWidth(30)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setStyleSheet("color: #f5efe3; font-size: 11px;")
            row.addWidget(name, 1)
            row.addWidget(bar_bg, 5)
            row.addWidget(value)
            self.ui_stat_bars[stat_key] = {"fill": bar_fill, "label": value}
            self.ui_stats_layout.addLayout(row)
        layout.addWidget(self.ui_stats_widget)
        return panel

    def _build_profile_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("card")
        panel.setStyleSheet("""
            QFrame#card {
                background: #171b23;
                border: 1px solid #2f3542;
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(self._section_label("PROFILE"))
        self.profile_grid = QGridLayout()
        self.profile_grid.setHorizontalSpacing(10)
        self.profile_grid.setVerticalSpacing(10)
        layout.addLayout(self.profile_grid)
        self.profile_values = {}
        for i, (label, key) in enumerate([("BREATH APTITUDE", "breath"), ("LINEAGE", "lineage"), ("PATH", "path"), ("HOME", "home"), ("STYLE", "style"), ("CORRUPTION", "corruption"), ("WORLD FAME", "fame")]):
            self.profile_values[key] = self._profile_tile(label, "—")
            self.profile_grid.addWidget(self.profile_values[key], i // 2, i % 2)
        return panel

    def _build_operations_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("card")
        panel.setStyleSheet("""
            QFrame#card {
                background: #171b23;
                border: 1px solid #2f3542;
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(self._section_label("OPERATIONS"))
        self.menu_slots_container = QVBoxLayout()
        self.menu_slots_container.setSpacing(8)
        layout.addLayout(self.menu_slots_container)
        layout.addWidget(self._divider())
        self.life_actions_container = QVBoxLayout()
        self.life_actions_container.setSpacing(8)
        layout.addLayout(self.life_actions_container)
        layout.addWidget(self._divider())
        self.map_grid = QGridLayout()
        self.map_grid.setSpacing(8)
        self.map_buttons = {}
        layout.addLayout(self.map_grid)
        layout.addWidget(self._divider())
        self.npcs_container = QVBoxLayout()
        self.npcs_container.setSpacing(8)
        layout.addLayout(self.npcs_container)
        return panel

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("color: #f05a28; font-size: 11px; font-weight: 900; letter-spacing: 3px;")
        return label

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: #2f3542;")
        return line

    def _profile_tile(self, title: str, value: str) -> QFrame:
        tile = QFrame()
        tile.setStyleSheet("""
            QFrame {
                background: #11151c;
                border: 1px solid #4b2c1c;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(10, 10, 10, 10)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #c8b8a0; font-size: 10px; letter-spacing: 2px;")
        value_lbl = QLabel(value)
        value_lbl.setStyleSheet("color: #f5efe3; font-size: 13px; font-weight: 800;")
        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)
        tile.value_label = value_lbl  # type: ignore[attr-defined]
        return tile

    def _wrap_panel(self, layout: QVBoxLayout, scroll_widget: QWidget | None = None) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        frame.setStyleSheet("""
            QFrame#card {
                background: #171b23;
                border: 1px solid #2f3542;
                border-radius: 14px;
            }
        """)
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(0, 0, 0, 0)
        if scroll_widget is not None:
            inner.addWidget(scroll_widget)
        else:
            inner.addLayout(layout)
        return frame

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
        data = self.creation_page.get_creation_data()
        try:
            state = self.engine.new_game(data["name"], "", world_pack_id=data["world_pack"], world_options=data["world_options"])
        except GameRuleError as error:
            self._error(str(error))
            return
        self._dev_console.info(f"New shinobi life started: {data['name']}", "Game")
        self.pages.setCurrentWidget(self.game_page)
        self._render(state)

    def _continue_game(self) -> None:
        # Load only saves that carry the Naruto pack identity.
        saved_games = self._naruto_saved_games()
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

        QMessageBox.information(self, "Continue life", "No Naruto world-pack saves are available yet. Start a new shinobi life to create one.")

    @staticmethod
    def _naruto_saved_games() -> list[dict[str, Any]]:
        saved_games = []
        for game in game_config.list_games():
            if not game.get("has_save"):
                continue
            folder = game_config.GAMES_DIR / game["folder"]
            meta = game_config.read_game_json(folder, "meta.json", {}) or {}
            world = game_config.read_game_json(folder, "world.json", {}) or {}
            if meta.get("world_pack") == "naruto" or world.get("world", {}).get("pack_id") == "naruto":
                saved_games.append(game)
        return saved_games

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
        self.creation_page.name_input.clear()
        self.pages.setCurrentWidget(self.setup_page)
        self.creation_page.name_input.setFocus()
        self.statusBar().showMessage("Choose your village, family, chakra nature, and early strength.")

    def _apply_character_template(self, dialog: QDialog | None, name: str, era: str, age_text: str, start_year: int = 1, use_llm: bool = False) -> None:
        try:
            age = int(age_text) if age_text.strip() else None
        except ValueError:
            age = None
        template = build_character_template(name=name or "Player", era=era or "modern", age=age)
        origin_id = self.creation_page.get_creation_data().get("origin") or ""
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

    def _on_begin_without_generation(self) -> None:
        self._start_new_game()

    def _on_generate_clicked(self) -> None:
        # The active Naruto pack is fully deterministic and starts without LLM calls.
        self._start_new_game()

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
        template = build_character_template(name=name or "Player", era=era or "modern", age=age)
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

    def _perform_world_action(self, action_id: str) -> None:
        try:
            state = self.engine.perform_world_action(action_id)
        except GameRuleError as error:
            self._error(str(error))
            return
        self._render(state)

    def _interact_with_world_npc(self, npc_id: str, interaction_id: str) -> None:
        try:
            state = self.engine.interact_with_world_npc(npc_id, interaction_id)
        except GameRuleError as error:
            self._error(str(error))
            return
        self._render(state)

    def _travel_world_location(self, location_id: str) -> None:
        try:
            state = self.engine.travel_world_location(location_id)
        except GameRuleError as error:
            self._error(str(error))
            return
        self._render(state)

    def _purchase_world_item(self, item_id: str) -> None:
        self._run_action(self.engine.purchase_world_item, item_id)

    def _apply_for_world_job(self, job_id: str) -> None:
        self._run_action(self.engine.apply_for_world_job, job_id)

    def _advance_world_year(self) -> None:
        try:
            state = self.engine.advance_world_year()
        except GameRuleError as error:
            self._error(str(error))
            return
        self._render(state)

    def _save_world_game(self) -> None:
        try:
            self._render(self.engine.save_game())
            self.statusBar().showMessage("Life saved", 3000)
        except GameRuleError as error:
            self._error(str(error))

    def _render(self, state: dict) -> None:
        """Render the active center workspace from authoritative engine state."""
        if hasattr(self, "naruto_screen"):
            self.naruto_screen.set_state(state)
            player = state.get("player", {})
            age = player.get("age", 0)
            year = state.get("year", 1)
            self.statusBar().showMessage(f"Age {age}  |  Year {year}  |  {player.get('location', 'Village')}")
            return

        """Legacy fallback retained for old screen construction paths."""
        player = state.get("player", {})
        stats = player.get("stats", {})
        age = player.get("age", 25)
        self.age_circle.setText(str(age))
        self.game_title.setText(player.get("name", "Unknown"))
        self.status_line.setText(f"{state.get('rank', 'UNPROVEN')}  /  GRADE {state.get('grade', 'A')}")

        # The active game screen owns its pack-specific theme.
        
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
                val = int(player_ui_stats.get(stat_key, 50))
                val = max(0, min(100, val))
                bar_data["label"].setText(str(val))
        else:
            self.ui_stats_widget.setVisible(False)

        profile_map = {
            "breath": player.get("breath_aptitude", state.get("breath_aptitude", "—")),
            "lineage": player.get("lineage", "—"),
            "path": player.get("path", state.get("path", "—")),
            "home": player.get("home", state.get("home", "—")),
            "style": player.get("style", state.get("style", "—")),
            "corruption": player.get("corruption", state.get("corruption", 0)),
            "fame": player.get("world_fame", state.get("world_fame", 0)),
        }
        for key, tile in self.profile_values.items():
            tile.value_label.setText(str(profile_map.get(key, "—")))
        
        # Update actions badge
        actions = state.get("actions_remaining", 0)
        self.actions_badge.setText(f"ACTIONS {actions}")
        if actions <= 0:
            self.actions_badge.setStyleSheet("""
                QLabel {
                    background: #da3633;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 800;
                    padding: 7px 12px;
                    border-radius: 12px;
                    letter-spacing: 2px;
                }
            """)
        else:
            self.actions_badge.setStyleSheet("""
                QLabel {
                    background: #f05a28;
                    color: #11151c;
                    font-size: 11px;
                    font-weight: 800;
                    padding: 7px 12px;
                    border-radius: 12px;
                    letter-spacing: 2px;
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
        self._render_menu_slots(state)
        self._render_life_actions(state)

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
                font-size: 15px;
                font-weight: 800;
                color: #f05a28;
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
                    color: #7a6f61;
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
                            background: #11151c;
                            border: 1px solid #2f3542;
                            border-radius: 8px;
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
            empty_npc.setStyleSheet("color: #7a6f61; font-size: 11px; font-style: italic; padding: 4px 0;")
            self.npcs_container.addWidget(empty_npc)
        else:
            for npc in here:
                npc_card = QFrame()
                npc_card.setObjectName("npc_card")
                npc_card.setStyleSheet("""
                    QFrame#npc_card {
                        background: #11151c;
                        border: 1px solid #2f3542;
                        border-radius: 8px;
                        padding: 8px;
                        margin: 0;
                    }
                    QFrame#npc_card:hover {
                        border-color: #f05a28;
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

    def _render_life_actions(self, state: dict) -> None:
        self._clear_layout(self.life_actions_container)
        actions = state.get("life_actions", [])
        if not actions:
            empty = QLabel("No life actions available yet.")
            empty.setStyleSheet("color: #7a6f61; font-size: 11px; font-style: italic;")
            self.life_actions_container.addWidget(empty)
            return
        for action in actions[:8]:
            card = QFrame()
            card.setObjectName("npc_card")
            card.setStyleSheet("""
                QFrame#npc_card {
                    background: #11151c;
                    border: 1px solid #2f3542;
                    border-radius: 8px;
                }
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            title = QLabel(f"{action.get('label', 'Action')}  <span style='color:#8b949e;font-size:10px;'>[{action.get('category', 'life')}]</span>")
            title.setTextFormat(Qt.TextFormat.RichText)
            title.setStyleSheet("color: #f5efe3; font-size: 12px; font-weight: 800;")
            desc = QLabel(action.get("description", ""))
            desc.setWordWrap(True)
            desc.setStyleSheet("color: #b7aa95; font-size: 11px;")
            card_layout.addWidget(title)
            card_layout.addWidget(desc)
            self.life_actions_container.addWidget(card)

    def _render_menu_slots(self, state: dict) -> None:
        self._clear_layout(self.menu_slots_container)
        era = state.get("player", {}).get("era", "modern")
        slots = state.get("menu_slots") or get_menu_slots(era)
        for slot in slots:
            row = QFrame()
            row.setStyleSheet("""
                QFrame {
                    background: #11151c;
                    border: 1px solid #2f3542;
                    border-radius: 8px;
                }
            """)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 8, 10, 8)
            label = QLabel(slot.get("label", "Slot"))
            label.setStyleSheet("color: #f5efe3; font-size: 12px; font-weight: 800;")
            category = QLabel(slot.get("category", ""))
            category.setStyleSheet("color: #8b949e; font-size: 10px; letter-spacing: 2px;")
            row_layout.addWidget(label)
            row_layout.addStretch()
            row_layout.addWidget(category)
            self.menu_slots_container.addWidget(row)

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
        encounter = state.get("current_encounter")
        random_event = state["active_random_event"]
        event = encounter or random_event or state["event"]
        is_random = random_event is not None
        is_encounter = encounter is not None
        if not is_random and not is_encounter and state["actions_remaining"] > 0:
            self._error("Use all seasonal actions before opening the next decision.")
            return
        if is_encounter:
            dialog.setWindowTitle("Life encounter")
        else:
            dialog.setWindowTitle("A moment between seasons" if is_random else "New Year")
        eyebrow = QLabel("RANDOM EVENT" if is_random else "LIFE ENCOUNTER" if is_encounter else "NEW YEAR DECISION")
        eyebrow.setObjectName("eyebrow")
        title = QLabel(event["title"])
        title.setStyleSheet("font-family: Georgia; font-size: 25px; font-weight: 700; color: #f0f6fc;")
        body = QLabel(event["text"])
        body.setWordWrap(True)
        body.setStyleSheet("color: #8b949e;")
        choices = QVBoxLayout()
        method = self.engine.resolve_encounter if is_encounter else self.engine.choose_random if is_random else self.engine.choose_main
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
        enabled_box = QCheckBox("Allow optional local-model assistance")
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
        self.statusBar().showMessage("LM Studio settings saved. Deterministic game rules remain in control.", 5000)
        self._test_llm_connection(payload)

    def _test_llm_connection(self, settings: dict) -> None:
        connected, details = check_llm_connection(settings.get("base_url", ""), settings.get("model", ""))
        if connected:
            QMessageBox.information(self, "LM Studio connection", details)
            self._dev_console.info("LLM connection test: successful", "LLM")
        else:
            QMessageBox.warning(self, "LM Studio connection", details)
            self._dev_console.warn(f"LLM connection test: failed: {details}", "LLM")

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
