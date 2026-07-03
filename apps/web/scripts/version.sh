#!/usr/bin/env bash
set -euo pipefail

GIT_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

if [ -n "$GIT_TAG" ]; then
  echo "$GIT_TAG-$GIT_COMMIT"
else
  echo "0.0.0-$GIT_COMMIT"
fi
