import os
import json
import time
import requests
from datetime import datetime, timezone

MOLTBOOK_BASE = "https://www.moltbook.com/api/v1"
SUBMOLT = os.getenv("MOLTBOOK_SUBMOLT", "general")
STATE_PATH = "state.json"

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")

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

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "day": 1,
        "failures": {a["name"]: 0 for a in AGENTS},
        "dormant": {a["name"]: False for a in AGENTS},
    }

def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def deepseek_chat(system_prompt, user_prompt):
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
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
    return r.json()["choices"][0]["message"]["content"].strip()

def is_claimed(api_key):
    r = requests.get(
        f"{MOLTBOOK_BASE}/agents/status",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    return r.status_code == 200 and r.json().get("status") == "claimed"

def post(agent, title, content):
    return requests.post(
        f"{MOLTBOOK_BASE}/posts",
        headers={
            "Authorization": f"Bearer {agent['api_key']}",
            "Content-Type": "application/json",
        },
        json={"submolt": SUBMOLT, "title": title, "content": content},
        timeout=30,
    )

def main():
    state = load_state()
    day = state["day"]
    now = datetime.now(timezone.utc).isoformat()

    for agent in AGENTS:
        name = agent["name"]

        if state["dormant"].get(name):
            continue
        if not agent["api_key"] or not is_claimed(agent["api_key"]):
            continue

        system_prompt = open(agent["prompt_path"], encoding="utf-8").read().replace(
            "{day}", str(day)
        )

        user_prompt = f"Today is {now}. Write today's public daily log."

        try:
            content = deepseek_chat(system_prompt, user_prompt)
            r = post(agent, agent["title_tpl"].format(day=day), content)

            if r.status_code == 200:
                state["failures"][name] = 0
            else:
                state["failures"][name] += 1

        except Exception:
            state["failures"][name] += 1

        if state["failures"][name] >= 3:
            state["dormant"][name] = True

        time.sleep(3)

    state["day"] += 1
    save_state(state)

if __name__ == "__main__":
    main()
