# LGDA-010: Test Infrastructure Enhancement

**Priority**: MEDIUM | **Type**: Quality | **Parallel**: Can run with LGDA-007, LGDA-008, LGDA-009

## Архитектурный контекст
Based on **ADR-004** (Test Strategy), we need comprehensive test coverage for production deployment, including integration tests with real services and performance validation.

## Цель задачи
Build comprehensive test infrastructure supporting TDD development, integration testing with real services, performance validation, and production deployment confidence.

## Детальный анализ

### Current Problems
- **Low test coverage**: 0% coverage on main business logic
- **Missing integration tests**: No tests with real BigQuery/LLM services
- **No performance tests**: No validation of response times or resource usage
- **Test environment mismatch**: Dev tests don't match production conditions
- **Manual testing overhead**: Real-world validation requires manual intervention

### Solution Architecture
```python
# tests/conftest.py
@pytest.fixture(scope="session")
def test_config():
    """Test-specific configuration with overrides"""
    return TestConfig(
        use_real_services=os.getenv("LGDA_INTEGRATION_TESTS", "false").lower() == "true",
        bigquery_project="test-project-123456",
        test_dataset="lgda_test_data",
        llm_provider="mock",
        max_test_duration=30
    )

@pytest.fixture
def mock_bigquery_client():
    """Mock BigQuery client with realistic responses"""

@pytest.fixture
def real_bigquery_client():
    """Real BigQuery client for integration tests"""
```

### Test Infrastructure Components

1. **Unit Test Framework** (`tests/unit/`)
   - **Component isolation**: Test each node independently
   - **Mock all external services**: BigQuery, LLM providers, file system
   - **Fast execution**: All unit tests < 10 seconds
   - **TDD support**: Easy test-first development

2. **Integration Test Framework** (`tests/integration/`)
   - **Real service integration**: Optional real BigQuery/LLM testing
   - **End-to-end scenarios**: Full pipeline validation
   - **Environment configuration**: Test/staging/production configs
   - **Performance validation**: Response time and resource usage

3. **Performance Test Framework** (`tests/performance/`)
   - **Load testing**: Multiple concurrent requests
   - **Response time validation**: SLA compliance testing
   - **Resource usage monitoring**: Memory, CPU, BigQuery slots
   - **Regression testing**: Performance comparison over time

4. **Test Data Management** (`tests/fixtures/`)
   - **Realistic test data**: Representative BigQuery responses
   - **Schema validation**: Ensure test data matches production
   - **Data generation**: Automated test data creation
   - **Privacy compliance**: No real customer data in tests

### Detailed Implementation

#### Unit Test Coverage Enhancement
```python
# tests/unit/test_nodes.py
class TestPlanNode:
    def test_plan_generation_with_schema(self):
        """Plan node generates valid plans with schema context"""

    def test_plan_handles_complex_queries(self):
        """Plan node creates appropriate structure for complex analytics"""

    def test_plan_validates_table_access(self):
        """Plan node enforces table access security"""

class TestSQLSynthesisNode:
    def test_sql_generation_accuracy(self):
        """SQL generation produces syntactically correct queries"""

    def test_sql_injection_prevention(self):
        """SQL generation prevents injection attacks"""

    def test_sql_optimization_hints(self):
        """SQL generation includes performance optimizations"""
```

#### Integration Test Scenarios
```python
# tests/integration/test_end_to_end.py
class TestRealWorldScenarios:
    @pytest.mark.integration
    def test_simple_analytics_end_to_end(self):
        """Simple order count query works end-to-end"""

    @pytest.mark.integration
    def test_complex_customer_segmentation(self):
        """Complex customer analysis produces insights"""

    @pytest.mark.integration
    def test_error_recovery_with_real_services(self):
        """Error recovery works with real service failures"""
```

#### Performance Test Suite
```python
# tests/performance/test_response_times.py
class TestPerformanceRequirements:
    def test_simple_query_response_time(self):
        """Simple queries complete within 10 seconds"""

    def test_complex_query_response_time(self):
        """Complex queries complete within 60 seconds"""

    def test_concurrent_request_handling(self):
        """System handles 5 concurrent requests"""

    def test_memory_usage_bounds(self):
        """Memory usage stays within 512MB bounds"""
```

