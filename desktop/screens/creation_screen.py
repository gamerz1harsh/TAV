"""Component: Character Creation Screen UI Module."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QScrollArea, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

# Assuming these are available from the parent scope/project structure
from game_engine import ORIGINS 
from character_creation import enumerate_eras


class CreationScreen(QWidget):
    """
    Encapsulates the entire widget layout and user input controls for creating a new character.
    Signals are emitted to communicate intent back to the main application controller (RivertonWindow).
    """
    # Signals emitted when user clicks primary action buttons
    generate_requested = Signal()
    begin_requested = Signal()
    back_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("central")
        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(52, 24, 52, 24)
        layout.setSpacing(12)

        header = QLabel("Create Your Character")
        header.setObjectName("title")
        header.setStyleSheet("font-size: 36px;")
        layout.addWidget(header)

        # --- Form Layout (Inputs) ---
        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Your name")
        self.name_input.setMaxLength(32)
        form.addRow("Name", self.name_input)

        # Defaulting Era input to the first available era
        default_era = enumerate_eras()[0]
        self.era_input = QLineEdit(default_era)
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

        # --- Origin Group (Buttons) ---
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

        # --- Controls (Buttons) ---
        controls = QHBoxLayout()
        generate = QPushButton("Generate")
        generate.setCursor(Qt.CursorShape.PointingHandCursor)
        generate.clicked.connect(self.generate_requested.emit) # Emit signal instead of calling method
        controls.addWidget(generate)

        begin = QPushButton("Begin without generation")
        begin.setCursor(Qt.CursorShape.PointingHandCursor)
        begin.clicked.connect(self.begin_requested.emit) # Emit signal instead of calling method
        controls.addWidget(begin)

        back = QPushButton("Back")
        back.setObjectName("quiet")
        back.setProperty("class", "quiet")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_requested.emit) # Emit signal instead of calling method
        controls.addWidget(back)

        controls.addStretch()
        layout.addLayout(controls)


    def get_creation_data(self) -> dict:
        """
        Gathers all current user selections needed to create the character template dictionary 
        in the main application logic.
        """
        # Determine origin ID from the checked button
        button = self.origin_group.checkedButton()
        origin_id = button.property("origin_id") if button else None

        return {
            "name": self.name_input.text(),
            "era": self.era_input.text(),
            "age": self.age_input.text(),
            "start_year": int(self.start_year_box.currentText()),
            "use_llm": self.llm_box.isChecked(),
            "origin": origin_id,
        }

# Example usage of the class structure (for testing purposes, not run in main)
if __name__ == '__main__':
    app = QApplication([])
    screen = CreationScreen()
    screen.show()