## 1. Update tracking.py - Generation Functions

- [ ] 1.1 Modify `make_state_comment()` to output BASE64 marker at END of comment
- [ ] 1.2 Modify `make_gate_comment()` to output BASE64 marker at END of comment
- [ ] 1.3 Create helper function `_encode_stokowski64(data: dict) -> str` for consistent encoding

## 2. Update tracking.py - Parsing Functions

- [ ] 2.1 Modify `_iter_stokowski_marker_json()` to parse `stokowski64:` markers at end of comments
- [ ] 2.2 Create helper function `_decode_stokowski64(marker: str) -> dict | None` for consistent decoding
- [ ] 2.3 Update `_collect_tracking_entries()` to use new decoder
- [ ] 2.4 Update `_comment_body_is_stokowski_tracking()` to detect `stokowski64:` pattern

## 3. Update reporting.py

- [ ] 3.1 Modify `format_report_comment()` to output BASE64 marker at END of comment
- [ ] 3.2 Modify `format_no_report_comment()` to output BASE64 marker at END of comment
- [ ] 3.3 Update imports to use tracking helper if shared

## 4. Update agent_gate_route.py

- [ ] 4.1 Modify `format_route_error_comment()` to use unified `stokowski64:` format at END
- [ ] 4.2 Remove old `b64:` format in favor of unified format

## 5. Update Tests - tracking.py tests

- [ ] 5.1 Update `test_tracking_json_extraction.py` for new BASE64 format
- [ ] 5.2 Update `test_tracking_gate_waiting.py` for new BASE64 format
- [ ] 5.3 Update `test_parse_latest_tracking_timestamp.py` for new BASE64 format
- [ ] 5.4 Add test for backward compatibility rejection (old format ignored)

## 6. Update Tests - reporting and route tests

- [ ] 6.1 Update `test_reporting.py` for new BASE64 format
- [ ] 6.2 Update `test_agent_gate_route.py` for unified `stokowski64:` format

## 7. Update Documentation

- [ ] 7.1 Update `AGENTS.md` to reflect new `stokowski64:` marker format
- [ ] 7.2 Update `docs/lifecycle-template.md` if it references marker format
- [ ] 7.3 Update any other docs referencing tracking markers

## 8. Verification

- [ ] 8.1 Run all tests: `uv run pytest tests/ -v`
- [ ] 8.2 Verify no old-style markers remain in test expectations
- [ ] 8.3 Validate BASE64 encoding/decoding round-trip
