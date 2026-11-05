"""Theme styles for Riverton application."""

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
