# GFG AutoSolver Pro — deployment-oriented starter

A Manifest V3 Chrome extension + FastAPI service for:
- capturing a GFG problem from the currently open page,
- generating a Java solution + explanation with OpenAI,
- optional local Java compile check,
- committing `.java` + `.md` artifacts to GitHub,
- scheduled daily processing from an **authorized JSON problem feed**,
- GitHub Actions deployment/checks and Docker deployment.

## Compliance / scope
This project deliberately **does not automate GFG login, editor injection, or answer submission**. GeeksforGeeks' terms restrict automated/bot use. Use the extension to prepare and archive solutions, and submit manually on GFG. The daily runner needs a problem feed/source you are authorized to use. Never put secrets in extension code.

## Architecture
Chrome extension (capture + review) → FastAPI backend → OpenAI → optional `javac` check → GitHub Contents API.
Daily runner (APScheduler) → authorized feed → same pipeline.

## Local deployment (Docker)
1. Copy `backend/.env.example` to `backend/.env` and configure values.
2. `docker compose up --build -d`
3. Check `http://localhost:8787/health` and `http://localhost:8787/docs`.
4. Chrome: `chrome://extensions` → Developer mode → Load unpacked → `extension/`.
5. Extension Options: set backend to `http://127.0.0.1:8787`.
6. Visit a GFG problem page → extension → Capture → review fields → Solve + Commit.

## Production deployment
- Deploy backend on a private VM/container host with HTTPS (reverse proxy such as Caddy/Nginx).
- Set extension backend URL to the HTTPS service.
- Restrict backend access with `AUTOSOLVER_API_KEY` and firewall/rate limits.
- Store OpenAI/GitHub secrets in the host's secret manager, not in source control.
- Use `PROBLEM_FEED_URL` only for a permitted feed. The JSON endpoint must return:
  `{ "title":"...", "url":"...", "statement":"...", "constraints":"...", "examples":"..." }`
- Daily schedule uses `DAILY_TIME` and `TIMEZONE`; set `ENABLE_SCHEDULER=true`.
- GitHub token: fine-grained PAT limited to the target repository, Contents read/write.
- GitHub Actions runs tests/build checks; it does not need your secrets unless you add a scheduled authorized feed workflow.

## API
- `GET /health`
- `GET /daily/status`
- `POST /solve` body `{title,url,statement,constraints,examples}`
- `POST /daily/run` manual run from authorized feed
- `GET /docs` OpenAPI docs

## Repository output
- `gfg/<slug>.java`
- `gfg/<slug>.md`
- Idempotency: repeated same title overwrites same path with a new commit; consider changing slug strategy if you want versioned files.

## Limitations
- Problem extraction is heuristic; always review the captured statement.
- AI code is not guaranteed correct; compile checks cannot prove algorithmic correctness.
- The exact GFG Java signature may be ambiguous. Verify before submitting.
- Daily automation depends on a stable, authorized feed. No GFG scraping or submission is included.
