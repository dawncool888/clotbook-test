import os
import json
import time
import requests
from datetime import datetime, timezone

# ---------- Config ----------
MOLTBOOK_BASE = "https://www.moltbook.com/api/v1"
SUBMOLT = os.getenv("MOLTBOOK_SUBMOLT", "general")  # you can change to your own submolt later
STATE_PATH = "state.json"

# OpenAI (or compatible) env vars
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()  # choose your model

AGENTS = [
    {
        "name": "HealingAgent",
        "api_key": os.getenv("MOLTBOOK_API_KEY_HEALING", "").strip(),
        "prompt_path": "agents/healing_system.md",
        "title_tpl": "Daily Healing Reflection — Day {day}",
    },
    {
        "name": "DigitalTwinAgent",
        "api_key": os.getenv("MOLTBOOK_API_KEY_DIGITALTWIN", "").strip(),
        "prompt_path": "agents/digitaltwin_system.md",
        "title_tpl": "Daily Systems Reflection — Day {day}",
    },
    {
        "name": "ProfitAgent",
        "api_key": os.getenv("MOLTBOOK_API_KEY_PROFIT", "").strip(),
        "prompt_path": "agents/profit_system.md",
        "title_tpl": "Daily Opportunity Log — Day {day}",
    },
]

# ---------- Helpers ----------
def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"day": 1}

def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def molt_get(path, api_key, params=None):
    r = requests.get(
        f"{MOLTBOOK_BASE}{path}",
        headers={"Authorization": f"Bearer {api_key}"},
        params=params,
        timeout=30,
    )
    return r

def molt_post(path, api_key, payload):
    r = requests.post(
        f"{MOLTBOOK_BASE}{path}",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    return r

def is_claimed(api_key):
    r = molt_get("/agents/status", api_key)
    if r.status_code != 200:
        return False, f"status_check_http_{r.status_code}: {r.text[:200]}"
    data = r.json()
    return (data.get("status") == "claimed"), data.get("status")

def fetch_feed(api_key):
    # Use global posts feed. You can also use /feed once you subscribe/follow.
    r = molt_get("/posts", api_key, params={"sort": "new", "limit": 15})
    if r.status_code != 200:
        return []
    data = r.json()
    # Moltbook response usually wraps data; be defensive:
    posts = data.get("data") or data.get("posts") or data.get("results") or []
    # If API returns raw list:
    if isinstance(data, list):
        posts = data
    # Normalize into a small context string:
    lines = []
    for p in posts[:15]:
        title = p.get("title", "")
        content = (p.get("content") or "")[:400]
        author = (p.get("author") or {}).get("name", "")
        submolt = (p.get("submolt") or {}).get("name", p.get("submolt", ""))
        lines.append(f"- [{submolt}] {title} (by {author}) :: {content}".strip())
    return "\n".join(lines)

def openai_chat(system_prompt, user_prompt):
    # Minimal OpenAI Chat Completions call (works with many compatible endpoints if adjusted).
    url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions").strip()
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.8,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    j = r.json()
    return j["choices"][0]["message"]["content"].strip()

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

# ---------- Main ----------
def main():
    if not OPENAI_API_KEY:
        raise RuntimeError("Missing OPENAI_API_KEY")
    state = load_state()
    day = int(state.get("day", 1))

    # Use the first agent's key to fetch feed context (any claimed key works; if none claimed, feed still fetchable but posting won't)
    feed_context = None
    for a in AGENTS:
        if a["api_key"]:
            feed_context = fetch_feed(a["api_key"])
            break
    if feed_context is None:
        feed_context = ""

    now = datetime.now(timezone.utc).isoformat()

    any_posted = False
    for idx, a in enumerate(AGENTS):
        if not a["api_key"]:
            print(f"[{a['name']}] Missing API key env var; skipping.")
            continue

        claimed, status = is_claimed(a["api_key"])
        if not claimed:
            print(f"[{a['name']}] Not claimed yet (status={status}); skipping post.")
            continue

        sys_prompt_tpl = read_file(a["prompt_path"])
        system_prompt = sys_prompt_tpl.replace("{day}", str(day))

        title = a["title_tpl"].format(day=day)

        user_prompt = f"""Today is {now} (UTC).
Here are recent Moltbook posts (new):
{feed_context}

Task:
- Write today's public daily growth log in the required format.
- Keep it high-signal and non-repetitive.
- Do NOT include any private keys or sensitive data.
"""

        content = openai_chat(system_prompt, user_prompt)

        payload = {"submolt": SUBMOLT, "title": title, "content": content}
        r = molt_post("/posts", a["api_key"], payload)

        if r.status_code == 200:
            print(f"[{a['name']}] Posted: {title}")
            any_posted = True
        else:
            print(f"[{a['name']}] Failed to post ({r.status_code}): {r.text[:300]}")

        # avoid bursts; also respects API + keeps logs readable
        time.sleep(3)

    # Advance day only if at least one agent posted
    if any_posted:
        state["day"] = day + 1
        save_state(state)
        print(f"Advanced day counter to {state['day']}.")
    else:
        print("No posts made; day counter unchanged.")

if __name__ == "__main__":
    main()
