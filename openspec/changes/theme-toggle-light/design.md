## Context

The Stokowski dashboard (`stokowski/web.py`) uses CSS custom properties (variables) for theming. Currently, only a dark theme is defined in `:root`. The dashboard is a single HTML file with inline CSS and JavaScript served via FastAPI.

Current theme colors (dark):
- Background: `#080808` (bg), `#0f0f0f` (surface)
- Text: `#e8e8e0`
- Accents: amber (`#e8b84b`), green (`#4cba6e`), red (`#d95f52`), blue (`#5b9cf6`)

## Goals / Non-Goals

**Goals:**
- Implement a light theme with good contrast and readability
- Add a visible theme toggle button in the header
- Persist user's theme preference across sessions
- Respect system preference on first visit
- Maintain visual polish consistent with current dark theme

**Non-Goals:**
- Multiple theme variants (sepia, high-contrast, etc.)
- Server-side theme storage
- Theme scheduling (auto-switch based on time of day)

## Decisions

**1. CSS Variable Approach**
- Use a `data-theme` attribute on `<html>` or `<body>` element to switch between themes
- Define light theme variables under `[data-theme="light"]` selector
- This allows instant theme switching without reloading

**2. Toggle Button Placement**
- Place in header next to status dot and timestamp
- Use a simple icon button (sun/moon or similar) to save space
- Icon changes based on current theme state

**3. Storage Strategy**
- Use `localStorage` for persistence (key: `stokowski-theme`)
- Check `localStorage` first, fall back to `prefers-color-scheme`, default to dark
- No server-side storage needed

**4. Theme Colors for Light Mode**
- Background: Light gray (`#f5f5f5`, `#ffffff`)
- Text: Dark gray (`#1a1a1a`, `#333333`)
- Keep accent colors similar but may adjust saturation slightly for light backgrounds
- Borders: Light grays (`#e0e0e0`, `#d0d0d0`)

**5. Transition Strategy**
- Add CSS transitions on color and background-color changes (200-300ms)
- Apply to all themed elements for smooth switching

## Risks / Trade-offs

**[Risk] Flash of unstyled content (FOUC) or wrong theme on page load**
→ Mitigation: Inline a small script in `<head>` to set theme before rendering, or use `color-scheme` CSS property

**[Risk] Light theme may have insufficient contrast**
→ Mitigation: Test with accessibility tools, ensure WCAG AA compliance for text contrast

**[Risk] Grid background pattern may not work well in light mode**
→ Mitigation: Adjust grid line opacity or use a subtler pattern
