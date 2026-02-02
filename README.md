# Unified Moltbook Agent (DeepSeek + GitHub Actions)

This repo runs a daily autonomous agent via GitHub Actions:
- Uses DeepSeek API for reasoning/generation
- Writes private memory & logs into `memory/`
- Optionally posts a public update to Moltbook (currently uses HealingAgent key)

## Required GitHub Secrets
- DEEPSEEK_API_KEY
- DEEPSEEK_MODEL (suggest: deepseek-chat)
- MOLTBOOK_KEY_HEALING (moltbook_sk_... to post)

(Optional, later)
- MOLTBOOK_API_KEY_DIGITALTWIN
- MOLTBOOK_API_KEY_PROFIT

## Run Manually
GitHub → Actions → Daily Moltbook Growth Logs → Run workflow

## Outputs
- Private daily log: `memory/unified/logs/YYYY-MM-DD.md`
- State/memory: `memory/unified/state.json`, `memory/unified/longterm.json`
- Profit tracking: `memory/profit/opportunities.json`
