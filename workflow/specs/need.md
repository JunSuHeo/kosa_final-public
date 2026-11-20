# Runner 패키지

## 현재 필요한 항목

| 패키지 | 설치 커맨드 |
| --- | --- |
| Python 3.12 이상 | `brew install python@3.12` |
| Git, GitHub CLI (`gh`) | `brew install git gh` |
| Node.js, npm (Codex CLI 설치용) | `brew install node` |
| Codex CLI 0.171.0 | `npm install --global --prefix "$HOME/.local" @openai/codex@0.171.0` |
| `sandbox-exec` | macOS 기본 제공, 설치 불필요 |

## PostgreSQL 백엔드 검사 활성화 시

| 패키지 | 설치 커맨드 |
| --- | --- |
| uv | `brew install uv` |
| FastAPI, Uvicorn, Psycopg, Pydantic Settings, HTTPX, PyJWT, pytest | `cd PRJ/backend && uv sync --frozen` |
| PostgreSQL 서버·클라이언트 (`initdb`, `pg_ctl`, `createdb`) | `brew install postgresql@17` |

## 브라우저 E2E 활성화 시

| 패키지 | 설치 커맨드 |
| --- | --- |
| Docker Desktop | `brew install --cask docker` |
| Frontend 패키지 | `cd PRJ/frontend && npm ci` |
| Playwright Chromium | `cd PRJ/frontend && npx playwright install chromium` |
