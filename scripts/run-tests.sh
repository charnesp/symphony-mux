#!/bin/bash
# Run tests script for pre-commit hooks

set -e

echo "Running Stokowski tests..."

# Run pytest with coverage and short traceback
python -m pytest tests/ -v --tb=short "$@"

echo "Tests passed!"
