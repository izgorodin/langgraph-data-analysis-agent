# LGDA-012: Performance Optimization and Caching

**Priority**: MEDIUM | **Type**: Performance | **Parallel**: Can run with LGDA-007, LGDA-008, LGDA-011

## Архитектурный контекст
Based on **ADR-006** (Performance Strategy), we need systematic performance optimization including intelligent caching, query optimization, and resource management to ensure production scalability.

## Цель задачи
Implement comprehensive performance optimization with intelligent caching, query optimization, and resource management to achieve production SLA requirements.

## Детальный анализ

### Current Problems
- **No caching strategy**: Repeated identical queries execute multiple times
- **Suboptimal SQL generation**: LLM generates unoptimized queries
- **Resource waste**: No connection pooling or resource reuse
- **Memory inefficiency**: Large DataFrames loaded entirely into memory
- **Sequential processing**: No parallelization of independent operations

### Solution Architecture
```python
# src/performance/cache.py
class QueryCache:
    def __init__(self, redis_client: Optional[Redis] = None):
        self.redis = redis_client
        self.memory_cache = TTLCache(maxsize=1000, ttl=3600)

    async def get_cached_result(self, query_hash: str) -> Optional[CacheEntry]:
        """Get cached query result with semantic similarity"""

    async def cache_query_result(self, query: str, result: pd.DataFrame, metadata: Dict):
        """Cache query result with intelligent expiration"""

# src/performance/optimization.py
class QueryOptimizer:
    def optimize_sql(self, sql: str, schema: Dict) -> str:
        """Apply SQL optimization patterns"""
        # Add LIMIT clauses to non-aggregated queries
        # Optimize JOIN orders based on table sizes
        # Add appropriate indexes suggestions
        # Partition-aware query optimization
```

### Performance Components

1. **Intelligent Caching** (`src/performance/cache.py`)
   - **Query result caching**: Cache BigQuery results with TTL
   - **Semantic similarity**: Cache similar queries, not just identical
   - **LLM response caching**: Cache prompt responses for identical contexts
   - **Schema caching**: Cache table metadata for faster planning

2. **Query Optimization** (`src/performance/optimization.py`)
   - **SQL optimization**: Automatic query performance improvements
   - **Cost estimation**: Predict and limit BigQuery costs
   - **Execution planning**: Optimize query execution order
   - **Result size management**: Automatic LIMIT and pagination

3. **Resource Management** (`src/performance/resources.py`)
   - **Connection pooling**: Reuse BigQuery and LLM connections
   - **Memory management**: Stream large results, avoid OOM
   - **Concurrency control**: Limit concurrent operations
   - **Resource monitoring**: Track and optimize resource usage

4. **Parallel Processing** (`src/performance/parallel.py`)
   - **Concurrent execution**: Parallelize independent operations
   - **Async optimization**: Non-blocking I/O operations
   - **Pipeline parallelism**: Overlap planning, execution, analysis
   - **Batch processing**: Group similar operations

### Detailed Implementation

#### Intelligent Query Caching
```python
# src/performance/semantic_cache.py
class SemanticQueryCache:
    def __init__(self, similarity_threshold: float = 0.85):
        self.threshold = similarity_threshold
        self.embeddings_cache = {}

    async def find_similar_cached_query(self, question: str) -> Optional[CacheEntry]:
        """Find semantically similar cached queries"""
        question_embedding = await self.get_question_embedding(question)

        for cached_question, cache_entry in self.cache.items():
            similarity = self.cosine_similarity(question_embedding, cache_entry.embedding)
            if similarity > self.threshold:
                return cache_entry

        return None

    async def cache_with_embedding(self, question: str, result: pd.DataFrame):
        """Cache result with semantic embedding"""
        embedding = await self.get_question_embedding(question)
        cache_entry = CacheEntry(
            question=question,
            result=result,
            embedding=embedding,
            timestamp=datetime.utcnow()
        )
        self.cache[question] = cache_entry
```

#### SQL Query Optimization
```python
# src/performance/sql_optimizer.py
class SQLOptimizer:
    def __init__(self, schema_info: Dict):
        self.schema = schema_info

    def optimize_query(self, sql: str) -> OptimizedQuery:
        """Apply comprehensive SQL optimizations"""
        parsed = sqlparse.parse(sql)[0]

        optimizations = []

        # Add LIMIT if missing and not aggregated
        if not self._has_aggregation(parsed) and not self._has_limit(parsed):
            optimizations.append(self._add_limit_clause(parsed, 10000))

        # Optimize JOIN order based on table sizes
        if self._has_joins(parsed):
            optimizations.append(self._optimize_join_order(parsed))

        # Add cost estimation
        estimated_cost = self._estimate_query_cost(parsed)

        return OptimizedQuery(
            original_sql=sql,
            optimized_sql=self._apply_optimizations(parsed, optimizations),
            estimated_cost=estimated_cost,
            optimizations_applied=optimizations
        )
```

#### Memory-Efficient Processing
```python
# src/performance/memory_management.py
class DataFrameStreamer:
    def __init__(self, chunk_size: int = 10000):
        self.chunk_size = chunk_size

    async def stream_bigquery_results(self, query: str) -> AsyncIterator[pd.DataFrame]:
        """Stream BigQuery results in chunks to avoid memory issues"""
        job = self.client.query(query)

        for chunk in job.result(page_size=self.chunk_size):
            yield chunk.to_dataframe()

    async def process_large_dataset(self, query: str, processor: Callable) -> Any:
        """Process large datasets without loading everything into memory"""
        aggregated_result = None

        async for chunk in self.stream_bigquery_results(query):
            chunk_result = await processor(chunk)
            aggregated_result = self._aggregate_results(aggregated_result, chunk_result)

        return aggregated_result
```

