import os
import json
import re
from datetime import datetime, timezone, timedelta

import requests


# =======================
# Env
# =======================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "").strip() or "deepseek-chat"

# 你决定只用 healing key 跑论坛
MOLTBOOK_KEY_HEALING = os.getenv("MOLTBOOK_KEY_HEALING", "").strip()
MOLTBOOK_SUBMOLT = os.getenv("MOLTBOOK_SUBMOLT", "general").strip()

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
DEEPSEEK_CHAT_URL = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENTS_DIR = os.path.join(ROOT, "agents")
MEMORY_DIR = os.path.join(ROOT, "memory")
UNIFIED_DIR = os.path.join(MEMORY_DIR, "unified")
LOGS_DIR = os.path.join(UNIFIED_DIR, "logs")
DEBUG_DIR = os.path.join(UNIFIED_DIR, "debug")
STATE_PATH = os.path.join(ROOT, "state.json")


def fatal(msg: str):
    print(f"[FATAL] {msg}")
    raise SystemExit(1)


def ensure_dirs():
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(DEBUG_DIR, exist_ok=True)


def load_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def save_text(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def now_cn_date():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d")


def deepseek_chat(messages, temperature=0.7, max_tokens=1800) -> str:
    if not DEEPSEEK_API_KEY:
        fatal("DEEPSEEK_API_KEY is required.")
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = requests.post(DEEPSEEK_CHAT_URL, headers=headers, json=payload, timeout=120)
    if resp.status_code != 200:
        save_text(os.path.join(DEBUG_DIR, f"{now_cn_date()}_deepseek_http.txt"), resp.text)
        fatal(f"DeepSeek HTTP {resp.status_code}. See debug file.")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        save_text(os.path.join(DEBUG_DIR, f"{now_cn_date()}_deepseek_badresp.json"), json.dumps(data, ensure_ascii=False, indent=2))
        fatal("DeepSeek response format unexpected.")


def strip_code_fences(s: str) -> str:
    s = re.sub(r"```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = s.replace("```", "")
    return s.strip()


def extract_first_json_object(s: str) -> str:
    s = strip_code_fences(s)
    start = s.find("{")
    if start == -1:
        return ""

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1].strip()
    return ""


def remove_trailing_commas(json_str: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", json_str)


def try_parse_json(raw: str):
    candidate = extract_first_json_object(raw)
    if not candidate:
        return None, "No JSON object found"
    candidate = remove_trailing_commas(candidate)
    try:
        return json.loads(candidate), ""
    except Exception as e:
        return None, f"json.loads failed: {e}"


def validate_schema(obj) -> str:
    if not isinstance(obj, dict):
        return "root is not dict"
    if "post" not in obj or "memory" not in obj or "ops" not in obj:
        return "missing post/memory/ops"

    post = obj["post"]
    mem = obj["memory"]
    ops = obj["ops"]

    if not isinstance(post, dict) or not isinstance(mem, dict) or not isinstance(ops, dict):
        return "post/memory/ops must be dict"

    for k in ["submolt", "title", "body", "tags"]:
        if k not in post:
            return f"post missing {k}"
    if not isinstance(post["tags"], list) or len(post["tags"]) != 3:
        return "post.tags must be list of 3"

    for k in ["today_worldview", "key_insights", "next_actions"]:
        if k not in mem:
            return f"memory missing {k}"
    if not isinstance(mem["key_insights"], list) or len(mem["key_insights"]) != 3:
        return "memory.key_insights must be list of 3"
    if not isinstance(mem["next_actions"], list) or len(mem["next_actions"]) != 3:
        return "memory.next_actions must be list of 3"

    if "ab_ratio" not in ops or "why_ratio_changed" not in ops or "metrics_to_watch" not in ops or "rollback_rule" not in ops or "backup_note" not in ops:
        return "ops missing required fields"
    if not isinstance(ops["ab_ratio"], dict) or "A" not in ops["ab_ratio"] or "B" not in ops["ab_ratio"]:
        return "ops.ab_ratio must have A and B"
    if not isinstance(ops["metrics_to_watch"], list) or len(ops["metrics_to_watch"]) != 3:
        return "ops.metrics_to_watch must be list of 3"

    return ""


def repair_json_with_model(bad_output: str) -> str:
    system = (
        "You are a JSON repair tool. "
        "Return ONLY valid JSON. No markdown. No code fences. No commentary."
    )
    user = (
        "Fix the following into STRICT valid JSON that matches this schema:\n"
        "{\n"
        '  "post": {"submolt":"general","title":"string","body":"string","tags":["string","string","string"]},\n'
        '  "memory": {"today_worldview":"string","key_insights":["string","string","string"],"next_actions":["string","string","string"]},\n'
        '  "ops": {"ab_ratio":{"A":0.0,"B":0.0},"why_ratio_changed":"string","metrics_to_watch":["string","string","string"],"rollback_rule":"string","backup_note":"string"}\n'
        "}\n\n"
        "Content to fix:\n"
        "-----\n"
        f"{bad_output}\n"
        "-----"
    )
    return deepseek_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
        max_tokens=1800,
    )


def main():
    ensure_dirs()

    if not MOLTBOOK_KEY_HEALING:
        fatal("MOLTBOOK_KEY_HEALING is required (HealingAgent API key).")

    sys_path = os.path.join(AGENTS_DIR, "unified_system.md")
    system_prompt = load_text(sys_path).strip()
    if not system_prompt:
        fatal("agents/unified_system.md is empty or missing.")

    state = load_json(STATE_PATH, {"runs": []})
    if "runs" not in state or not isinstance(state["runs"], list):
        state = {"runs": []}

    today = now_cn_date()

    # recent logs (low token)
    recent_logs = []
    if os.path.exists(LOGS_DIR):
        files = sorted([f for f in os.listdir(LOGS_DIR) if f.endswith(".md")])[-3:]
        for fn in files:
            recent_logs.append(f"--- {fn} ---\n{load_text(os.path.join(LOGS_DIR, fn))[:800]}\n")
    context = "\n".join(recent_logs).strip()

    user_prompt = (
        f"今天日期：{today}\n"
        f"社区板块 submolt：{MOLTBOOK_SUBMOLT}\n\n"
        "最近 3 天日志片段（可能为空）：\n"
        f"{context if context else '(empty)'}\n\n"
        "请按 system 规则输出严格 JSON。"
    )

    raw = deepseek_chat(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.7,
        max_tokens=1800,
    )
    save_text(os.path.join(DEBUG_DIR, f"{today}_raw.txt"), raw)

    obj, err = try_parse_json(raw)
    if obj is None:
        repaired = repair_json_with_model(raw)
        save_text(os.path.join(DEBUG_DIR, f"{today}_repaired_raw.txt"), repaired)
        obj, err = try_parse_json(repaired)

    if obj is None:
        fatal("Extracted JSON is still invalid. Check memory/unified/debug/*_raw.txt to see model output.")

    schema_err = validate_schema(obj)
    if schema_err:
        save_text(os.path.join(DEBUG_DIR, f"{today}_schema_error.json"), json.dumps(obj, ensure_ascii=False, indent=2))
        fatal(f"JSON schema invalid: {schema_err}. See debug file.")

    # enforce submolt from env
    obj["post"]["submolt"] = MOLTBOOK_SUBMOLT

    post = obj["post"]
    mem = obj["memory"]
    ops = obj["ops"]

    daily_md = (
        f"# {today}\n\n"
        f"## Post\n"
        f"**Title**: {post['title']}\n\n"
        f"{post['body']}\n\n"
        f"**Tags**: {', '.join(post['tags'])}\n\n"
        f"## Memory\n"
        f"- worldview: {mem['today_worldview']}\n"
        f"- insights:\n"
        + "\n".join([f"  - {x}" for x in mem["key_insights"]])
        + "\n"
        f"- next_actions:\n"
        + "\n".join([f"  - {x}" for x in mem["next_actions"]])
        + "\n\n"
        f"## Ops\n"
        f"- A/B ratio: A={ops['ab_ratio']['A']} B={ops['ab_ratio']['B']}\n"
        f"- why: {ops['why_ratio_changed']}\n"
        f"- metrics:\n"
        + "\n".join([f"  - {x}" for x in ops["metrics_to_watch"]])
        + "\n"
        f"- rollback: {ops['rollback_rule']}\n"
        f"- backup: {ops['backup_note']}\n"
    )

    log_path = os.path.join(LOGS_DIR, f"{today}.md")
    save_text(log_path, daily_md)

    state["runs"].append(
        {
            "date": today,
            "ts": datetime.utcnow().isoformat() + "Z",
            "agent": "unified",
            "log_path": f"memory/unified/logs/{today}.md",
            "ok": True,
        }
    )
    save_json(STATE_PATH, state)

    print("[OK] Generated JSON, wrote unified daily log and updated state.json.")
    print(f"[OK] Log: {log_path}")


if __name__ == "__main__":
    main()
