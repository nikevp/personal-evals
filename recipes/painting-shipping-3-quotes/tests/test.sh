#!/bin/bash
set -euo pipefail

rubric_dir=$(mktemp -d)
trap 'rm -rf "$rubric_dir"' EXIT
cp /tests/reshipper_contacts.toml /tests/contact_research_judge.md "$rubric_dir/"

uvx --from 'harbor-rewardkit[documents]==0.1.*' rewardkit "$rubric_dir" \
  --workspace /logs/artifacts
