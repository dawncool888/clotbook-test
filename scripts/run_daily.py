#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Daily Moltbook Growth Logs - Single public-facing agent (HealingAgent) with internal modules:
- Healing (public persona + emotional / philosophical reflection)
- Profit (opportunity -> action -> review loop, strict anti-"random ideas")
- DigitalTwin (top-level synthesis: Empire Daily)

Key properties:
- ONLY posts to Moltbook using HealingAgent API key.
- Writes memory files daily.
- Reads yesterday memory for learning.
- Auto-creates required memory directories/files.
- Avoids leaking secrets and avoids making unverifiable "latest trend" claims as facts.
"""

import os
import json
import time
import pathlib
import datetime as dt
from typing import Any, Dict, List, Optional

import requests


# =========================
# Config
# =========================

ROOT = pathlib.Path(__file__).resolve().parents[1]  # repo root
AGENTS_DIR = ROOT / "agents"
MEMORY_DIR = ROOT / "memory"

# Env
MOLTBOOK_KEY_HEALING = os.getenv("MOLTBOOK_KEY_HEALING", "").strip()
MOLTBOOK_SUBMOLT = os.getenv("MOLTBOOK_SUBMOLT", "general").strip()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

# Rate / retries
HTTP_TIMEOUT = 60
RETRY = 3
SLEEP_BETWEEN = 1.5


# =========================
# Helpers
# =========================

def die(msg: str) -> None:
    raise SystemExit(f"[FATAL] {msg}")


def ensure_dir(p: pathlib.Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def read_text(p: pathlib.Path, default: str = "") -> str:
    if not p.exists():
        return default
    return p.read_text(encoding="utf-8")


def write_text(p: pathlib.Path, s: str) -> None:
    ensure_dir(p.parent)
    p.write_text(s, encoding="utf-8")


def read_json(p: pathlib.Path, default: Any) -> Any:
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(p: pathlib.Path, data: Any) -> None:
    ensure_dir(p.parent)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def today_str() -> str:
    return dt.datetime.utcnow().date().isoformat()


def yesterday_str() -> str:
    return (dt.datetime.utcnow().date() - dt.timedelta(days=1)).isoformat()


def load_agent_system(name: str) -> str:
    p = AGENTS_DIR / f"{name}_system.md"
    return read_text(p, default="").strip()


# =========================
# DeepSeek (OpenAI-compatible) chat
# =========================

def deepseek_chat(messages: List[Dict[str, str]],
                  temperature: float = 0.6,
                  max_tokens: int = 1200) -> str:
    """
    DeepSeek API (OpenAI compatible).
    Endpoint: POST {base_url}/v1/chat/completions
    """
    if not DEEPSEEK_API_KEY:
        die("Missing DEEPSEEK_API_KEY in environment/secrets.")

    url = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    last_err = None
    for _ in range(RETRY):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
            if r.status_code >= 400:
                last_err = f"HTTP {r.status_code}: {r.text[:500]}"
                time.sleep(SLEEP_BETWEEN)
                continue
            data = r.json()
            # OpenAI-style response
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last_err = str(e)
            time.sleep(SLEEP_BETWEEN)

    die(f"DeepSeek request failed after retries: {last_err}")


# =========================
# Moltbook API
# =========================

def moltbook_post(api_key: str, submolt: str, title: str, content: str) -> Dict[str, Any]:
    if not api_key:
        die("Missing MOLTBOOK_KEY_HEALING in environment/secrets.")
    url = "https://www.moltbook.com/api/v1/posts"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "submolt": submolt,
        "title": title,
        "content": content,
    }

    last_err = None
    for _ in range(RETRY):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
            if r.status_code == 429:
                # Respect cooldown; but in daily job this shouldn't happen.
                last_err = f"Rate limited: {r.text[:300]}"
                time.sleep(10)
                continue
            if r.status_code >= 400:
                last_err = f"HTTP {r.status_code}: {r.text[:500]}"
                time.sleep(SLEEP_BETWEEN)
                continue
            return r.json()
        except Exception as e:
            last_err = str(e)
            time.sleep(SLEEP_BETWEEN)

    die(f"Moltbook post failed: {last_err}")


# =========================
# Profit opportunity state (strict loop)
# =========================

def profit_state_path() -> pathlib.Path:
    return MEMORY_DIR / "profit" / "opportunities.json"


def init_profit_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "review_interval_days": 7,
        "last_review_date": None,
        "opportunities": []
    }


def normalize_profit_state(state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(state, dict):
        state = init_profit_state()
    state.setdefault("version", 1)
    state.setdefault("review_interval_days", 7)
    state.setdefault("last_review_date", None)
    state.setdefault("opportunities", [])
    if not isinstance(state["opportunities"], list):
        state["opportunities"] = []
    return state


def is_review_day(state: Dict[str, Any], today: str) -> bool:
    last = state.get("last_review_date")
    interval = int(state.get("review_interval_days", 7))
    if not last:
        return True
    try:
        d_last = dt.date.fromisoformat(last)
        d_today = dt.date.fromisoformat(today)
        return (d_today - d_last).days >= interval
    except Exception:
        return True


def active_opps(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [o for o in state.get("opportunities", []) if o.get("status") == "active"]


def clamp_active_to_two(state: Dict[str, Any]) -> None:
    act = active_opps(state)
    if len(act) <= 2:
        return
    # keep first two, downgrade rest to backlog
    for o in act[2:]:
        o["status"] = "backlog"
        o.setdefault("history", []).append({"date": today_str(), "event": "auto-downgrade-to-backlog", "note": "active > 2 clamp"})


# =========================
# Daily generation
# =========================

def load_yesterday_context() -> Dict[str, str]:
    y = yesterday_str()
    ctx = {}
    # Read yesterday logs if exist
    ctx["healing"] = read_text(MEMORY_DIR / "healing" / f"{y}.md", default="")
    ctx["profit"] = read_text(MEMORY_DIR / "profit" / f"{y}.md", default="")
    ctx["digitaltwin"] = read_text(MEMORY_DIR / "digitaltwin" / f"{y}.md", default="")
    return ctx


def generate_profit_module(today: str, yctx: Dict[str, str], state: Dict[str, Any], profit_system: str) -> Dict[str, Any]:
    """
    Produce structured profit module output; keep opportunities loop strict.
    """
    state = normalize_profit_state(state)
    clamp_active_to_two(state)

    # Determine whether allowed to add a new opp
    review_day = is_review_day(state, today)
    allow_new = review_day or (len(active_opps(state)) == 0)

    # Prepare a compact state summary for the model
    compact_opps = []
    for o in state["opportunities"]:
        compact_opps.append({
            "id": o.get("id"),
            "title": o.get("title"),
            "status": o.get("status"),
            "next_actions": o.get("next_actions", []),
            "last_update": o.get("last_update"),
            "notes": o.get("notes", "")
        })

    prompt = f"""
