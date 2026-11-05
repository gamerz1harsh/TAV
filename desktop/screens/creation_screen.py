"""Character setup for starting a Naruto world-pack life."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from world_pack import get_world_pack


class CreationScreen(QWidget):
    """A focused identity setup using the selected pack's declared options."""

    generate_requested = Signal()
    begin_requested = Signal()
    back_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("central")
        self.pack = get_world_pack("naruto")
        self.setStyleSheet("""
            QWidget { background: #111820; color: #e7eee8; font-family: 'Bahnschrift', 'Yu Gothic UI', sans-serif; }
            QLabel#eyebrow { color: #63c6bb; font-size: 10px; font-weight: 800; letter-spacing: 2px; }
            QLabel#title { color: #e7eee8; font-size: 32px; font-weight: 850; }
            QLabel#muted { color: #99aaa5; }
            QFrame#setupCard { background: #1d2a32; border: 1px solid #34474c; border-radius: 14px; }
            QLineEdit, QComboBox, QSpinBox { background: #142027; color: #e7eee8; border: 1px solid #34474c; border-radius: 8px; padding: 9px 11px; min-height: 20px; }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #63c6bb; }
            QPushButton { background: #24343c; color: #e7eee8; border: 1px solid #34474c; border-radius: 8px; padding: 11px 16px; font-weight: 700; }
            QPushButton:hover { border-color: #63c6bb; }
            QPushButton#primary { background: #9fce91; color: #17231e; border-color: #9fce91; font-weight: 900; }
            QPushButton#primary:hover { background: #b4dca7; }
            QScrollArea { border: 0; background: transparent; }
        """)
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(34, 26, 34, 26)
        outer.setSpacing(16)
        eyebrow = QLabel("NARUTO WORLD PACK  /  NEW LIFE")
        eyebrow.setObjectName("eyebrow")
        outer.addWidget(eyebrow)
        title = QLabel("Create your shinobi")
        title.setObjectName("title")
        outer.addWidget(title)
        intro = QLabel("Choose the roots of your character. Your village, family, and nature create a starting point; birth traits are rolled by the world simulation.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        row = QHBoxLayout(content)
        row.setSpacing(16)

        identity = self._card()
        identity_layout = QVBoxLayout(identity)
        identity_layout.setContentsMargins(20, 20, 20, 20)
        identity_layout.setSpacing(14)
        identity_title = QLabel("IDENTITY")
        identity_title.setObjectName("eyebrow")
        identity_layout.addWidget(identity_title)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Name")
        self.name_input.setMaxLength(32)
        form.addRow("Name", self.name_input)
        self.age_input = QSpinBox()
        self.age_input.setRange(0, 30)
        self.age_input.setValue(0)
        form.addRow("Starting age", self.age_input)
        self.village_input = self._options_combo(self.pack["character_creation"]["villages"])
        form.addRow("Village", self.village_input)
        self.clan_input = self._options_combo(self.pack["character_creation"]["clans"])
        form.addRow("Family", self.clan_input)
        self.nature_input = self._options_combo(self.pack["character_creation"]["chakra_natures"])
        form.addRow("Chakra nature", self.nature_input)
        identity_layout.addLayout(form)
        identity_layout.addStretch()
        row.addWidget(identity, 3)

        preview = self._card()
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(22, 22, 22, 22)
        preview_layout.setSpacing(12)
        preview_label = QLabel("THE FIRST CHAPTER")
        preview_label.setObjectName("eyebrow")
        preview_layout.addWidget(preview_label)
        preview_title = QLabel("A village,\na family,\na path.")
        preview_title.setStyleSheet("font-size: 27px; font-weight: 850; color: #e7eee8;")
        preview_layout.addWidget(preview_title)
        preview_text = QLabel("Your first years are open. Train your body, learn chakra control, study at the academy, and decide who earns your trust. Two random traits are drawn at birth; you do not choose a starting perk.")
        preview_text.setObjectName("muted")
        preview_text.setWordWrap(True)
        preview_layout.addWidget(preview_text)
        preview_layout.addSpacing(6)
        for text in ("3 personal actions and 2 social actions each year through age 12", "5 personal actions and 3 social actions from ages 13 to 17", "7 personal actions and 4 social actions from age 18 onward"):
            item = QLabel(f"-   {text}")
            item.setWordWrap(True)
            item.setStyleSheet("color: #b7c6be; padding: 5px 0;")
            preview_layout.addWidget(item)
        preview_layout.addStretch()
        row.addWidget(preview, 2)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        controls = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(self.back_requested.emit)
        controls.addWidget(back)
        controls.addStretch()
        self.begin_button = QPushButton("Begin life")
        self.begin_button.setObjectName("primary")
        self.begin_button.setMinimumWidth(190)
        self.begin_button.setMinimumHeight(46)
        self.begin_button.clicked.connect(self.begin_requested.emit)
        controls.addWidget(self.begin_button)
        outer.addLayout(controls)

    @staticmethod
    def _card() -> QFrame:
        frame = QFrame()
        frame.setObjectName("setupCard")
        return frame

    @staticmethod
    def _options_combo(options: list[dict]) -> QComboBox:
        combo = QComboBox()
        for option in options:
            combo.addItem(option.get("name", option["id"]), option["id"])
        return combo

    def get_creation_data(self) -> dict:
        return {
            "name": self.name_input.text(),
            "age": str(self.age_input.value()),
            "start_year": 1,
            "world_pack": "naruto",
            "world_options": {
                "age": self.age_input.value(),
                "village": self.village_input.currentData(),
                "clan": self.clan_input.currentData(),
                "chakra_nature": self.nature_input.currentData(),
            },
        }


if __name__ == "__main__":
    app = QApplication([])
    screen = CreationScreen()
    screen.show()
    raise SystemExit(app.exec())
