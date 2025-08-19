"""Response quality validation for LLM outputs."""

from __future__ import annotations

import json
import re
from typing import Dict, Optional, Tuple

import sqlglot

from .models import LLMContext, LLMResponse


class ValidationResult:
    """Result of response validation."""
    
    def __init__(
        self, 
        is_valid: bool, 
        quality_score: float, 
        issues: Optional[list] = None,
        extracted_content: Optional[str] = None
    ):
        self.is_valid = is_valid
        self.quality_score = quality_score  # 0.0 to 1.0
        self.issues = issues or []
        self.extracted_content = extracted_content


class ResponseValidator:
    """Validates LLM responses for quality and security."""
    
    def __init__(self):
        self.min_quality_score = 0.6
        
    def validate_response(self, response: LLMResponse, context: Optional[str] = None) -> ValidationResult:
        """Validate response based on context."""
        if response.context == LLMContext.SQL_GENERATION:
            return self.validate_sql_response(response.text, context)
        elif response.context == LLMContext.PLANNING:
            return self.validate_plan_response(response.text, context)
        elif response.context == LLMContext.ANALYSIS:
            return self.validate_analysis_response(response.text, context)
        else:
            return self.validate_general_response(response.text, context)
    
    def validate_sql_response(self, response: str, context: Optional[str] = None) -> ValidationResult:
        """Validate SQL generation response."""
        issues = []
        quality_score = 1.0
        
        # Extract SQL from response
        sql_query = self._extract_sql_from_response(response)
        
        if not sql_query:
            return ValidationResult(False, 0.0, ["No SQL query found in response"])
        
        # Check SQL syntax
        try:
            parsed = sqlglot.parse_one(sql_query, dialect="bigquery")
            if not parsed:
                issues.append("Invalid SQL syntax")
                quality_score -= 0.4
        except Exception as e:
            issues.append(f"SQL parsing error: {str(e)}")
            quality_score -= 0.4
        
        # Check for dangerous patterns
        dangerous_patterns = [
            r'\bDROP\b', r'\bDELETE\b', r'\bTRUNCATE\b', 
            r'\bINSERT\b', r'\bUPDATE\b', r'\bALTER\b'
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, sql_query, re.IGNORECASE):
                issues.append(f"Dangerous SQL operation detected: {pattern}")
                quality_score -= 0.3
        
        # Check for required LIMIT clause (basic protection)
        if not re.search(r'\bLIMIT\b', sql_query, re.IGNORECASE):
            # Not necessarily an error, but reduce quality score slightly
            quality_score -= 0.1
        
        is_valid = quality_score >= self.min_quality_score
        
        return ValidationResult(is_valid, quality_score, issues, sql_query)
    
    def validate_plan_response(self, response: str, context: Optional[str] = None) -> ValidationResult:
        """Validate analysis plan response."""
        issues = []
        quality_score = 1.0
        
        # Try to extract JSON plan
        plan_json = self._extract_json_from_response(response)
        
        if not plan_json:
            issues.append("No valid JSON plan found")
            quality_score -= 0.5  # More severe penalty
        else:
            # Check for required fields
            required_fields = ["task", "tables"]
            for field in required_fields:
                if field not in plan_json:
                    issues.append(f"Missing required field: {field}")
                    quality_score -= 0.3  # More severe penalty
        
        # Check response length and structure
        if len(response.strip()) < 20:
            issues.append("Response too short")
            quality_score -= 0.3
        
        is_valid = quality_score >= self.min_quality_score
        
        return ValidationResult(is_valid, quality_score, issues, json.dumps(plan_json) if plan_json else None)
    
    def validate_analysis_response(self, response: str, context: Optional[str] = None) -> ValidationResult:
        """Validate analysis response."""
        issues = []
        quality_score = 1.0
        
        # Check basic response quality
        if len(response.strip()) < 50:
            issues.append("Analysis response too short")
            quality_score -= 0.5  # More severe penalty
        
        # Check for key insights structure
        insight_indicators = ["insight", "finding", "trend", "pattern", "recommendation"]
        if not any(indicator in response.lower() for indicator in insight_indicators):
            issues.append("Response lacks clear insights")
            quality_score -= 0.5  # More severe penalty
        
        # Check for factual consistency (basic check)
        if self._contains_obvious_hallucinations(response):
            issues.append("Potential factual inconsistencies detected")
            quality_score -= 0.4
        
        is_valid = quality_score >= self.min_quality_score
        
        return ValidationResult(is_valid, quality_score, issues, response.strip())
    
    def validate_general_response(self, response: str, context: Optional[str] = None) -> ValidationResult:
        """Validate general response."""
        issues = []
        quality_score = 1.0
        
        # Basic quality checks
        if len(response.strip()) < 10:
            issues.append("Response too short")
            quality_score -= 0.5  # More severe penalty
        
        if self._check_prompt_injection(response):
            issues.append("Potential prompt injection detected")
            quality_score -= 0.5
        
        is_valid = quality_score >= self.min_quality_score
        
        return ValidationResult(is_valid, quality_score, issues, response.strip())
    
    def _extract_sql_from_response(self, response: str) -> Optional[str]:
        """Extract SQL query from response text."""
        # Look for SQL code blocks
        sql_pattern = r'```(?:sql)?\s*(.*?)\s*```'
        match = re.search(sql_pattern, response, re.DOTALL | re.IGNORECASE)
        
        if match:
            return match.group(1).strip()
        
        # Look for SELECT statements
        select_pattern = r'(SELECT\s+.*?)(?:\n\n|\Z)'
        match = re.search(select_pattern, response, re.DOTALL | re.IGNORECASE)
        
        if match:
            return match.group(1).strip()
        
        return None
    
    def _extract_json_from_response(self, response: str) -> Optional[Dict]:
        """Extract JSON from response text."""
        # Look for JSON code blocks
        json_pattern = r'```(?:json)?\s*(.*?)\s*```'
        match = re.search(json_pattern, response, re.DOTALL)
        
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Look for JSON-like structures
        try:
            # Try to find JSON object boundaries
            start = response.find('{')
            if start >= 0:
                bracket_count = 0
                for i, char in enumerate(response[start:], start):
                    if char == '{':
                        bracket_count += 1
                    elif char == '}':
                        bracket_count -= 1
                        if bracket_count == 0:
                            json_str = response[start:i+1]
                            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            pass
        
        return None
    
    def _contains_obvious_hallucinations(self, response: str) -> bool:
        """Check for obvious factual hallucinations."""
        # This is a basic implementation
        # In production, would use more sophisticated fact-checking
        hallucination_patterns = [
            r'\b(definitely|certainly|absolutely)\s+(?:wrong|incorrect|false)\b',
            r'\b(?:impossible|never|always)\s+(?:true|false|happens)\b',
        ]
        
        for pattern in hallucination_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                return True
        
        return False
    
    def _check_prompt_injection(self, response: str) -> bool:
        """Check for potential prompt injection attempts."""
        injection_patterns = [
            r'ignore\s+(?:previous|earlier)\s+instructions',
            r'forget\s+(?:everything|all)\s+(?:above|before)',
            r'system\s*:\s*',
            r'you\s+are\s+now\s+a?\s*(?:different|new)',
        ]
        
        for pattern in injection_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                return True
        
        return False