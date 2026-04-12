## Why

The Stokowski dashboard currently only supports a dark theme. Users want the ability to switch between light and dark themes for better visibility in different lighting conditions and personal preference.

## What Changes

- Add a light theme with appropriate color variables (light backgrounds, dark text, adjusted accent colors)
- Add a theme toggle button in the dashboard header for switching between light and dark themes
- Persist theme preference to localStorage so it survives page reloads
- Set default theme based on system preference (`prefers-color-scheme`)
- Ensure smooth transitions when switching themes

## Capabilities

### New Capabilities
- `theme-toggle`: Theme switching system with light/dark modes, localStorage persistence, and system preference detection

### Modified Capabilities
- None (this is a UI enhancement that doesn't change existing requirements)

## Impact

- `stokowski/web.py`: CSS variables for theming, toggle button HTML, JavaScript for theme switching logic