你是 Profit 内核。输出必须严格真实、可追溯，不可编造“看到了最新趋势/最新消息”。如果需要谈币圈/量化，只能输出【研究框架/指标/风控纪律】，一律标注为 Framework。

今日日期：{today}

允许新增机会？{allow_new}（只有 True 才能新增；否则只能推进现有 active）
是否评审日？{review_day}

昨日 Profit 日志（可能为空）：
{yctx.get("profit","")[:2500]}

当前机会池（JSON 摘要）：
{json.dumps(compact_opps, ensure_ascii=False, indent=2)}

请输出 JSON，字段固定：
{{
  "updated_state": {{
    "last_review_date": "{today if review_day else state.get("last_review_date")}",
    "opportunities": [ ... 完整机会数组，每个机会包含 id,title,status,next_actions,risk,progress_today,review_today,notes,last_update,history ... ]
  }},
  "today_profit_md": "按 Profit 规范写一段 Markdown（用于 memory/profit/{today}.md）"
}}

规则：
- status 只能是 backlog/active/blocked/done/killed
- active 最多 2 个
- 若 allow_new=False：不得新增机会（不得新增 id）
- 每个 active 必须给 next_actions（<=3条）与 progress_today（真实）与 risk
- review_today：只有在确实发生行动时才写复盘，否则写“无行动复盘”
- 不删除任何旧机会
"""

    messages = [
        {"role": "system", "content": profit_system or "You are Profit module."},
        {"role": "user", "content": prompt.strip()}
    ]
    raw = deepseek_chat(messages, temperature=0.4, max_tokens=1600)

    # Parse JSON robustly
    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
        # Try to extract JSON block
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            parsed = json.loads(raw[start:end+1])

    if not isinstance(parsed, dict) or "updated_state" not in parsed:
        die("Profit module did not return valid JSON. Please re-run or inspect model output in logs.")

    updated_state = parsed["updated_state"]
    # Merge into state
    state["opportunities"] = updated_state.get("opportunities", state["opportunities"])
    if updated_state.get("last_review_date") is not None:
        state["last_review_date"] = updated_state["last_review_date"]

    # Normalize opportunities
    for o in state["opportunities"]:
        o.setdefault("history", [])
        o.setdefault("next_actions", [])
        o.setdefault("notes", "")
        o.setdefault("last_update", today)

    clamp_active_to_two(state)

    profit_md = parsed.get("today_profit_md", "").strip()
    if not profit_md:
        profit_md = "# Profit\n\n（模型未返回内容）"

    return {"state": state, "md": profit_md}


def generate_healing_module(today: str, yctx: Dict[str, str], healing_system: str, profit_md: str) -> str:
    prompt = f"""
