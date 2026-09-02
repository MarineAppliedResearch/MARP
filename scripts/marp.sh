#!/bin/sh
#
# Manage the MARP workspace: clone, inspect and update every component
# repository listed in services/repos.yml.
#
# The MARP ecosystem is a polyrepo. This umbrella repository holds the
# workspace layout and the component registry, but each component is its own
# independent Git repository cloned as a subdirectory here. That gives one
# place from which every interconnected project is reachable -- by a developer
# or by an agent -- without merging their histories.
#
# This script is what turns a fresh clone of the umbrella into that workspace.
# It reads services/repos.yml, which is the single source of truth for what
# exists and where it belongs, so adding a component means editing the registry
# and the .gitignore rather than editing this script.
#
# POSIX counterpart of scripts/marp.ps1. The two must stay behaviourally
# identical; the registry they read is shared. Windows is the primary
# development platform here, but the registry lists linux and macos for every
# component except the desktop GUI, so a Windows-only bootstrap would
# contradict it.
#
# Author: Isaac Travers

set -eu

usage() {
    cat <<'USAGE'
Usage: scripts/marp.sh [command] [options]

Commands:
  list      What the registry declares, and whether it is present here (default).
  clone     Clone whatever is missing. Never touches what is already there.
  status    Branch, uncommitted changes and drift from upstream, per repo.
  pull      Fast-forward every clean repository. Skips dirty ones.
  doctor    Check the workspace is sound, and in particular that the umbrella
            cannot absorb a component.

Options:
  --group all|components|related   Restrict to one category. Default: all.
                                   components are part of a MARP deployment;
                                   related are developed alongside but are not.
  --protocol https|ssh             Clone protocol. Default: https.
  -h, --help                       This text.

Examples:
  scripts/marp.sh clone
  scripts/marp.sh clone --group components --protocol ssh
  scripts/marp.sh doctor
USAGE
}

# The umbrella root is the parent of this script's directory. Deriving it
# rather than trusting the current directory means the script works when it is
# invoked from anywhere, including from inside a component.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(dirname -- "$SCRIPT_DIR")
REGISTRY="$REPO_ROOT/services/repos.yml"

# Directory names components used to have, as "old:new" pairs. Kept only so a
# part-migrated checkout is reported clearly instead of looking like a missing
# repository.
LEGACY_DIRECTORIES='MARE_API:MARP_API'

COMMAND=list
GROUP=all
PROTOCOL=https

while [ $# -gt 0 ]; do
    case "$1" in
        list|clone|status|pull|doctor) COMMAND=$1 ;;
        --group) GROUP=${2:?--group needs a value}; shift ;;
        --protocol) PROTOCOL=${2:?--protocol needs a value}; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown argument: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

case "$GROUP" in all|components|related) ;; *) echo "--group must be all, components or related" >&2; exit 2 ;; esac
case "$PROTOCOL" in https|ssh) ;; *) echo "--protocol must be https or ssh" >&2; exit 2 ;; esac

if [ -t 1 ]; then
    C_RED=$(printf '\033[31m'); C_YEL=$(printf '\033[33m')
    C_GRN=$(printf '\033[32m'); C_CYN=$(printf '\033[36m')
    C_DIM=$(printf '\033[2m');  C_OFF=$(printf '\033[0m')
else
    C_RED=; C_YEL=; C_GRN=; C_CYN=; C_DIM=; C_OFF=
fi

# Failures are counted in a file rather than in a variable. Nearly every check
# below runs inside a `... | while read` loop, which POSIX shells run in a
# subshell -- so a variable incremented there is discarded the moment the loop
# ends, and the script would exit 0 while printing failures. One byte appended
# per failure survives that, and the count is the file's size.
FAILURE_LOG=$(mktemp)
trap 'rm -f "$FAILURE_LOG"' EXIT

failure_count() { wc -c < "$FAILURE_LOG" | tr -d ' '; }

