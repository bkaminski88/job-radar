"""
Two-step smoke test for the Discord bot setup, run from the command line.

Step 1 — post a test message and add reactions:
    python smoke_test.py post

Then go react to that message in Discord with 👍 yourself.

Step 2 — check whether your reaction was picked up:
    python smoke_test.py check

Requires env vars: DISCORD_BOT_TOKEN, DISCORD_WEBHOOK_URL, DISCORD_USER_ID
(same ones the real pipeline uses).

State is saved to smoke_test_state.json between steps so you don't have to
copy-paste message/channel IDs by hand.
"""
import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()  # reads .env in the current directory into os.environ

REQUIRED_VARS = ["DISCORD_BOT_TOKEN", "DISCORD_WEBHOOK_URL", "DISCORD_USER_ID"]
missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
if missing:
    raise SystemExit(
        f"Missing or empty env var(s): {', '.join(missing)}\n"
        f"Check that your .env file (in this same folder) has these set, "
        f"with no extra quotes/spaces, and that it was saved without a BOM "
        f"(the PowerShell -Encoding utf8 gotcha from Stage 2)."
    )

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
DISCORD_USER_ID = os.environ["DISCORD_USER_ID"]

STATE_FILE = "smoke_test_state.json"
THUMBS_UP = "👍"
THUMBS_DOWN = "👎"

BOT_HEADERS = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}


def verify_bot_token() -> None:
    r = requests.get("https://discord.com/api/v10/users/@me", headers=BOT_HEADERS, timeout=15)
    if r.status_code != 200:
        raise SystemExit(
            f"Bot token check failed ({r.status_code}): {r.text}\n"
            f"Double check DISCORD_BOT_TOKEN is the Bot token, not the app's "
            f"client secret or the webhook URL."
        )
    bot_user = r.json()
    print(f"[ok] Bot token valid — logged in as {bot_user['username']}")


def get_webhook_channel_id() -> str:
    r = requests.get(DISCORD_WEBHOOK_URL, timeout=15)
    if r.status_code != 200:
        raise SystemExit(f"Could not read webhook info ({r.status_code}): {r.text}")
    channel_id = r.json()["channel_id"]
    print(f"[ok] Webhook posts to channel_id={channel_id}")
    return channel_id


def verify_bot_can_see_channel(channel_id: str) -> None:
    url = f"https://discord.com/api/v10/channels/{channel_id}"
    r = requests.get(url, headers=BOT_HEADERS, timeout=15)
    if r.status_code != 200:
        raise SystemExit(
            f"Bot cannot see channel {channel_id} ({r.status_code}): {r.text}\n"
            f"This usually means the bot hasn't been invited to the server "
            f"that channel belongs to, or lacks View Channel permission."
        )
    print(f"[ok] Bot can see channel #{r.json().get('name', channel_id)}")


def post_test_message(channel_id: str) -> str:
    resp = requests.post(
        f"{DISCORD_WEBHOOK_URL}?wait=true",
        json={"content": "🔧 job-radar Stage 3 smoke test — react 👍 to this message, "
                          "then run `python smoke_test.py check`"},
        timeout=15,
    )
    resp.raise_for_status()
    message_id = resp.json()["id"]
    print(f"[ok] Posted test message, message_id={message_id}")
    return message_id


def add_reactions(channel_id: str, message_id: str) -> None:
    for emoji in (THUMBS_UP, THUMBS_DOWN):
        url = (f"https://discord.com/api/v10/channels/{channel_id}"
               f"/messages/{message_id}/reactions/{emoji}/@me")
        r = requests.put(url, headers=BOT_HEADERS, timeout=15)
        if r.status_code not in (200, 204):
            raise SystemExit(f"Failed to add reaction {emoji} ({r.status_code}): {r.text}")
        print(f"[ok] Bot added reaction {emoji}")


def check_user_reaction(channel_id: str, message_id: str, emoji: str) -> bool:
    url = (f"https://discord.com/api/v10/channels/{channel_id}"
           f"/messages/{message_id}/reactions/{emoji}")
    r = requests.get(url, headers=BOT_HEADERS, timeout=15)
    if r.status_code != 200:
        raise SystemExit(f"Reaction lookup failed ({r.status_code}): {r.text}")
    reactors = r.json()
    return any(str(u["id"]) == str(DISCORD_USER_ID) for u in reactors)


def run_post() -> None:
    verify_bot_token()
    channel_id = get_webhook_channel_id()
    verify_bot_can_see_channel(channel_id)
    message_id = post_test_message(channel_id)
    add_reactions(channel_id, message_id)

    with open(STATE_FILE, "w") as f:
        json.dump({"channel_id": channel_id, "message_id": message_id}, f)

    print("\nNow go react with 👍 on that message in Discord, "
          "then run: python smoke_test.py check")


def run_check() -> None:
    if not os.path.exists(STATE_FILE):
        raise SystemExit("No smoke_test_state.json found — run `python smoke_test.py post` first.")

    with open(STATE_FILE) as f:
        state = json.load(f)

    verify_bot_token()

    if check_user_reaction(state["channel_id"], state["message_id"], THUMBS_UP):
        print(f"[PASS] Detected your 👍 reaction (user_id={DISCORD_USER_ID}). "
              f"Bot setup is working end to end.")
    elif check_user_reaction(state["channel_id"], state["message_id"], THUMBS_DOWN):
        print(f"[PASS] Detected your 👎 reaction (user_id={DISCORD_USER_ID}). "
              f"Bot setup is working end to end.")
    else:
        print("[WAIT] No reaction from your user ID found yet. "
              "Make sure you reacted on the message, and that DISCORD_USER_ID "
              "matches the account you reacted with. Run check again after reacting.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("post", "check"):
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "post":
        run_post()
    else:
        run_check()
