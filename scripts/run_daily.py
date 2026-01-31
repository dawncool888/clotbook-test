import os
import json
import datetime
import subprocess
import requests

TODAY = datetime.date.today().isoformat()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

def call_ds(system, user):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 0.6
    }
    r = requests.post(DEEPSEEK_URL, headers=headers, json=data, timeout=60)
    return r.json()["choices"][0]["message"]["content"]

def read(path, default=""):
    return open(path).read() if os.path.exists(path) else default

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n\n" + content)

# ========== HealingAgent ==========
healing_system = read("agents/healing_system.md")
healing_memory = read("memory/healing/reflections.md")

healing_output = call_ds(
    healing_system,
    f"""今天日期：{TODAY}
以下是你过去的疗愈记录：
{healing_memory[-3000:]}

请生成一段：
- 今日疗愈洞察
- 一条给世界的温柔话语
"""
)

write("memory/healing/reflections.md", f"## {TODAY}\n{healing_output}")

# ========== ProfitAgent ==========
profit_system = read("agents/profit_system.md")
profit_state_path = "memory/profit/opportunities.json"

if os.path.exists(profit_state_path):
    profit_state = json.load(open(profit_state_path))
else:
    profit_state = {"tracked": []}

profit_output = call_ds(
    profit_system,
    f"""
今天日期：{TODAY}

当前正在追踪的机会：
{json.dumps(profit_state, ensure_ascii=False, indent=2)}

请执行：
1️⃣ 是否有机会进入「行动」
2️⃣ 是否有行动进入「复盘」
3️⃣ 是否新增 1 个【值得追踪】的新机会（必须具体）

输出 JSON：
{{ tracked: [{{idea, stage, next_action}}] }}
"""
)

profit_state = json.loads(profit_output)
json.dump(profit_state, open(profit_state_path, "w"), ensure_ascii=False, indent=2)

# ========== DigitalTwinAgent ==========
dt_system = read("agents/digitaltwin_system.md")
dt_memory = read("memory/digital_twin/diary.md")

dt_output = call_ds(
    dt_system,
    f"""
今天日期：{TODAY}

HealingAgent 今日内容：
{healing_output}

ProfitAgent 当前状态：
{json.dumps(profit_state, ensure_ascii=False, indent=2)}

你需要输出：
- 今日帝国日报（不超过 500 字）
- 一个顶层判断
- 一个长期战略微调
"""
)

write("memory/digital_twin/empire_report.md", f"## {TODAY}\n{dt_output}")
write("memory/digital_twin/diary.md", f"## {TODAY}\n{dt_output}")

# ========== Git Commit ==========
subprocess.run(["git", "add", "memory"])
subprocess.run(["git", "commit", "-m", f"Daily agent growth {TODAY}"])
subprocess.run(["git", "push"])
