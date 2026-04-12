## ADDED Requirements

### Requirement: Theme toggle button visibility
The system SHALL display a theme toggle button in the dashboard header when the dashboard is loaded.

#### Scenario: Dashboard loads with toggle visible
- **WHEN** the dashboard page loads
- **THEN** a theme toggle button SHALL be visible in the header next to the status dot

### Requirement: Theme switching
The system SHALL toggle between light and dark themes when the user clicks the theme toggle button.

#### Scenario: Toggle from dark to light
- **WHEN** the user clicks the theme toggle button while in dark mode
- **THEN** the dashboard SHALL switch to light theme colors

#### Scenario: Toggle from light to dark
- **WHEN** the user clicks the theme toggle button while in light mode
- **THEN** the dashboard SHALL switch to dark theme colors

### Requirement: Theme persistence
The system SHALL persist the user's theme preference in localStorage and restore it on subsequent visits.

#### Scenario: Theme preference survives reload
- **GIVEN** the user has selected light theme
- **WHEN** the page is reloaded
- **THEN** the dashboard SHALL display in light theme

### Requirement: System preference detection
The system SHALL detect and respect the user's system color scheme preference on first visit (when no localStorage value exists).

#### Scenario: First visit respects system preference
- **GIVEN** the user's system preference is set to light
- **AND** no theme has been stored in localStorage
- **WHEN** the dashboard loads for the first time
- **THEN** the dashboard SHALL display in light theme

### Requirement: Smooth theme transitions
The system SHALL apply smooth transitions when switching between themes.

#### Scenario: Theme change animates smoothly
- **WHEN** the user toggles the theme
- **THEN** color changes SHALL animate over 200-300ms

### Requirement: Light theme color palette
The system SHALL define a light theme with appropriate color contrast for readability.

#### Scenario: Light theme has proper contrast
- **GIVEN** the theme is set to light mode
- **THEN** background colors SHALL be light (#f5f5f5 or lighter)
- **AND** text colors SHALL be dark (#1a1a1a or darker)
- **AND** accent colors SHALL remain visible and accessible
