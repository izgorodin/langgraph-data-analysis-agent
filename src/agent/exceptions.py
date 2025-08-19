"""Custom exceptions for SQL validation."""

from __future__ import annotations


class SQLValidationError(Exception):
    """Base exception for SQL validation errors.
    
    All SQL validation errors inherit from this base class
    to provide consistent error handling throughout the system.
    """
    
    def __init__(self, message: str, sql: str = "", details: str = ""):
        self.message = message
        self.sql = sql
        self.details = details
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        """Format the error message with context."""
        if self.sql:
            return f"{self.message}\nSQL: {self.sql[:100]}{'...' if len(self.sql) > 100 else ''}"
        return self.message


class SecurityViolationError(SQLValidationError):
    """Exception raised when SQL violates security policies.
    
    This includes SQL injection attempts, unauthorized table access,
    or other security policy violations as defined in ADR 003.
    """
    pass


class ParseError(SQLValidationError):
    """Exception raised when SQL cannot be parsed.
    
    This occurs when the SQL syntax is invalid or not supported
    by the sqlglot BigQuery dialect parser.
    """
    pass


class TableAccessError(SQLValidationError):
    """Exception raised when SQL attempts to access unauthorized tables.
    
    Only tables in the whitelist (orders, order_items, products, users)
    are allowed as per ADR 003 security policies.
    """
    
    def __init__(self, message: str, forbidden_tables: set[str], sql: str = "", details: str = ""):
        self.forbidden_tables = forbidden_tables
        super().__init__(message, sql, details)


class StatementTypeError(SQLValidationError):
    """Exception raised when SQL contains non-SELECT statements.
    
    Only SELECT statements are allowed as per ADR 003.
    DML (INSERT, UPDATE, DELETE) and DDL (CREATE, DROP, ALTER) are forbidden.
    """
    
    def __init__(self, message: str, statement_type: str, sql: str = "", details: str = ""):
        self.statement_type = statement_type
        super().__init__(message, sql, details)


class InjectionAttemptError(SecurityViolationError):
    """Exception raised when SQL contains potential injection patterns.
    
    This includes classic SQL injection patterns like semicolon injection,
    comment injection, union injection, and other malicious patterns.
    """
    
    def __init__(self, message: str, injection_type: str, sql: str = "", details: str = ""):
        self.injection_type = injection_type
        super().__init__(message, sql, details)


class PerformanceViolationError(SQLValidationError):
    """Exception raised when SQL violates performance constraints.
    
    This includes queries that are too complex, take too long to parse,
    or exceed resource limits.
    """
    pass