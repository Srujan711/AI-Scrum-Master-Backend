# 🚀 Quick Start: Free AI Setup (No OpenAI Required!)

You have **3 options** for free AI. Choose based on your preference:

---

## ⚡ Option 1: Ollama (RECOMMENDED - 100% Free, Local)

**Best for development** - No API keys, completely private

### Installation (5 minutes):

```bash
# 1. Install Ollama
brew install ollama

# 2. Start Ollama (keep this terminal open)
ollama serve

# 3. In a NEW terminal, pull a model
ollama pull llama3.2  # 2GB download, fast
# OR for better quality:
ollama pull llama3.1  # 4.7GB download, slower but better

# 4. Update your .env file:
echo "" >> .env
echo "# Ollama (Free Local AI)" >> .env
echo "USE_OLLAMA=true" >> .env
echo "OLLAMA_BASE_URL=http://localhost:11434" >> .env
echo "OLLAMA_MODEL=llama3.2" >> .env

# 5. Done! Start your backend:
python3 -m uvicorn app.main:app --reload
```

**Pros:**
- ✅ FREE forever
- ✅ No API keys needed
- ✅ Works offline
- ✅ Private (data never leaves your Mac)

**Cons:**
- ❌ Need to keep `ollama serve` running
- ❌ Uses 2-5GB disk space

---

## 🌩️ Option 2: Groq (Free Cloud, Super Fast)

**Best if you want cloud-based** - 14,400 free requests/day

### Setup (2 minutes):

```bash
# 1. Sign up (no credit card): https://console.groq.com
# 2. Get your API key from the dashboard
# 3. Update .env:

# Comment out the placeholder OpenAI key:
# OPENAI_API_KEY=sk-placeholder-replace-with-real-key

# Add Groq config:
OPENAI_API_BASE=https://api.groq.com/openai/v1
OPENAI_API_KEY=gsk_YOUR_GROQ_KEY_HERE
OPENAI_MODEL=llama-3.1-8b-instant

# 4. Done! Start your backend:
python3 -m uvicorn app.main:app --reload
```

**Pros:**
- ✅ FREE (generous limits)
- ✅ 10x faster than OpenAI
- ✅ No installation needed
- ✅ Great quality (Llama 3.1)

**Cons:**
- ❌ Requires internet
- ❌ 2-minute signup needed

---

## 🤗 Option 3: Together.ai ($25 Free Credits)

### Setup (2 minutes):

```bash
# 1. Sign up: https://api.together.xyz
# 2. Get API key
# 3. Update .env:

OPENAI_API_BASE=https://api.together.xyz/v1
OPENAI_API_KEY=YOUR_TOGETHER_KEY_HERE
OPENAI_MODEL=meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo

# 4. Done! Restart backend
```

---

## 🧪 Testing Your Setup

After choosing an option above:

```bash
# 1. Start your backend
python3 -m uvicorn app.main:app --reload

# 2. Test health check
curl http://localhost:8000/health

# Should return: {"status":"healthy",...}

# 3. Once you complete Task 2 (seed data) and Task 3 (standup agent),
#    you'll be able to test AI-generated standup summaries!
```

---

## My Recommendation: Use Ollama

**Why?**
1. Zero cost, forever
2. No API keys to manage
3. Data stays on your machine
4. Perfect for Weeks 1-4 development
5. You can switch to Groq later if needed

**Installation:**
```bash
brew install ollama
ollama serve  # In one terminal
ollama pull llama3.2  # In another terminal
```

Then add to `.env`:
```bash
USE_OLLAMA=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

---

## Comparison at a Glance

| Feature | Ollama | Groq | Together.ai |
|---------|--------|------|-------------|
| Cost | FREE ✅ | FREE* ✅ | $25 credits |
| Speed | Fast | Ultra Fast | Medium |
| Quality | Good (8/10) | Great (8.5/10) | Good (8/10) |
| Setup Time | 5 min | 2 min | 2 min |
| API Key | NO ✅ | Yes | Yes |
| Works Offline | YES ✅ | No | No |

---

## Next Steps

1. Choose an option above and set it up
2. Continue with **Task 2: Create Seed Data**
3. Build your first AI feature!

Questions? Check [docs/AI_PROVIDER_COMPARISON.md](docs/AI_PROVIDER_COMPARISON.md) for detailed comparisons.