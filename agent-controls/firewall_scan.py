#!/usr/bin/env python3
"""Bounded stdin JSON scanner. No cloud/model calls; never logs scanned content."""
import argparse
import json
import sys

LIMIT = 1024 * 1024


def scan(text, profile="text"):
    from llamafirewall import LlamaFirewall, UserMessage, Role, ScannerType
    scanners = [ScannerType.REGEX, ScannerType.HIDDEN_ASCII]
    if profile == "code":
        scanners = [ScannerType.CODE_SHIELD]
    result = LlamaFirewall(scanners={Role.USER: scanners}).scan(UserMessage(text))
    # Reasons from scanners can include source text. Deliberately do not export them.
    return {"decision": result.decision.value, "status": result.status.value,
            "score": result.score, "profile": profile,
            "scanners": [item.value for item in scanners]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["text", "code"], default="text")
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("Input exceeds 1 MiB")
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("text"), str):
            raise ValueError("Expected JSON object with string text")
        result = scan(data["text"], args.profile)
        print(json.dumps(result))
        return 0 if result["status"] == "success" else 2
    except Exception as error:
        # Do not print exception text: third-party errors can contain scanned input.
        print(json.dumps({"decision": "error", "status": "error",
                          "error_type": type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
