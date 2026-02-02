import os
import json
import re
import sys
import datetime as dt
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]

AGENTS_DIR = ROOT / "agents"
MEM_DIR = ROOT / "memory"
UNIFIED_DIR = MEM_DIR / "unified"
UNIFIED_LOGS_DIR = UNIFIED_DIR / "logs"
PROFIT_DIR = MEM_DIR / "profit"

STATE_PATH = UNIFIED_DIR / "state.json"
LONGTERM_PATH = UNIFIED_DIR / "longterm.json"
OPPS_PATH = PROFIT_DIR / "opportunities.json"


def fatal(msg: str):
    print(f"[FATAL] {msg}", file=sys.stderr)
    sys.exit(1)


def ensure_dirs():
    UNIFIED_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PROFIT_DIR.mkdir(parents=True, exist_ok=True)


def read_text(path: Path, default: str = "") -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return default


def read_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def today_str_utc():
    return dt.datetime.utcnow().date().isoformat()


def yesterday_str_utc():
    return (dt.datetime.utcnow().date() - dt.timedelta(days=1)).isoformat()


def is_review_day(state: dict) -> bool:
    wd = dt.datetime.utcnow().strftime("%a")  # Mon Tue Wed Thu Fri Sat Sun
    target = (state.get("rules", {}) or {}).get("weekly_review_day", "Sun")
    return wd.lower().startswith(str(target).lower()[:3])


def redact_secrets(text: str) -> str:
    patterns = [
        r"moltbook_sk_[A-Za-z0-9_\-]+",
        r"sk-[A-Za-z0-9_\-]+",
        r"Bearer\s+[A-Za-z0-9_\-\.]+",
        r"DEEPSEEK_[A-Za-z0-9_\-]+",
    ]
    out = text
    for p in patterns:
        out = re.sub(p, "***REDACTED***", out)
    return out


def deepseek_chat(api_key: str, model: str, messages: list, temperature: float = 0.5) -> str:
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"DeepSeek API error {r.status_code}: {r.text[:500]}")
    data = r.json()
    return data["choices"][0]["message"]["content"]


def moltbook_post(moltbook_key: str, title: str, body: str) -> dict:
    """
    Best-effort. If it fails, we still write memory & commit.
    """
    url_candidates = [
        "https://www.moltbook.com/api/v1/posts",
        "https://www.moltbook.com/api/v1/posts/create",
        "https://www.moltbook.com/api/v1/post",
    ]
    headers = {"Authorization": f"Bearer {moltbook_key}", "Content-Type": "application/json"}
    payload_candidates = [
        {"title": title, "body": body},
        {"title": title, "content": body},
        {"text": f"# {title}\n\n{body}"},
    ]

    last_err = None
    for url in url_candidates:
        for payload in payload_candidates:
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
                if 200 <= resp.status_code < 300:
                    try:
                        return {"ok": True, "url": url, "response": resp.json()}
                    except Exception:
                        return {"ok": True, "url": url, "response_text": resp.text[:500]}
                last_err = f"{url} -> {resp.status_code}: {resp.text[:300]}"
            except Exception as e:
                last_err = f"{url} -> exception: {str(e)}"
    return {"ok": False, "error": last_err or "unknown"}


