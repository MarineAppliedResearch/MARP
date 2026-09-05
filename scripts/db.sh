#!/bin/sh
#
# Provision and run the MARP PostgreSQL database. Invoked as `marp db <command>`.
#
# marp-api cannot run without a PostgreSQL database, and nothing else in the
# workspace provided one -- the development database was a hand-built server on
# a virtual machine, which a second machine cannot reproduce automatically.
# This script closes that gap.
#
# Nothing lands outside the workspace. The server and the database both live
# under `.postgres/`, which is git-ignored, so deleting this workspace leaves
# nothing behind.
#
# The schema is not this script's to own. It belongs to marp-api, which carries
# the baseline and every migration, so `up` finishes by running marp-api's own
# two commands against the new database. If marp-api cannot be driven, this
# stops and prints those commands rather than guessing -- a running database
# and honest instructions beat a silent half-finished one.
#
# POSIX counterpart of scripts/db.ps1, with one unavoidable difference. The
# official PostgreSQL project publishes plain binary archives for Windows and
# macOS but not for Linux, where distributions package it instead. So on macOS
# this downloads a self-contained PostgreSQL exactly as the Windows script
# does, and on Linux it uses the PostgreSQL already installed, reporting
# clearly what to install if there is none. The database it produces is the
# same either way.
#
# Author: Isaac Travers

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(dirname -- "$SCRIPT_DIR")
POSTGRES_DIR="$REPO_ROOT/.postgres"
# Set after argument parsing, because --data-dir moves them. The PostgreSQL binaries
# stay in .postgres/ and are shared: a second worktree needs its own data directory,
# not its own 300 MB download.
DATA_DIR=
LOG_FILE=
INSTANCE=
API_DIR="$REPO_ROOT/MARP_API"

# Pinned rather than tracking latest, so "it worked last week" stays
# traceable. 18.6 matches the development server.
POSTGRES_VERSION='18.6-1'
POSTGRES_MAJOR='18'

ROLE='marp_user'
DATABASE='mare_v1'
DB_HOST_ADDR='127.0.0.1'

COMMAND=status
# PostgreSQL's own port, because tools and documentation assume it. If
# something is already there this script stops and says so rather than quietly
# choosing another and leaving your .env disagreeing with reality.
PORT=5432
PASSWORD='marp_dev_password'

usage() {
    cat <<'USAGE'
Usage: scripts/marp.sh db <command> [options]

Commands:
  up        fetch or locate PostgreSQL, start it, create the database, load the schema.
  down      stop the server. The database is kept.
  status    what exists and what is running (default).
  env       the DB_* settings marp-api needs.
  destroy   stop the server and delete the database.

Options:
  --port N        TCP port. Default 5432.
  --data-dir NAME A separate database under .postgres/instances/NAME, so a second
                  worktree on this machine gets its own. Needs its own --port too;
                  one server cannot serve two data directories.
  --password P    Password for the database role.
  -h, --help      This text.
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        up|down|status|env|destroy) COMMAND=$1 ;;
        --port) PORT=${2:?--port needs a value}; shift ;;
        --data-dir) INSTANCE=${2:?--data-dir needs a value}; shift ;;
        --password) PASSWORD=${2:?--password needs a value}; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown argument: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [ -n "$INSTANCE" ]; then
    DATA_DIR="$POSTGRES_DIR/instances/$INSTANCE/data"
    LOG_FILE="$POSTGRES_DIR/instances/$INSTANCE/server.log"
else
    DATA_DIR="$POSTGRES_DIR/data"
    LOG_FILE="$POSTGRES_DIR/server.log"
fi

if [ -t 1 ]; then
    C_CYN=$(printf '\033[36m'); C_YEL=$(printf '\033[33m')
    C_GRN=$(printf '\033[32m'); C_DIM=$(printf '\033[2m'); C_OFF=$(printf '\033[0m')
else
    C_CYN=; C_YEL=; C_GRN=; C_DIM=; C_OFF=
fi