fail()  { printf 'x' >> "$FAILURE_LOG"; printf '  %sFAIL%s  %s\n' "$C_RED" "$C_OFF" "$1"; }
warn()  { printf '  %sWARN%s  %s\n' "$C_YEL" "$C_OFF" "$1"; }
pass()  { printf '  %sok%s    %s\n' "$C_DIM" "$C_OFF" "$1"; }
head1() { printf '%s%s%s\n' "$C_CYN" "$1" "$C_OFF"; }

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
#
# Deliberately not a YAML parser. Requiring a YAML library before the workspace
# even exists would defeat the point of a bootstrap script, and the one thing
# guaranteed present on every platform here is awk. Instead the registry's
# shape is constrained and documented in its own header: group keys at column
# 0, a repository key at two spaces, its fields at four, and folded values
# running on at six or more. Anything else is ignored rather than guessed at,
# and doctor fails on a registry it could not read -- so an edit that breaks
# this surfaces as a check failure rather than as a silently skipped
# repository.
#
# Emits one pipe-separated record per entry:
#   group|name|repository|directory|default_branch|visibility

read_registry() {
    [ -f "$REGISTRY" ] || { echo "Component registry not found at $REGISTRY" >&2; exit 1; }

    awk '
        function emit() {
            if (name != "") print grp "|" name "|" repo "|" dir "|" branch "|" vis
        }
        /^[ \t]*#/ { next }
        /^(components|related):[ \t]*$/ {
            emit(); grp = $0; sub(/:.*/, "", grp); name = ""; next
        }
        grp == "" { next }
        /^  [A-Za-z0-9_.-]+:[ \t]*$/ {
            emit()
            name = $0; sub(/^  /, "", name); sub(/:.*/, "", name)
            repo = ""; dir = ""; branch = ""; vis = ""
            next
        }
        /^    [a-z_]+:/ {
            if (name == "") next
            key = $0; sub(/^    /, "", key); sub(/:.*/, "", key)
            val = $0; sub(/^    [a-z_]+:[ \t]*/, "", val)
            gsub(/^[ \t]+|[ \t]+$/, "", val)
            # A folded or literal block marker carries no value of its own.
            if (val == ">" || val == "|" || val == "") next
            if (key == "repository") repo = val
            else if (key == "directory") dir = val
            else if (key == "default_branch") branch = val
            else if (key == "visibility") vis = val
        }
        END { emit() }
    ' "$REGISTRY" | {
        if [ "$GROUP" = all ]; then cat; else grep "^$GROUP|" || true; fi
    }
}

# The registry allows `repository: null` for a component that is planned but
# not yet created, so that the layout can be documented before the code exists.
# Those entries are real registry content, not errors, and every command has to
# step over them rather than try to clone "null".
is_clonable() { [ -n "$1" ] && [ "$1" != null ]; }

clone_url() {
    if [ "$PROTOCOL" = ssh ]; then printf 'git@github.com:%s.git\n' "$1"
    else printf 'https://github.com/%s.git\n' "$1"; fi
}

