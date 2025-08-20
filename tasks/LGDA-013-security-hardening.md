# LGDA-013: Security Hardening and Compliance

**Priority**: HIGH | **Type**: Security | **Parallel**: Can run with LGDA-007, LGDA-008, LGDA-010

## Architectural Context
Based on **ADR-007** (Security Strategy), we need comprehensive security hardening including SQL injection prevention, data privacy, audit trails, and compliance framework for production deployment.

## Objective
Implement production-grade security with comprehensive SQL injection prevention, data privacy controls, audit trails, and compliance framework suitable for enterprise deployment.

## Detailed Analysis

### Current Problems
- **Basic SQL injection prevention**: Limited to simple pattern matching
- **No data privacy controls**: No PII detection or masking
- **Missing audit trails**: No tracking of data access or query execution
- **No authentication/authorization**: No user identity or access control
- **Compliance gaps**: No GDPR, SOX, or industry compliance framework
- **Secret management**: API keys in plain text configuration

### Solution Architecture
```python
# src/security/core.py
class SecurityManager:
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.sql_validator = SQLSecurityValidator()
        self.privacy_controller = DataPrivacyController()
        self.audit_logger = AuditLogger()

    async def validate_and_execute_query(
        self,
        query: str,
        user_context: UserContext
    ) -> SecureQueryResult:
        """Comprehensive security validation before query execution"""

# src/security/sql_security.py
class SQLSecurityValidator:
    def __init__(self):
        self.allowed_functions = SAFE_SQL_FUNCTIONS
        self.blocked_patterns = DANGEROUS_SQL_PATTERNS
        self.parser = sqlparse

    def validate_sql_security(self, sql: str) -> SecurityValidationResult:
        """Multi-layer SQL security validation"""
        # 1. Parse and validate syntax
        # 2. Check for injection patterns
        # 3. Validate table access permissions
        # 4. Ensure safe function usage
        # 5. Validate query complexity limits
```

### Security Components

1. **SQL Injection Prevention** (`src/security/sql_security.py`)
   - **Advanced parsing**: AST-based SQL analysis beyond pattern matching
   - **Whitelist validation**: Only approved functions and operations allowed
   - **Dynamic analysis**: Runtime injection detection
   - **Parameterized queries**: Safe parameter binding where possible

2. **Data Privacy Controls** (`src/security/privacy.py`)
   - **PII detection**: Automatic identification of sensitive data
   - **Data masking**: Anonymize sensitive information in results
   - **Access controls**: Column-level and row-level security
   - **Retention policies**: Automatic data expiration and cleanup

3. **Authentication & Authorization** (`src/security/auth.py`)
   - **User identity management**: Integration with enterprise identity providers
   - **Role-based access control**: Fine-grained permissions
   - **API key management**: Secure credential handling
   - **Session management**: Secure session handling and expiration

4. **Audit & Compliance** (`src/security/audit.py`)
   - **Comprehensive audit trails**: All data access and modifications
   - **Compliance reporting**: GDPR, SOX, HIPAA compliance reports
   - **Data lineage tracking**: Track data flow and transformations
   - **Regulatory controls**: Configurable compliance frameworks

### Detailed Implementation

#### Advanced SQL Security Validation
```python
# src/security/sql_validator.py
class AdvancedSQLValidator:
    def __init__(self):
        self.safe_functions = {
            'COUNT', 'SUM', 'AVG', 'MIN', 'MAX',
            'ROUND', 'CAST', 'EXTRACT', 'DATE', 'TIMESTAMP'
        }
        self.dangerous_patterns = [
            r';\s*(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE)',
            r'UNION\s+SELECT',
            r'(exec|execute)\s*\(',
            r'--.*$',
            r'/\*.*?\*/',
        ]

    def validate_ast_security(self, sql: str) -> SecurityValidationResult:
        """AST-based security validation"""
        try:
            parsed = sqlglot.parse_one(sql, dialect="bigquery")
        except Exception as e:
            return SecurityValidationResult(
                is_safe=False,
                violation_type="PARSE_ERROR",
                details=f"SQL parsing failed: {e}"
            )

        # Validate node types
        for node in parsed.walk():
            if isinstance(node, sqlglot.expressions.Drop):
                return SecurityValidationResult(
                    is_safe=False,
                    violation_type="DANGEROUS_OPERATION",
                    details="DROP statements not allowed"
                )

        return SecurityValidationResult(is_safe=True)

    def validate_table_access(self, sql: str, user_permissions: Set[str]) -> bool:
        """Validate user has access to all referenced tables"""
        tables = self.extract_table_references(sql)
        unauthorized_tables = tables - user_permissions

        if unauthorized_tables:
            raise SecurityError(f"Access denied to tables: {unauthorized_tables}")

        return True
```

