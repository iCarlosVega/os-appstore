#!/usr/bin/env bash
# Run from a normal Terminal after the migration hands off a stable baseline.
set -euo pipefail

if [[ "${1:-}" != "--migration-ready" || "$#" -ne 1 ]]; then
  printf '%s\n' 'Usage: bash scripts/prepare-ai-worktrees.sh --migration-ready' >&2
  printf '%s\n' 'Run only after the migration finishes or explicitly hands off the AI modules.' >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$repo_root"
plan='docs/superpowers/plans/2026-10-11-ai-agent-parallel.md'
required=(
  "$plan" backend/requirements.txt backend/app/db.py backend/app/store.py
  backend/app/models.py backend/app/config.py backend/app/jev.py
  backend/app/budget.py backend/app/search.py backend/app/github.py
  backend/app/discovery.py backend/app/maintenance.py backend/app/jobs.py
  backend/app/discord.py backend/app/cli.py
)
for item in "${required[@]}"; do
  if [[ ! -f "$item" ]]; then
    printf 'Missing baseline file: %s\n' "$item" >&2
    exit 1
  fi
done

new_repo=false
if [[ ! -e .git ]]; then
  if git rev-parse --show-toplevel >/dev/null 2>&1; then
    printf '%s\n' 'Refusing to initialize inside a different parent Git repository.' >&2
    exit 1
  fi
  git init -b main
  new_repo=true
fi

actual_root="$(git rev-parse --show-toplevel)"
actual_root="$(cd "$actual_root" && pwd -P)"
if [[ "$actual_root" != "$repo_root" ]]; then
  printf '%s\n' 'Git root differs from the project root; stopping.' >&2
  exit 1
fi

# Local exclusions avoid edits to migration-owned .gitignore.
exclude_file="$(git rev-parse --git-path info/exclude)"
mkdir -p "$(dirname "$exclude_file")"
touch "$exclude_file"
for pattern in '/.worktrees/' '__pycache__/' '*.py[cod]' '.venv/'; do
  if ! grep -Fxq "$pattern" "$exclude_file"; then
    printf '%s\n' "$pattern" >> "$exclude_file"
  fi
done
git check-ignore -q .worktrees/probe

if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  # Never sweep credentials, databases, generated files, or unknown root files
  # into the initial commit. Existing repositories with unborn HEAD are manual.
  if [[ "$new_repo" != true ]]; then
    printf '%s\n' 'Repository has no commit. Commit the migration baseline, then rerun.' >&2
    exit 1
  fi
  paths=(
    .gitignore .dockerignore .ignore .env.example Dockerfile compose.yaml
    README.md package.json package-lock.json tsconfig.json next.config.ts
    next-env.d.ts src scripts migrations docs backend/requirements.txt backend/app
  )
  existing_paths=()
  for item in "${paths[@]}"; do
    [[ ! -e "$item" ]] || existing_paths+=("$item")
  done
  git add -- "${existing_paths[@]}"
  git commit -m 'chore: snapshot migration baseline and AI parallel handoffs'
fi

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  printf '%s\n' 'Checkout has pending changes. Commit the migration and handoffs before rerunning.' >&2
  git status --short
  exit 1
fi

git cat-file -e "HEAD:$plan"
base_commit="$(git rev-parse HEAD)"
names=(ai-provider-budget ai-catalog-search ai-discovery ai-maintenance-jobs)
branches=(ai/provider-budget ai/catalog-search ai/discovery ai/maintenance-jobs)
mkdir -p .worktrees

for index in "${!names[@]}"; do
  name="${names[$index]}"
  branch="${branches[$index]}"
  target="$repo_root/.worktrees/$name"
  handoff="docs/superpowers/handoffs/$name.md"
  git cat-file -e "HEAD:$handoff"
  if [[ -e "$target" ]]; then
    if [[ "$(git -C "$target" rev-parse --show-toplevel)" != "$target" ||
          "$(git -C "$target" branch --show-current)" != "$branch" ||
          "$(git -C "$target" rev-parse --git-common-dir)" != "$(git rev-parse --path-format=absolute --git-common-dir)" ]]; then
      printf 'Existing path is not the expected linked worktree: %s\n' "$target" >&2
      exit 1
    fi
    if ! git merge-base --is-ancestor "$base_commit" "$branch"; then
      printf 'Existing branch does not contain baseline %s: %s\n' "$base_commit" "$branch" >&2
      exit 1
    fi
    printf 'Reusing %s on %s\n' "$target" "$branch"
  else
    if git show-ref --verify --quiet "refs/heads/$branch"; then
      printf 'Branch already exists without this worktree: %s; inspect it before proceeding.\n' "$branch" >&2
      exit 1
    fi
    git worktree add -b "$branch" "$target" "$base_commit"
  fi
done

printf '\nCommon baseline: %s\n' "$base_commit"
git worktree list
printf '\nOpen one Codex session per AI worktree. Read %s and the matching handoff.\n' "$plan"
printf '%s\n' 'Dependencies, behavioral checks, live integrations, and deployment have not been run by this script.'
