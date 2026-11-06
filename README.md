# AI DevOps Incident Response Agent

An agent that **investigates** production incidents instead of just answering questions about them. Upload your runbooks, logs and metrics, describe what went wrong, and the agent searches the evidence, runs the numbers and reports back with sources.

<!-- Add a screenshot or short GIF here:
![Chat view](docs/screenshot.png)
-->

## Features

- **Evidence-based investigation.** The agent chooses which tools to call, reads the results and builds a diagnosis from them.
- **Runbook search (RAG).** Answers cite the source file and page.
- **Log analysis.** Works on any uploaded log, including plain text and JSON Lines.
- **Metrics analysis.** Accepts JSON snapshots, JSON series and CSV time series.
- **Precise arithmetic.** Percent change, error rate and ratios are calculated by a tool, not guessed by the model.
- **Automatic file routing.** Uploads are classified as docs, logs or metrics without any setup.
- **Per-incident conversations.** Logs and metrics belong to one conversation, while runbooks are shared across all of a user's conversations.
- **User accounts.** JWT-based authentication, with data kept per user in PostgreSQL.

## How it works

```
User question -> Agent (LangGraph + Groq)
                   |-- rag_tool          runbooks / architecture / deployment docs (PDF, MD, TXT)
                   |-- log_tool          any uploaded log (.log, .txt, .jsonl)
                   |-- metrics_tool      any uploaded metrics (.json snapshot / series, .csv time series)
                   '-- calculator_tool   percent change, error rate, ratios, precise arithmetic
```

## Tech stack

| Layer | Technology |
|-------|-----------|
| Agent | LangGraph, Groq LLM |
| Backend | Python, FastAPI (served with Uvicorn) |
| Database | PostgreSQL |
| Auth | JWT |
| Frontend | React, Tailwind CSS |

## Getting started

### Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer
- PostgreSQL
- A [Groq API key](https://console.groq.com/)

### 1. Backend

```bash
cd Backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env            # Windows: copy .env.example .env
```

Then edit `.env` and set:

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Your Groq API key |
| `DATABASE_URL` | PostgreSQL connection string for the `devops_agent` database |
| `JWT_SECRET` | A long random string used to sign tokens |

Create the database and apply the schema:

```bash
psql -U postgres -c "CREATE DATABASE devops_agent;"
psql -U postgres -d devops_agent -f schema.sql
```

Start the API:

```bash
uvicorn main:app --reload
```

### 2. Frontend

In a new terminal:

```bash
cd Frontend
npm install
npm run dev
```

Open the local URL printed in the terminal, create an account and sign in.

## Uploading files

Use the **+** button in the chat. Files are routed automatically:

| File type | Treated as | Used by |
|-----------|-----------|---------|
| `.pdf`, `.md`, `.rst` | Runbook / docs | `rag_tool` (cites file and page) |
| `.log`, `.out`, `.jsonl` | Logs | `log_tool` |
| `.txt` | Logs if it looks like log lines, otherwise docs | Auto-detected |
| `.csv` | Metrics time series | `metrics_tool` |
| `.json` | Metrics (snapshot or time series) | `metrics_tool` |

Notes:

- Re-uploading a file with the same name replaces the existing one.
- The file bar in the chat lists your uploads. Use its delete button to remove a single file.
- Deleting a conversation also deletes its logs and metrics. Runbooks stay available across your conversations.

## Try it

Upload everything in `test_pack/` (see `TEST_GUIDE.md`), then ask:

> After our latest deployment, API latency increased from 200ms to 800ms. Investigate using the runbook, logs and metrics.

The agent should pull the relevant runbook sections, find the matching log entries, compare the metrics before and after the deploy, calculate the change, and summarise the likely cause with references.

## Starting a fresh incident

Start a new conversation from the sidebar for each separate incident. Runbooks are shared across your conversations, while logs and metrics belong to a single conversation, so old incident data never leaks into a new investigation.

## Project structure

```
.
├── Backend/        FastAPI app, agent, tools, schema.sql
├── Frontend/       React + Tailwind UI
├── test_pack/      Sample runbook, logs and metrics for trying the agent
└── TEST_GUIDE.md   Walkthrough for the sample data
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `psql` command not found | Add the PostgreSQL `bin` folder to your PATH, or run the commands from pgAdmin's query tool. |
| Database connection error | Check `DATABASE_URL` in `.env` and confirm PostgreSQL is running. |
| Agent replies fail or time out | Check that `GROQ_API_KEY` is valid and you haven't hit your Groq rate limit. |
| Frontend can't reach the API | Make sure `uvicorn` is running and the frontend's API base URL points at it. |
| Uploaded `.txt` handled as docs instead of logs | Rename it to `.log` so it is routed to the log tool. |
