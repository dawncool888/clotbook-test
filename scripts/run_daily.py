import os
import json
import time
import requests
from datetime import datetime, timezone

# ---------- Config ----------
MOLTBOOK_BASE = "https://www.moltbook.com/api/v1"
SUBMOLT = os.getenv("MOLTBOOK_SUBMOLT", "general")
STATE_PATH = "state.json"

# DeepSeek (OpenAI-compatible) env vars
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()

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
    return requests.get(
        f"{MOLTBOOK_BASE}{path}",
        headers={"Authorization": f"Bearer {api_key}"},
        params=params,
        timeout=30,
    )

def molt_post(path, api_key, payload):
    return requests.post(
        f"{MOLTBOOK_BASE}{path}",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )

def is_claimed(api_key):
    r = molt_get("/agents/status", api_key)
    if r.status_code != 200:
        return False, f"status_check_http_{r.status_code}: {r.text[:200]}"
    data = r.json()
    return (data.get("status") == "claimed"), data.get("status")

def fetch_feed(api_key):
    r = molt_get("/posts", api_key, params={"sort": "new", "limit": 15})
    if r.status_code != 200:
        return ""
    data = r.json()
    posts = data.get("data") or data.get("posts") or data.get("results") or []
    if isinstance(data, list):
        posts = data

    lines = []
    for p in posts[:15]:
        title = p.get("title", "")
        content = (p.get("content") or "")[:360]
        author = (p.get("author") or {}).get("name", "")
        submolt = (p.get("submolt") or {}).get("name", p.get("submolt", ""))
        lines.append(f"- [{submolt}] {title} (by {author}) :: {content}".strip())
    return "\n".join(lines)

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

def deepseek_chat(system_prompt, user_prompt):
    """
    DeepSeek OpenAI-compatible endpoint:
    POST {base}/v1/chat/completions
    """
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("Missing DEEPSEEK_API_KEY")

    url = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.8,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=90)
    r.raise_for_status()
    j = r.json()
    return j["choices"][0]["message"]["content"].strip()

# ---------- Main ----------
def main():
    state = load_state()
    day = int(state.get("day", 1))
    now = datetime.now(timezone.utc).isoformat()

    # get feed context using any available key
    feed_context = ""
    for a in AGENTS:
        if a["api_key"]:
            feed_context = fetch_feed(a["api_key"])
            break

    any_posted = False
    for a in AGENTS:
        if not a["api_key"]:
            print(f"[{a['name']}] Missing Moltbook API key; skipping.")
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

        content = deepseek_chat(system_prompt, user_prompt)

        payload = {"submolt": SUBMOLT, "title": title, "content": content}
        r = molt_post("/posts", a["api_key"], payload)

        if r.status_code == 200:
            print(f"[{a['name']}] Posted: {title}")
            any_posted = True
        else:
            print(f"[{a['name']}] Failed to post ({r.status_code}): {r.text[:300]}")

        time.sleep(3)

    if any_posted:
        state["day"] = day + 1
        save_state(state)
        print(f"Advanced day counter to {state['day']}.")
    else:
        print("No posts made; day counter unchanged.")

if __name__ == "__main__":
    main()
