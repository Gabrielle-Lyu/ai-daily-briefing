# AI Daily Briefing — Claude Instructions

## Dev Team Orchestrator

The dev team lives at `/home/ubuntu/dev-team/team.py`.
Invoke it with: `env -u CLAUDECODE python3 /home/ubuntu/dev-team/team.py --cwd /home/ubuntu/projects/ai-daily-briefing "TASK"`

**Automatically use the orchestrator (without waiting to be asked) for:**
- Any UI/UX design or layout changes → spawn designer + reader/critic agents to agree first, then frontend to implement
- New features or significant architecture changes → run the full PM → architect → backend/frontend cycle
- Code review requests → spawn architect + backend/frontend + QA agents
- Bug fixes that touch multiple files → use backend or frontend agent

**Do NOT use the orchestrator for:**
- Small CSS tweaks or wording changes — just edit directly
- Reading files or answering questions
- Running the pipeline (`python3 main.py`)

## Project Structure

- `briefing/render.py` — all HTML/CSS output (pure Python string templates, no frontend framework)
- `briefing/llm.py` — calls `claude -p` via subprocess (OAuth, no API key needed)
- `briefing/config.py` — audience profiles + RSS sources
- `main.py` — pipeline runner (`--dry-run` skips LLM calls)
- `serve.py` — local HTTP server for previewing output
- `output/YYYY-MM-DD/` — generated HTML files

## Running

```bash
python3 main.py --dry-run       # fast test, no LLM
python3 main.py                 # real run via claude OAuth
python3 serve.py --no-browser  # serve on :8000
```

## Key Conventions

- LLM calls use `claude -p` subprocess with `CLAUDECODE` unset (already handled in `llm.py`)
- Keep all Python logic in `render.py` unchanged when redesigning — only touch CSS and HTML template strings
- After any render.py change, verify with `python3 main.py --dry-run`
