"""
Goal Parser

Parses GOAL.txt files to extract structured goal information.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
from enum import Enum


class CriterionStatus(Enum):
    """Status of an acceptance criterion"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AcceptanceCriterion:
    """A single acceptance criterion"""
    description: str
    status: CriterionStatus = CriterionStatus.PENDING
    completed: bool = False
    priority: int = 1
    tags: List[str] = field(default_factory=list)

    def mark_completed(self) -> None:
        self.completed = True
        self.status = CriterionStatus.COMPLETED

    def mark_failed(self) -> None:
        self.completed = False
        self.status = CriterionStatus.FAILED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "status": self.status.value,
            "completed": self.completed,
            "priority": self.priority,
            "tags": self.tags,
        }


@dataclass
class Goal:
    """Parsed goal structure"""
    title: str
    description: str = ""
    acceptance_criteria: List[AcceptanceCriterion] = field(default_factory=list)
    quality_requirements: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_content: str = ""

    @property
    def total_criteria(self) -> int:
        return len(self.acceptance_criteria)

    @property
    def completed_criteria(self) -> int:
        return sum(1 for c in self.acceptance_criteria if c.completed)

    @property
    def progress_percentage(self) -> float:
        if self.total_criteria == 0:
            return 0.0
        return (self.completed_criteria / self.total_criteria) * 100

    @property
    def is_achieved(self) -> bool:
        if not self.acceptance_criteria:
            return False
        return all(c.completed for c in self.acceptance_criteria)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "acceptance_criteria": [c.to_dict() for c in self.acceptance_criteria],
            "quality_requirements": self.quality_requirements,
            "constraints": self.constraints,
            "metadata": self.metadata,
            "progress": {
                "total": self.total_criteria,
                "completed": self.completed_criteria,
                "percentage": self.progress_percentage,
            },
        }

    def get_pending_criteria(self) -> List[AcceptanceCriterion]:
        """Get criteria that are not yet completed."""
        return [c for c in self.acceptance_criteria if not c.completed]

    def get_next_criterion(self) -> Optional[AcceptanceCriterion]:
        """Get the next criterion to work on."""
        pending = self.get_pending_criteria()
        if pending:
            # Return highest priority pending criterion
            return min(pending, key=lambda c: c.priority)
        return None


