#!/usr/bin/env bash

set -euo pipefail

branch="${1:-19.0}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
default_source_repo="${repo_root}/addons/.odoomates-source"
legacy_source_repo="${repo_root}/addons/odoomates"
source_repo="${ODOOMATES_SOURCE_DIR:-${default_source_repo}}"
remote_url="${ODOOMATES_REPO_URL:-https://github.com/odoomates/odooapps.git}"
target_dir="${2:-addons/odoomates-${branch%%.*}}"
target_path="${repo_root}/${target_dir}"
local_branch="worktree-${branch}"

if [[ ! -d "${source_repo}/.git" && -d "${legacy_source_repo}/.git" && "${source_repo}" == "${default_source_repo}" ]]; then
  source_repo="${legacy_source_repo}"
fi

if [[ ! -d "${source_repo}/.git" ]]; then
  mkdir -p "$(dirname "${source_repo}")"
  git clone "${remote_url}" "${source_repo}"
fi

git -C "${source_repo}" fetch --all --prune

if [[ -e "${target_path}" ]]; then
  echo "Target worktree already exists: ${target_path}" >&2
  exit 0
fi

if ! git -C "${source_repo}" show-ref --verify --quiet "refs/remotes/origin/${branch}"; then
  echo "Missing upstream branch origin/${branch} in ${source_repo}" >&2
  exit 1
fi

if git -C "${source_repo}" show-ref --verify --quiet "refs/heads/${local_branch}"; then
  git -C "${source_repo}" worktree add "${target_path}" "${local_branch}"
else
  git -C "${source_repo}" worktree add -b "${local_branch}" "${target_path}" "refs/remotes/origin/${branch}"
fi

echo "Prepared ${target_path} from ${branch} using ${source_repo}"