### Test Environment Configuration

#### Local Development Testing
- **Mock everything**: Fast feedback loop
- **Schema validation**: Ensure mocks match reality
- **TDD support**: Easy test-first development
- **Coverage reporting**: Track test coverage improvements

#### CI/CD Testing
- **Unit tests**: All environments
- **Integration tests**: With test BigQuery project
- **Performance regression**: Compare to baseline
- **Security scanning**: Dependency and code security

#### Pre-Production Testing
- **Real service integration**: Production-like environment
- **Load testing**: Expected production load
- **End-to-end scenarios**: Complete user journeys
- **Rollback testing**: Deployment rollback scenarios

### Dependencies
- **Uses LGDA-008**: Test configuration from unified config
- **Coordinates with LGDA-009**: Error handling test scenarios
- **Independent**: Core test infrastructure is standalone
- **Enables future**: Foundation for LGDA-011 (monitoring) testing

## Критерии приемки
## Возможные сложности
- Детерминизм и стабильность тестов под нагрузкой
- Стоимость интеграционных тестов с реальными сервисами
- Поддержка версий Python и кросс-платформенность CI

## Integration Points
Зависит от LGDA-008 (единая конфигурация), покрывает LGDA-007/009 сценарии, интегрируется с LGDA-011 (метрики тестов).

### Coverage Requirements
- ✅ Unit test coverage > 90% on business logic
- ✅ Integration test coverage for all user scenarios
- ✅ Performance test coverage for SLA requirements
- ✅ Error scenario test coverage > 80%

### Performance Requirements
- ✅ Unit test suite execution < 30 seconds
- ✅ Integration test suite execution < 10 minutes
- ✅ Performance test validation of < 60s response times
- ✅ CI/CD pipeline execution < 15 minutes

### Quality Requirements
- ✅ All tests deterministic and reliable
- ✅ Test data representative of production
- ✅ Clear test failure diagnostics
- ✅ Easy test maintenance and updates

### Integration Tests
```python
def test_unit_test_coverage_requirement():
    """Unit test coverage meets 90% requirement"""

def test_integration_tests_with_real_bigquery():
    """Integration tests work with real BigQuery"""

def test_performance_test_sla_validation():
    """Performance tests validate SLA requirements"""

def test_test_data_production_representative():
    """Test data matches production data patterns"""
```

## Test Scenario Priorities

### High Priority (Core Functionality)
- Simple analytics queries (order counts, AOV)
- Complex customer segmentation analysis
- Error recovery and retry scenarios
- Security validation (SQL injection, table access)

### Medium Priority (Edge Cases)
- Large dataset handling
- Concurrent request processing
- Provider failover scenarios
- Configuration validation

### Low Priority (Non-Functional)
- UI/UX testing
- Documentation validation
- Performance optimization edge cases
- Monitoring and alerting validation

## Test Data Strategy

### Mock Data Requirements
- **Realistic schema**: Match production BigQuery schema exactly
- **Representative volume**: Test with realistic data sizes
- **Edge case coverage**: Null values, empty results, large results
- **Performance representative**: Similar query complexity

### Real Data Integration
- **Test BigQuery project**: Separate project for integration tests
- **Anonymized data**: No real customer information
- **Controlled datasets**: Predictable results for validation
- **Cost management**: Limited query budgets

## Rollback Plan
1. **Test bypass**: `LGDA_SKIP_EXTENDED_TESTS=true`
2. **Gradual rollout**: Enable test categories incrementally
3. **Fallback to manual**: Manual testing if automated tests fail
4. **Test environment isolation**: Tests don't affect production

## Estimated Effort
**3-4 days** | **Files**: ~12 | **Tests**: ~25 new

## Parallel Execution Notes
- **Independent development**: Test infrastructure is largely standalone
- **Uses LGDA-008**: Leverage unified configuration for test config
- **Coordinates with LGDA-009**: Test error handling scenarios
- **Enables quality gates**: Foundation for deployment confidence
- **Can start immediately**: Mock-based tests can be developed while other tasks are in progress
