#!/bin/bash
# Runs only inside the independent test sandbox.
set -euo pipefail

setup_failed() {
    printf 'PRJ test setup failed: %s\n' "$1" >&2
    exit 78
}

pg_bin=
pg_ctl=$(command -v pg_ctl || true)
for dir in "${pg_ctl%/*}" /usr/lib/postgresql/*/bin; do
    if [[ -n "$dir" && -x "$dir/initdb" && -x "$dir/pg_ctl" && -x "$dir/createdb" ]]; then
        pg_bin=$dir
        break
    fi
done
[[ -n "$pg_bin" ]] || setup_failed "PostgreSQL server and client binaries are missing."

export UV_PROJECT_ENVIRONMENT=/tmp/uv-venv UV_CACHE_DIR=/tmp/uv-cache
export APP_ENV=local AUTH_MODE=mock AI_MODE=mock
mkdir -p "$UV_CACHE_DIR" /tmp/pg-socket || setup_failed "Scratch directories could not be created."
cp -R --no-preserve=mode,ownership /workflow/uv-cache/. "$UV_CACHE_DIR" ||
    setup_failed "The prepared uv cache could not be copied."
uv sync --offline --frozen --no-build --no-python-downloads --python "$(command -v python3)" ||
    setup_failed "The prepared cache does not satisfy the candidate lock file."

uid=$(id -u)
if ! getent passwd "$uid" >/dev/null; then
    printf 'test:x:%s:%s::/home/test:/bin/bash\n' "$uid" "$(id -g)" >> /etc/passwd ||
        setup_failed "The sandbox PostgreSQL user could not be initialized."
fi

export PGDATA=/tmp/pg-data
"$pg_bin/initdb" --no-locale --encoding=UTF8 --username=studio --auth-local=trust --auth-host=reject ||
    setup_failed "initdb did not create a temporary PostgreSQL cluster."
trap '"$pg_bin/pg_ctl" -m immediate stop >/dev/null 2>&1 || true' EXIT
"$pg_bin/pg_ctl" -w -l /tmp/postgresql.log -o "-c listen_addresses='' -c unix_socket_directories=/tmp/pg-socket -c dynamic_shared_memory_type=mmap" start ||
    { cat /tmp/postgresql.log >&2; setup_failed "Temporary PostgreSQL could not start."; }
"$pg_bin/createdb" -h /tmp/pg-socket -U studio studio_test ||
    setup_failed "The studio_test database could not be created."

export DATABASE_URL='postgresql:///studio_test?host=/tmp/pg-socket&user=studio'
uv run --no-sync --offline pytest -q -p no:cacheprovider
