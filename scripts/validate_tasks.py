#!/usr/bin/env python3
"""
Validate LGDA task specification files for compliance and consistency.
"""
import re
import sys
from pathlib import Path
from typing import List, Set


def validate_task_file(file_path: Path) -> List[str]:
    """Validate a single task file and return list of errors."""
    errors = []

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return [f"Failed to read file: {e}"]

    # Check filename format
    if not re.match(r"LGDA-\d{3}-.*\.md$", file_path.name):
        errors.append("Filename must follow format: LGDA-XXX-description.md")

    # Check for required LGDA-XXX identifier in content
    lgda_ids = re.findall(r"LGDA-\d{3}", content)
    if not lgda_ids:
        errors.append("File must contain at least one LGDA-XXX identifier")

    # Check for required sections (Russian or English)
    required_sections = [
        ("## Архитектурный контекст", "## Background"),
        ("## Цель задачи", "## Summary"),
        ("## Детальный анализ", "## Problem Description"),
        ("## Критерии приемки", "## Definition of Done"),
        ("## Возможные сложности", "## Implementation Difficulty"),
        ("## Integration Points", "## Integration Impact"),
    ]

    for ru_section, en_section in required_sections:
        if ru_section not in content and en_section not in content:
            errors.append(f"Missing required section: {ru_section} or {en_section}")

    # Check for ADR references
    if "ADR" not in content:
        errors.append("Task should reference relevant ADRs")

    # Check for security considerations if SQL-related
    if any(keyword in content.lower() for keyword in ["sql", "query", "bigquery"]):
        if "безопасност" not in content.lower() and "security" not in content.lower():
            errors.append("SQL-related tasks must include security considerations")

    # Check for performance targets
    if (
        "performance" not in content.lower()
        and "производительност" not in content.lower()
    ):
        errors.append("Task should include performance considerations")

    # Check for test strategy
    if "test" not in content.lower() and "тест" not in content.lower():
        errors.append("Task should include testing strategy")

    return errors


def main() -> None:
    """Main validation function."""
    tasks_dir = Path("tasks")

    if not tasks_dir.exists():
        print("ERROR: tasks/ directory not found")
        sys.exit(1)

    task_files = list(tasks_dir.glob("LGDA-*.md"))

    if not task_files:
        print("No LGDA task files found")
        return

    total_errors = 0
    all_task_ids: Set[str] = set()

    for task_file in sorted(task_files):
        errors = validate_task_file(task_file)

        if errors:
            print(f"\n❌ {task_file.name}:")
            for error in errors:
                print(f"  - {error}")
            total_errors += len(errors)
        else:
            print(f"✅ {task_file.name}")

        # Extract task IDs for duplicate checking
        content = task_file.read_text(encoding="utf-8")
        task_ids = re.findall(r"LGDA-\d{3}", content)
        for task_id in task_ids:
            if task_id in all_task_ids:
                print(f"⚠️  Duplicate task ID {task_id} found in {task_file.name}")
            all_task_ids.add(task_id)

    # Check for sequential numbering
    expected_ids = {f"LGDA-{i:03d}" for i in range(1, len(task_files) + 1)}
    found_ids = {
        re.search(r"LGDA-\d{3}", f.name).group()
        for f in task_files
        if re.search(r"LGDA-\d{3}", f.name)
    }

    missing_ids = expected_ids - found_ids
    if missing_ids:
        print(f"\n⚠️  Missing sequential task IDs: {sorted(missing_ids)}")

    print("\nValidation Summary:")
    print(f"  Files checked: {len(task_files)}")
    print(f"  Total errors: {total_errors}")
    print(f"  Unique task IDs: {len(all_task_ids)}")

    if total_errors > 0:
        sys.exit(1)
    else:
        print("✅ All task files are valid!")


if __name__ == "__main__":
    main()