#### Data Privacy Controller
```python
# src/security/privacy.py
class DataPrivacyController:
    def __init__(self):
        self.pii_patterns = {
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
            'phone': r'\b\d{3}-\d{3}-\d{4}\b',
            'credit_card': r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b'
        }

    def detect_pii_in_results(self, df: pd.DataFrame) -> PIIDetectionResult:
        """Detect PII in query results"""
        pii_findings = []

        for column in df.columns:
            for pii_type, pattern in self.pii_patterns.items():
                matches = df[column].astype(str).str.contains(pattern, na=False)
                if matches.any():
                    pii_findings.append(PIIFinding(
                        column=column,
                        pii_type=pii_type,
                        count=matches.sum()
                    ))

        return PIIDetectionResult(findings=pii_findings)

    def mask_sensitive_data(self, df: pd.DataFrame, mask_config: MaskConfig) -> pd.DataFrame:
        """Apply data masking based on configuration"""
        masked_df = df.copy()

        for finding in mask_config.pii_findings:
            if finding.column in masked_df.columns:
                if finding.pii_type == 'email':
                    masked_df[finding.column] = masked_df[finding.column].str.replace(
                        r'(\w+)@(\w+)', r'***@\2', regex=True
                    )
                elif finding.pii_type == 'credit_card':
                    masked_df[finding.column] = masked_df[finding.column].str.replace(
                        r'\d(?=\d{4})', '*', regex=True
                    )

        return masked_df
```

#### Comprehensive Audit Trail
```python
# src/security/audit.py
class AuditLogger:
    def __init__(self, config: AuditConfig):
        self.config = config
        self.storage = AuditStorageBackend(config.storage_type)

    async def log_query_execution(
        self,
        user: UserContext,
        question: str,
        sql: str,
        result_metadata: Dict
    ):
        """Log comprehensive query execution audit trail"""
        audit_event = AuditEvent(
            event_type="QUERY_EXECUTION",
            timestamp=datetime.utcnow(),
            user_id=user.user_id,
            user_email=user.email,
            session_id=user.session_id,
            question=question,
            sql_query=sql,
            tables_accessed=self.extract_tables(sql),
            rows_returned=result_metadata.get('row_count', 0),
            data_size_bytes=result_metadata.get('data_size', 0),
            execution_time_ms=result_metadata.get('execution_time', 0),
            pii_detected=result_metadata.get('pii_detected', False),
            compliance_flags=result_metadata.get('compliance_flags', [])
        )

        await self.storage.store_audit_event(audit_event)

    async def generate_compliance_report(
        self,
        report_type: str,
        start_date: datetime,
        end_date: datetime
    ) -> ComplianceReport:
        """Generate compliance reports for regulatory requirements"""
        events = await self.storage.query_audit_events(start_date, end_date)

        if report_type == "GDPR_DATA_ACCESS":
            return self.generate_gdpr_access_report(events)
        elif report_type == "SOX_DATA_INTEGRITY":
            return self.generate_sox_integrity_report(events)
        elif report_type == "HIPAA_DATA_USAGE":
            return self.generate_hipaa_usage_report(events)
```

