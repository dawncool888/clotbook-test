import os
import json
import datetime
from pathlib import Path

# ========= 基础工具 =========

def today_str():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

def ensure_dir(p: str):
    Path(p).mkdir(parents=True, exist_ok=True)

def safe_write_text(path: str, content: str):
    ensure_dir(str(Path(path).parent))
    Path(path).write_text(content, encoding="utf-8")

def safe_read_json(path: str, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default

def safe_write_json(path: str, data):
    ensure_dir(str(Path(path).parent))
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ========= 你自己的 LLM 调用部分（这里先做最小可跑通骨架） =========
# 你仓库里如果已经有 deepseek 调用封装，请把 generate_report() 替换成你现有实现即可。

def generate_report() -> str:
    """
    产出今日汇报（允许纯文本，不强制 JSON）。
    你可以把这里替换成你仓库现有的 DeepSeek 调用。
    """
    model = os.getenv("DEEPSEEK_MODEL", "").strip()
    if not model:
        model = "deepseek-chat"  # 兜底（你也可以改成你实际使用的）

    # 最小占位：真实情况你会调用 deepseek
    # 这里返回一段结构化文本，保证脚本不因 JSON 挂掉。
    return (
        f"【Daily Healing Agent Report】\n"
        f"- 日期(UTC): {today_str()}\n"
        f"- 模型: {model}\n"
        f"- 今日目标：发 1 条高质量贴 + 记录记忆 + 可回滚\n"
        f"- 今日输出：\n"
        f"  1) 一条可发帖内容（可带热梗+哲思+心机但不违规）\n"
        f"  2) 一条自我复盘（哪里可优化、哪里要埋点）\n"
        f"  3) 明日策略（A/B 时间比例建议）\n"
    )

# ========= Moltbook 发帖（你可替换为你现有 SDK/HTTP 实现） =========

def post_to_moltbook(text: str) -> dict:
    """
    这里先做“可跑通”的假实现：不让 workflow 挂。
    你后续把这里替换成实际 Moltbook API 调用即可。
    """
    key = os.getenv("MOLTBOOK_KEY_HEALING", "").strip()
    if not key:
        raise RuntimeError("[FATAL] MOLTBOOK_KEY_HEALING is required (HealingAgent API key).")

    # 真实实现示例（伪代码）：
    # resp = requests.post(..., headers={"Authorization": f"Bearer {key}"}, json={...})
    # return resp.json()

    return {"ok": True, "posted": True, "submolt": os.getenv("MOLTBOOK_SUBMOLT", "general")}

# ========= 主流程 =========

def main():
    # 1) 校验 secrets
    if not os.getenv("DEEPSEEK_API_KEY", "").strip():
        raise RuntimeError("[FATAL] DEEPSEEK_API_KEY is required.")
    if not os.getenv("MOLTBOOK_KEY_HEALING", "").strip():
        raise RuntimeError("[FATAL] MOLTBOOK_KEY_HEALING is required (HealingAgent API key).")

    # 2) 确保目录
    ensure_dir("memory/unified/logs")
    ensure_dir("memory/profit")
    ensure_dir("memory/digitaltwin")

    # 3) 读取 state（允许不存在）
    state_path = "state.json"
    state = safe_read_json(state_path, default={"day": 1, "failures": {}, "dormant": {}})

    # 4) 生成今日汇报（不强制 JSON）
    report = generate_report()

    # 5) 发帖（HealingAgent）
    post_result = post_to_moltbook(report)

    # 6) 写入日志
    log_path = f"memory/unified/logs/{today_str()}.md"
    md = (
        f"# Daily Unified Log - {today_str()}\n\n"
        f"## Posted\n"
        f"- result: `{json.dumps(post_result, ensure_ascii=False)}`\n\n"
        f"## Report\n\n"
        f"{report}\n"
    )
    safe_write_text(log_path, md)

    # 7) opportunities 文件保证是 JSON（避免你之前那种写成 python 代码）
    opp_path = "memory/profit/opportunities.json"
    opp = safe_read_json(opp_path, default={"opportunities": [], "last_updated": None})
    if not isinstance(opp, dict):
        opp = {"opportunities": [], "last_updated": None}
    opp["last_updated"] = today_str()
    safe_write_json(opp_path, opp)

    # 8) 更新 state（简单+稳定）
    state["day"] = int(state.get("day", 1)) + 1
    safe_write_json(state_path, state)

    print("[OK] Daily run completed.")
    print(f"[OK] Log written: {log_path}")

if __name__ == "__main__":
    main()