class GoalParser:
    """
    Parser for GOAL.txt files.

    Supports markdown-style goal definitions with:
    - Title (# heading)
    - Description
    - Acceptance criteria (checkbox lists)
    - Quality requirements
    - Constraints
    """

    # Section headers
    SECTION_PATTERNS = {
        "description": r"^##\s*(Beschreibung|Description)\s*$",
        "criteria": r"^##\s*(Akzeptanzkriterien|Acceptance\s*Criteria)\s*$",
        "quality": r"^##\s*(Qualit.tsanforderungen|Quality\s*Requirements)\s*$",
        "constraints": r"^##\s*(Constraints|Einschr.nkungen)\s*$",
    }

    # Checkbox pattern: - [ ] or - [x]
    CHECKBOX_PATTERN = re.compile(r"^-\s*\[([ xX])\]\s*(.+)$")

    # List item pattern: - item
    LIST_PATTERN = re.compile(r"^-\s+(.+)$")

    def __init__(self):
        self._compiled_patterns = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.SECTION_PATTERNS.items()
        }

    def parse_file(self, file_path: str) -> Goal:
        """
        Parse a goal file.

        Args:
            file_path: Path to GOAL.txt file

        Returns:
            Parsed Goal object

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Goal file not found: {file_path}")

        content = path.read_text(encoding="utf-8")
        return self.parse_content(content)

    def parse_content(self, content: str) -> Goal:
        """
        Parse goal content string.

        Args:
            content: Raw goal content

        Returns:
            Parsed Goal object
        """
        if not content.strip():
            raise ValueError("Goal content is empty")

        lines = content.split("\n")
        goal = Goal(title="", raw_content=content)

        # Parse title (first # heading)
        goal.title = self._extract_title(lines)

        # Parse sections
        current_section = "description"
        section_content: Dict[str, List[str]] = {
            "description": [],
            "criteria": [],
            "quality": [],
            "constraints": [],
        }

        for line in lines:
            # Check for section header
            new_section = self._identify_section(line)
            if new_section:
                current_section = new_section
                continue

            # Skip title line
            if line.strip().startswith("# ") and not line.strip().startswith("## "):
                continue

            # Add line to current section
            if line.strip():
                section_content[current_section].append(line)

        # Process sections
        goal.description = "\n".join(section_content["description"]).strip()
        goal.acceptance_criteria = self._parse_criteria(section_content["criteria"])
        goal.quality_requirements = self._parse_list(section_content["quality"])
        goal.constraints = self._parse_list(section_content["constraints"])

        return goal

    def _extract_title(self, lines: List[str]) -> str:
        """Extract title from first # heading."""
        for line in lines:
            if line.strip().startswith("# ") and not line.strip().startswith("## "):
                return line.strip()[2:].strip()
        return "Untitled Goal"

    def _identify_section(self, line: str) -> Optional[str]:
        """Identify if line is a section header."""
        for name, pattern in self._compiled_patterns.items():
            if pattern.match(line.strip()):
                return name
        return None

    def _parse_criteria(self, lines: List[str]) -> List[AcceptanceCriterion]:
        """Parse acceptance criteria from lines."""
        criteria = []

        for line in lines:
            match = self.CHECKBOX_PATTERN.match(line.strip())
            if match:
                completed = match.group(1).lower() == "x"
                description = match.group(2).strip()

                criterion = AcceptanceCriterion(
                    description=description,
                    completed=completed,
                    status=CriterionStatus.COMPLETED if completed else CriterionStatus.PENDING,
                )
                criteria.append(criterion)

        return criteria

    def _parse_list(self, lines: List[str]) -> List[str]:
        """Parse simple list items."""
        items = []

        for line in lines:
            match = self.LIST_PATTERN.match(line.strip())
            if match:
                items.append(match.group(1).strip())
            elif line.strip() and not line.strip().startswith("#"):
                # Non-list content, treat as single item
                items.append(line.strip())

        return items

    def create_goal(
        self,
        title: str,
        description: str,
        criteria: List[str],
        quality: List[str] = None,
        constraints: List[str] = None,
    ) -> Goal:
        """
        Create a Goal programmatically.

        Args:
            title: Goal title
            description: Goal description
            criteria: List of acceptance criteria strings
            quality: Optional quality requirements
            constraints: Optional constraints

        Returns:
            Goal object
        """
        return Goal(
            title=title,
            description=description,
            acceptance_criteria=[
                AcceptanceCriterion(description=c) for c in criteria
            ],
            quality_requirements=quality or [],
            constraints=constraints or [],
        )

    def to_markdown(self, goal: Goal) -> str:
        """
        Convert Goal back to markdown format.

        Args:
            goal: Goal object

        Returns:
            Markdown string
        """
        lines = [f"# {goal.title}", ""]

        if goal.description:
            lines.extend(["## Description", "", goal.description, ""])

        if goal.acceptance_criteria:
            lines.extend(["## Acceptance Criteria", ""])
            for c in goal.acceptance_criteria:
                checkbox = "[x]" if c.completed else "[ ]"
                lines.append(f"- {checkbox} {c.description}")
            lines.append("")

        if goal.quality_requirements:
            lines.extend(["## Quality Requirements", ""])
            for q in goal.quality_requirements:
                lines.append(f"- {q}")
            lines.append("")

        if goal.constraints:
            lines.extend(["## Constraints", ""])
            for c in goal.constraints:
                lines.append(f"- {c}")
            lines.append("")

        return "\n".join(lines)