#### Secure Configuration Management
```python
# src/security/secrets.py
class SecureConfigManager:
    def __init__(self, vault_provider: str = "hashicorp_vault"):
        self.vault = self.create_vault_client(vault_provider)

    async def get_secure_credential(self, credential_path: str) -> str:
        """Retrieve credentials from secure vault"""
        try:
            return await self.vault.get_secret(credential_path)
        except VaultError as e:
            raise SecurityError(f"Failed to retrieve credential: {e}")

    def mask_sensitive_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive configuration for logging"""
        masked_config = config.copy()

        sensitive_keys = ['api_key', 'password', 'secret', 'token', 'credential']
        for key in masked_config:
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                masked_config[key] = "***MASKED***"

        return masked_config
```

### Security Validation Framework

#### Multi-Layer Security Checks
1. **Input validation**: Question sanitization and length limits
2. **SQL analysis**: AST parsing and pattern detection
3. **Access control**: Table and column permission validation
4. **Output filtering**: PII detection and masking
5. **Audit logging**: Comprehensive activity tracking

#### Threat Modeling Coverage
- **SQL injection attacks**: Malicious SQL in natural language input
- **Data exfiltration**: Unauthorized access to sensitive data
- **Privilege escalation**: Accessing data beyond authorized scope
- **Compliance violations**: GDPR, SOX, HIPAA regulatory breaches
- **Insider threats**: Legitimate users accessing inappropriate data

### Dependencies
- **Coordinates with LGDA-008**: Use secure configuration management
- **Independent**: Core security can be developed standalone
- **Integrates with LGDA-010**: Security testing framework
- **Foundation**: Required for production deployment

## Acceptance Criteria

### Security Requirements
- ✅ Zero SQL injection vulnerabilities in penetration testing
- ✅ All PII automatically detected and masked in results
- ✅ Complete audit trail for all data access operations
- ✅ Role-based access control with fine-grained permissions

### Compliance Requirements
- ✅ GDPR compliance: Data subject rights, consent tracking, data minimization
- ✅ SOX compliance: Data integrity, change tracking, access controls
- ✅ HIPAA compliance: PHI protection, access logging, breach detection
- ✅ Industry standards: ISO 27001, NIST Cybersecurity Framework alignment

### Performance Requirements
- ✅ Security validation overhead < 500ms per request
- ✅ Audit logging overhead < 100ms per request
- ✅ PII detection overhead < 200ms per result set
- ✅ No impact on core functionality performance

### Integration Tests
```python
def test_sql_injection_prevention():
    """All known SQL injection techniques are blocked"""

def test_pii_detection_accuracy():
    """PII detection has >95% accuracy with <1% false positives"""

def test_audit_trail_completeness():
    """All data access operations are logged completely"""

def test_access_control_enforcement():
    """Users can only access authorized data"""

def test_compliance_reporting():
    """Compliance reports meet regulatory requirements"""
```

## Security Scenarios Coverage

### Attack Scenarios
- **SQL injection via natural language**: Malicious intent in business questions
- **Data exfiltration attempts**: Users trying to access unauthorized data
- **Privilege escalation**: Attempting to access higher-privilege data
- **Social engineering**: Manipulating system through crafted questions

### Compliance Scenarios
- **GDPR data subject requests**: Right to access, rectification, erasure
- **SOX audit requirements**: Financial data integrity and controls
- **HIPAA breach notification**: PHI access and disclosure tracking
- **Industry audits**: Demonstrating security controls and compliance

### Operational Security
- **Incident response**: Security event detection and response
- **Security monitoring**: Real-time threat detection and alerting
- **Access review**: Periodic access rights validation
- **Vulnerability management**: Security update and patch management

## Rollback Plan
1. **Security bypass**: `LGDA_SECURITY_VALIDATION=basic` (emergency only)
2. **Component-specific disable**: Disable specific security features independently
3. **Fallback to basic**: Use original simple pattern-based validation
4. **Monitoring**: Track security events and rollback if issues detected

## Estimated Effort
**4-5 days** | **Files**: ~12 | **Tests**: ~20 new

## Parallel Execution Notes
- **Independent development**: Core security components can be developed standalone
- **Coordinates with LGDA-008**: Integrate with secure configuration management
- **Uses LGDA-010**: Leverage test infrastructure for security testing
- **Foundation for production**: Required before production deployment
- **Can start immediately**: Security validation and audit framework development can begin independently
