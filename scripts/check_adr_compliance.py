#!/usr/bin/env python3
"""
Check ADR compliance in source code files.
"""
import re
import sys
from pathlib import Path
from typing import List, Dict


def get_adr_references() -> Dict[str, str]:
    """Get all available ADR references from docs/adr/."""
    adr_refs = {}
    adr_dir = Path("docs/adr")
    
    if not adr_dir.exists():
        return adr_refs
    
    for adr_file in adr_dir.glob("*.md"):
        if match := re.match(r'(\d{3})-(.+)\.md', adr_file.name):
            adr_id = f"ADR {match.group(1)}"
            adr_refs[adr_id] = match.group(2).replace('-', ' ')
    
    return adr_refs


def check_file_adr_compliance(file_path: Path, adr_refs: Dict[str, str]) -> List[str]:
    """Check a single file for ADR compliance."""
    warnings = []
    
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return warnings
    
    # Check for ADR references in comments
    adr_mentions = re.findall(r'ADR \d{3}', content)
    
    # Check for specific compliance requirements
    if 'sql' in file_path.name.lower() or 'bigquery' in file_path.name.lower():
        if 'ADR 003' not in content:
            warnings.append("SQL-related files should reference ADR 003 (security policies)")
    
    if 'llm' in file_path.name.lower() or 'gemini' in file_path.name.lower():
        if 'ADR 002' not in content:
            warnings.append("LLM-related files should reference ADR 002 (LLM selection)")
        if 'ADR 004' not in content:
            warnings.append("LLM-related files should reference ADR 004 (fallback strategy)")
    
    if 'config' in file_path.name.lower():
        if not any(f'ADR {i:03d}' in content for i in range(1, 7)):
            warnings.append("Configuration files should reference relevant ADRs")
    
    # Check for invalid ADR references
    for adr_ref in adr_mentions:
        if adr_ref not in adr_refs:
            warnings.append(f"Invalid ADR reference: {adr_ref}")
    
    return warnings


def main():
    """Main compliance checking function."""
    if len(sys.argv) < 2:
        print("Usage: python check_adr_compliance.py <file1> [file2] ...")
        sys.exit(1)
    
    adr_refs = get_adr_references()
    print(f"Found {len(adr_refs)} ADR documents")
    
    total_warnings = 0
    
    for file_path_str in sys.argv[1:]:
        file_path = Path(file_path_str)
        
        if not file_path.exists() or not file_path.suffix == '.py':
            continue
        
        warnings = check_file_adr_compliance(file_path, adr_refs)
        
        if warnings:
            print(f"\n⚠️  {file_path}:")
            for warning in warnings:
                print(f"  - {warning}")
            total_warnings += len(warnings)
    
    if total_warnings > 0:
        print(f"\nTotal ADR compliance warnings: {total_warnings}")
        # Don't fail the build for warnings, just notify
        # sys.exit(1)
    else:
        print("✅ No ADR compliance issues found")


if __name__ == "__main__":
    main()
