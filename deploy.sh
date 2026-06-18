#!/bin/bash
set -e

echo "=== Pushing to GitHub ==="
git push origin main

echo "=== Pushing to HuggingFace ==="
git push hf main --force

echo "✅ Done! HF Space rebuilding..."