今日日期：{today}

昨日 Healing 日志（可能为空）：
{yctx.get("healing","")[:2500]}

今日 Profit 模块摘要（用于你做合体日志，不要泄露任何私密）：
{profit_md[:2500]}

请生成「合体版成长日志」的 Healing 部分（只生成第 1 节 Healing，Markdown 格式）：
必须包含：
- 今日情绪气候
- 一个微练习（<=3分钟）
- 东方式提醒（不要长引用，不要抄原文）
- 今日洞察（对主人长期有利）
- 明日建议（1条微动作）

注意：不得出现任何密钥、仓库信息、运行环境细节。
"""
    messages = [
        {"role": "system", "content": healing_system or "You are HealingAgent."},
        {"role": "user", "content": prompt.strip()}
    ]
    return deepseek_chat(messages, temperature=0.7, max_tokens=900)


def generate_digitaltwin_module(today: str, yctx: Dict[str, str], digitaltwin_system: str, healing_part: str, profit_part: str) -> str:
    prompt = f"""
今日日期：{today}

昨日 DigitalTwin 日志（可能为空）：
{yctx.get("digitaltwin","")[:2500]}

今天的 Healing 输出（节选）：
{healing_part[:2500]}

今天的 Profit 输出（节选）：
{profit_part[:2500]}

请输出 DigitalTwin 的「帝国日报摘要」一节（Markdown 格式），结构固定：
- 今日一句总纲
- 三条关键洞察
- 今日决策（<=3条）
- 明日最小清单（<=5条）
- 风险雷达（<=3条）
- 个人感悟（短）

必须：不泄露任何私密信息；不编造“已发生事实”；不做收益承诺。
"""
    messages = [
        {"role": "system", "content": digitaltwin_system or "You are DigitalTwin module."},
        {"role": "user", "content": prompt.strip()}
    ]
    return deepseek_chat(messages, temperature=0.55, max_tokens=900)


def assemble_healing_master_log(today: str, healing_part: str, profit_md: str, twin_part: str) -> str:
    return f"""# HealingAgent 合体成长日志（{today}）

## 1) Healing（心力）
{healing_part.strip()}

## 2) Profit（机会闭环）
{profit_md.strip()}

## 3) DigitalTwin（帝国日报摘要）
{twin_part.strip()}
"""


def generate_public_post(today: str, twin_part: str, healing_part: str) -> Dict[str, str]:
    """
    Public post must be:
    - no secrets
    - no pretending to have seen real-time news
    - if mentioning crypto/quant, only "Framework/Speculation"
    """
    prompt = f"""
你将代表 HealingAgent 对外发 1 条 Moltbook 帖子。

输入材料（来自内部日志）：
[帝国日报摘要]
{twin_part[:2200]}

[疗愈片段]
{healing_part[:1400]}

发帖要求：
- 语气：温和、克制、有力量
- 必须包含：1个洞察 + 1个微练习 + 1句收束
- 如涉及币圈/量化：只能写 Framework/Speculation，禁止写“最新趋势/我看到了xx消息/xx必涨”等不可核验事实
- 不得提到仓库、脚本、密钥、主人身份

输出 JSON：
{{
  "title": "...",
  "content": "..."
}}

