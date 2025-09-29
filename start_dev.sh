#!/bin/bash

# Development Startup Script for AI Scrum Master
# This script checks and starts all required services

set -e

echo "🚀 AI Scrum Master - Development Startup"
echo "=========================================="
echo ""

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama is not installed"
    echo "Please install it with: brew install ollama"
    exit 1
fi

echo "✅ Ollama is installed"

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "⚠️  Ollama is not running"
    echo ""
    echo "Starting Ollama in background..."
    nohup ollama serve > /tmp/ollama.log 2>&1 &
    echo "✅ Ollama started (logs: /tmp/ollama.log)"
    sleep 2
else
    echo "✅ Ollama is already running"
fi

# Check if model is available
echo ""
echo "📦 Checking for llama3.2 model..."
if ollama list 2>/dev/null | grep -q "llama3.2"; then
    echo "✅ Model llama3.2 is available"
else
    echo "❌ Model llama3.2 not found"
    echo "Downloading... (this may take a few minutes)"
    ollama pull llama3.2
fi

echo ""
echo "✅ All prerequisites are ready!"
echo ""
echo "Starting FastAPI backend..."
echo "=========================================="
echo ""

# Set environment variable and start backend
export USE_OLLAMA=true
python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000