#### Parallel Pipeline Execution
```python
# src/performance/parallel_pipeline.py
class ParallelPipelineExecutor:
    def __init__(self, max_concurrency: int = 3):
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_with_parallelism(self, state: AgentState) -> AgentState:
        """Execute pipeline with intelligent parallelism"""

        # Phase 1: Planning (sequential)
        state = await self.plan_node(state)

        # Phase 2: SQL generation and validation (can be parallel for multiple queries)
        if len(state.sub_queries) > 1:
            sql_tasks = [
                self.generate_and_validate_sql(sub_query)
                for sub_query in state.sub_queries
            ]
            results = await asyncio.gather(*sql_tasks)
            state.sql_queries = results
        else:
            state = await self.synthesize_sql_node(state)
            state = await self.validate_sql_node(state)

        # Phase 3: Execution (parallel where safe)
        # Phase 4: Analysis and reporting (parallel for multiple datasets)

        return state
```

### Performance Optimization Targets

#### Response Time Optimization
- **Simple queries**: < 10 seconds (target: 5 seconds)
- **Complex queries**: < 60 seconds (target: 30 seconds)
- **Cache hits**: < 2 seconds (target: 500ms)
- **Planning phase**: < 5 seconds (target: 2 seconds)

#### Resource Optimization
- **Memory usage**: < 512MB per request (target: 256MB)
- **BigQuery slots**: Efficient slot utilization
- **LLM tokens**: Optimize prompt size and reduce waste
- **Connection reuse**: 90%+ connection pool hit rate

#### Cost Optimization
- **BigQuery costs**: < $0.10 per query (target: $0.05)
- **LLM costs**: < $0.02 per request (target: $0.01)
- **Infrastructure costs**: Minimize compute and memory requirements
- **Cache efficiency**: 60%+ cache hit rate for repeated patterns

### Dependencies
- **Independent**: Core performance optimization can be developed standalone
- **Coordinates with LGDA-008**: Use performance configuration from unified config
- **Uses LGDA-011**: Performance metrics and monitoring integration
- **Enhances all components**: Performance improvements benefit entire pipeline

## Критерии приемки
## Возможные сложности
- Регрессии производительности при оптимизациях
- Ограничения BigQuery/LLM провайдеров
- Баланс качества анализа и скорости

## Integration Points
Работает в связке с LGDA-007 (ретраи), LGDA-008 (конфиг), LGDA-011 (метрики производительности), LGDA-013 (безопасность).

## Безопасность
- Оптимизация SQL (LIMIT, JOIN order и т.п.) не должна обходить/ослаблять проверки безопасности (см. LGDA-013)
- Кэширование исключает хранение PII/секретов; внедрить маскирование и строгие TTL
- Логи/метрики не содержат SQL/секретов; применять маскирование

### Performance Requirements
- ✅ 95th percentile response time < 60 seconds for complex queries
- ✅ 95th percentile response time < 10 seconds for simple queries
- ✅ Cache hit rate > 60% for repeated query patterns
- ✅ Memory usage < 512MB per concurrent request

### Cost Requirements
- ✅ BigQuery cost < $0.10 per query on average
- ✅ LLM cost < $0.02 per request on average
- ✅ Infrastructure cost optimization of 30% vs naive implementation
- ✅ No queries exceed $1.00 cost without explicit approval

### Scalability Requirements
- ✅ Handle 10 concurrent requests without degradation
- ✅ Linear scalability up to 50 concurrent requests
- ✅ Graceful degradation under resource pressure
- ✅ No memory leaks over 24-hour operation

### Integration Tests
```python
def test_query_result_caching_accuracy():
    """Cached results match fresh query results"""

def test_semantic_similarity_caching():
    """Similar questions return cached results appropriately"""

def test_sql_optimization_performance():
    """Optimized queries perform better than originals"""

def test_memory_usage_bounds():
    """Memory usage stays within defined bounds"""

def test_parallel_execution_correctness():
    """Parallel execution produces same results as sequential"""
```

## Performance Optimization Scenarios

### High-Volume Usage
- **Concurrent requests**: Multiple users asking questions simultaneously
- **Repeated patterns**: Common business questions asked frequently
- **Large datasets**: Analysis of millions of records
- **Complex analytics**: Multi-table joins and aggregations

### Resource-Constrained Environments
- **Limited memory**: Environments with memory constraints
- **Cost sensitivity**: Minimizing BigQuery and LLM costs
- **Network limitations**: Slow or unreliable connections
- **CPU constraints**: Limited processing power

### Peak Load Handling
- **Traffic spikes**: Sudden increases in usage
- **Batch processing**: Processing multiple requests
- **Background operations**: Maintenance and optimization tasks
- **Failover scenarios**: Performance during provider failures

## Rollback Plan
1. **Performance bypass**: `LGDA_DISABLE_PERFORMANCE_OPTIMIZATIONS=true`
2. **Component-specific disable**: Disable caching, optimization, or parallelism independently
3. **Fallback to simple**: Sequential processing without optimization
4. **Performance monitoring**: Track performance impact and rollback if degraded

## Estimated Effort
**3-4 days** | **Files**: ~10 | **Tests**: ~12 new

## Parallel Execution Notes
- **Independent development**: Performance optimization has minimal dependencies
- **Coordinates with LGDA-008**: Leverage unified configuration for performance settings
- **Uses LGDA-011**: Integrate with monitoring for performance tracking
- **Benefits all tasks**: Performance improvements benefit entire system
- **Can start immediately**: Core caching and optimization can be developed independently
