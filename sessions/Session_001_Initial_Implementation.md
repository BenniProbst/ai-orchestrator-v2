# Session 001: AI Orchestrator V2 - Vollständige Implementierung

**Datum:** 2026-01-07
**Dauer:** ~2 Stunden
**Autor:** Claude Code (claude-opus-4-5-20251101)
**Status:** ✅ ABGESCHLOSSEN

---

## 📋 Inhaltsverzeichnis

1. [Projektziel und Anforderungen](#1-projektziel-und-anforderungen)
2. [Architektur-Entscheidungen](#2-architektur-entscheidungen)
3. [Implementierte Komponenten](#3-implementierte-komponenten)
4. [Dateistruktur](#4-dateistruktur)
5. [Interface-Definitionen](#5-interface-definitionen)
6. [Test-Suite](#6-test-suite)
7. [Konfiguration](#7-konfiguration)
8. [Git Repository](#8-git-repository)
9. [Verwendungsbeispiele](#9-verwendungsbeispiele)
10. [Bekannte Einschränkungen](#10-bekannte-einschränkungen)
11. [Zukünftige Erweiterungen](#11-zukünftige-erweiterungen)
12. [Änderungsprotokoll](#12-änderungsprotokoll)

---

## 1. Projektziel und Anforderungen

### 1.1 Ausgangslage

Das Projekt basiert auf dem Vorgänger `claude-codex-orchestrator` (V1), der eine einfache
unidirektionale Kommunikation zwischen Claude Code und Codex CLI ermöglichte.

**V1 Einschränkungen:**
- Manuelle Interaktion erforderlich
- Keine echte Bidirektionalität
- Kein Rollentausch möglich
- Keine Zielvalidierung

### 1.2 Anforderungen für V2

| Anforderung | Priorität | Status |
|-------------|-----------|--------|
| Zielorientierung (GOAL.txt) | Hoch | ✅ |
| Modularer Rollentausch | Hoch | ✅ |
| Autonome Entscheidungsfindung | Hoch | ✅ |
| Verifikation nach Implementierung | Hoch | ✅ |
| Korrektur-Schleife | Mittel | ✅ |
| Checkpoint/Resume | Mittel | ✅ |
| 60+ Unit/Integration Tests | Hoch | ✅ |
| GitHub Repository | Mittel | ✅ |

### 1.3 Benutzeranforderungen (Original)

> "Bitte Plane ein Python skript nach dem letzten claude master Projekt. Das Ziel ist es
> eine Anfrage und ein in einer Textdatei festgeschriebenes Zielbild für eine Implementierung
> zu erreichen. Claude code kennt auf einer Implementierung alle Befehle um eine codex session
> zu bedienen. Dann entscheidet es bezüglich der Rückgaben von codex nach eigener Nachforschung,
> ob ein Schritt sinnvoll ist und per Definition implementiert werden sollte oder besser nicht.
> Die Rollen von Claude code und codex sollen Modular gegeneinander vertauscht werden können..."

---

## 2. Architektur-Entscheidungen

### 2.1 Übergeordnete Architektur

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

### 2.2 Design-Patterns

| Pattern | Verwendung | Begründung |
|---------|------------|------------|
| **Strategy Pattern** | Rollen (Master/Worker) | Ermöglicht Rollentausch ohne Codeänderung |
| **Factory Pattern** | Agent-Erstellung | Zentrale Konfiguration und Instanziierung |
| **Template Method** | IAgent Interface | Gemeinsame Struktur für verschiedene AI-Agents |
| **Observer** | Progress Tracking | Statusupdates ohne enge Kopplung |
| **Memento** | Checkpoint/Resume | Session-Zustand speichern und wiederherstellen |

### 2.3 Schichtenarchitektur

```
┌─────────────────────────────────────────────┐
│            Orchestrator (Steuerung)          │
├─────────────────────────────────────────────┤
│     Roles (Master/Worker Strategien)         │
├─────────────────────────────────────────────┤
│        Agents (Claude/Codex Adapter)         │
├─────────────────────────────────────────────┤
│   Goal Parser │ Protocol │ Verification      │
├─────────────────────────────────────────────┤
│            External CLIs (claude, codex)     │
└─────────────────────────────────────────────┘
```

### 2.4 Entscheidung: Dateibasierte IPC vs Named Pipes

**Gewählt:** Dateibasierte IPC (wie V1)

**Begründung:**
- Plattformunabhängig (Windows/Linux/macOS)
- Einfacheres Debugging (Dateien können inspiziert werden)
- Checkpoint/Resume nativ möglich
- Codex CLI `exec` Mode unterstützt keine echten Pipes

**Trade-offs:**
- Höhere Latenz als Named Pipes
- Dateisystem-I/O erforderlich

---

## 3. Implementierte Komponenten

### 3.1 Agents (`src/agents/`)

#### 3.1.1 IAgent Interface (`base.py`)

```python
class IAgent(ABC):
    """Abstract base class for AI agents."""

    @abstractmethod
    def execute(self, prompt: str, work_dir: Optional[str] = None) -> AgentResponse:
        """Execute a prompt/command using this agent."""
        pass

    @abstractmethod
    def analyze(self, context: str, question: str) -> str:
        """Analyze context and answer a question about it."""
        pass

    @abstractmethod
    def verify(self, expected: str, actual: str) -> bool:
        """Verify that actual output matches expected outcome."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this agent is available and properly configured."""
        pass
```

**Datenklassen:**
- `AgentResponse`: Ergebnis einer Agent-Ausführung
- `AgentConfig`: Konfiguration für einen Agent
- `AgentType`: Enum (CLAUDE, CODEX)
- `AgentCapability`: Enum für Agent-Fähigkeiten

#### 3.1.2 ClaudeAgent (`claude_agent.py`)

**Implementierte Methoden:**
- `execute()`: Führt Claude Code CLI aus mit `--print` Modus
- `analyze()`: Analysiert Kontext und beantwortet Fragen
- `verify()`: Verifiziert Output gegen Erwartung
- `plan_implementation()`: Erstellt Implementierungspläne
- `review_code()`: Code-Review mit Kriterien

**Capabilities:**
- CODE_ANALYSIS
- CODE_REVIEW
- PLANNING
- VERIFICATION
- DOCUMENTATION
- CODE_GENERATION
- REFACTORING

#### 3.1.3 CodexAgent (`codex_agent.py`)

**Implementierte Methoden:**
- `execute()`: Führt `codex exec` aus mit `--full-auto --json`
- `execute_with_stdin()`: Piping für lange Prompts
- `generate_code()`: Code-Generierung mit Spezifikation
- `run_tests()`: Test-Ausführung
- `implement_feature()`: Feature-Implementierung

**Capabilities:**
- CODE_GENERATION
- FILE_OPERATIONS
- TEST_EXECUTION
- REFACTORING
- CODE_ANALYSIS

#### 3.1.4 AgentFactory (`factory.py`)

```python
# Einfache Erstellung
agent = AgentFactory.create(AgentType.CLAUDE)

# Mit Konfiguration
agent = AgentFactory.create(AgentType.CODEX, timeout=600)

# Master-Worker Paar
master, worker = AgentFactory.create_pair(
    master_type=AgentType.CLAUDE,
    worker_type=AgentType.CODEX,
)
```

### 3.2 Roles (`src/roles/`)

#### 3.2.1 IRoleStrategy Interface (`base.py`)

```python
class IRoleStrategy(ABC):
    """Abstract base class for role strategies (Master/Worker)."""

    @abstractmethod
    def decide_next_step(
        self,
        goal_description: str,
        current_state: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> Decision:
        """Decide what the next step should be."""
        pass

    @abstractmethod
    def implement_step(self, instruction: Instruction) -> AgentResponse:
        """Implement an instruction."""
        pass

    @abstractmethod
    def verify_implementation(
        self,
        instruction: Instruction,
        response: AgentResponse,
    ) -> VerificationResult:
        """Verify that an implementation meets expectations."""
        pass

    @abstractmethod
    def create_correction(
        self,
        original_instruction: Instruction,
        issues: List[str],
    ) -> Instruction:
        """Create a correction instruction based on issues."""
        pass
```

**Datenklassen:**
- `Decision`: Entscheidung mit Typ (IMPLEMENT/SKIP/DONE/RETRY/CORRECT/ERROR)
- `Instruction`: Anweisung vom Master an Worker
- `VerificationResult`: Ergebnis der Verifikation

#### 3.2.2 MasterRole (`master.py`)

**Hauptfunktionen:**
- `decide_next_step()`: Analysiert Zustand und entscheidet
- `verify_implementation()`: Verifiziert Worker-Output
- `create_correction()`: Erstellt Korrektur-Anweisungen
- `analyze_codebase()`: Analysiert Projektstruktur

**Entscheidungslogik:**
```
IF goal_achieved THEN DONE
ELSE IF step_unnecessary THEN SKIP
ELSE IF last_step_failed AND retryable THEN RETRY
ELSE IF verification_failed THEN CORRECT
ELSE IMPLEMENT next_step
```

#### 3.2.3 WorkerRole (`worker.py`)

**Hauptfunktionen:**
- `implement_step()`: Implementiert Anweisungen
- `verify_implementation()`: Basis-Selbstverifikation
- `execute_tests()`: Führt Tests aus
- `apply_fix()`: Wendet Fixes an
- `refactor_code()`: Refactoring

### 3.3 Goal System (`src/goal/`)

#### 3.3.1 GoalParser (`parser.py`)

**Unterstütztes Format:**
```markdown
# Titel des Ziels

## Description
Beschreibung des gewünschten Ergebnisses.

## Acceptance Criteria
- [ ] Kriterium 1 (offen)
- [x] Kriterium 2 (erledigt)
- [ ] Kriterium 3 (offen)

## Quality Requirements
- Qualitätsanforderung 1
- Qualitätsanforderung 2

## Constraints
- Einschränkung 1
- Einschränkung 2
```

**Datenklassen:**
- `Goal`: Hauptklasse mit allen Zielinformationen
- `AcceptanceCriterion`: Einzelnes Akzeptanzkriterium
- `CriterionStatus`: Enum (PENDING, IN_PROGRESS, COMPLETED, FAILED)

#### 3.3.2 GoalValidator (`validator.py`)

**Validierungsmodi:**
- **Mit AI Agent:** Intelligente semantische Validierung
- **Ohne Agent:** Einfache regelbasierte Prüfung

**Output:**
- `ValidationResult`: Enthält Status, Score, Details
- `CriterionValidation`: Validierung pro Kriterium

#### 3.3.3 ProgressTracker (`progress.py`)

**Funktionen:**
- Session-Start/Stop tracking
- Iteration-Recording mit Metadaten
- Kriterien-Status-Updates
- JSON-Persistenz
- Zusammenfassungs-Generierung

### 3.4 Protocol (`src/protocol/`)

#### 3.4.1 Messages (`messages.py`)

**Nachrichtentypen:**
| Typ | Verwendung |
|-----|------------|
| `RequestMessage` | Master → Worker Anweisung |
| `ResponseMessage` | Worker → Master Ergebnis |
| `ErrorMessage` | Fehler-Kommunikation |
| `StatusMessage` | Fortschritts-Updates |
| `DecisionMessage` | Master-Entscheidungen |
| `VerificationMessage` | Verifikations-Ergebnisse |

**Factory:**
```python
request = MessageFactory.create_request("Implement feature X")
response = MessageFactory.create_response(success=True, output="Done")
error = MessageFactory.create_error("E001", "Something failed")
```

#### 3.4.2 Serializer (`serializer.py`)

**Formate:**
- **JSON:** Maschinenlesbar, strukturiert
- **Markdown:** Menschenlesbar, für Logs

```python
# JSON
serializer = JSONSerializer()
json_str = serializer.serialize(message)
message = serializer.deserialize(json_str)

# Markdown
serializer = MarkdownSerializer()
md_str = serializer.serialize(message)

# Auto-Detect
serializer = SerializerFactory.auto_detect(data)
```

### 3.5 Verification (`src/verification/`)

#### 3.5.1 Checker (`checker.py`)

**Implementierte Checker:**

| Checker | Prüft |
|---------|-------|
| `SyntaxChecker` | Code-Syntax (.py, .js, .ts, .go, .rs, .cpp, .c) |
| `TestChecker` | Test-Ausführung und -Ergebnisse |
| `GoalMatcher` | Ziel-Übereinstimmung |
| `QualityChecker` | Code-Qualitätsmetriken |

**Kombinierter Checker:**
```python
checker = VerificationChecker(agent=master_agent)
report = checker.verify({
    "files": ["src/main.py"],
    "work_dir": "/project",
    "goal": "Create REST API",
    "implementation": "...",
})

print(f"Passed: {report.passed}")
print(f"Score: {report.overall_score}")
```

### 3.6 Orchestrator (`src/orchestrator.py`)

#### 3.6.1 Konfiguration

```python
@dataclass
class OrchestratorConfig:
    max_iterations: int = 20
    timeout_seconds: int = 300
    checkpoint_interval: int = 5
    strict_verification: bool = True
    max_correction_attempts: int = 3
    master_agent_type: AgentType = AgentType.CLAUDE
    worker_agent_type: AgentType = AgentType.CODEX
    work_dir: str = "."
    session_dir: str = "sessions"
    goal_file: str = "GOAL.txt"
```

#### 3.6.2 Haupt-Loop

```python
def run(self) -> bool:
    while iteration < max_iterations:
        # 1. Master analysiert und entscheidet
        decision = master.decide_next_step(goal, state, history)

        if decision.type == DONE:
            return True

        if decision.type == SKIP:
            continue

        # 2. Worker implementiert
        response = worker.implement_step(decision.instruction)

        # 3. Master verifiziert
        verification = master.verify_implementation(instruction, response)

        if not verification.passed:
            # 4. Korrektur-Schleife
            handle_verification_failure(...)

        # 5. Checkpoint
        if iteration % checkpoint_interval == 0:
            save_checkpoint()

    return False  # Max iterations reached
```

#### 3.6.3 Rollentausch

```python
def swap_roles(self) -> None:
    """Swap Master and Worker roles between agents."""
    # Swap agent types
    self.config.master_agent_type, self.config.worker_agent_type = (
        self.config.worker_agent_type,
        self.config.master_agent_type,
    )

    # Swap agents
    self._master_agent, self._worker_agent = (
        self._worker_agent,
        self._master_agent,
    )

    # Recreate roles
    self._master_role = MasterRole(self._master_agent)
    self._worker_role = WorkerRole(self._worker_agent)
```

---

## 4. Dateistruktur

```
ai-orchestrator-v2/
├── src/
│   ├── __init__.py                 # Package exports
│   ├── orchestrator.py             # Haupt-Orchestrator (450 Zeilen)
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                 # IAgent Interface (150 Zeilen)
│   │   ├── claude_agent.py         # Claude Adapter (200 Zeilen)
│   │   ├── codex_agent.py          # Codex Adapter (220 Zeilen)
│   │   └── factory.py              # Agent Factory (100 Zeilen)
│   │
│   ├── roles/
│   │   ├── __init__.py
│   │   ├── base.py                 # IRoleStrategy (120 Zeilen)
│   │   ├── master.py               # Master Role (280 Zeilen)
│   │   └── worker.py               # Worker Role (180 Zeilen)
│   │
│   ├── goal/
│   │   ├── __init__.py
│   │   ├── parser.py               # Goal Parser (250 Zeilen)
│   │   ├── validator.py            # Goal Validator (230 Zeilen)
│   │   └── progress.py             # Progress Tracker (200 Zeilen)
│   │
│   ├── protocol/
│   │   ├── __init__.py
│   │   ├── messages.py             # Message Types (280 Zeilen)
│   │   └── serializer.py           # Serializers (250 Zeilen)
│   │
│   └── verification/
│       ├── __init__.py
│       └── checker.py              # Verification (350 Zeilen)
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Pytest fixtures (200 Zeilen)
│   ├── test_agents.py              # Agent Tests (300 Zeilen)
│   ├── test_roles.py               # Role Tests (280 Zeilen)
│   ├── test_goal.py                # Goal Tests (250 Zeilen)
│   ├── test_protocol.py            # Protocol Tests (300 Zeilen)
│   ├── test_verification.py        # Verification Tests (280 Zeilen)
│   ├── test_orchestrator.py        # Orchestrator Tests (320 Zeilen)
│   ├── test_integration.py         # Integration Tests (350 Zeilen)
│   └── test_edge_cases.py          # Edge Case Tests (350 Zeilen)
│
├── examples/
│   ├── goal_simple.txt             # Einfaches Beispiel-Ziel
│   └── goal_complex.txt            # Komplexes Beispiel-Ziel
│
├── sessions/                       # Session-Dokumentation
│   └── Session_001_*.md
│
├── .gitignore
├── GOAL.txt                        # Aktives Ziel
├── config.yaml                     # Konfiguration
├── requirements.txt                # Dependencies
├── setup.py                        # Package Setup
└── README.md                       # Dokumentation

Gesamt: ~5200 Zeilen Code + ~2800 Zeilen Tests = ~8000 Zeilen
```

---

## 5. Interface-Definitionen

### 5.1 IAgent

```python
class IAgent(ABC):
    @property
    def agent_type(self) -> AgentType: ...
    @property
    def capabilities(self) -> List[AgentCapability]: ...

    def execute(self, prompt: str, work_dir: Optional[str]) -> AgentResponse: ...
    def analyze(self, context: str, question: str) -> str: ...
    def verify(self, expected: str, actual: str) -> bool: ...
    def is_available(self) -> bool: ...
    def has_capability(self, capability: AgentCapability) -> bool: ...
```

### 5.2 IRoleStrategy

```python
class IRoleStrategy(ABC):
    @property
    def role_name(self) -> str: ...

    def decide_next_step(self, goal: str, state: Dict, history: List) -> Decision: ...
    def implement_step(self, instruction: Instruction) -> AgentResponse: ...
    def verify_implementation(self, instruction: Instruction, response: AgentResponse) -> VerificationResult: ...
    def create_correction(self, instruction: Instruction, issues: List[str]) -> Instruction: ...
```

### 5.3 Serializer

```python
class Serializer(ABC):
    def serialize(self, message: Message) -> str: ...
    def deserialize(self, data: str) -> Message: ...
```

### 5.4 IChecker

```python
class IChecker(ABC):
    @property
    def name(self) -> str: ...

    def check(self, context: Dict[str, Any]) -> CheckResult: ...
```

---

## 6. Test-Suite

### 6.1 Test-Übersicht

| Datei | Anzahl Tests | Fokus |
|-------|--------------|-------|
| `test_agents.py` | 10 | Agent-Implementierungen |
| `test_roles.py` | 10 | Master/Worker Rollen |
| `test_goal.py` | 8 | Goal Parsing & Validation |
| `test_protocol.py` | 7 | Messages & Serialization |
| `test_verification.py` | 5 | Verification Checkers |
| `test_orchestrator.py` | ~10 | Orchestrator Logic |
| `test_integration.py` | 10 | Full Workflows |
| `test_edge_cases.py` | 10 | Randfälle & Fehler |
| **Gesamt** | **~60** | |

### 6.2 Test-Kategorien

#### Unit Tests (40)

**Agents:**
1. `test_claude_agent_execute_success`
2. `test_claude_agent_execute_timeout`
3. `test_claude_agent_analyze_codebase`
4. `test_codex_agent_execute_success`
5. `test_codex_agent_execute_timeout`
6. `test_codex_agent_json_output`
7. `test_agent_capability_detection`
8. `test_agent_error_handling`
9. `test_agent_retry_logic`
10. `test_agent_output_parsing`

**Roles:**
1. `test_master_decide_implement`
2. `test_master_decide_skip`
3. `test_master_decide_done`
4. `test_master_verify_success`
5. `test_master_verify_failure`
6. `test_worker_implement_success`
7. `test_worker_implement_partial`
8. `test_role_swap_claude_to_codex`
9. `test_role_swap_codex_to_claude`
10. `test_role_configuration_validation`

**Goal:**
1. `test_goal_parse_simple`
2. `test_goal_parse_complex`
3. `test_goal_parse_with_criteria`
4. `test_goal_validate_achieved`
5. `test_goal_validate_partial`
6. `test_goal_validate_failed`
7. `test_goal_criteria_extraction`
8. `test_goal_progress_tracking`

**Protocol:**
1. `test_message_serialize_json`
2. `test_message_serialize_markdown`
3. `test_message_deserialize`
4. `test_protocol_request_response`
5. `test_protocol_error_handling`
6. `test_protocol_version_compat`
7. `test_protocol_streaming`

**Verification:**
1. `test_verify_code_syntax`
2. `test_verify_test_pass`
3. `test_verify_goal_match`
4. `test_verify_diff_analysis`
5. `test_verify_quality_metrics`

#### Integration Tests (10)

1. `test_full_workflow_simple_goal`
2. `test_full_workflow_complex_goal`
3. `test_workflow_with_corrections`
4. `test_workflow_role_swap_midway`
5. `test_workflow_multi_iteration`
6. `test_workflow_with_verification_failure`
7. `test_workflow_timeout_recovery`
8. `test_workflow_state_persistence`
9. `test_workflow_resume_from_checkpoint`
10. `test_workflow_concurrent_agents`

#### Edge Case Tests (10)

1. `test_empty_goal_file`
2. `test_invalid_goal_format`
3. `test_agent_unavailable`
4. `test_both_agents_unavailable`
5. `test_circular_correction_loop`
6. `test_max_iterations_reached`
7. `test_work_dir_not_exists`
8. `test_work_dir_no_permissions`
9. `test_large_output_handling`
10. `test_unicode_in_goal_and_output`

### 6.3 Test-Ausführung

```bash
# Alle Tests
pytest tests/ -v

# Mit Coverage
pytest tests/ --cov=src --cov-report=html

# Nur Unit Tests
pytest tests/test_agents.py tests/test_roles.py tests/test_goal.py -v

# Nur Integration Tests
pytest tests/test_integration.py -v

# Nur Edge Cases
pytest tests/test_edge_cases.py -v
```

---

## 7. Konfiguration

### 7.1 config.yaml

```yaml
orchestrator:
  max_iterations: 20        # Maximale Durchläufe
  timeout_seconds: 300      # Timeout pro Operation
  checkpoint_interval: 5    # Checkpoint alle N Iterationen
  strict_verification: true # Alle Kriterien müssen erfüllt sein
  max_correction_attempts: 3 # Max. Korrekturversuche

roles:
  master: claude            # Master-Agent (claude/codex)
  worker: codex             # Worker-Agent (claude/codex)

agents:
  claude:
    command: claude
    timeout: 120
    sandbox: true
    json_output: true
  codex:
    command: codex
    timeout: 300
    sandbox: true
    full_auto: true
    json_output: true

goal:
  file: GOAL.txt
  validation_strict: true

logging:
  level: INFO
  file: sessions/orchestrator.log

session:
  auto_save: true
  checkpoint_interval: 5
```

### 7.2 Umgebungsvariablen

```bash
export ORCHESTRATOR_MAX_ITERATIONS=30
export ORCHESTRATOR_WORK_DIR=/path/to/project
export ORCHESTRATOR_MASTER=codex
export ORCHESTRATOR_WORKER=claude
```

---

## 8. Git Repository

### 8.1 Repository-Details

| Eigenschaft | Wert |
|-------------|------|
| **URL** | https://github.com/BenniProbst/ai-orchestrator-v2 |
| **Sichtbarkeit** | Public |
| **Lizenz** | MIT |
| **Sprache** | Python |

### 8.2 Commits

| Commit | Beschreibung | Dateien |
|--------|--------------|---------|
| `f15d469` | Initial commit: AI Orchestrator V2 | 28 |
| `a04d8d4` | Add comprehensive test suite (60 tests) | 10 |

### 8.3 Branching-Strategie

```
main (production-ready)
  └── feature/* (neue Features)
  └── fix/* (Bugfixes)
  └── docs/* (Dokumentation)
```

---

## 9. Verwendungsbeispiele

### 9.1 Einfache Verwendung

```python
from src import Orchestrator, OrchestratorConfig
from src.agents.base import AgentType

# Standard-Konfiguration (Claude=Master, Codex=Worker)
config = OrchestratorConfig()
orchestrator = Orchestrator(config)

# Ausführen
success = orchestrator.run()
print(f"Goal achieved: {success}")
```

### 9.2 Mit Rollentausch

```python
from src import Orchestrator, OrchestratorConfig
from src.agents.base import AgentType

# Codex als Master, Claude als Worker
config = OrchestratorConfig(
    master_agent_type=AgentType.CODEX,
    worker_agent_type=AgentType.CLAUDE,
)
orchestrator = Orchestrator(config)

# Oder zur Laufzeit tauschen
orchestrator.swap_roles()
```

### 9.3 Mit eigenem Goal

```python
from src import Orchestrator, OrchestratorConfig
from src.goal.parser import GoalParser

# Goal erstellen
parser = GoalParser()
goal = parser.create_goal(
    title="Mein Projekt",
    description="Beschreibung",
    criteria=["Kriterium 1", "Kriterium 2"],
    constraints=["Python 3.11+"],
)

# Orchestrator mit Goal
orchestrator = Orchestrator(goal=goal)
```

### 9.4 CLI-Verwendung

```bash
# Standard
python -m src.orchestrator --goal GOAL.txt --work-dir ./project

# Mit Rollentausch
python -m src.orchestrator --master codex --worker claude

# Mit Resume
python -m src.orchestrator --resume sessions/checkpoint_abc123.json
```

### 9.5 Progress-Tracking

```python
from src.goal.progress import ProgressTracker
from src.goal.parser import GoalParser

parser = GoalParser()
goal = parser.parse_file("GOAL.txt")

tracker = ProgressTracker(goal, session_dir="sessions")
tracker.start()

# Iteration aufzeichnen
tracker.record_iteration(
    action="Implemented user login",
    result="Login endpoint created",
    success=True,
    files_changed=["src/auth/login.py"],
)

# Zusammenfassung
print(tracker.get_summary())
```

---

## 10. Bekannte Einschränkungen

### 10.1 Technische Einschränkungen

| Einschränkung | Auswirkung | Workaround |
|---------------|------------|------------|
| Keine echten Pipes | Höhere Latenz | Dateibasierte IPC akzeptieren |
| CLI-Abhängigkeit | Agents müssen installiert sein | `is_available()` prüfen |
| Synchrone Ausführung | Kein paralleles Processing | Sequentieller Workflow |
| Timeout-Handling | Lange Tasks können fehlschlagen | Timeout erhöhen |

### 10.2 Funktionale Einschränkungen

- **Keine Multi-Session:** Ein Orchestrator = eine Session
- **Kein Hot-Reload:** Konfigurationsänderungen erfordern Neustart
- **Limitierte Sprachen:** Syntax-Check nur für bekannte Sprachen
- **Keine GUI:** Nur CLI und API

### 10.3 Bekannte Issues

1. **Windows CRLF:** Git warnt vor Zeilenenden-Konvertierung
2. **Large Files:** Output > 1MB kann langsam sein
3. **Unicode Paths:** Pfade mit Sonderzeichen könnten Probleme machen

---

## 11. Zukünftige Erweiterungen

### 11.1 Geplant (Priorität Hoch)

- [ ] Web UI für Monitoring
- [ ] WebSocket-basierte Live-Updates
- [ ] Multi-Session Support
- [ ] Automatische Retry-Logik

### 11.2 Geplant (Priorität Mittel)

- [ ] Named Pipes als Alternative
- [ ] Plugin-System für Checker
- [ ] Prometheus Metriken
- [ ] Docker Container

### 11.3 Ideen (Priorität Niedrig)

- [ ] Cloud-Deployment (AWS/GCP)
- [ ] IDE-Integration (VS Code Extension)
- [ ] Grafana Dashboard
- [ ] Slack/Discord Integration

---

## 12. Änderungsprotokoll

### Version 2.0.0 (2026-01-07)

**Neu:**
- Vollständige Neuimplementierung basierend auf V1
- Modularer Rollentausch (Claude ↔ Codex)
- Zielorientierung mit GOAL.txt
- Verifikation nach Implementierung
- Korrektur-Schleife bei Fehlern
- Checkpoint/Resume Funktionalität
- 60 Unit/Integration Tests
- JSON und Markdown Serialisierung
- Syntax, Test, Goal und Quality Checker

**Geändert:**
- Architektur komplett überarbeitet
- Neue Interface-Definitionen
- Verbesserte Fehlerbehandlung

**Behoben:**
- N/A (Erstveröffentlichung V2)

---

## Anhang A: Sequenzdiagramm

```
┌────────┐     ┌────────┐     ┌────────┐     ┌────────┐
│  User  │     │ Orch.  │     │ Master │     │ Worker │
└───┬────┘     └───┬────┘     └───┬────┘     └───┬────┘
    │              │              │              │
    │  run()       │              │              │
    │─────────────>│              │              │
    │              │              │              │
    │              │  decide()    │              │
    │              │─────────────>│              │
    │              │              │              │
    │              │  Decision    │              │
    │              │<─────────────│              │
    │              │              │              │
    │              │              │  implement() │
    │              │──────────────┼─────────────>│
    │              │              │              │
    │              │              │  Response    │
    │              │<─────────────┼──────────────│
    │              │              │              │
    │              │  verify()    │              │
    │              │─────────────>│              │
    │              │              │              │
    │              │ Verification │              │
    │              │<─────────────│              │
    │              │              │              │
    │  result      │              │              │
    │<─────────────│              │              │
    │              │              │              │
```

---

## Anhang B: Klassendiagramm (vereinfacht)

```
                    ┌─────────────┐
                    │ Orchestrator│
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────┴─────┐   ┌──────┴──────┐  ┌─────┴─────┐
    │ MasterRole│   │ GoalParser  │  │WorkerRole │
    └─────┬─────┘   └──────┬──────┘  └─────┬─────┘
          │                │               │
    ┌─────┴─────┐   ┌──────┴──────┐  ┌─────┴─────┐
    │  IAgent   │   │    Goal     │  │  IAgent   │
    └─────┬─────┘   └─────────────┘  └─────┬─────┘
          │                                │
    ┌─────┴─────┐                   ┌─────┴─────┐
    │ClaudeAgent│                   │CodexAgent │
    └───────────┘                   └───────────┘
```

---

*Session erstellt: 2026-01-07*
*Letzte Aktualisierung: 2026-01-07*
*Autor: Claude Code (claude-opus-4-5-20251101)*
