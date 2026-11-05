# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFrame, QGridLayout, QHBoxLayout,
)

class StartScreen(QWidget):
    """The initial screen for the Riverton application, handling New Game and Continue Game logic."""
    # Signals to communicate actions back to RivertonWindow
    new_game_requested = Signal()
    continue_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("central")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
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
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(24)

        # New Game Button
        new_btn = QPushButton("New Game")
        new_btn.setFixedHeight(54)
        new_btn.setMinimumWidth(280)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self.new_game_requested.emit)
        layout.addWidget(new_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Continue Game Button (Conditional visibility handled by the parent)
        self.continue_btn = QPushButton("Continue Game")
        self.continue_btn.setFixedHeight(44)
        self.continue_btn.setMinimumWidth(280)
        self.continue_btn.setObjectName("quiet")
        self.continue_btn.setProperty("class", "quiet")
        self.continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.continue_btn.clicked.connect(self.continue_requested.emit)
        layout.addWidget(self.continue_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()

        # Version label
        version = QLabel("v1.0.0")
        version.setStyleSheet("color: #30363d; font-size: 10px;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)