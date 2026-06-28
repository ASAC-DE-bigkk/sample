#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}"

git submodule sync --recursive
git submodule update --init --recursive dags dbt

for path in dags dbt; do
  echo "Updating ${path} from origin/main"
  git -C "${path}" checkout -q main

  if git -C "${path}" ls-remote --exit-code --heads origin main >/dev/null 2>&1; then
    git -C "${path}" fetch origin main
    git -C "${path}" merge --ff-only FETCH_HEAD
  else
    echo "Skipping ${path}: origin/main is not available yet"
  fi
done
