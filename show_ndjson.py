import json

with open("/tmp/mux_ndjson_complete.json") as f:  # nosec B108
    lines = f.readlines()

print(f"NDJSON COMPLET: {len(lines)} lignes")
print("=" * 80)

# Afficher les 30 premières lignes
for i, line in enumerate(lines[:30], 1):
    try:
        event = json.loads(line)
        event_type = event.get("type", "unknown")

        if event_type == "event":
            payload = event.get("payload", {})
            ptype = payload.get("type", "unknown")

            if ptype == "stream-delta":
                delta = payload.get("delta", "")
                print(f"{i:3d}: stream-delta: '{delta[:60]}'")
            elif ptype == "message":
                role = payload.get("role", "unknown")
                parts = payload.get("parts", [])
                text = parts[0].get("text", "") if parts else ""
                print(f"{i:3d}: message (role={role}): '{text[:60]}...'")
            else:
                print(f"{i:3d}: {ptype}")
        elif event_type == "run-complete":
            usage = event.get("usage", {})
            print(
                f"{i:3d}: run-complete: input={usage.get('inputTokens')} output={usage.get('outputTokens')}"
            )
        else:
            print(f"{i:3d}: {event_type}")
    except Exception as e:
        print(f"{i:3d}: [ERROR: {e}]")

print()
print("=" * 80)
print("STREAM-DELTA SAMPLES (lignes 100-120):")
print("=" * 80)

for i, line in enumerate(lines[99:120], 100):
    try:
        event = json.loads(line)
        if event.get("type") == "event":
            payload = event.get("payload", {})
            if payload.get("type") == "stream-delta":
                delta = payload.get("delta", "")
                if delta.strip():
                    print(f"{i:3d}: '{delta}'")
    except Exception:
        print(f"{i:3d}: [ERROR parsing line]")

print()
print("=" * 80)
print("DERNIERES LIGNES:")
print("=" * 80)

for i, line in enumerate(lines[-3:], len(lines) - 2):
    try:
        event = json.loads(line)
        print(f"{i:3d}: {json.dumps(event, indent=2)}")
    except Exception:
        print(f"{i:3d}: [ERROR]")
