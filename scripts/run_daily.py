name: Daily Moltbook Growth Logs

on:
  workflow_dispatch:
  schedule:
    - cron: "0 1 * * *"   # 每天 UTC 01:00 运行（你可以后改）

jobs:
  run:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install deps
        run: pip install -r requirements.txt

      - name: Run daily agents
        env:
          # ===== DeepSeek（大脑）=====
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          DEEPSEEK_MODEL: ${{ secrets.DEEPSEEK_MODEL }}

          # ===== Moltbook keys（发帖权限）=====
          MOLTBOOK_KEY_HEALING: ${{ secrets.MOLTBOOK_KEY_HEALING }}
          MOLTBOOK_KEY_DIGITALTWIN: ${{ secrets.MOLTBOOK_API_KEY_DIGITALTWIN }}
