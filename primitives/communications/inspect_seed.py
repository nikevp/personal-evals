"""Show the exact communication start state that an evaluation attempt will receive."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seed", type=Path, help="Path to a task-owned seed file")
    parser.add_argument("--json", action="store_true", help="Print normalized JSON")
    args = parser.parse_args()

    document = json.loads(args.seed.read_text(encoding="utf-8"))
    channel = document.get("channel")
    if channel not in {"sms", "email"}:
        raise SystemExit(f"Seed has unsupported channel: {channel!r}")

    if args.json:
        print(json.dumps(document, indent=2, ensure_ascii=False))
        return

    account = document["account"]
    print(
        f"{channel.upper()} account: {account['display_name']} <{account['address']}>"
    )
    print(f"Conversations: {len(document['conversations'])}")
    for conversation in document["conversations"]:
        contacts = ", ".join(
            f"{item['display_name']} <{item['address']}>"
            for item in conversation["participants"]
        )
        print(f"\n[{conversation['id']}] {conversation.get('subject', '(no subject)')}")
        print(f"With: {contacts}")
        for message in conversation["messages"]:
            sender = message["sender"]["display_name"]
            body = message["body"].replace("\n", "\n    ")
            print(f"  {message['sent_at']}  {message['direction']}  {sender}")
            print(f"    {body}")


if __name__ == "__main__":
    main()
