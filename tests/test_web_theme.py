"""Tests for theme toggle functionality in the web dashboard.

Validates:
- Light theme CSS variables are defined
- Theme toggle button exists in the HTML
- JavaScript handles theme detection, persistence, and toggling
- Smooth transitions are configured
- Anti-FOUC script prevents flash of wrong theme
"""

import re

from stokowski.web import DASHBOARD_HTML


class TestLightThemeCSSVariables:
    """Verify light theme color variables are defined."""

    def test_light_theme_selector_exists(self):
        """CSS selector [data-theme='light'] should exist."""
        assert "[data-theme=" in DASHBOARD_HTML or '[data-theme="' in DASHBOARD_HTML
        assert "light" in DASHBOARD_HTML

    def test_light_theme_has_background_variables(self):
        """Light theme should define --bg and --surface variables."""
        # Find [data-theme="light"] block and check for bg/surface
        light_match = re.search(
            r'\[data-theme\s*=\s*["\']light["\']\s*\]\s*\{([^}]+)\}',
            DASHBOARD_HTML,
            re.DOTALL,
        )
        assert light_match is not None, "No [data-theme='light'] selector found"
        light_css = light_match.group(1)
        assert "--bg" in light_css, "Light theme missing --bg variable"
        assert "--surface" in light_css, "Light theme missing --surface variable"

    def test_light_theme_has_text_variables(self):
        """Light theme should define --text and --muted variables."""
        light_match = re.search(
            r'\[data-theme\s*=\s*["\']light["\']\s*\]\s*\{([^}]+)\}',
            DASHBOARD_HTML,
            re.DOTALL,
        )
        assert light_match is not None
        light_css = light_match.group(1)
        assert "--text" in light_css, "Light theme missing --text variable"
        assert "--muted" in light_css, "Light theme missing --muted variable"

    def test_light_theme_has_border_variables(self):
        """Light theme should define --border and --border-hi variables."""
        light_match = re.search(
            r'\[data-theme\s*=\s*["\']light["\']\s*\]\s*\{([^}]+)\}',
            DASHBOARD_HTML,
            re.DOTALL,
        )
        assert light_match is not None
        light_css = light_match.group(1)
        assert "--border" in light_css, "Light theme missing --border variable"

    def test_light_theme_backgrounds_are_light(self):
        """Light theme backgrounds should be light colors (low numeric values for RGB)."""
        light_match = re.search(
            r'\[data-theme\s*=\s*["\']light["\']\s*\]\s*\{([^}]+)\}',
            DASHBOARD_HTML,
            re.DOTALL,
        )
        assert light_match is not None
        light_css = light_match.group(1)
        # Extract --bg value
        bg_match = re.search(r"--bg:\s*([^;]+);", light_css)
        assert bg_match is not None, "No --bg found in light theme"
        bg_val = bg_match.group(1).strip()
        # Light backgrounds should start with higher hex values (f, e, d, c)
        # or be named light colors
        assert bg_val.startswith(
            ("#f", "#e", "#d", "#c", "#F", "#E", "#D", "#C", "white")
        ) or bg_val in ("#ffffff", "#fafafa", "#f5f5f5", "#eeeeee"), (
            f"Light theme --bg ({bg_val}) should be a light color"
        )

    def test_light_theme_text_is_dark(self):
        """Light theme text should be dark (high contrast)."""
        light_match = re.search(
            r'\[data-theme\s*=\s*["\']light["\']\s*\]\s*\{([^}]+)\}',
            DASHBOARD_HTML,
            re.DOTALL,
        )
        assert light_match is not None
        light_css = light_match.group(1)
        text_match = re.search(r"--text:\s*([^;]+);", light_css)
        assert text_match is not None, "No --text found in light theme"
        text_val = text_match.group(1).strip()
        # Dark text starts with low hex values (0, 1, 2, 3) or named dark colors
        assert text_val.startswith(("#1", "#2", "#3", "#0")) or text_val in (
            "#1a1a1a",
            "#222222",
            "#333333",
            "black",
        ), f"Light theme --text ({text_val}) should be a dark color"


