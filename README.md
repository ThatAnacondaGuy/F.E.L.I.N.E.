# Meow OS — Personal AI Chief of Staff

A local-first, multi-agent Personal Operating System that understands, organizes, prioritizes, plans, monitors, and helps execute Aniket's digital life.

## Quick Start

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Run setup wizard
python setup_wizard.py

# Start the server
python -m uvicorn api.main:app --reload --port 8000
```

Then open http://localhost:8000

## Architecture

- **Core**: Orchestrator, Planner, Prioritizer, Event Bus, Audit Trail
- **Agents**: 11 specialized agents (Chief of Staff, Academic, Career, etc.)
- **Integrations**: Gmail, Calendar, Classroom, GitHub, RSS, Web Scraper
- **Models**: Local LLM via Ollama, ChromaDB vector store
- **Memory**: Personal knowledge graph, semantic search, persistent memory
- **UI**: Dark-themed command center dashboard

## License

Private — for Aniket's personal use.