# The same repository is reached as https://github.com/Org/Name.git, as
# git@github.com:Org/Name.git, and with or without the .git suffix. Comparing
# raw URLs would report a false mismatch for a clone that is perfectly correct
# but was made over the other protocol.
remote_slug() {
    printf '%s' "$1" | sed -e 's/\.git$//' \
        -e 's#^git@[^:]*:##' \
        -e 's#^ssh://git@[^/]*/##' \
        -e 's#^https\{0,1\}://[^/]*/##' \
        -e 's#^/*##' -e 's#/*$##'
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_list() {
    printf '%-10s %-22s %-44s %-22s %-8s %-8s %s\n' GROUP NAME REPOSITORY DIRECTORY BRANCH VISIBLE PRESENT
    read_registry | while IFS='|' read -r grp name repo dir branch vis; do
        if [ -d "$REPO_ROOT/$dir/.git" ]; then present=yes
        elif [ -e "$REPO_ROOT/$dir" ]; then present='not a repo'
        else present=no; fi
        is_clonable "$repo" || repo='(not created)'
        printf '%-10s %-22s %-44s %-22s %-8s %-8s %s\n' "$grp" "$name" "$repo" "$dir" "$branch" "$vis" "$present"
    done
    printf '\nRegistry: %s\n' "$REGISTRY"
}

cmd_clone() {
    records=$(read_registry)
    [ -n "$records" ] || { fail "no entries read from $REGISTRY -- has its layout changed?"; return; }

    printf '%s\n' "$records" | while IFS='|' read -r grp name repo dir branch vis; do
        [ -n "$dir" ] || continue
        target="$REPO_ROOT/$dir"

        if ! is_clonable "$repo"; then
            warn "$name: no repository yet, nothing to clone"
            continue
        fi
        if [ -d "$target/.git" ]; then
            pass "$dir: already cloned"
            continue
        fi
        # A directory that exists without a .git is either a half-finished
        # clone or somebody's unrelated files. Cloning into it would either
        # fail messily or bury whatever is there, so stop and say so.
        if [ -e "$target" ]; then
            fail "$dir: exists but is not a Git repository; refusing to clone over it"
            continue
        fi

        printf '%sCloning %s -> %s (%s)%s\n' "$C_CYN" "$repo" "$dir" "$branch" "$C_OFF"
        if [ -n "$branch" ]; then
            set -- --branch "$branch"
        else
            set --
        fi
        if ! git clone "$@" "$(clone_url "$repo")" "$target"; then
            if [ "$vis" = private ]; then
                fail "$dir: clone failed (private repository: check your credentials)"
            else
                fail "$dir: clone failed"
            fi
        fi
    done

    if [ "$(failure_count)" -eq 0 ]; then
        printf '\n%sWorkspace ready. Open marp.code-workspace, or run: scripts/marp.sh doctor%s\n' "$C_GRN" "$C_OFF"
    fi
}

cmd_status() {
    printf '%-22s %-24s %-8s %s\n' DIRECTORY BRANCH CHANGES UPSTREAM
    read_registry | while IFS='|' read -r grp name repo dir branch vis; do
        [ -n "$dir" ] || continue
        if [ ! -d "$REPO_ROOT/$dir/.git" ]; then
            printf '%-22s %-24s %-8s %s\n' "$dir" - - 'not cloned'
            continue
        fi
        current=$(git -C "$REPO_ROOT/$dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')
        changes=$(git -C "$REPO_ROOT/$dir" status --porcelain 2>/dev/null | grep -c . || true)
        # No upstream is normal for a local-only branch, so it is reported
        # rather than treated as a problem.
        if counts=$(git -C "$REPO_ROOT/$dir" rev-list --left-right --count 'HEAD...@{u}' 2>/dev/null); then
            upstream="ahead $(echo "$counts" | awk '{print $1}'), behind $(echo "$counts" | awk '{print $2}')"
        else
            upstream='no upstream'
        fi
        printf '%-22s %-24s %-8s %s\n' "$dir" "$current" "$changes" "$upstream"
    done
}

cmd_pull() {
    read_registry | while IFS='|' read -r grp name repo dir branch vis; do
        [ -n "$dir" ] || continue
        if [ ! -d "$REPO_ROOT/$dir/.git" ]; then
            warn "$dir: not cloned"
            continue
        fi
        # Pulling over uncommitted work is how someone loses an afternoon.
        # Fast-forward only, and only when there is nothing to lose.
        if [ -n "$(git -C "$REPO_ROOT/$dir" status --porcelain)" ]; then
            warn "$dir: uncommitted changes, skipped"
            continue
        fi
        if out=$(git -C "$REPO_ROOT/$dir" pull --ff-only 2>&1); then
            pass "$dir: $(printf '%s' "$out" | head -n 1)"
        else
            fail "$dir: $(printf '%s' "$out" | head -n 1)"
        fi
    done
}

# The check that matters most is the ignore check. Every component lives as a
# directory inside this repository, so if one stops being ignored then a commit
# here quietly picks up either its files or a gitlink pointing at it. Neither
# belongs in the umbrella's history, and both are awkward to undo later.
# Verifying it is cheap, so it is verified rather than assumed.
cmd_doctor() {
    records=$(read_registry)

    head1 'Git'
    if version=$(git --version 2>/dev/null); then pass "$version"; else fail 'git is not on PATH'; fi

    head1 'Registry'
    if [ -z "$records" ]; then
        fail "no entries read from $REGISTRY -- has its layout changed?"
    else
        pass "$(printf '%s\n' "$records" | grep -c .) entries read"
    fi
    printf '%s\n' "$records" | while IFS='|' read -r grp name repo dir branch vis; do
        [ -n "$name" ] || continue
        [ -n "$dir" ] || fail "$name: registry entry has no directory"
        [ -n "$branch" ] || fail "$name: registry entry has no default_branch"
    done

    head1 'Umbrella ignores every component directory'
    printf '%s\n' "$records" | while IFS='|' read -r grp name repo dir branch vis; do
        [ -n "$dir" ] || continue
        # Asking about a path inside the directory rather than about the
        # directory itself. A trailing slash makes check-ignore report a false
        # positive for a directory that no rule covers at all, and a bare name
        # fails to match a directory-only rule when the directory is not yet on
        # disk. "<dir>/.git" is right in both cases, and every one of these
        # directories is a Git repository, so it is the honest thing to ask
        # about.
        if git -C "$REPO_ROOT" check-ignore --quiet -- "$dir/.git"; then
            pass "$dir/ is ignored"
        else
            fail "$dir/ is NOT ignored -- add it to .gitignore before committing here"
        fi
    done

    head1 'Component clones'
    printf '%s\n' "$records" | while IFS='|' read -r grp name repo dir branch vis; do
        [ -n "$dir" ] || continue
        if [ ! -e "$REPO_ROOT/$dir" ]; then
            warn "$dir: not cloned (run: scripts/marp.sh clone)"
            continue
        fi
        if [ ! -d "$REPO_ROOT/$dir/.git" ]; then
            fail "$dir: present but not a Git repository"
            continue
        fi
        is_clonable "$repo" || continue
        actual=$(remote_slug "$(git -C "$REPO_ROOT/$dir" remote get-url origin 2>/dev/null || true)")
        expected=$(remote_slug "$repo")
        if [ "$actual" = "$expected" ]; then
            pass "$dir: origin is $expected"
        else
            fail "$dir: origin is ${actual:-none}, registry says $expected"
        fi
    done

    head1 'Former directory names'
    any_legacy=0
    for pair in $LEGACY_DIRECTORIES; do
        old=${pair%%:*}; new=${pair#*:}
        [ -e "$REPO_ROOT/$old" ] || continue
        any_legacy=1
        # An empty shell left behind by a part-finished rename is a different
        # problem from a directory that still holds the repository, and telling
        # someone to rename a directory they have already renamed would send
        # them looking for work that is done.
        if [ -z "$(ls -A "$REPO_ROOT/$old" 2>/dev/null)" ] && [ -d "$REPO_ROOT/$new/.git" ]; then
            warn "$old/ is an empty leftover from the rename to $new/; delete it (something may still hold it open)"
        else
            warn "$old/ is still here; it was renamed to $new/ -- rename it so the workspace file and the registry find it"
        fi
    done
    [ "$any_legacy" -eq 1 ] || pass 'none present'

    head1 'Umbrella working tree'
    visible=$(git -C "$REPO_ROOT" status --porcelain)
    leaked=
    for dir in $(printf '%s\n' "$records" | awk -F'|' '{print $4}'); do
        [ -n "$dir" ] || continue
        if printf '%s\n' "$visible" | grep -q -- "$dir"; then
            leaked="$leaked $dir"
        fi
    done
    if [ -n "$leaked" ]; then
        fail "the umbrella sees changes under${leaked} -- a commit here would carry them"
    else
        pass 'no component paths visible to the umbrella'
    fi

    printf '\n'
    if [ "$(failure_count)" -eq 0 ]; then
        printf '%sWorkspace looks sound.%s\n' "$C_GRN" "$C_OFF"
    else
        printf '%s%s problem(s) found.%s\n' "$C_RED" "$(failure_count)" "$C_OFF"
    fi
}

case "$COMMAND" in
    list)   cmd_list ;;
    clone)  cmd_clone ;;
    status) cmd_status ;;
    pull)   cmd_pull ;;
    doctor) cmd_doctor ;;
esac

[ "$(failure_count)" -eq 0 ] || exit 1
exit 0
