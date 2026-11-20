#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
studio_dir=$(pwd)
mkdir -p .research
run_dir=$(mktemp -d "$studio_dir/.research/e2e.XXXXXXXX")
project="kosa-e2e-$(basename "$run_dir" | cut -d. -f2 | tr '[:upper:]' '[:lower:]')"
STUDIO_REPOSITORY_HOST_ROOT="$run_dir/repositories"
E2E_FIXTURE_REPO=search-fixture
export STUDIO_REPOSITORY_HOST_ROOT E2E_FIXTURE_REPO
compose() {
  docker compose --project-directory "$studio_dir" --env-file "$studio_dir/.env.example" -p "$project" \
    -f "$studio_dir/compose.yaml" -f "$studio_dir/infra/test.compose.yaml" \
    -f "$studio_dir/infra/repositories.compose.yaml" "$@"
}
started=false
cleanup() {
  result=$?
  trap - EXIT
  if [ "$started" = true ]; then
    if [ "$result" -ne 0 ]; then compose ps || true; fi
    if ! compose down -v --rmi local; then
      echo "Cleanup failed. Fixture retained at $run_dir" >&2
      exit 1
    fi
  fi
  if [ "$result" -ne 0 ] && [ -d "$run_dir/frontend/test-results" ]; then
    echo "Playwright evidence retained at $run_dir/frontend/test-results" >&2
  else
    rm -rf "$run_dir"
  fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

fixture="$STUDIO_REPOSITORY_HOST_ROOT/$E2E_FIXTURE_REPO"
mkdir -p "$fixture" "$run_dir/frontend"
git -C "$fixture" init -q
printf '%s\n' 'export function fixtureSearch() { return "fixture result"; }' > "$fixture/search.ts"
printf '%s\n' ':root { --brand-primary: #0c7a6b; --background: #ffffff; --surface: #f1f7f5; --text: #172033; } .sidebar { border-radius: 4px; gap: 12px; font-family: Arial, sans-serif; }' > "$fixture/theme.css"
git -C "$fixture" add search.ts theme.css
git -C "$fixture" -c user.name=Fixture -c user.email=fixture@example.invalid commit -qm fixture

# Per-run npm and Playwright outputs allow two checks from the same checkout.
cp -R frontend/tests frontend/package.json frontend/package-lock.json frontend/playwright.config.ts "$run_dir/frontend/"
cd "$run_dir/frontend"
npm ci
if [ "${GITHUB_ACTIONS:-}" = true ]; then
  npx playwright install --with-deps chromium
else
  npx playwright install chromium
fi
started=true
compose up --build --detach --wait --wait-timeout 120 db api worker web
endpoint=$(compose port web 80)
export E2E_BASE_URL="http://$endpoint"
printf 'E2E project %s at %s\n' "$project" "$E2E_BASE_URL"
if [ "$#" -gt 0 ]; then
  npm run test:e2e -- "$@"
else
  npm run test:e2e -- tests/studio.spec.ts tests/source-planning.spec.ts tests/users.spec.ts tests/login.spec.ts tests/supabase-accounts.spec.ts
fi
