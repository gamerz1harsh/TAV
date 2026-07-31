"""Developer Console for Riverton — event logging and diagnostics.

Provides a dockable console window that logs game events, state changes,
LLM interactions, and errors for debugging and diagnosis purposes.
Opens automatically with the game and can be toggled via View menu or Ctrl+`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QAction, QKeySequence, QTextCursor, QColor, QFont
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLineEdit, QComboBox, QLabel, QFrame, QCheckBox,
)


# Color scheme for log levels
LOG_COLORS = {
    "DEBUG":   QColor(140, 140, 160),    # Gray
    "INFO":    QColor(88, 166, 255),     # Blue
    "WARN":    QColor(210, 153, 34),     # Yellow/Orange
    "ERROR":   QColor(248, 81, 73),      # Red
    "CRITICAL": QColor(255, 50, 50),     # Bright Red
    "STATE":   QColor(63, 185, 80),      # Green
    "LLM":     QColor(180, 130, 255),    # Purple
    "EVENT":   QColor(247, 129, 102),    # Coral
}


class LogEmitter(QObject):
    """Signal-based emitter for thread-safe logging from any thread."""
    log_signal = Signal(str, str, str)  # level, source, message


class DevConsole(QDockWidget):
    """A dockable developer console for logging game events."""

    def __init__(self, parent=None) -> None:
        super().__init__("Dev Console", parent)
        self.setObjectName("dev_console")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Thread-safe log emitter
        self._emitter = LogEmitter()
        self._emitter.log_signal.connect(self._append_log_threadsafe)

        # Track log count for auto-clear
        self._log_count = 0

        # Build UI
        self._build_ui()

        # Log initial message
        self.info("Dev Console initialized", "System")

    def _build_ui(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        # Filter label
        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        toolbar.addWidget(filter_label)

        # Level filter combo
        self.level_filter = QComboBox()
        self.level_filter.addItems(["ALL", "DEBUG", "INFO", "WARN", "ERROR", "STATE", "EVENT", "LLM"])
        self.level_filter.setFixedWidth(100)
        self.level_filter.setStyleSheet("""
            QComboBox {
                background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
                border-radius: 4px; padding: 3px 6px; font-size: 11px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { image: none; border-left: 4px solid transparent;
                border-right: 4px solid transparent; border-top: 6px solid #8b949e;
                margin-right: 4px; }
            QComboBox:hover { border-color: #58a6ff; }
        """)
        self.level_filter.currentTextChanged.connect(self._apply_filter)
        toolbar.addWidget(self.level_filter)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search logs...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
                border-radius: 4px; padding: 3px 8px; font-size: 11px;
            }
            QLineEdit:focus { border-color: #58a6ff; }
        """)
        self.search_input.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.search_input, 1)

        # Auto-scroll toggle
        self.auto_scroll_cb = QCheckBox("Auto-scroll")
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.setStyleSheet("color: #8b949e; font-size: 11px;")
        toolbar.addWidget(self.auto_scroll_cb)

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(60)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
                border-radius: 4px; padding: 3px 8px; font-size: 11px;
            }
            QPushButton:hover { background: #30363d; border-color: #58a6ff; }
        """)
        clear_btn.clicked.connect(self._clear_logs)
        toolbar.addWidget(clear_btn)

        layout.addLayout(toolbar)

        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Consolas, Courier New, monospace", 10))
        self.log_display.setStyleSheet("""
            QTextEdit {
                background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
                border-radius: 4px; padding: 6px;
            }
        """)
        self.log_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.log_display, 1)

        # Status bar
        status_bar = QHBoxLayout()
        self.log_status = QLabel("0 entries")
        self.log_status.setStyleSheet("color: #8b949e; font-size: 10px;")
        status_bar.addWidget(self.log_status)
        status_bar.addStretch()

        # Keyboard shortcut hint
        hint = QLabel("Ctrl+` to toggle")
        hint.setStyleSheet("color: #484f58; font-size: 10px;")
        status_bar.addWidget(hint)

        layout.addLayout(status_bar)

        self.setWidget(container)

    def log(self, level: str, message: str, source: str = "") -> None:
        """Add a log entry. Thread-safe — can be called from any thread."""
        self._emitter.log_signal.emit(level, source, message)

    def _append_log_threadsafe(self, level: str, source: str, message: str) -> None:
        """Append a log entry (runs in main thread via signal)."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        source_str = f"[{source}]" if source else ""
        level_str = level.ljust(8)

        # Format: [HH:MM:SS.mmm] [LEVEL] [source] message
        log_line = f"{timestamp}  {level_str}  {source_str}  {message}"

        # Get color for level
        color = LOG_COLORS.get(level, QColor(200, 200, 200))

        # Store raw text for filtering
        if not hasattr(self, '_all_logs'):
            self._all_logs = []
        self._all_logs.append((level, source, log_line))

        # Check if this entry passes the current filter
        if self._passes_filter(level, source, log_line):
            self._append_colored(log_line, color)

        self._log_count += 1
        self.log_status.setText(f"{self._log_count} entries")

    def _append_colored(self, text: str, color: QColor) -> None:
        """Append colored text to the log display."""
        self.log_display.setTextColor(color)
        self.log_display.append(text)

        if self.auto_scroll_cb.isChecked():
            cursor = self.log_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.log_display.setTextCursor(cursor)

    def _passes_filter(self, level: str, source: str, log_line: str) -> bool:
        """Check if a log entry passes the current filter criteria."""
        # Level filter
        level_filter = self.level_filter.currentText()
        if level_filter != "ALL" and level != level_filter:
            return False

        # Text search
        search_text = self.search_input.text().strip().lower()
        if search_text and search_text not in log_line.lower():
            return False

        return True

    def _apply_filter(self) -> None:
        """Re-apply the current filter to all logs."""
        if not hasattr(self, '_all_logs'):
            return

        # Save scroll position
        scrollbar = self.log_display.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10 if scrollbar.maximum() > 0 else True

        self.log_display.clear()
        for level, source, log_line in self._all_logs:
            if self._passes_filter(level, source, log_line):
                color = LOG_COLORS.get(level, QColor(200, 200, 200))
                self._append_colored(log_line, color)

        # Restore scroll position
        if was_at_bottom:
            cursor = self.log_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.log_display.setTextCursor(cursor)

    def _clear_logs(self) -> None:
        """Clear all log entries."""
        self.log_display.clear()
        self._all_logs = []
        self._log_count = 0
        self.log_status.setText("0 entries")

    # Convenience logging methods
    def debug(self, message: str, source: str = "") -> None:
        self.log("DEBUG", message, source)

    def info(self, message: str, source: str = "") -> None:
        self.log("INFO", message, source)

    def warn(self, message: str, source: str = "") -> None:
        self.log("WARN", message, source)

    def error(self, message: str, source: str = "") -> None:
        self.log("ERROR", message, source)

    def state(self, message: str, source: str = "") -> None:
        self.log("STATE", message, source)

    def llm(self, message: str, source: str = "") -> None:
        self.log("LLM", message, source)

    def log_event(self, message: str, source: str = "") -> None:
        self.log("EVENT", message, source)