def main():
    ensure_dirs()

    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"
    if not deepseek_key:
        fatal("DEEPSEEK_API_KEY is required.")

    moltbook_key_healing = os.getenv("MOLTBOOK_KEY_HEALING", "").strip()
    if not moltbook_key_healing:
        fatal("MOLTBOOK_KEY_HEALING is required (HealingAgent Moltbook key).")

    system_unified = read_text(AGENTS_DIR / "unified_system.md", "")
    if not system_unified:
        fatal("agents/unified_system.md is missing or empty.")

    state = read_json(STATE_PATH, default={
        "ab_ratio": {"A_profit": 0.7, "B_empire": 0.3},
        "last_run_date": None,
        "last_7d_signal": {"progress_score": 0, "notes": ""},
        "rules": {"max_daily_budget_usd": 100, "weekly_review_day": "Sun", "allow_new_opportunities_only_on_review_day": True}
    })
    longterm = read_json(LONGTERM_PATH, default={"north_star": "", "principles": [], "playbooks": [], "glossary": {}})
    opps = read_json(OPPS_PATH, default={"last_review_date": None, "opportunities": []})

    today = today_str_utc()
    yday = yesterday_str_utc()

    yday_log_path = UNIFIED_LOGS_DIR / f"{yday}.md"
    yday_log = read_text(yday_log_path, "")

    review_day = is_review_day(state)
    allow_new_rule = (state.get("rules", {}) or {}).get("allow_new_opportunities_only_on_review_day", True)
    allow_new_today = bool(review_day) if allow_new_rule else True

    compact_opps = []
    for o in (opps.get("opportunities") or []):
        compact_opps.append({
            "id": o.get("id"),
            "title": o.get("title"),
            "status": o.get("status"),
            "next_actions": o.get("next_actions"),
            "progress": o.get("progress"),
            "risk": o.get("risk"),
            "budget_usd": o.get("budget_usd"),
            "metrics": o.get("metrics"),
            "evidence": o.get("evidence"),
            "updated_at": o.get("updated_at"),
        })

    user_context = {
        "today": today,
        "review_day": review_day,
        "allow_new": allow_new_today,
        "state": state,
        "longterm": longterm,
        "yesterday_log_excerpt": yday_log[:4000],
        "opportunities_compact": compact_opps[:30],
        "constraints": {
            "max_daily_budget_usd": (state.get("rules", {}) or {}).get("max_daily_budget_usd", 100),
            "no_private_leak": True,
            "no_fake_to_owner": True
        }
    }

    prompt = f"""
你将基于以下上下文运行今天的 UnifiedAgent 日报与更新。

上下文(JSON)：
{json.dumps(user_context, ensure_ascii=False, indent=2)}

要求：
- 你必须返回严格 JSON（不要外层 markdown，不要 ```）。
- private_log_md：写给主人，必须真实、可追溯、可执行，不编造事实。
- public_post：用于社区发帖（用 HealingAgent 发），允许观点/框架/学习，但不得伪造“真实交易收益/主人真实经历”。
- updated_state：可调整 A/B 比例与规则，但要把理由写在 private_log_md。
- profit_update：输出 opportunities.json 的新内容（完整结构）；非 review day 默认不新增机会，只推进 active next_actions。
"""

    messages = [
        {"role": "system", "content": system_unified},
        {"role": "user", "content": prompt}
    ]

    try:
        content = deepseek_chat(deepseek_key, deepseek_model, messages, temperature=0.5)
    except Exception as e:
        fatal(f"DeepSeek call failed: {str(e)}")

    try:
        result = json.loads(content)
    except Exception:
        m = re.search(r"\{.*\}\s*$", content, re.S)
        if not m:
            fatal("Model output is not valid JSON and no JSON object could be extracted.")
        try:
            result = json.loads(m.group(0))
        except Exception:
            fatal("Extracted JSON is still invalid.")

    public_post = result.get("public_post", {}) or {}
    private_log_md = result.get("private_log_md", "") or ""
    updated_state = result.get("updated_state", None)
    profit_update = result.get("profit_update", None)

    private_log_md = redact_secrets(private_log_md)
    public_title = redact_secrets(str(public_post.get("title", ""))[:120])
    public_body = redact_secrets(str(public_post.get("body", ""))[:4000])

    # Save private log
    log_path = UNIFIED_LOGS_DIR / f"{today}.md"
    write_text(log_path, private_log_md)

    # Save state
    if isinstance(updated_state, dict):
        updated_state["last_run_date"] = today
        write_json(STATE_PATH, updated_state)
    else:
        state["last_run_date"] = today
        write_json(STATE_PATH, state)

    # Save opportunities
    if isinstance(profit_update, dict) and "opportunities" in profit_update:
        if "last_review_date" not in profit_update:
            profit_update["last_review_date"] = opps.get("last_review_date")
        write_json(OPPS_PATH, profit_update)
    else:
        write_json(OPPS_PATH, opps)

    # Post to Moltbook (best-effort)
    post_enabled = bool(public_post.get("enabled", True))
    post_result = {"skipped": True}
    if post_enabled and public_title and public_body:
        post_result = moltbook_post(moltbook_key_healing, public_title, public_body)

    print("[OK] Daily run completed.")
    print(f"[INFO] Private log written: {log_path.as_posix()}")
    print(f"[INFO] State written: {STATE_PATH.as_posix()}")
    print(f"[INFO] Opportunities written: {OPPS_PATH.as_posix()}")
    print(f"[INFO] Moltbook post: {json.dumps(post_result, ensure_ascii=False)[:500]}")


if __name__ == "__main__":
    main()
