# AI Orchestrator V2

Bidirektionales Master-Worker System mit modularem Rollentausch zwischen **Claude Code** und **Codex CLI**.

## Features

- **Zielorientierung**: GOAL.txt definiert das Implementierungsziel
- **Modularer Rollentausch**: Claude ↔ Codex Rollen jederzeit vertauschbar
- **Autonome Entscheidung**: Master entscheidet basierend auf Analyse
- **Verifikation**: Worker-Output wird vom Master verifiziert
- **Korrektur-Schleife**: Automatische Korrekturen bei Fehlern

## Architektur

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AI-ORCHESTRATOR V2 MIT ROLLENTAUSCH                       │
│                                                                              │
│  ┌─────────────────┐                           ┌─────────────────┐          │
│  │   GOAL.txt      │                           │   MASTER        │          │
│  │   (Zielbild)    │──────────────────────────▶│   (Entscheider) │          │
│  └─────────────────┘                           │                 │          │
│                                                │  Claude / Codex │          │
│  ┌─────────────────┐   Entscheidung           │  (konfigurierb.)│          │
│  │   WORKER        │◀──────────────────────────│                 │          │
│  │ (Implementierer)│                           └────────┬────────┘          │
│  │                 │                                    │                   │
│  │  Codex / Claude │   Verifikation                     │                   │
│  │  (konfigurierb.)│───────────────────────────────────▶│                   │
│  └─────────────────┘                                    │                   │
│                                                         ▼                   │
│                                              ┌─────────────────┐            │
│                                              │  GOAL ACHIEVED? │            │
│                                              │  (Zielabgleich) │            │
│                                              └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Clone repository
git clone https://github.com/BenniProbst/ai-orchestrator-v2.git
cd ai-orchestrator-v2

# Install dependencies
pip install -r requirements.txt

# Or install as package
pip install -e .
```

## Quick Start

1. **Goal definieren** - Erstelle eine `GOAL.txt`:

```markdown
# Mein Implementierungsziel

## Description
Beschreibung was erreicht werden soll.

## Acceptance Criteria
- [ ] Kriterium 1
- [ ] Kriterium 2

## Constraints
- Einschränkung 1
```

2. **Orchestrator starten**:

```bash
python -m src.orchestrator --goal GOAL.txt --work-dir ./project
```

3. **Mit Rollentausch**:

```bash
# Codex als Master, Claude als Worker
python -m src.orchestrator --master codex --worker claude
```

## Konfiguration

### config.yaml

```yaml
orchestrator:
  max_iterations: 20
  timeout_seconds: 300
  checkpoint_interval: 5

roles:
  master: claude
  worker: codex

agents:
  claude:
    command: claude
    timeout: 120
  codex:
    command: codex
    timeout: 300
    full_auto: true
```

## Workflow

1. **Master analysiert** aktuellen Stand und GOAL.txt
2. **Master entscheidet** nächsten Schritt (IMPLEMENT/SKIP/DONE)
3. **Worker implementiert** die Anweisung
4. **Master verifiziert** das Ergebnis
5. Bei Fehlern: **Korrektur-Schleife**
6. Wiederholen bis GOAL erreicht

## API

### Orchestrator

```python
from src import Orchestrator, OrchestratorConfig

config = OrchestratorConfig(
    master_agent_type=AgentType.CLAUDE,
    worker_agent_type=AgentType.CODEX,
    max_iterations=20,
)

orchestrator = Orchestrator(config)

# Run
success = orchestrator.run()

# Swap roles
orchestrator.swap_roles()

# Get status
status = orchestrator.get_status()
```

### Goal Parser

```python
from src.goal import GoalParser, Goal

parser = GoalParser()
goal = parser.parse_file("GOAL.txt")

print(f"Title: {goal.title}")
print(f"Progress: {goal.progress_percentage}%")
```

## Tests

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

## Projektstruktur

```
ai-orchestrator-v2/
├── src/
│   ├── __init__.py
│   ├── orchestrator.py      # Haupt-Orchestrator
│   ├── agents/              # Agent-Adapter
│   │   ├── base.py          # IAgent Interface
│   │   ├── claude_agent.py
│   │   ├── codex_agent.py
│   │   └── factory.py
│   ├── roles/               # Rollen-Strategien
│   │   ├── base.py          # IRoleStrategy
│   │   ├── master.py
│   │   └── worker.py
│   ├── goal/                # Ziel-Management
│   │   ├── parser.py
│   │   ├── validator.py
│   │   └── progress.py
│   ├── protocol/            # Kommunikation
│   │   ├── messages.py
│   │   └── serializer.py
│   └── verification/        # Verifikation
│       └── checker.py
├── tests/                   # Test Suite
├── examples/                # Beispiel-Goals
├── GOAL.txt                 # Aktives Ziel
├── config.yaml              # Konfiguration
└── README.md
```

## Voraussetzungen

- Python 3.11+
- Claude Code CLI installiert (`claude`)
- Codex CLI installiert (`codex`)

## Lizenz

MIT License

## Autor

BenniProbst