step() { printf '%s==> %s%s\n' "$C_CYN" "$1" "$C_OFF"; }
ok()   { printf '%s    %s%s\n' "$C_DIM" "$1" "$C_OFF"; }
warn() { printf '%s    %s%s\n' "$C_YEL" "$1" "$C_OFF"; }

# ---------------------------------------------------------------------------
# Locating PostgreSQL
# ---------------------------------------------------------------------------

platform() {
    case "$(uname -s)" in
        Darwin) echo macos ;;
        Linux) echo linux ;;
        MINGW*|MSYS*|CYGWIN*) echo windows ;;
        *) echo unknown ;;
    esac
}

# Set by locate_postgres to the directory holding initdb, pg_ctl and psql.
BIN_DIR=

<<'DOC'
Find a PostgreSQL to use, downloading one on macOS if needed.

On Linux this deliberately uses what is installed rather than fetching
anything: the PostgreSQL project does not publish a portable Linux build, and
assembling one would mean maintaining something every distribution already
maintains better. A missing PostgreSQL is reported with the command to install
it, which is a one-line fix, rather than worked around.
DOC
locate_postgres() {
    if [ -x "$POSTGRES_DIR/pgsql/bin/initdb" ]; then
        BIN_DIR="$POSTGRES_DIR/pgsql/bin"
        return 0
    fi

    case "$(platform)" in
        windows)
            warn 'On Windows use the PowerShell script, which downloads PostgreSQL for you:'
            warn '    .\scripts\marp.ps1 db up'
            return 1
            ;;
        macos)
            fetch_macos || return 1
            BIN_DIR="$POSTGRES_DIR/pgsql/bin"
            return 0
            ;;
        linux)
            # Distribution packages put the binaries outside PATH, so the
            # versioned location is checked before giving up.
            for candidate in "/usr/lib/postgresql/$POSTGRES_MAJOR/bin" "/usr/pgsql-$POSTGRES_MAJOR/bin"; do
                if [ -x "$candidate/initdb" ]; then BIN_DIR="$candidate"; ok "using $candidate"; return 0; fi
            done
            if command -v initdb >/dev/null 2>&1; then
                BIN_DIR=$(dirname -- "$(command -v initdb)")
                ok "using $BIN_DIR"
                return 0
            fi
            warn "PostgreSQL $POSTGRES_MAJOR is not installed."
            warn '  Debian/Ubuntu:  sudo apt install postgresql-18'
            warn '  Fedora/RHEL:    sudo dnf install postgresql18-server'
            warn '  macOS/Windows:  handled automatically; this message is Linux-only.'
            warn 'Nothing is downloaded here because no portable Linux build is published.'
            return 1
            ;;
        *)
            warn "Unrecognised platform $(uname -s); install PostgreSQL $POSTGRES_MAJOR and re-run."
            return 1
            ;;
    esac
}

fetch_macos() {
    url="https://get.enterprisedb.com/postgresql/postgresql-$POSTGRES_VERSION-osx-binaries.zip"
    archive="$POSTGRES_DIR/postgresql-$POSTGRES_VERSION.zip"
    mkdir -p "$POSTGRES_DIR"

    if [ ! -f "$archive" ]; then
        step "Downloading PostgreSQL $POSTGRES_VERSION -- a few hundred MB, once"
        # --progress-bar rather than silence: a download that looks hung gets
        # killed, and this one takes minutes.
        curl -L --progress-bar -o "$archive.partial" "$url" || { rm -f "$archive.partial"; return 1; }
        mv "$archive.partial" "$archive"
    else
        ok 'archive already downloaded, reusing it'
    fi

    step 'Unpacking'
    unzip -q -o "$archive" -d "$POSTGRES_DIR" || return 1
    [ -x "$POSTGRES_DIR/pgsql/bin/initdb" ] || { warn 'archive did not contain pgsql/bin/initdb'; return 1; }
    rm -f "$archive"
    ok "$("$POSTGRES_DIR/pgsql/bin/postgres" --version)"
}

