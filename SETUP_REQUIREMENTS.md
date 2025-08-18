# Setup Requirements for Development

## Required API Keys and Services

### 1. Google Cloud Platform Setup
**Required for BigQuery access**

```bash
# Install Google Cloud CLI
brew install google-cloud-sdk

# Authenticate (choose one method)
gcloud auth application-default login

# OR use service account key
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"

# Set your GCP project
gcloud config set project YOUR_PROJECT_ID
```

**Required Environment Variables:**
```env
BIGQUERY_PROJECT=your-gcp-project-id
BIGQUERY_LOCATION=US
DATASET_ID=bigquery-public-data.thelook_ecommerce
```

### 2. Google AI Studio (Gemini API)
**Required for LLM functionality**

1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Create API key
3. Add to environment:

```env
GOOGLE_API_KEY=your_google_ai_studio_key
MODEL_NAME=gemini-1.5-pro
```

### 3. Optional: AWS Bedrock (Fallback)
**Optional for LLM fallback**

```bash
# Install AWS CLI
brew install awscli

# Configure credentials
aws configure
```

```env
AWS_REGION=eu-west-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0
```

## Development Tools Setup

### 1. Python Environment
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install development dependencies
pip install -r requirements.txt
pip install pytest pytest-mock pytest-cov ruff mypy pre-commit
```

### 2. Pre-commit Hooks
```bash
# Install pre-commit hooks
pre-commit install

# Test hooks work
pre-commit run --all-files
```

### 3. VS Code Extensions (Recommended)
- Python
- Pylance  
- Python Test Explorer
- Jupyter (for data analysis)
- Thunder Client (for API testing)

## MCP Servers (Not Required)

For this project, we **don't need** to set up MCP servers because:

1. **BigQuery access** - Direct API via google-cloud-bigquery
2. **Gemini API** - Direct HTTP calls via google-generativeai
3. **Local development** - All processing happens locally
4. **Simple architecture** - No need for protocol abstraction

## Testing Without Real APIs

### Mock Development Setup
```bash
# For development without real API keys
export MOCK_MODE=true
export GOOGLE_API_KEY=mock_key_for_testing
export BIGQUERY_PROJECT=mock_project
```

### Test Data
- Use synthetic DataFrames for testing
- Mock BigQuery responses with sample schemas
- Mock LLM responses with realistic JSON

## Cost Considerations

### BigQuery
- **Free tier**: 1TB query processing per month
- **Cost control**: MAX_BYTES_BILLED=100000000 (100MB limit)
- **Recommendation**: Start with small queries during development

### Gemini API
- **Free tier**: Available for development
- **Rate limits**: 15 requests per minute (free tier)
- **Cost tracking**: Monitor token usage

## Quick Setup Script

Create `setup_dev.sh`:
```bash
#!/bin/bash
echo "Setting up LangGraph Data Analysis Agent development environment..."

# Check if required tools are installed
command -v python3 >/dev/null 2>&1 || { echo "Python 3 required but not installed."; exit 1; }
command -v gcloud >/dev/null 2>&1 || { echo "Google Cloud CLI recommended. Install with: brew install google-cloud-sdk"; }

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-mock pytest-cov ruff mypy pre-commit

# Setup pre-commit
pre-commit install

# Copy environment template
cp .env.example .env
echo "Please edit .env file with your API keys"

echo "Setup complete! Next steps:"
echo "1. Edit .env file with your API keys"
echo "2. Run: gcloud auth application-default login"
echo "3. Run: pytest to verify setup"
```

## Minimal Setup for LGDA-001

For starting with TDD, you need:
1. **Python 3.10+** ✓ (already have)
2. **pytest tools** - `pip install pytest pytest-mock pytest-cov`
3. **Mock credentials** - for testing without real APIs

Real API keys needed only for integration testing (LGDA-010+).

Ready to proceed with LGDA-001 using mocks?
