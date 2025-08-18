## Architecture overview

This agent uses a LangGraph pipeline to transform a natural‑language business question into a validated BigQuery query and a concise insight report. The flow is: plan -> synthesize SQL -> validate -> execute -> analyze -> report, with strict SQL safety policies and BigQuery cost guards.

Key components:
- CLI (Click + Rich) for interaction and verbose tracing
- LangGraph nodes for each step with clear transitions
- Google BigQuery as the data source (public dataset thelook_ecommerce)
- Gemini (google-generativeai) as the LLM backend (optional Bedrock fallback)

### Component diagram

```mermaid
flowchart TD
  subgraph CLI["� CLI INTERFACE"]
    U["👤 USER"]
  end
  
  subgraph AGENT["🤖 LANGGRAPH AGENT"]
    P["📋 PLAN<br/>Schema-aware JSON"] 
    S["🔧 SYNTHESIZE SQL<br/>Template + LLM"]
    V["✅ VALIDATE SQL<br/>sqlglot + policies"]
    X["▶️ EXECUTE SQL<br/>BigQuery runner"]
    A["📊 ANALYZE DATA<br/>pandas summary"]
    R["📝 GENERATE REPORT<br/>Executive insight"]
    
    M[("💾 SHORT MEMORY<br/>Chat History")]
    
    P --> S --> V
    V -->|"✓ Valid"| X
    V -->|"❌ Invalid"| PF["🔄 FALLBACK"]
    X --> A --> R
    
    P -.-> M
    R -.-> M
  end

  U ==>|"💬 Business Question"| P
  R ==>|"📄 Final Report"| U

  subgraph GCP["☁️ GOOGLE CLOUD PLATFORM"]
    BQ[("🗄️ BIGQUERY<br/>thelook_ecommerce")]
    SCHEMA[("📋 SCHEMA<br/>INFORMATION_SCHEMA")]
  end

  subgraph LLMS["🧠 LANGUAGE MODELS"]
    G["✨ GEMINI<br/>Primary LLM"]
    BR["🔄 BEDROCK<br/>Fallback LLM"]
  end

  P --> SCHEMA
  X --> BQ
  P --> G
  S --> G
  R --> G
  PF --> BR

  %% Strong styling
  classDef agentBox fill:#1565C0,stroke:#0D47A1,stroke-width:3px,color:#FFFFFF
  classDef gcpBox fill:#0F9D58,stroke:#0D7E3B,stroke-width:3px,color:#FFFFFF
  classDef llmBox fill:#FF6F00,stroke:#E65100,stroke-width:3px,color:#FFFFFF
  classDef cliBox fill:#7B1FA2,stroke:#4A148C,stroke-width:3px,color:#FFFFFF
  classDef memoryBox fill:#D32F2F,stroke:#B71C1C,stroke-width:3px,color:#FFFFFF
  classDef dataBox fill:#388E3C,stroke:#1B5E20,stroke-width:3px,color:#FFFFFF

  class P,S,V,X,A,R,PF agentBox
  class BQ,SCHEMA dataBox
  class G,BR llmBox
  class U cliBox
  class M memoryBox
```

### Data flow diagram

```mermaid
sequenceDiagram
  participant U as "👤 USER"
  participant C as "� CLI"
  participant A as "🤖 AGENT"
  participant M as "💾 MEMORY"
  participant L as "✨ GEMINI"
  participant BQ as "🗄️ BIGQUERY"
  participant PD as "📊 PANDAS"

  Note over U,PD: Business Analysis Flow

  U->>+C: Business Question
  C->>+A: Process Question
  
  Note over A,M: Load Context
  A->>M: Get Chat History
  M-->>A: Previous Context

  Note over A,L: Planning Phase
  A->>+L: Generate Plan (schema-aware)
  L-->>-A: JSON Plan
  
  Note over A,BQ: Schema Discovery
  A->>+BQ: Fetch Table Schemas
  BQ-->>-A: Column Metadata

  Note over A,L: SQL Generation
  A->>+L: Synthesize SQL Query
  L-->>-A: BigQuery SQL
  
  Note over A: Security Validation
  A->>A: Validate SQL (SELECT-only, whitelist)

  alt SQL Valid
    Note over A,BQ: Data Execution
    A->>+BQ: Execute Query (limits applied)
    BQ-->>-A: Result Dataset
    
    Note over A,PD: Data Analysis
    A->>+PD: Analyze DataFrame
    PD-->>-A: Statistical Summary
    
    Note over A,L: Report Generation
    A->>+L: Generate Business Insight
    L-->>-A: Executive Report
    
    Note over A,M: Store Session
    A->>M: Save Interaction
  else SQL Invalid
    Note over A: Error Handling
    A->>A: Fallback Strategy
  end

  A-->>-C: Final Report
  C-->>-U: Business Insight

  Note over U,PD: Session Complete
```

Notes:
- SQL safety: only SELECT; only tables orders, order_items, products, users; enforced LIMIT on non-aggregates; maximum_bytes_billed.
- Resilience: optional LLM fallback path; use_query_cache enabled to reduce cost/latency.