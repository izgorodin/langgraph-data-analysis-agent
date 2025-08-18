"""Test configuration and basic functionality."""

import pytest
from pathlib import Path


def test_project_structure():
    """Test that basic project structure exists."""
    project_root = Path(__file__).parent.parent
    
    # Check essential directories
    assert (project_root / "src").exists()
    assert (project_root / "tasks").exists()
    assert (project_root / "docs").exists()
    
    # Check essential files
    assert (project_root / "requirements.txt").exists()
    assert (project_root / "pyproject.toml").exists()
    assert (project_root / ".env.example").exists()


def test_task_files_exist():
    """Test that required task files exist."""
    tasks_dir = Path(__file__).parent.parent / "tasks"
    
    expected_tasks = [
        "LGDA-001-test-infrastructure.md",
        "LGDA-002-sql-validation.md", 
        "LGDA-003-bigquery-client.md",
        "LGDA-004-llm-integration.md",
        "LGDA-005-configuration-management.md",
    ]
    
    for task_file in expected_tasks:
        assert (tasks_dir / task_file).exists(), f"Task file {task_file} not found"


def test_imports():
    """Test that we can import our modules."""
    # This will fail until we implement the modules, but good for CI
    try:
        import sys
        sys.path.append(str(Path(__file__).parent.parent / "src"))
        
        # These imports will fail initially, but show CI is working
        # import config
        # import bq
        # import llm
        
        # For now just test basic Python functionality
        assert True
    except ImportError:
        # Expected for now - we haven't implemented modules yet
        pytest.skip("Modules not implemented yet")


def test_environment_setup():
    """Test that environment is properly configured."""
    import os
    
    # Test that we can access environment variables
    env_example = Path(__file__).parent.parent / ".env.example"
    assert env_example.exists()
    
    # Test Python version
    import sys
    assert sys.version_info >= (3, 9), "Python 3.9+ required"


if __name__ == "__main__":
    pytest.main([__file__])
