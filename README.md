# HisabClub

HisabClub is a privacy-first, self-hosted Indian personal finance ledger.

## What it does
- imports credit card and bank statements (including password-protected PDFs)
- supports manual uploads and optional Android SMS enrichment
- merges transactions into a unified ledger
- provides budgeting, insights, bill tracking, and reconciliation support

## Stack
- FastAPI backend + PostgreSQL + Redis
- React web frontend
- React Native mobile app
- optional local llama.cpp with QwQ-32B for AI-assisted tasks

## Start
```bash
docker compose up -d --build
```

For local LLM mode:
```bash
./start-llm.sh
```

## Knowledge transfer
See `knowledge.md` for complete architecture, migrations, model paths, and rollout history.
