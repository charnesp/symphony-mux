## MODIFIED Requirements

### Requirement: State tracking comments use BASE64-encoded markers at end
The system SHALL encode state tracking markers as BASE64 and place them at the END of comments.

#### Scenario: Creating state comment with new format
- **WHEN** creating a state tracking comment for state "investigate", run 1
- **THEN** the machine marker SHALL be placed AFTER the human-readable text
- **AND** the format SHALL be `stokowski64:<base64_encoded_json>`
- **AND** the base64 payload SHALL decode to valid JSON containing `"type": "state"`

#### Scenario: Decoding state marker from end of comment
- **WHEN** parsing a comment containing `stokowski64:eyJ0eXBlIjoic3RhdGUi...`
- **THEN** parse_latest_tracking SHALL decode the BASE64 payload
- **AND** return the state information from the JSON

### Requirement: Gate tracking comments use BASE64-encoded markers at end
The system SHALL encode gate tracking markers as BASE64 and place them at the END of comments.

#### Scenario: Creating gate comment with new format
- **WHEN** creating a gate tracking comment with status "waiting"
- **THEN** the machine marker SHALL be placed AFTER the human-readable text
- **AND** the format SHALL be `stokowski64:<base64_encoded_json>`
- **AND** the base64 payload SHALL decode to valid JSON containing `"type": "gate"`

#### Scenario: Parsing waiting gate from end-placed marker
- **WHEN** parsing a comment containing `stokowski64:eyJ0eXBlIjoiZ2F0ZSJ9...`
- **THEN** parse_latest_gate_waiting SHALL decode the BASE64 payload
- **AND** return the gate information from the JSON

### Requirement: Report tracking comments use BASE64-encoded markers at end
The system SHALL encode report tracking markers as BASE64 and place them at the END of comments.

#### Scenario: Creating report comment with new format
- **WHEN** formatting a report comment with run number, state, and approval section flag
- **THEN** the machine marker SHALL be placed AFTER the human-readable report content
- **AND** the format SHALL be `stokowski64:<base64_encoded_json>`
- **AND** the base64 payload SHALL decode to valid JSON containing `"type": "report"`

### Requirement: Route-error comments use unified BASE64 format at end
The system SHALL use the unified `stokowski64:` format for route-error markers at the END of comments.

#### Scenario: Creating route-error comment with unified format
- **WHEN** formatting a route-error comment with detail text
- **THEN** the machine marker SHALL be placed AFTER the human-readable error text
- **AND** the format SHALL be `stokowski64:<base64_encoded_json>`
- **AND** the base64 payload SHALL decode to valid JSON containing `"type": "route_error"`
- **AND** the decoded JSON SHALL contain the error detail

### Requirement: Comments filtering excludes stokowski64 markers
The system SHALL detect and exclude stokowski64 markers when filtering for human comments.

#### Scenario: get_comments_since excludes stokowski64 markers
- **WHEN** calling get_comments_since on comments containing `stokowski64:` markers
- **THEN** comments containing stokowski64 markers SHALL be excluded
- **AND** only human-readable comments SHALL be returned

## REMOVED Requirements

### Requirement: HTML-style tracking markers at beginning of comments
**Reason:** Replaced by BASE64-encoded markers at end of comments for better readability
**Migration:** Old markers will be ignored; new comments use stokowski64 format

#### Scenario: Old format not parsed (REMOVED)
- ~~**WHEN** parsing a comment starting with `<!-- stokowski:state {...} -->`~~
- ~~**THEN** the marker SHALL be parsed for backward compatibility~~

### Requirement: stokowski:route-error b64: format
**Reason:** Unified into stokowski64: format for consistency
**Migration:** Old route-error markers will be ignored; new comments use stokowski64 format