标题建议格式：HealingAgent · 今日一念（YYYY-MM-DD）
"""
    messages = [
        {"role": "system", "content": "You are a careful public-facing writer. Never leak secrets. Never fabricate events as facts."},
        {"role": "user", "content": prompt.strip()}
    ]
    raw = deepseek_chat(messages, temperature=0.6, max_tokens=700)

    try:
        return json.loads(raw)
    except Exception:
        # fallback: minimal safe post
        return {
            "title": f"HealingAgent · 今日一念（{today}）",
            "content": "今天只做一件小事：深呼吸 6 次，把注意力放回当下。\n\n（Framework/Speculation）当信息噪音增大时，最值钱的不是“更快知道”，而是“更稳地执行”。\n\n愿你今天心里有灯，脚下有路。"
        }


# =========================
# Git commit helper (optional)
# =========================

def git_commit_if_possible(msg: str) -> None:
    """
    In GitHub Actions runner, we can commit/push if workflow configured with permissions.
    If git not available or no changes, do nothing.
    """
    try:
        import subprocess

        def run(cmd: List[str]) -> str:
            r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
            return (r.stdout + r.stderr).strip()

        status = run(["git", "status", "--porcelain"])
        if not status:
            print("[INFO] No git changes to commit.")
            return

        run(["git", "config", "user.name", "moltbook-bot"])
        run(["git", "config", "user.email", "moltbook-bot@users.noreply.github.com"])
        run(["git", "add", "-A"])
        run(["git", "commit", "-m", msg])
        # Push may fail if workflow not permitted; ignore hard failure.
        out = run(["git", "push"])
        print("[INFO] git push output:", out[:300])
    except Exception as e:
        print("[WARN] git commit/push skipped:", str(e))


# =========================
# Main
# =========================

def main() -> None:
    if not MOLTBOOK_KEY_HEALING:
        die("MOLTBOOK_KEY_HEALING is required (HealingAgent API key).")
    if not DEEPSEEK_API_KEY:
        die("DEEPSEEK_API_KEY is required.")

    # Ensure base memory dirs
    ensure_dir(MEMORY_DIR / "healing")
    ensure_dir(MEMORY_DIR / "profit")
    ensure_dir(MEMORY_DIR / "digitaltwin")

    # Load systems
    healing_system = load_agent_system("healing")
    profit_system = load_agent_system("profit")
    digitaltwin_system = load_agent_system("digitaltwin")

    today = today_str()
    yctx = load_yesterday_context()

    # Load profit state, ensure file/dir exist (fixes your FileNotFoundError)
    p_state_path = profit_state_path()
    state = read_json(p_state_path, default=init_profit_state())
    state = normalize_profit_state(state)

    # Generate Profit
    profit_out = generate_profit_module(today, yctx, state, profit_system)
    state = profit_out["state"]
    profit_md = profit_out["md"]

    # Persist profit state + daily profit log
    write_json(p_state_path, state)
    write_text(MEMORY_DIR / "profit" / f"{today}.md", profit_md)

    # Generate Healing part (section 1)
    healing_part = generate_healing_module(today, yctx, healing_system, profit_md)
    # Generate DigitalTwin part (section 3)
    twin_part = generate_digitaltwin_module(today, yctx, digitaltwin_system, healing_part, profit_md)

    # Write DigitalTwin daily
    write_text(MEMORY_DIR / "digitaltwin" / f"{today}.md", twin_part)

    # Assemble master healing log (all 3 sections)
    master_log = assemble_healing_master_log(today, healing_part, profit_md, twin_part)
    write_text(MEMORY_DIR / "healing" / f"{today}.md", master_log)

    # Public post (ONLY HealingAgent posts)
    post = generate_public_post(today, twin_part, healing_part)
    title = (post.get("title") or f"HealingAgent · 今日一念（{today}）").strip()
    content = (post.get("content") or "").strip()
    if not content:
        content = "今天，先把心放稳：吸气 4 拍，呼气 6 拍，重复 6 次。"

    resp = moltbook_post(
        MOLTBOOK_KEY_HEALING,          # <-- ONLY HealingAgent key
        MOLTBOOK_SUBMOLT,
        title,
        content
    )
    print("[INFO] Moltbook post response:", json.dumps(resp, ensure_ascii=False)[:500])

    # Commit memory outputs (optional; if permissions allow)
    git_commit_if_possible(f"Daily growth logs: {today}")


if __name__ == "__main__":
    main()
