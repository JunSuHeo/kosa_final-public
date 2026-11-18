#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
studio_dir=$(pwd)
export STUDIO_COMPOSE_PROJECT=planning-studio-e2e
export STUDIO_DB_PORT=54332
export STUDIO_API_PORT=8011
export STUDIO_WEB_PORT=5175
export AUTH_MODE=mock
export AI_MODE=mock
mkdir -p .research
STUDIO_REPOSITORY_HOST_ROOT=$(mktemp -d "$(pwd)/.research/e2e-repos.XXXXXX")
export STUDIO_REPOSITORY_HOST_ROOT
E2E_FIXTURE_REPO="search-${STUDIO_REPOSITORY_HOST_ROOT##*.}"
export E2E_FIXTURE_REPO
mkdir "$STUDIO_REPOSITORY_HOST_ROOT/$E2E_FIXTURE_REPO"
fixture="$STUDIO_REPOSITORY_HOST_ROOT/$E2E_FIXTURE_REPO"
git -C "$fixture" init -q
printf '%s\n' 'export function fixtureSearch() { return "fixture result"; }' > "$fixture/search.ts"
git -C "$fixture" add search.ts
git -C "$fixture" -c user.name=Fixture -c user.email=fixture@example.invalid commit -qm fixture
cleanup() {
  docker compose -f "$studio_dir/compose.yaml" -f "$studio_dir/infra/repositories.compose.yaml" down
  rm -rf "$STUDIO_REPOSITORY_HOST_ROOT"
}
trap cleanup EXIT
docker compose -f compose.yaml -f infra/repositories.compose.yaml up --build -d db api worker web
cd frontend
npm ci
npx playwright install chromium
E2E_BASE_URL=http://localhost:5175 npm run test:e2e