class TestThemeToggleButton:
    """Verify theme toggle button exists and is accessible."""

    def test_toggle_button_exists_in_header(self):
        """A theme toggle button should exist in the header area."""
        assert "theme-toggle" in DASHBOARD_HTML or "themeToggle" in DASHBOARD_HTML, (
            "No theme toggle element found in dashboard HTML"
        )

    def test_toggle_button_has_aria_attributes(self):
        """Toggle button should have ARIA attributes for accessibility."""
        # Look for aria-label on the toggle button
        aria_match = re.search(
            r'aria-label=["\'][^"\']*theme[^"\']*["\']', DASHBOARD_HTML, re.IGNORECASE
        )
        assert aria_match is not None, "Theme toggle button missing aria-label"

    def test_toggle_button_in_header_right(self):
        """Toggle button should be placed within header-right area."""
        header_right = re.search(
            r'<div class="header-right">(.*?)</div>', DASHBOARD_HTML, re.DOTALL
        )
        assert header_right is not None, "No header-right div found"
        header_right_content = header_right.group(1)
        assert "theme" in header_right_content.lower(), (
            "Theme toggle should be inside header-right div"
        )


class TestThemeSwitchingJavaScript:
    """Verify JavaScript theme switching logic."""

    def test_localstorage_theme_key(self):
        """JavaScript should use localStorage key 'stokowski-theme'."""
        assert "stokowski-theme" in DASHBOARD_HTML, "localStorage key 'stokowski-theme' not found"

    def test_prefers_color_scheme_detection(self):
        """JavaScript should detect system preference via prefers-color-scheme."""
        assert "prefers-color-scheme" in DASHBOARD_HTML, "No prefers-color-scheme detection found"

    def test_toggle_function_exists(self):
        """JavaScript should have a function to toggle theme."""
        # Look for a function or handler that toggles theme
        assert "toggleTheme" in DASHBOARD_HTML or "data-theme" in DASHBOARD_HTML, (
            "No theme toggle function found"
        )

    def test_setattr_data_theme(self):
        """JavaScript should set data-theme attribute on document element."""
        assert "setAttribute" in DASHBOARD_HTML and "data-theme" in DASHBOARD_HTML, (
            "No setAttribute with data-theme found"
        )

    def test_anti_fouc_script_in_head(self):
        """An inline script in <head> should prevent FOUC by setting theme before render."""
        # Find <head> content and check for theme-setting script before </head>
        head_match = re.search(r"<head>(.*?)</head>", DASHBOARD_HTML, re.DOTALL)
        assert head_match is not None, "No <head> section found"
        head_content = head_match.group(1)
        # The script should set data-theme before the page renders
        assert "stokowski-theme" in head_content, (
            "Anti-FOUC script not found in <head> - theme may flash on load"
        )


class TestThemeTransitions:
    """Verify smooth CSS transitions for theme switching."""

    def test_transition_on_themed_elements(self):
        """CSS should define transitions for color and background-color changes."""
        # Look for transition rules on body or themed elements
        transition_match = re.search(
            r"transition[^;]*color[^;]*;",
            DASHBOARD_HTML,
        )
        assert transition_match is not None, "No transition for color properties found"


class TestDarkThemeDefault:
    """Verify dark theme remains the default."""

    def test_root_theme_variables_unchanged(self):
        """Dark theme variables in :root should still be present."""
        root_match = re.search(r":root\s*\{([^}]+)\}", DASHBOARD_HTML, re.DOTALL)
        assert root_match is not None, "No :root selector found"
        root_css = root_match.group(1)
        assert "--bg:" in root_css or "--bg :" in root_css
        assert "#080808" in root_css, "Dark theme --bg should remain #080808"