# Every call sets the password for the child process only. Exporting PGPASSWORD
# would leak it to everything else started from this shell.
pg() {
    tool=$1; shift
    PGPASSWORD="$PASSWORD" "$BIN_DIR/$tool" "$@"
}

is_initialised() { [ -f "$DATA_DIR/PG_VERSION" ]; }
is_running()     { is_initialised && "$BIN_DIR/pg_ctl" -D "$DATA_DIR" status >/dev/null 2>&1; }

# Reported for a message, not used as a decision: a port in use may well be
# this script's own server from an earlier session.
port_holder() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1" (PID "$2")"}'
    fi
}

# ---------------------------------------------------------------------------

do_init() {
    if is_initialised; then ok '.postgres/data already initialised'; return 0; fi

    step 'Creating the database cluster'
    mkdir -p "$POSTGRES_DIR"
    password_file="$POSTGRES_DIR/.initdb-password"
    # printf without a newline: a trailing one becomes part of the password.
    printf '%s' "$PASSWORD" > "$password_file"
    chmod 600 "$password_file"

    # --no-sync skips flushing the new cluster to disk, which is most of
    # initdb's runtime. The risk it accepts is losing the cluster if the
    # machine dies during these few seconds, and the answer to that is running
    # `up` again. Not a trade worth making for a database holding real
    # records; entirely worth it for this one.
    if ! pg initdb -D "$DATA_DIR" -U "$ROLE" --auth=scram-sha-256 \
            --pwfile="$password_file" --encoding=UTF8 --no-sync >/dev/null; then
        rm -f "$password_file"
        return 1
    fi
    rm -f "$password_file"
    ok "cluster created, role '$ROLE'"
}

do_start() {
    do_init || return 1
    if is_running; then ok "already running on port $PORT"; return 0; fi

    # Checked before starting rather than after failing, so the message names
    # the real problem instead of leaving an error in a log file.
    holder=$(port_holder || true)
    if [ -n "${holder:-}" ]; then
        warn "Port $PORT is already in use by $holder."
        warn "Stop it, or place this database elsewhere:  marp.sh db up --port 5433"
        return 1
    fi

    step "Starting PostgreSQL on $DB_HOST_ADDR:$PORT"
    # Localhost only: a development database with a known password has no
    # business accepting connections from the network.
    pg pg_ctl -D "$DATA_DIR" -l "$LOG_FILE" \
        -o "-p $PORT -c listen_addresses=127.0.0.1" start >/dev/null || return 1

    is_running || { warn "Server did not start. See $LOG_FILE"; return 1; }
    ok 'running'
}

do_stop() {
    is_initialised || { ok 'nothing to stop'; return 0; }
    is_running || { ok 'not running'; return 0; }
    step 'Stopping PostgreSQL'
    pg pg_ctl -D "$DATA_DIR" -m fast stop >/dev/null
    ok 'stopped'
}

create_database() {
    if pg psql -h "$DB_HOST_ADDR" -p "$PORT" -U "$ROLE" -d postgres -tAc \
        "select 1 from pg_database where datname = '$DATABASE'" 2>/dev/null | grep -q 1; then
        ok "database $DATABASE already exists"
        return 0
    fi
    step "Creating database $DATABASE"
    pg createdb -h "$DB_HOST_ADDR" -p "$PORT" -U "$ROLE" "$DATABASE"
}

<<'DOC'
Have marp-api put its schema into the new database.

The schema belongs to marp-api: it holds the baseline and every migration.
Keeping a second copy here would drift the first time somebody adds one, so
this runs marp-api's own commands instead.

