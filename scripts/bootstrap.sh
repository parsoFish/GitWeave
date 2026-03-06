#!/bin/bash
set -e

echo "🚀 Starting GitWeave Bootstrap..."

# Check Prerequisites
echo "Checking prerequisites..."

if ! command -v git &> /dev/null; then
    echo "❌ git is not installed."
    exit 1
fi
echo "✅ git found"

if ! command -v terraform &> /dev/null; then
    echo "❌ terraform is not installed."
    exit 1
fi
echo "✅ terraform found"

if ! command -v python3 &> /dev/null; then
    echo "❌ python3 is not installed."
    exit 1
fi
echo "✅ python3 found"

# Check Directory Structure
echo "Verifying directory structure..."
REQUIRED_DIRS=("modules" "config" "infra" "metrics" ".github/workflows")
for dir in "${REQUIRED_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        echo "⚠️  Directory '$dir' missing. Creating..."
        mkdir -p "$dir"
    else
        echo "✅ $dir exists"
    fi
done

echo "🎉 Bootstrap check complete! You can now proceed to 'infra/' to initialize Terraform."
