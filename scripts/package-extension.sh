#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "${script_dir}/.." && pwd)"
extension_dir="${repo_dir}/extension"
dist_dir="${repo_dir}/dist"
package_path="${dist_dir}/tailr-extension.zip"
temp_dir="$(mktemp -d)"
temp_package="${temp_dir}/tailr-extension.zip"

mkdir -p "${dist_dir}"

(
  cd "${extension_dir}"
  zip -q -r "${temp_package}" . \
    -x '*.DS_Store' \
    -x '__MACOSX/*'
)

mv -f "${temp_package}" "${package_path}"
rmdir "${temp_dir}"

unzip -tq "${package_path}"
printf '%s\n' "Built ${package_path}"
