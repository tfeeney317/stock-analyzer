#!/bin/bash
# Setup script - Run this in /Users/feeneyfam/stock-analyzer

echo "Stock Analyzer Deployment Setup"
echo "================================="

# Check if gh is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI not installed."
    echo ""
    echo "Run: brew install gh"
    echo ""
    echo "Then come back and run: ./deploy.sh"
    exit 1
fi

# Check if already logged in
gh auth status || (echo "Run: gh auth login" && exit 1)

echo "✅ GitHub CLI ready"

# Initialize git if not already
if [ ! -d .git ]; then
    echo "📦 Initializing git..."
    git init
    git add -A
    git commit -m "Initial commit - Stock Analyzer"
fi

# Ask for repo name
echo ""
read -p "Enter GitHub repo name (e.g., stock-analyzer): " REPO_NAME

# Create repo
echo "Creating GitHub repo..."
gh repo create $REPO_NAME --private --source=. --push

echo ""
echo "✅ Deployed to GitHub!"
echo ""
echo "Now deploy to cloud:"
echo "1. Frontend: Go to https://vercel.com and import this repo"
echo "2. Backend: Go to https://render.com and connect the backend folder"
echo ""
echo "For frontend on Vercel:"
echo "  - Build command: npm run build"
echo "  - Output directory: .next"
echo "  - Environment variable: NEXT_PUBLIC_API_URL = your-render-backend-url"
echo ""
echo "For backend on Render:"
echo "  - Build command: pip install -r requirements.txt"  
echo "  - Start command: uvicorn app.main:app --host 0.0.0.0 --port \$PORT"
echo "  - Environment: Add your Yahoo Finance data source (optional)"