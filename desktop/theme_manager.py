"""Theme Manager for Riverton V1.

Applies era-based color schemes, fonts, and UI labels at the app level.
Switching eras instantly changes the entire UI appearance.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
THEMES_DIR = DATA_DIR / "themes"

# Fallback modern theme (used when theme JSON files are missing)
DEFAULT_THEME: dict[str, Any] = {
    "era": "modern",
    "colors": {
        "background": "#0d1117",
        "card_bg": "#161b22",
        "card_border": "#30363d",
        "accent": "#58a6ff",
        "accent_secondary": "#1f6feb",
        "text_primary": "#f0f6fc",
        "text_secondary": "#c9d1d9",
        "text_muted": "#8b949e",
        "success": "#238636",
        "warning": "#d29922",
        "danger": "#f85149",
        "info": "#58a6ff",
        "stat_health": "#fb7185",
        "stat_happiness": "#c084fc",
        "stat_smarts": "#60a5fa",
        "stat_looks": "#fbbf24",
    },
    "fonts": {
        "display": "Georgia, 'Times New Roman', serif",
        "body": "'Segoe UI', -apple-system, sans-serif",
        "mono": "'Consolas', 'Courier New', monospace",
    },
    "ui_labels": {
        "brand": "RIVERTON // MODERN LIFE",
        "journal_title": "LIFE LOG",
        "snapshot_title": "LIFE SNAPSHOT",
        "operations_title": "NEXT MOVES",
        "status_title": "STATUS",
        "profile_title": "PROFILE",
        "map_title": "MAP",
        "people_title": "PEOPLE HERE",
        "actions_title": "ACTIONS",
    },
}


class ThemeManager:
    """Manages era-based UI themes."""

    def __init__(self) -> None:
        self._themes: dict[str, dict[str, Any]] = {}
        self._current_era: str = "modern"
        self._load_all_themes()

    def _load_all_themes(self) -> None:
        """Load all theme JSON files from the themes directory."""
        if not THEMES_DIR.exists():
            self._themes = {"modern": DEFAULT_THEME}
            return

        for theme_file in THEMES_DIR.glob("*_theme.json"):
            try:
                data = json.loads(theme_file.read_text(encoding="utf-8"))
                era = data.get("era", theme_file.name.replace("_theme.json", ""))
                self._themes[era] = data
            except (json.JSONDecodeError, OSError):
                continue

        # Ensure modern theme always exists
        self._themes.setdefault("modern", DEFAULT_THEME)

    def get_theme(self, era: str | None = None) -> dict[str, Any]:
        """Get the theme for an era (defaults to current era)."""
        era_key = era or self._current_era
        return self._themes.get(era_key, DEFAULT_THEME)

    def apply_theme(self, app: QApplication, era: str) -> None:
        """Apply the theme for the given era to the application."""
        self._current_era = era
        theme = self.get_theme(era)
        app.setStyleSheet(self._build_stylesheet(theme))

    def _build_stylesheet(self, theme: dict[str, Any]) -> str:
        """Build a QSS stylesheet from the theme data."""
        colors = theme.get("colors", DEFAULT_THEME["colors"])
        fonts = theme.get("fonts", DEFAULT_THEME["fonts"])

        bg = colors.get("background", "#0d1117")
        card_bg = colors.get("card_bg", "#161b22")
        card_border = colors.get("card_border", "#30363d")
        accent = colors.get("accent", "#58a6ff")
        accent_secondary = colors.get("accent_secondary", "#1f6feb")
        text_primary = colors.get("text_primary", "#f0f6fc")
        text_secondary = colors.get("text_secondary", "#c9d1d9")
        text_muted = colors.get("text_muted", "#8b949e")
        success = colors.get("success", "#238636")
        warning = colors.get("warning", "#d29922")
        danger = colors.get("danger", "#f85149")
        info = colors.get("info", "#58a6ff")
        display_font = fonts.get("display", "Georgia, serif")
        body_font = fonts.get("body", "'Segoe UI', sans-serif")
        mono_font = fonts.get("mono", "'Consolas', monospace")

        return f"""
        QWidget {{
            background: {bg};
            color: {text_secondary};
            font-family: {body_font};
            font-size: 13px;
        }}
        QWidget#central {{
            background: {bg};
        }}

        /* Headers */
        QLabel#eyebrow {{
            color: {accent};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.5px;
            text-transform: uppercase;
        }}
        QLabel#title {{
            font-family: {display_font};
            font-size: 40px;
            font-weight: 700;
            color: {text_primary};
        }}
        QLabel#subtitle {{
            color: {text_muted};
            font-size: 13px;
            font-weight: 500;
        }}

        /* Cards & Groups */
        QFrame.card, QGroupBox {{
            background: {card_bg};
            border: 1px solid {card_border};
            border-radius: 8px;
        }}
        QFrame.card:hover {{
            border-color: {accent};
        }}
        QGroupBox {{
            margin-top: 14px;
            padding: 20px 14px 14px 14px;
            font-weight: 700;
            color: {text_primary};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 6px;
            color: {accent};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1px;
        }}

        /* Buttons */
        QPushButton {{
            background: {success};
            color: #ffffff;
            border: 1px solid {success};
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: 600;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: {accent_secondary};
            border-color: {accent};
        }}
        QPushButton:pressed {{
            background: {accent_secondary};
        }}
        QPushButton:disabled {{
            background: {card_bg};
            color: {text_muted};
            border-color: {card_border};
        }}

        /* Location buttons */
        QPushButton.location {{
            background: {card_bg};
            color: {text_secondary};
            border: 1px solid {card_border};
            border-radius: 6px;
            padding: 8px 14px;
        }}
        QPushButton.location:hover {{
            background: {card_border};
            border-color: {accent};
            color: {text_primary};
        }}
        QPushButton.location:checked {{
            background: {accent_secondary};
            color: #ffffff;
            border-color: {accent};
        }}

        /* Origin buttons */
        QPushButton.origin {{
            background: {card_bg};
            color: {text_secondary};
            border: 1px solid {card_border};
            border-radius: 8px;
            padding: 16px;
            text-align: left;
            font-size: 12px;
        }}
        QPushButton.origin:hover {{
            background: {card_border};
            border-color: {accent};
        }}
        QPushButton.origin:checked {{
            border: 2px solid {accent};
            background: {card_border};
        }}

        /* Quiet buttons */
        QPushButton.quiet {{
            background: transparent;
            color: {text_muted};
            border: 1px solid {card_border};
        }}
        QPushButton.quiet:hover {{
            color: {text_primary};
            border-color: {accent};
        }}

        /* Text inputs */
        QLineEdit {{
            background: {bg};
            color: {text_secondary};
            border: 1px solid {card_border};
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 13px;
        }}
        QLineEdit:focus {{
            border-color: {accent};
        }}
        QLineEdit::placeholder {{
            color: {text_muted};
        }}

        /* Text edit / journal */
        QTextEdit {{
            background: {bg};
            color: {text_secondary};
            border: 1px solid {card_border};
            border-radius: 6px;
            padding: 8px;
            font-size: 12px;
        }}

        /* Combo box */
        QComboBox {{
            background: {bg};
            color: {text_secondary};
            border: 1px solid {card_border};
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
        }}
        QComboBox:hover {{
            border-color: {accent};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid {text_muted};
            margin-right: 6px;
        }}
        QComboBox QAbstractItemView {{
            background: {card_bg};
            color: {text_secondary};
            border: 1px solid {card_border};
            selection-background-color: {accent_secondary};
        }}

        /* Checkboxes */
        QCheckBox {{
            color: {text_secondary};
            font-size: 12px;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {card_border};
            border-radius: 3px;
            background: {bg};
        }}
        QCheckBox::indicator:checked {{
            background: {accent_secondary};
            border-color: {accent};
        }}

        /* Scroll areas */
        QScrollArea {{
            border: none;
            background: transparent;
        }}
        QScrollBar:vertical {{
            background: {card_bg};
            width: 10px;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {card_border};
            border-radius: 5px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {text_muted};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        /* Progress bars */
        QProgressBar {{
            background: {card_bg};
            border: 1px solid {card_border};
            border-radius: 6px;
            text-align: center;
            color: {text_muted};
            font-size: 11px;
        }}
        QProgressBar::chunk {{
            background: {success};
            border-radius: 5px;
        }}

        /* Menu bar */
        QMenuBar {{
            background: {card_bg};
            color: {text_muted};
            border-bottom: 1px solid {card_border};
            padding: 2px;
        }}
        QMenuBar::item {{
            padding: 6px 12px;
            border-radius: 4px;
        }}
        QMenuBar::item:selected {{
            background: {card_border};
            color: {text_primary};
        }}
        QMenu {{
            background: {card_bg};
            color: {text_secondary};
            border: 1px solid {card_border};
            border-radius: 6px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 8px 32px 8px 12px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background: {accent_secondary};
            color: #ffffff;
        }}
        QMenu::separator {{
            height: 1px;
            background: {card_border};
            margin: 4px 8px;
        }}

        /* Status bar */
        QStatusBar {{
            background: {card_bg};
            color: {text_muted};
            border-top: 1px solid {card_border};
            font-size: 11px;
        }}
        QStatusBar::item {{
            border: none;
        }}

        /* Dialog styling */
        QDialog {{
            background: {bg};
        }}
        QDialog QLabel {{
            color: {text_secondary};
        }}
        QDialogButtonBox QPushButton {{
            min-width: 80px;
        }}
        """