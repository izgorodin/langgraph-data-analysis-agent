from __future__ import annotations

import os
from typing import Optional

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

from .config import settings

# Configure Gemini
if settings.google_api_key:
    genai.configure(api_key=settings.google_api_key)


def llm_completion(
    prompt: str, system: Optional[str] = None, model: Optional[str] = None
) -> str:
    """Generate completion with fallback to mock responses during development."""
    
    # If in test mode or API limits exceeded, use mock responses
    if os.getenv("LGDA_USE_MOCK_LLM") == "true" or not settings.google_api_key:
        return _mock_llm_response(prompt, system)
    
    try:
        model = model or settings.model_name
        contents = prompt if system is None else f"System: {system}\n\nUser: {prompt}"
        resp = genai.GenerativeModel(model).generate_content(contents)
        return resp.text or ""
    except ResourceExhausted:
        # API quota exceeded - fallback to mock
        print("🔄 API quota exceeded, using mock response")
        return _mock_llm_response(prompt, system)
    except Exception as e:
        # Other errors - fallback to mock
        print(f"🔄 LLM error: {e}, using mock response")
        return _mock_llm_response(prompt, system)


def _mock_llm_response(prompt: str, system: Optional[str] = None) -> str:
    """Smart mock responses based on prompt content."""
    
    prompt_lower = prompt.lower()
    
    # Plan generation
    if "json object" in prompt_lower and "analysis request" in prompt_lower:
        return '''{"task": "sales_analysis", "tables": ["orders", "order_items", "products"], "time_range": "last_30_days", "dimensions": ["product_name"], "metrics": ["total_sales"], "filters": [], "grain": "daily"}'''
    
    # SQL generation
    if "bigquery" in prompt_lower and "select" in prompt_lower:
        return '''SELECT 
    p.name as product_name,
    SUM(oi.sale_price) as total_sales,
    COUNT(*) as order_count
FROM `bigquery-public-data.thelook_ecommerce.order_items` oi
JOIN `bigquery-public-data.thelook_ecommerce.products` p ON oi.product_id = p.id
WHERE oi.created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY p.name
ORDER BY total_sales DESC
LIMIT 1000'''
    
    # Report generation  
    if "insight" in prompt_lower or "report" in prompt_lower:
        return '''Based on the sales analysis, here are the key insights:

📈 **Top Performance**: The highest-selling products generated significant revenue in the last 30 days.

💡 **Key Metrics**: 
- Total sales volume shows strong market demand
- Order frequency indicates customer engagement
- Product diversity demonstrates market reach

🎯 **Next Questions**:
1. Which product categories drive the most profit margins?
2. What seasonal trends can we identify in customer purchasing behavior?'''
    
    return "Mock LLM response for development testing."


def llm_fallback(prompt: str, system: Optional[str] = None) -> str:
    # Placeholder for Bedrock if needed later
    return _mock_llm_response(prompt, system)
