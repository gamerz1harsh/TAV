"""Center-workspace game UI for the Naruto life-sim pack."""
from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtCore import QPointF
from PySide6.QtGui import QBrush, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


PALETTE = {
    "canvas": "#111820",
    "rail": "#18232b",
    "surface": "#1d2a32",
    "surface_lift": "#24343c",
    "line": "#34474c",
    "text": "#e7eee8",
    "muted": "#99aaa5",
    "green": "#9fce91",
    "teal": "#63c6bb",
    "gold": "#e6bd75",
    "red": "#df8079",
    "blue": "#83a8ce",
}


class RadarChart(QWidget):
    """Compact six-axis shinobi attribute chart rendered without extra packages."""

    AXES = (("STR", "strength"), ("AGI", "agility"), ("INT", "intelligence"), ("VIT", "vitality"), ("CHK", "chakra_control"), ("RES", "chakra_capacity"))

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.values: dict[str, int] = {}
        self.setMinimumHeight(270)
        self.setMinimumWidth(300)

    def set_values(self, values: dict[str, Any]) -> None:
        self.values = {key: max(0, min(100, int(values.get(key, 0)))) for _, key in self.AXES}
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2 + 2)
        radius = max(65, min(self.width() * 0.34, self.height() * 0.34))
        axis_count = len(self.AXES)
        for level in (0.25, 0.5, 0.75, 1.0):
            points = QPolygonF([
                QPointF(center.x() + math.sin(2 * math.pi * i / axis_count) * radius * level,
                        center.y() - math.cos(2 * math.pi * i / axis_count) * radius * level)
                for i in range(axis_count)
            ])
            painter.setPen(QPen(Qt.GlobalColor.darkGray, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(points)
        data_points = []
        painter.setPen(QPen(Qt.GlobalColor.gray, 1))
        for i, (label, key) in enumerate(self.AXES):
            angle = 2 * math.pi * i / axis_count
            outer = QPointF(center.x() + math.sin(angle) * radius, center.y() - math.cos(angle) * radius)
            painter.drawLine(center, outer)
            text_point = QPointF(center.x() + math.sin(angle) * (radius + 20), center.y() - math.cos(angle) * (radius + 20) + 5)
            painter.setPen(QPen(Qt.GlobalColor.white, 1))
            painter.drawText(text_point, label)
            value = self.values.get(key, 0) / 100
            data_points.append(QPointF(center.x() + math.sin(angle) * radius * value, center.y() - math.cos(angle) * radius * value))
        painter.setPen(QPen(Qt.GlobalColor.cyan, 2))
        painter.setBrush(QBrush(Qt.GlobalColor.cyan, Qt.BrushStyle.Dense4Pattern))
        painter.drawPolygon(QPolygonF(data_points))
        painter.end()


class NarutoGameScreen(QWidget):
    """Navigation, year controls, and center pages for one world-pack game."""

    action_requested = Signal(str)
    social_requested = Signal(str, str)
    travel_requested = Signal(str)
    advance_year_requested = Signal()
    save_requested = Signal()
    settings_requested = Signal()
    purchase_requested = Signal(str)
    apply_job_requested = Signal(str)
    work_job_requested = Signal()

    NAVIGATION = [
        ("dashboard", "Life", "01", "⌂"),
        ("character", "Character", "02", "◈"),
        ("stats", "Stats", "03", "⬡"),
        ("training", "Training", "04", "⚔"),
        ("techniques", "Techniques", "05", "✦"),
        ("people", "People", "06", "◉"),
        ("career", "Career", "07", "▤"),
        ("village", "Map & Village", "08", "⌖"),
        ("memories", "Memories", "09", "◷"),
        ("settings", "Model Settings", "10", "⚙"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._state: dict[str, Any] = {}
        self._page_index: dict[str, int] = {}
        self.setObjectName("shinobiShell")
        self.setStyleSheet(self._stylesheet())
        self._build()

    @staticmethod
    def _stylesheet() -> str:
        p = PALETTE
        return f"""
            QWidget#shinobiShell {{ background: {p['canvas']}; color: {p['text']}; font-family: 'Bahnschrift', 'Yu Gothic UI', sans-serif; }}
            QWidget {{ background: transparent; color: {p['text']}; font-size: 13px; }}
            QLabel {{ background: transparent; border: none; padding: 0; }}
            QFrame#navRail {{ background: {p['rail']}; border-right: 1px solid {p['line']}; }}
            QFrame#topBar {{ background: {p['rail']}; border-bottom: 1px solid {p['line']}; }}
            QFrame.card {{ background: {p['surface']}; border: 1px solid {p['line']}; border-radius: 12px; }}
            QFrame.subcard {{ background: {p['surface_lift']}; border: 1px solid {p['line']}; border-radius: 10px; }}
            QLabel#brand {{ color: {p['green']}; font-size: 17px; font-weight: 900; letter-spacing: 2px; }}
            QLabel#eyebrow {{ color: {p['teal']}; font-size: 10px; font-weight: 800; letter-spacing: 2px; }}
            QLabel#pageTitle {{ color: {p['text']}; font-size: 28px; font-weight: 800; }}
            QLabel#muted {{ color: {p['muted']}; }}
            QLabel#metric {{ color: {p['text']}; font-size: 23px; font-weight: 800; }}
            QLabel#navSection {{ color: {p['muted']}; font-size: 9px; font-weight: 800; letter-spacing: 2px; padding: 10px 8px 3px; }}
            QPushButton {{ background: {p['surface_lift']}; color: {p['text']}; border: 1px solid {p['line']}; border-radius: 8px; padding: 10px 13px; font-weight: 650; text-align: left; }}
            QPushButton:hover {{ border-color: {p['teal']}; background: #2a3d44; }}
            QPushButton:checked {{ background: #29413f; border-color: {p['teal']}; color: {p['green']}; }}
            QPushButton#primary {{ background: {p['green']}; border-color: {p['green']}; color: #17231e; font-weight: 900; text-align: center; }}
            QPushButton#primary:hover {{ background: #b4dca7; }}
            QPushButton:disabled {{ color: #75837f; background: #1a252b; border-color: #2b3a3f; }}
            QProgressBar {{ background: #11191f; border: 0; border-radius: 3px; height: 5px; text-align: center; }}
            QProgressBar::chunk {{ background: {p['teal']}; border-radius: 4px; }}
            QScrollArea {{ border: 0; background: transparent; }}
        """

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.nav_rail = QFrame()
        self.nav_rail.setObjectName("navRail")
        self.nav_rail.setFixedWidth(218)
        nav = QVBoxLayout(self.nav_rail)
        nav.setContentsMargins(14, 20, 14, 18)
        nav.setSpacing(6)
        brand = QLabel("SHINOBI\nLIFE")
        brand.setObjectName("brand")
        nav.addWidget(brand)
        pack_name = QLabel("NARUTO WORLD PACK")
        pack_name.setObjectName("eyebrow")
        nav.addWidget(pack_name)
        nav.addSpacing(18)
        nav.addWidget(self._nav_section("YOUR LIFE"))
        self.nav_buttons: dict[str, QPushButton] = {}
        for page_id, label, number, icon in self.NAVIGATION:
            button = QPushButton(f"{icon}   {number}   {label}")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, key=page_id: self.show_page(key))
            self.nav_buttons[page_id] = button
            nav.addWidget(button)
        nav.addStretch()
        footer = QLabel("A life shaped by\nthe choices you make.")
        footer.setObjectName("muted")
        nav.addWidget(footer)
        root.addWidget(self.nav_rail)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        self.top_bar = self._build_top_bar()
        workspace_layout.addWidget(self.top_bar)
        self.pages = QStackedWidget()
        self._page_index["dashboard"] = self.pages.addWidget(self._build_dashboard())
        self._page_index["character"] = self.pages.addWidget(self._build_character_page())
        self._page_index["stats"] = self.pages.addWidget(self._build_stats_page())
        self._page_index["training"] = self.pages.addWidget(self._build_training_page())
        self._page_index["techniques"] = self.pages.addWidget(self._build_techniques_page())
        self._page_index["people"] = self.pages.addWidget(self._build_people_page())
        self._page_index["career"] = self.pages.addWidget(self._build_career_page())
        self._page_index["village"] = self.pages.addWidget(self._build_village_page())
        self._page_index["memories"] = self.pages.addWidget(self._build_memories_page())
        self._page_index["settings"] = self.pages.addWidget(self._build_settings_page())
        workspace_layout.addWidget(self.pages, 1)
        root.addWidget(workspace, 1)
        self.show_page("dashboard")

    @staticmethod
    def _nav_section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("navSection")
        return label

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(26, 13, 26, 13)
        layout.setSpacing(14)
        identity = QVBoxLayout()
        identity.setSpacing(2)
        self.player_name = QLabel("New shinobi")
        self.player_name.setStyleSheet("font-size: 16px; font-weight: 800;")
        self.player_identity = QLabel("Hidden Leaf  /  Academy candidate")
        self.player_identity.setObjectName("muted")
        identity.addWidget(self.player_name)
        identity.addWidget(self.player_identity)
        layout.addLayout(identity)
        layout.addStretch()
        self.age_label = QLabel("AGE 10")
        self.age_label.setObjectName("eyebrow")
        layout.addWidget(self.age_label)
        self.year_label = QLabel("YEAR 1")
        self.year_label.setObjectName("muted")
        layout.addWidget(self.year_label)
        self.action_counter = QLabel("PERSONAL 3 / 3   SOCIAL 2 / 2")
        self.action_counter.setStyleSheet(f"color: {PALETTE['gold']}; font-weight: 800;")
        layout.addWidget(self.action_counter)
        save = QPushButton("Save")
        save.clicked.connect(self.save_requested.emit)
        layout.addWidget(save)
        return bar

    def _page_shell(self, eyebrow: str, title: str, subtitle: str) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 26, 30, 30)
        layout.setSpacing(16)
        label = QLabel(eyebrow.upper())
        label.setObjectName("eyebrow")
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        description = QLabel(subtitle)
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(title_label)
        layout.addWidget(description)
        layout.addSpacing(4)
        layout.addStretch()
        scroll.setWidget(container)
        scroll._content_layout = layout  # Keep page builders compact.
        return scroll, layout

    @staticmethod
    def _card() -> QFrame:
        frame = QFrame()
        frame.setProperty("class", "card")
        frame.setStyleSheet(f"QFrame {{ background: {PALETTE['surface']}; border: 1px solid {PALETTE['line']}; border-radius: 12px; }}")
        return frame

    def _build_dashboard(self) -> QWidget:
        page, layout = self._page_shell("Life overview", "Your shinobi year", "Choose how you spend the year. Actions are yours to use; advance whenever you are ready.")
        stats_card = self._card()
        stats_layout = QVBoxLayout(stats_card)
        stats_layout.setContentsMargins(20, 17, 20, 18)
        stats_layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("CURRENT CONDITION")
        title.setObjectName("eyebrow")
        header.addWidget(title)
        header.addStretch()
        self.dashboard_actions = QLabel("5 actions available")
        self.dashboard_actions.setObjectName("muted")
        header.addWidget(self.dashboard_actions)
        stats_layout.addLayout(header)
        self.condition_bars: dict[str, QProgressBar] = {}
        self.condition_values: dict[str, QLabel] = {}
        condition_names = [("health", "Health", PALETTE["red"]), ("happiness", "Happiness", PALETTE["gold"]), ("smarts", "Academy knowledge", PALETTE["blue"])]
        for key, label_text, color in condition_names:
            line = QHBoxLayout()
            name = QLabel(label_text)
            name.setObjectName("muted")
            line.addWidget(name)
            line.addStretch()
            value = QLabel("50")
            value.setFixedWidth(32)
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            line.addWidget(value)
            stats_layout.addLayout(line)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}")
            stats_layout.addWidget(bar)
            self.condition_bars[key] = bar
            self.condition_values[key] = value
        layout.insertWidget(layout.count() - 1, stats_card)

        split = QHBoxLayout()
        profile_card = self._card()
        profile_layout = QVBoxLayout(profile_card)
        profile_layout.setContentsMargins(20, 18, 20, 18)
        profile_layout.setSpacing(10)
        label = QLabel("SHINOBI PROFILE")
        label.setObjectName("eyebrow")
        profile_layout.addWidget(label)
        self.dashboard_profile = QLabel("Village / clan / chakra")
        self.dashboard_profile.setWordWrap(True)
        self.dashboard_profile.setStyleSheet("font-size: 17px; font-weight: 750;")
        profile_layout.addWidget(self.dashboard_profile)
        self.dashboard_focus = QLabel("Start with the foundations: body, academy, chakra, or relationships.")
        self.dashboard_focus.setObjectName("muted")
        self.dashboard_focus.setWordWrap(True)
        profile_layout.addWidget(self.dashboard_focus)
        split.addWidget(profile_card, 1)

        memory_card = self._card()
        memory_layout = QVBoxLayout(memory_card)
        memory_layout.setContentsMargins(20, 18, 20, 18)
        memory_layout.setSpacing(8)
        memory_title = QLabel("RECENT MEMORIES")
        memory_title.setObjectName("eyebrow")
        memory_layout.addWidget(memory_title)
        self.dashboard_memories = QLabel("Your story will collect here as you act.")
        self.dashboard_memories.setObjectName("muted")
        self.dashboard_memories.setWordWrap(True)
        memory_layout.addWidget(self.dashboard_memories)
        split.addWidget(memory_card, 1)
        layout.insertLayout(layout.count() - 1, split)

        advance_row = QHBoxLayout()
        year_hint = QLabel("Unused actions are forfeited when you advance.")
        year_hint.setObjectName("muted")
        advance_row.addWidget(year_hint)
        advance_row.addStretch()
        advance = QPushButton("Advance to next year  >")
        advance.setObjectName("primary")
        advance.setMinimumWidth(230)
        advance.setMinimumHeight(46)
        advance.clicked.connect(self.advance_year_requested.emit)
        advance_row.addWidget(advance)
        layout.insertLayout(layout.count() - 1, advance_row)
        return page

    def _build_character_page(self) -> QWidget:
        page, layout = self._page_shell("Identity", "Character", "A compact identity sheet for the life you are building.")
        self.character_grid = QGridLayout()
        self.character_grid.setHorizontalSpacing(12)
        self.character_grid.setVerticalSpacing(12)
        layout.insertLayout(layout.count() - 1, self.character_grid)
        return page

    def _build_stats_page(self) -> QWidget:
        page, layout = self._page_shell("Detailed profile", "Stats", "Your condition and shinobi attributes live here in detail.")
        self.combat_power_label = QLabel("COMBAT POWER  0")
        self.combat_power_label.setObjectName("eyebrow")
        layout.insertWidget(layout.count() - 1, self.combat_power_label)
        self.radar_chart = RadarChart()
        layout.insertWidget(layout.count() - 1, self.radar_chart)
        skills_title = QLabel("DISCIPLINE LEVELS")
        skills_title.setObjectName("eyebrow")
        layout.insertWidget(layout.count() - 1, skills_title)
        self.skills_grid = QGridLayout()
        self.skills_grid.setHorizontalSpacing(12)
        self.skills_grid.setVerticalSpacing(8)
        layout.insertLayout(layout.count() - 1, self.skills_grid)
        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(12)
        self.stats_grid.setVerticalSpacing(12)
        layout.insertLayout(layout.count() - 1, self.stats_grid)
        return page

    def _build_training_page(self) -> QWidget:
        page, layout = self._page_shell("Develop your path", "Training", "Training consumes personal actions. Each discipline develops its own progression.")
        self.training_budget = QLabel("PERSONAL ACTIONS 3 / 3")
        self.training_budget.setObjectName("eyebrow")
        layout.insertWidget(layout.count() - 1, self.training_budget)
        self.training_grid = QGridLayout()
        self.training_grid.setHorizontalSpacing(12)
        self.training_grid.setVerticalSpacing(12)
        layout.insertLayout(layout.count() - 1, self.training_grid)
        unlock_header = QLabel("PROGRESSION PATH")
        unlock_header.setObjectName("eyebrow")
        layout.insertWidget(layout.count() - 1, unlock_header)
        self.unlock_list = QVBoxLayout()
        self.unlock_list.setSpacing(8)
        layout.insertLayout(layout.count() - 1, self.unlock_list)
        return page

    def _build_techniques_page(self) -> QWidget:
        page, layout = self._page_shell("Technique library", "Techniques", "Learned techniques will appear here. Technique practice will build mastery for the selected jutsu.")
        self.techniques_list = QVBoxLayout()
        self.techniques_list.setSpacing(9)
        layout.insertLayout(layout.count() - 1, self.techniques_list)
        return page

    def _build_people_page(self) -> QWidget:
        page, layout = self._page_shell("Your relationships", "People", "Social actions strengthen bonds and open up future personal paths.")
        self.people_grid = QGridLayout()
        self.people_grid.setHorizontalSpacing(12)
        self.people_grid.setVerticalSpacing(12)
        layout.insertLayout(layout.count() - 1, self.people_grid)
        return page

    def _build_village_page(self) -> QWidget:
        page, layout = self._page_shell("Places and institutions", "Village", "Your home village contains the places that shape a shinobi life.")
        self.village_list = QVBoxLayout()
        self.village_list.setSpacing(10)
        layout.insertLayout(layout.count() - 1, self.village_list)
        return page

    def _build_career_page(self) -> QWidget:
        page, layout = self._page_shell("Work and standing", "Career", "Jobs are tied to age, shinobi rank, and where you show up. Work spends a personal action; experience earns promotions over time.")
        self.career_list = QVBoxLayout()
        self.career_list.setSpacing(10)
        layout.insertLayout(layout.count() - 1, self.career_list)
        return page

    def _build_memories_page(self) -> QWidget:
        page, layout = self._page_shell("Your history", "Memories", "Small choices accumulate into a life. Every action is recorded here.")
        self.memories_list = QVBoxLayout()
        self.memories_list.setSpacing(8)
        layout.insertLayout(layout.count() - 1, self.memories_list)
        return page

    def _build_settings_page(self) -> QWidget:
        page, layout = self._page_shell("Local generation", "Model Settings", "Set the LM Studio endpoint and model name. The Naruto rules remain playable without a running model.")
        card = self._information_card("LM Studio connection", "Use the OpenAI-compatible local server, usually http://127.0.0.1:1234/v1. Saving settings checks whether the selected model can answer a small request.")
        layout.insertWidget(layout.count() - 1, card)
        button = QPushButton("Configure local model")
        button.setObjectName("primary")
        button.clicked.connect(self.settings_requested.emit)
        layout.insertWidget(layout.count() - 1, button)
        return page

    def show_page(self, page_id: str) -> None:
        if page_id not in self._page_index:
            return
        self.pages.setCurrentIndex(self._page_index[page_id])
        for key, button in self.nav_buttons.items():
            button.setChecked(key == page_id)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                NarutoGameScreen._clear_layout(item.layout())

    @staticmethod
    def _add_detail(layout, row: int, column: int, label: str, value: Any, color: str | None = None) -> None:
        card = NarutoGameScreen._card()
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 13, 16, 14)
        eyebrow = QLabel(label.upper())
        eyebrow.setObjectName("eyebrow")
        box.addWidget(eyebrow)
        content = QLabel(str(value))
        content.setWordWrap(True)
        content.setStyleSheet(f"font-size: 17px; font-weight: 750; color: {color or PALETTE['text']};")
        box.addWidget(content)
        layout.addWidget(card, row, column)

    def set_state(self, state: dict[str, Any]) -> None:
        self._state = state
        player = state.get("player", {})
        naruto = state.get("naruto", player.get("naruto", {}))
        village = naruto.get("village", {}).get("name", "Unknown Village")
        clan = naruto.get("clan", {}).get("name", "Unassigned")
        nature = naruto.get("chakra_nature", {}).get("name", "Undiscovered")
        age = int(player.get("age", 0))
        rank = state.get("world_state", {}).get("rank", "Academy Student")
        year = int(state.get("year", 1))
        personal = int(state.get("personal_actions_remaining", 0))
        social = int(state.get("social_actions_remaining", 0))
        budget = state.get("action_budget", {"personal": personal, "social": social})
        self.player_name.setText(player.get("name", "New shinobi"))
        self.player_identity.setText(f"{village}  /  {rank}")
        self.age_label.setText(f"AGE {age}")
        self.year_label.setText(f"YEAR {year}")
        self.action_counter.setText(f"PERSONAL {personal} / {budget.get('personal', personal)}   SOCIAL {social} / {budget.get('social', social)}")
        self.dashboard_actions.setText(f"{personal + social} actions available this year")
        self.dashboard_profile.setText(f"{village}\n{clan}  /  {nature} nature  /  {rank}")
        attributes = naruto.get("attributes", {})
        ui_stats = player.get("ui_stats", {})
        condition = {
            "health": int(ui_stats.get("health", 50)),
            "happiness": int(ui_stats.get("happiness", 50)),
            "smarts": int(attributes.get("academy_knowledge", ui_stats.get("smarts", 50))),
        }
        for key, value in condition.items():
            self.condition_values[key].setText(str(value))
            self.condition_bars[key].setValue(max(0, min(100, value)))
        recent = state.get("memories", [])[-3:]
        self.dashboard_memories.setText("\n\n".join(str(item) for item in reversed(recent)) or "Your story will collect here as you act.")
        self.dashboard_focus.setText(f"Chakra control {attributes.get('chakra_control', 0)}  |  Body conditioning {attributes.get('body_conditioning', 0)}  |  Academy knowledge {attributes.get('academy_knowledge', 0)}")
        self._render_character(naruto, age)
        self._render_stats(naruto, ui_stats)
        self._render_actions(state.get("world_actions", []), personal, social)
        self._render_unlocks(state.get("training_unlocks", []))
        self._render_techniques(naruto.get("techniques", []))
        self._render_people(naruto.get("relationships", {}), social)
        self._render_career(state.get("world_careers", {}), state)
        self._render_village(naruto, state)
        self._render_memories(state.get("memories", []))

    def _render_character(self, naruto: dict[str, Any], age: int) -> None:
        self._clear_layout(self.character_grid)
        village = naruto.get("village", {}).get("name", "Unknown")
        clan = naruto.get("clan", {}).get("name", "Unassigned")
        nature = naruto.get("chakra_nature", {}).get("name", "Undiscovered")
        perks = ", ".join(item.get("name", "") for item in naruto.get("perks", [])) or "None"
        self._add_detail(self.character_grid, 0, 0, "Village", village)
        self._add_detail(self.character_grid, 0, 1, "Clan", clan)
        self._add_detail(self.character_grid, 1, 0, "Chakra Nature", nature)
        self._add_detail(self.character_grid, 1, 1, "Perks", perks)
        self._add_detail(self.character_grid, 2, 0, "Age", age)
        self._add_detail(self.character_grid, 2, 1, "Current Path", self._state.get("player", {}).get("life_stage", "shinobi").title())
        lineage = naruto.get("clan", {}).get("lineage") or {}
        lineage_value = f"{lineage.get('name')} ({lineage.get('status', 'dormant')})" if lineage else "No inherited eye trait"
        self._add_detail(self.character_grid, 3, 0, "Lineage", lineage_value)

    def _render_stats(self, naruto: dict[str, Any], ui_stats: dict[str, Any]) -> None:
        self._clear_layout(self.stats_grid)
        self._clear_layout(self.skills_grid)
        attributes = naruto.get("attributes", {})
        skills = naruto.get("skills", {})
        self.combat_power_label.setText(f"COMBAT POWER  /  {self._state.get('combat_power', 0):,}")
        self.radar_chart.set_values(attributes)
        for index, (skill, level) in enumerate(sorted(skills.items())):
            level_label = f"LEVEL {int(level)}" if int(level) else "UNTRAINED"
            self._add_detail(self.skills_grid, index // 4, index % 4, skill.replace("_", " "), level_label, PALETTE["teal"])
        stats = [
            ("Health", ui_stats.get("health", 50), PALETTE["red"]),
            ("Happiness", ui_stats.get("happiness", 50), PALETTE["gold"]),
            ("Academy Knowledge", naruto.get("attributes", {}).get("academy_knowledge", 0), PALETTE["blue"]),
        ]
        for key, label in [("strength", "Strength"), ("agility", "Agility"), ("intelligence", "Intelligence"), ("vitality", "Vitality"), ("chakra_capacity", "Chakra Capacity"), ("chakra_control", "Chakra Control"), ("body_conditioning", "Body Conditioning"), ("hand_seals", "Hand Seals"), ("willpower", "Willpower")]:
            stats.append((label, attributes.get(key, 0), PALETTE["teal"]))
        selected_nature = naruto.get("chakra_nature", {}).get("id")
        for key, value in naruto.get("nature_affinity", {}).items():
            selected = key == selected_nature
            stats.append((f"{key.title()} Affinity" + (" - Primary" if selected else ""), value, PALETTE["gold"] if selected else PALETTE["muted"]))
        for index, (label, value, color) in enumerate(stats):
            self._add_detail(self.stats_grid, index // 3, index % 3, label, value, color)
        row = (len(stats) + 2) // 3
        for key, value in naruto.get("mastery", {}).items():
            self._add_detail(self.stats_grid, row, 0, f"{key.replace('_', ' ')} Mastery", value, PALETTE["green"])
            row += 1

    def _render_actions(self, actions: list[dict[str, Any]], personal: int, social: int) -> None:
        self._clear_layout(self.training_grid)
        self.training_budget.setText(f"PERSONAL ACTIONS {personal}   /   SOCIAL ACTIONS {social}")
        available = [item for item in actions if item.get("action_type") == "personal" and item.get("available")]
        if not available:
            self.training_grid.addWidget(self._information_card("No training available here", "Travel to the Academy or Training Grounds, meet the age and skill requirements, or advance to another year."), 0, 0, 1, 2)
            return
        for index, action in enumerate(available):
            card = self._card()
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 14, 16, 14)
            box.setSpacing(8)
            heading = QLabel(action.get("label", "Training"))
            heading.setStyleSheet("font-size: 16px; font-weight: 800;")
            description = QLabel(action.get("description", ""))
            description.setObjectName("muted")
            description.setWordWrap(True)
            button = QPushButton("Train  >")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, action_id=action["id"]: self.action_requested.emit(action_id))
            box.addWidget(heading)
            box.addWidget(description)
            box.addStretch()
            box.addWidget(button)
            self.training_grid.addWidget(card, index // 2, index % 2)
        self.training_grid.setColumnStretch(0, 1)
        self.training_grid.setColumnStretch(1, 1)

    def _render_unlocks(self, unlocks: list[dict[str, Any]]) -> None:
        self._clear_layout(self.unlock_list)
        visible_unlocks = [unlock for unlock in unlocks if unlock.get("unlocked")]
        if not visible_unlocks:
            self.unlock_list.addWidget(self._information_card("No new path unlocked yet", "Build your foundations and check back as your age, control, and academy knowledge grow."))
        for unlock in visible_unlocks:
            card = self._card()
            row = QHBoxLayout(card)
            row.setContentsMargins(15, 10, 15, 10)
            name = QLabel(unlock.get("label", unlock.get("id", "Progression")))
            name.setStyleSheet("font-weight: 800;")
            description = QLabel(unlock.get("description", ""))
            description.setObjectName("muted")
            description.setWordWrap(True)
            status = QLabel("AVAILABLE")
            status.setStyleSheet(f"color: {PALETTE['green']}; font-size: 10px; font-weight: 800;")
            row.addWidget(name, 1)
            row.addWidget(description, 3)
            row.addWidget(status, 2)
            self.unlock_list.addWidget(card)

    def _render_techniques(self, techniques: list[dict[str, Any]]) -> None:
        self._clear_layout(self.techniques_list)
        if not techniques:
            card = self._card()
            box = QVBoxLayout(card)
            box.setContentsMargins(18, 16, 18, 16)
            title = QLabel("No techniques learned yet")
            title.setStyleSheet("font-size: 16px; font-weight: 800;")
            body = QLabel("Technique learning will enter through training, mentors, clan paths, and age or relationship events. Once learned, practice will improve that technique's individual mastery.")
            body.setObjectName("muted")
            body.setWordWrap(True)
            box.addWidget(title)
            box.addWidget(body)
            self.techniques_list.addWidget(card)
        rank_order = {"Academy": 0, "D": 1, "C": 2, "B": 3, "A": 4, "S": 5}
        for technique in sorted(techniques, key=lambda item: (rank_order.get(item.get("rank", "Academy"), 9), item.get("name", ""))):
            mastery = int(technique.get("mastery", 0))
            card = self._card()
            box = QVBoxLayout(card)
            title = QLabel(f"{technique.get('name', 'Technique')}   /   {technique.get('rank', 'Academy')} RANK")
            title.setStyleSheet("font-size: 15px; font-weight: 800;")
            detail = QLabel(f"{technique.get('nature', 'Ninjutsu')}  |  MASTERY LEVEL {mastery // 10 + 1}  |  {mastery}%")
            detail.setObjectName("eyebrow")
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(mastery)
            bar.setTextVisible(False)
            bar.setFixedHeight(5)
            box.addWidget(title)
            box.addWidget(detail)
            box.addWidget(bar)
            self.techniques_list.addWidget(card)

    def _render_people(self, relationships: dict[str, Any], social: int) -> None:
        self._clear_layout(self.people_grid)
        people = self._state.get("world_people", [])
        interactions = self._state.get("world_interactions", [])
        current_location = self._state.get("world_location", "home")
        current_age = int(self._state.get("player", {}).get("age", 0))
        for index, person in enumerate(people):
            card = self._card()
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 14, 16, 14)
            title = QLabel(person.get("name", "Unknown") + "  /  " + person.get("role", "Village resident"))
            title.setStyleSheet("font-size: 15px; font-weight: 800;")
            relation = QLabel(f"Affinity {person.get('affinity', 0)}   |   Trust {person.get('trust', 0)}")
            relation.setObjectName("eyebrow")
            body = QLabel(person.get("description", ""))
            body.setObjectName("muted")
            body.setWordWrap(True)
            reaction = QLabel(person.get("reaction", "They are still getting to know you."))
            reaction.setStyleSheet(f"color: {PALETTE['green']}; font-size: 11px;")
            reaction.setWordWrap(True)
            box.addWidget(title)
            box.addWidget(relation)
            box.addWidget(body)
            box.addWidget(reaction)
            for memory in person.get("memories", [])[-2:]:
                memory_label = QLabel("REMEMBERS  /  " + memory)
                memory_label.setObjectName("muted")
                memory_label.setWordWrap(True)
                memory_label.setStyleSheet(f"color: {PALETTE['gold']}; font-size: 11px;")
                box.addWidget(memory_label)
            button_row = QHBoxLayout()
            compatible = [item for item in interactions if not item.get("requires_role") or item["requires_role"] == person.get("role")]
            for interaction in compatible:
                button = QPushButton(interaction.get("label", "Interact"))
                in_range = interaction.get("range") == "anywhere" or person.get("location") == current_location
                age_ready = current_age >= int(interaction.get("min_age", 0))
                button.setEnabled(social > 0 and in_range and age_ready)
                tooltip = interaction.get("description", "")
                if not in_range:
                    tooltip += f" Travel to {person.get('location', 'their location').replace('_', ' ')} first."
                if not age_ready:
                    tooltip += f" Available at age {interaction['min_age']}."
                button.setToolTip(tooltip)
                button.clicked.connect(lambda checked=False, npc_id=person["id"], action_id=interaction["id"]: self.social_requested.emit(npc_id, action_id))
                button_row.addWidget(button)
            box.addLayout(button_row)
            self.people_grid.addWidget(card, index // 2, index % 2)
        self.people_grid.setColumnStretch(0, 1)
        self.people_grid.setColumnStretch(1, 1)

    def _render_career(self, careers: dict[str, Any], state: dict[str, Any]) -> None:
        self._clear_layout(self.career_list)
        active = careers.get("active", {})
        if active.get("job_id"):
            promotion = next((item for job in careers.get("jobs", []) if job.get("id") == active.get("job_id") for item in job.get("promotions", []) if int(active.get("experience", 0)) < int(item.get("work_xp", 0))), None)
            target = promotion.get("work_xp") if promotion else None
            progress = int(active.get("experience", 0))
            goal = f"Next promotion at {target} work marks" if target else "Top promotion reached"
            self.career_list.addWidget(self._information_card(f"{active.get('title', 'Employed')}  /  {progress} WORK MARKS", goal))
            workplace = next((job.get("location") for job in careers.get("jobs", []) if job.get("id") == active.get("job_id")), "")
            work = QPushButton("Work a shift  >")
            work.setObjectName("primary")
            work.setEnabled(state.get("world_location") == workplace and int(state.get("personal_actions_remaining", 0)) > 0)
            work.clicked.connect(self.work_job_requested.emit)
            self.career_list.addWidget(work)
        else:
            self.career_list.addWidget(self._information_card("No current position", "Build your reputation, meet the rank and age requirements, and visit a workplace to apply."))
        for job in careers.get("jobs", []):
            card = self._card()
            row = QHBoxLayout(card)
            details = QVBoxLayout()
            title = QLabel(job.get("name", "Village work"))
            title.setStyleSheet("font-size: 15px; font-weight: 800;")
            summary = QLabel(f"{job.get('pay', 0)} Ryo per shift  /  {job.get('min_rank', 'Any rank')}  /  Apply at {job.get('location', '').replace('_', ' ').title()}")
            summary.setObjectName("muted")
            details.addWidget(title)
            details.addWidget(summary)
            row.addLayout(details, 1)
            if job.get("id") == active.get("job_id"):
                status = QLabel(active.get("title", "ACTIVE"))
                status.setObjectName("eyebrow")
                row.addWidget(status)
            else:
                apply = QPushButton("Apply" if job.get("available") else "Not eligible")
                apply.setEnabled(bool(job.get("available")) and not active.get("job_id"))
                apply.setToolTip(job.get("lock_reason", "Application available here."))
                apply.clicked.connect(lambda checked=False, key=job["id"]: self.apply_job_requested.emit(key))
                row.addWidget(apply)
            self.career_list.addWidget(card)

    def _render_village(self, naruto: dict[str, Any], state: dict[str, Any]) -> None:
        self._clear_layout(self.village_list)
        village = naruto.get("village", {}).get("name", "Unknown Village")
        current_location = state.get("world_location", "home")
        self.village_list.addWidget(self._information_card(f"{village}  /  VILLAGE MAP", f"Current location: {current_location.replace('_', ' ').title()}  |  Travel is free. People and activities are tied to where you are."))
        places = state.get("world_places", [])
        for index, place in enumerate(places):
            card = self._card()
            row = QHBoxLayout(card)
            row.setContentsMargins(16, 13, 16, 13)
            details = QVBoxLayout()
            title = QLabel(place.get("name", "Village Place"))
            title.setStyleSheet("font-size: 15px; font-weight: 800;")
            description = QLabel(place.get("description", ""))
            description.setObjectName("muted")
            description.setWordWrap(True)
            details.addWidget(title)
            details.addWidget(description)
            row.addLayout(details, 1)
            if place.get("id") == current_location:
                status = QLabel("YOU ARE HERE")
                status.setObjectName("eyebrow")
                row.addWidget(status)
            else:
                button = QPushButton("Go")
                button.clicked.connect(lambda checked=False, key=place["id"]: self.travel_requested.emit(key))
                row.addWidget(button)
            self.village_list.addWidget(card)
        shop = state.get("world_shop", {})
        if shop.get("items"):
            self.village_list.addWidget(self._information_card("MARKET  /  SUPPLIES", f"Wallet: {state.get('world_wallet', 0)} Ryo. Visit Market Street to buy equipment and supplies."))
            for item in shop["items"]:
                card = self._card()
                row = QHBoxLayout(card)
                details = QVBoxLayout()
                name = QLabel(f"{item.get('name', 'Item')}  /  {item.get('price', 0)} Ryo")
                name.setStyleSheet("font-size: 15px; font-weight: 800;")
                description = QLabel(item.get("description", ""))
                description.setObjectName("muted")
                description.setWordWrap(True)
                details.addWidget(name)
                details.addWidget(description)
                row.addLayout(details, 1)
                buy = QPushButton("Buy")
                buy.setEnabled(current_location == shop.get("location") and int(state.get("world_wallet", 0)) >= int(item.get("price", 0)))
                buy.setToolTip("Travel to Market Street and make sure you have enough Ryo.")
                buy.clicked.connect(lambda checked=False, key=item["id"]: self.purchase_requested.emit(key))
                row.addWidget(buy)
                self.village_list.addWidget(card)

    def _render_memories(self, memories: list[Any]) -> None:
        self._clear_layout(self.memories_list)
        if not memories:
            self.memories_list.addWidget(self._information_card("No memories yet", "Take an action to begin building your life record."))
            return
        for index, memory in enumerate(reversed(memories)):
            self.memories_list.addWidget(self._information_card(f"LIFE RECORD  /  {len(memories) - index:02d}", str(memory)))

    @staticmethod
    def _information_card(title_text: str, detail_text: str) -> QFrame:
        card = NarutoGameScreen._card()
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 13, 16, 14)
        box.setSpacing(6)
        title = QLabel(title_text)
        title.setStyleSheet("font-size: 15px; font-weight: 800;")
        detail = QLabel(detail_text)
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        box.addWidget(title)
        box.addWidget(detail)
        return card
