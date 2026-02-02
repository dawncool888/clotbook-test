name: Daily Moltbook Growth Logs

on:
  workflow_dispatch:
  schedule:
    - cron: "0 1 * * *" # 每天 UTC 01:00（中国=上午9点）

jobs:
  run:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          persist-credentials: true
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install deps
        run: pip install -r requirements.txt

      - name: Run daily agent
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          DEEPSEEK_MODEL: ${{ secrets.DEEPSEEK_MODEL }}
          MOLTBOOK_KEY_HEALING: ${{ secrets.MOLTBOOK_KEY_HEALING }}
        run: python scripts/run_daily.py

      - name: Commit & Push memory
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add -A
          git diff --cached --quiet || git commit -m "chore: daily agent memory update"
          git push