Returns non-zero when marp-api cannot be driven, which the caller reports as
work remaining rather than as a failure. A running but empty database is a
perfectly good outcome as long as the person is told plainly what is left.
DOC
load_schema() {
    [ -f "$API_DIR/package.json" ] || { warn 'MARP_API is not cloned, so the schema was not loaded.'; return 1; }
    [ -d "$API_DIR/node_modules" ] || { warn 'MARP_API has no node_modules, so the schema was not loaded.'; return 1; }

    for tool in node npx; do
        command -v "$tool" >/dev/null 2>&1 || {
            warn "$tool is not on PATH, so the schema was not loaded."
            return 1
        }
    done

    # Real environment variables rather than edits to MARP_API/.env: dotenv
    # does not override what is already set, so these win for these two
    # commands only and that repository's configuration is left as written.
    DB_HOST="$DB_HOST_ADDR" DB_PORT="$PORT" DB_NAME="$DATABASE" \
    DB_USER="$ROLE" DB_PASSWORD="$PASSWORD" DB_DIALECT=postgres \
    sh -c "
        cd '$API_DIR' || exit 1
        printf '%s\n' '==> Loading the baseline schema (MARP_API)'
        node scripts/init-database.js || exit 1
        printf '%s\n' '==> Applying migrations (MARP_API)'
        npx sequelize-cli db:migrate || exit 1
    " || return 1
}

do_up() {
    locate_postgres || return 1
    do_start || return 1
    create_database

    if load_schema; then
        printf '\n%sDatabase ready.%s\n' "$C_GRN" "$C_OFF"
        do_env
    else
        printf '\n%sDatabase is running, but the schema is not loaded.%s\n' "$C_YEL" "$C_OFF"
        printf '\n%sFinish it in the MARP_API checkout:%s\n' "$C_CYN" "$C_OFF"
        echo '    cd MARP_API'
        echo '    npm install                      # if you have not already'
        echo '    node scripts/init-database.js'
        echo '    npx sequelize-cli db:migrate'
        do_env
    fi
}

do_status() {
    step 'MARP database'
    locate_postgres || return 1
    ok "$("$BIN_DIR/postgres" --version)"

    is_initialised || { warn 'cluster not created (run: marp.sh db up)'; return 0; }

    if ! is_running; then
        warn 'not running (run: marp.sh db up)'
        holder=$(port_holder || true)
        [ -z "${holder:-}" ] || warn "note: something else is on port $PORT -- $holder"
        return 0
    fi

    ok "running on $DB_HOST_ADDR:$PORT"
    summary=$(pg psql -h "$DB_HOST_ADDR" -p "$PORT" -U "$ROLE" -d "$DATABASE" -tAc "
        select (select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE')
            || ' tables, '
            || (select count(*) from information_schema.tables where table_schema='public' and table_type='VIEW')
            || ' views, '
            || (select count(*) from \"SequelizeMeta\")
            || ' migrations applied'
    " 2>/dev/null || true)

    if [ -n "${summary:-}" ]; then ok "$DATABASE: $summary"
    else warn "$DATABASE has no schema yet -- see: marp.sh db up"; fi
}

# Printed, not written. MARP_API/.env also holds Jellyfin credentials, a
# session secret and reporting connection details; rewriting somebody's
# configuration file to save them a copy and paste is a poor trade.
do_env() {
    printf '\n%sSet these in MARP_API/.env :%s\n\n' "$C_CYN" "$C_OFF"
    echo "DB_HOST=$DB_HOST_ADDR"
    echo "DB_PORT=$PORT"
    echo "DB_NAME=$DATABASE"
    echo "DB_USER=$ROLE"
    echo "DB_PASSWORD=$PASSWORD"
    echo 'DB_DIALECT=postgres'
    echo ''
}

do_destroy() {
    locate_postgres || return 1
    do_stop
    [ -d "$DATA_DIR" ] || { ok 'no database to delete'; return 0; }
    step 'Deleting the database'
    rm -rf "$DATA_DIR"
    rm -f "$LOG_FILE"
    ok 'deleted. The PostgreSQL binaries are kept, so `up` will not download again.'
}

case "$COMMAND" in
    up)      do_up ;;
    down)    locate_postgres && do_stop ;;
    status)  do_status ;;
    env)     do_env ;;
    destroy) do_destroy ;;
esac
