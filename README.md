# TFT AI Stats Agent (LLM + MCP + Database)

This project is a small end-to-end AI system that:

1. Collects high-level Teamfight Tactics (TFT) match data from Riot's API  
2. Stores and normalizes it into a PostgreSQL database  
3. Exposes statistical queries through a FastAPI backend  
4. Uses a local LLM (via Ollama) connected through an MCP tool server  
5. Allows natural language questions like:

> “What is the best 2nd item for Yunara if she already has Guinsoo?”

The LLM does **not guess** — it calls a tool that queries real match data from the database.

---

# Architecture Overview

User
↓
Local LLM (Ollama - qwen3:8b)
↓
Agent Loop (ollama_agent.py)
↓
MCP Server (mcp_server.py)
↓
FastAPI Stats Backend
↓
PostgreSQL Database


The system uses:

- **Riot API** → Data ingestion
- **PostgreSQL** → Match storage & normalization
- **FastAPI** → Stats endpoints
- **MCP (Model Context Protocol)** → Tool exposure
- **Ollama** → Local LLM runtime
- **qwen3:8b** → Local instruct model

---

#What Data Is Used?

- High-level ranked TFT matches (Masters/GM+)
- Units
- Traits
- Items
- Placement
- Player performance metrics

From this data we compute:

- Top 4 rate
- Average placement
- Sample size filtering
- Conditional item performance (e.g., given item X, what's best next item?)

---

#Setup Instructions

## 1) Start PostgreSQL (Docker)

```bash
docker compose up -d
```
## 2) Run FastAPI Backend
```
uvicorn api:app --reload
```
Verify:
http://127.0.0.1:8000/docs

## 3) Install & Run Ollama
Download Ollama:
https://ollama.com

Pull the model: 
```
ollama pull qwen3:8b
```

## 4) Run the MCP
```
Run MCP Server
```
## 5) Run the agent
```
python ollama_agent.py
```

An example query could look like : "Yunara with Guinsoo what is the best 2nd item?"
