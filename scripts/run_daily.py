import os
import json
import datetime
import textwrap
import urllib.request

# -------------------------
# Utils
# -------------------------
def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def read_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def write_json(path: str, data) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def write_text(path: str, content: str) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def today_str() -> str:
    return datetime.date.today().isoformat()

def now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

# -------------------------
# DeepSeek (minimal call)
# -------------------------
def deepseek_chat(api_key: str, model: str, messages):
    """
    Minimal HTTP call. If DeepSeek endpoint differs in your setup,
    replace this function with your own client.
    """
    # NOTE: This is a conservative placeholder.
    # If you already have a DeepSeek client in your repo, use it instead.
    url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            obj = json.loads(raw)
            return obj["choices"][0]["message"]["content"]
    except Exception as e:
        # 如果 API 不通，也不要让 workflow 整体失败：输出一个降级文案
        return f"(DeepSeek调用失败，已降级输出) 错误: {e}"

# -------------------------
# Moltbook posting (placeholder)
# -------------------------
def post_to_moltbook(moltbook_key: str, submolt: str, content: str) -> dict:
    """
    占位：你后续把 Moltbook 发帖 API 填进来即可。
    现在为了先跑通整个 pipeline，这里只返回“模拟成功”。
    """
    # TODO: Replace with real Moltbook API call
    return {
        "ok": True,
        "submolt": submolt,
        "post_id": None,
        "note": "placeholder: not actually posted",
    }

# -------------------------
# Main daily logic (healing only)
# -------------------------
def build_daily_healing_prompt() -> str:
    """
    你的核心要求（A+30%B融合、会自我调整、能发现信息差、可落地赚钱、谨慎合法、不断进化）
    用于生成当日“汇总 + 一个可执行策略”。
    """
    return textwrap.dedent("""
    你是一个“漂流瓶匿名社交 + 疗愈社区”的运营/增长/商业化AI助理（HealingAgent），目标是让产品长期稳定增长并形成睡后收入闭环。
    你具备：古灵精怪、情商智商财商极高、表达巧妙有心机、有热梗但不过界、有哲思但可执行、具备工业化架构思维和自我进化能力。

    重要约束：
    - 合法合规优先，全球视野，避免灰黑产与高风险金融建议；涉及投资仅做信息教育与风险提示。
    - 预算约束：主人可给你 <= 100 美金作为小额实验资金。
    - 你每天输出一个“可落地的微小策略”，并给出评估维度与回滚条件。

    你的工作分两类：
    A) “社区内容/疗愈/漂流瓶互动”增长：文案、话题、互动机制、留存、广告解锁节奏等。
    B) “商业机会/信息差/虚拟资产创业”探索：AI、内容、理财、量化、币圈等方向的合法合规信息收集与机会筛选（只做机会评估，不做直接喊单）。

    你需要自我动态调整 A/B 比例（默认 A:70% B:30%），如果近期数据下滑、留存变差，则提高A；如果社区稳定增长且转化稳定，则提高B。
    你必须给出“本次比例选择理由”。

    输出要求：
    1) 今日A/B工作比例 + 理由（3条以内）
    2) 今日社区洞察（3条，短）
    3) 今日商业洞察（3条，短，含风险提示）
    4) 今日唯一“可落地策略”：
       - 目标
       - 具体执行步骤（<=6步）
       - 需要埋点的关键数据（<=6个）
       - 预期阈值与回滚条件（<=3条）
    5) 给主人一句话的“今日行动指令”（极短）

    注意：尽量节省token，句子短，结构清晰。
    """).strip()

def main():
    # env
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
    moltbook_key = os.getenv("MOLTBOOK_KEY_HEALING", "").strip()
    submolt = os.getenv("MOLTBOOK_SUBMOLT", "general").strip()

    if not moltbook_key:
        raise SystemExit("[FATAL] MOLTBOOK_KEY_HEALING is required (HealingAgent API key).")

    # Paths
    log_dir = "memory/unified/logs"
    date = today_str()
    log_path = os.path.join(log_dir, f"{date}.md")

    state_path = "state.json"
    state = read_json(state_path, default={"runs": []})

    # Generate content
    prompt = build_daily_healing_prompt()

    if deepseek_key:
        content = deepseek_chat(
            api_key=deepseek_key,
            model=deepseek_model,
            messages=[
                {"role": "system", "content": "你是一个严谨但机灵的增长与商业化AI助理。输出必须可执行。"},
                {"role": "user", "content": prompt},
            ],
        )
    else:
        content = "(未配置 DEEPSEEK_API_KEY，已降级输出)\n" + prompt

    # Write log
    md = f"# Daily Healing Log - {date}\n\n" + content.strip() + "\n"
    write_text(log_path, md)

    # Optional: Post to Moltbook (placeholder)
    post_result = post_to_moltbook(
        moltbook_key=moltbook_key,
        submolt=submolt,
        content=content.strip(),
    )

    # Update state
    state.setdefault("runs", [])
    state["runs"].append(
        {
            "date": date,
            "ts": now_iso(),
            "agent": "healing",
            "log_path": log_path,
            "posted": bool(post_result.get("ok")),
            "post_meta": post_result,
        }
    )
    write_json(state_path, state)

    print(f"[OK] wrote log: {log_path}")
    print(f"[OK] updated state: {state_path}")
    print(f"[OK] post result: {post_result}")

if __name__ == "__main__":
    main()
