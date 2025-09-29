#!/bin/bash

# Ollama Setup Script for AI Scrum Master
# This script helps you set up Ollama as a free alternative to OpenAI

set -e

echo "🚀 AI Scrum Master - Ollama Setup"
echo "=================================="
echo ""

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama is not installed."
    echo ""
    echo "Please install Ollama:"
    echo "  Option 1: brew install ollama"
    echo "  Option 2: Download from https://ollama.ai"
    echo ""
    exit 1
fi

echo "✅ Ollama is installed"
echo ""

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "⚠️  Ollama service is not running"
    echo "Starting Ollama..."
    echo ""
    echo "Run this in a separate terminal:"
    echo "  ollama serve"
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo "✅ Ollama service is running"
echo ""

# List available models
echo "📦 Checking installed models..."
MODELS=$(ollama list 2>/dev/null || echo "")

if [ -z "$MODELS" ]; then
    echo "No models installed yet."
else
    echo "Installed models:"
    echo "$MODELS"
fi
echo ""

# Recommend and pull a model
echo "📥 Recommended models:"
echo "  1. llama3.2 (3B) - Fast, good for development [~2GB]"
echo "  2. llama3.1 (8B) - Better quality [~4.7GB]"
echo "  3. mistral (7B) - Good balance [~4.1GB]"
echo ""

read -p "Which model would you like to install? (1/2/3 or 'skip'): " choice

case $choice in
    1)
        echo "Installing llama3.2..."
        ollama pull llama3.2
        MODEL_NAME="llama3.2"
        ;;
    2)
        echo "Installing llama3.1..."
        ollama pull llama3.1
        MODEL_NAME="llama3.1"
        ;;
    3)
        echo "Installing mistral..."
        ollama pull mistral
        MODEL_NAME="mistral"
        ;;
    skip)
        echo "Skipping model installation."
        MODEL_NAME="llama3.2"
        ;;
    *)
        echo "Invalid choice. Using llama3.2 as default."
        ollama pull llama3.2
        MODEL_NAME="llama3.2"
        ;;
esac

echo ""
echo "✅ Model ready: $MODEL_NAME"
echo ""

# Test the model
echo "🧪 Testing model..."
RESPONSE=$(curl -s http://localhost:11434/api/generate -d "{
  \"model\": \"$MODEL_NAME\",
  \"prompt\": \"Say 'Hello! I am ready to help your team.' in one sentence.\",
  \"stream\": false
}" | python3 -c "import sys, json; print(json.load(sys.stdin).get('response', 'Error'))")

echo "Response: $RESPONSE"
echo ""

# Update .env file
echo "📝 Updating .env file..."
if [ -f .env ]; then
    # Comment out existing OpenAI settings
    sed -i.bak 's/^OPENAI_API_KEY=/# OPENAI_API_KEY=/' .env
    sed -i.bak 's/^OPENAI_MODEL=/# OPENAI_MODEL=/' .env

    # Add Ollama settings
    if ! grep -q "OLLAMA_BASE_URL" .env; then
        echo "" >> .env
        echo "# Ollama Settings (Free Local AI)" >> .env
        echo "OLLAMA_BASE_URL=http://localhost:11434" >> .env
        echo "OLLAMA_MODEL=$MODEL_NAME" >> .env
        echo "USE_OLLAMA=true" >> .env
    fi

    echo "✅ .env file updated"
else
    echo "⚠️  .env file not found. Please create it from .env.example"
fi

echo ""
echo "🎉 Setup Complete!"
echo ""
echo "Next steps:"
echo "  1. Make sure Ollama is running: ollama serve"
echo "  2. Start your backend: python3 -m uvicorn app.main:app --reload"
echo "  3. Test AI features with free local AI!"
echo ""
echo "💡 Tip: You can switch models anytime with: ollama pull <model-name>"