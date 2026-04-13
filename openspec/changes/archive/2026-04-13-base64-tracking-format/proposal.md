## Why

The current machine-readable tracking markers (`stokowski:state`, `stokowski:gate`, `stokowski:report`, `stokowski:route-error`) use HTML-style comments at the BEGINNING of comments, making them visually noisy and reducing readability for humans reviewing Linear issues. Encoding these markers as BASE64 and placing them at the END of comments will significantly improve the user experience while preserving machine-parseability.

## What Changes

- **BREAKING**: Change tracking marker format from `<!-- stokowski:<type> {json} -->` at comment start to `stokowski64:<base64>` at comment end
- **BREAKING**: Update `stokowski:route-error` from `<!-- stokowski:route-error b64:{payload} -->` to the new unified `stokowski64:` format
- Update `tracking.py`: Modify `make_state_comment()` and `make_gate_comment()` to use BASE64 encoding and append to end
- Update `reporting.py`: Modify `format_report_comment()` and `format_no_report_comment()` to use BASE64 encoding and append to end
- Update `agent_gate_route.py`: Modify `format_route_error_comment()` to use unified `stokowski64:` format at end
- Update `tracking.py` parsers: Modify `parse_latest_tracking()`, `parse_latest_gate_waiting()`, and related functions to decode BASE64 from end of comments
- Update `get_comments_since()`: Detect new `stokowski64:` format when filtering tracking comments
- Update all tests to reflect new format and ensure backward compatibility is NOT maintained (clean migration)

## Capabilities

### New Capabilities
- (none - this is a format change to existing capabilities)

### Modified Capabilities
- `state-machine-tracking`: Change marker format from HTML-style comments to BASE64-encoded `stokowski64:` markers placed at end of comments
- `gate-tracking`: Change marker format for gate status tracking to BASE64-encoded end-placed markers
- `report-tracking`: Change report marker format to BASE64-encoded end-placed markers
- `route-error-tracking`: Change route-error marker format to unified BASE64 end-placed markers

## Impact

- **stokowski/tracking.py**: Core tracking marker generation and parsing functions
- **stokowski/reporting.py**: Report comment formatting functions
- **stokowski/agent_gate_route.py**: Route error comment formatting
- **tests/**: All tracking-related tests need updating to new format
- **AGENTS.md**: Documentation needs update to reflect new marker format
- **docs/**: Any lifecycle template documentation needs updating
