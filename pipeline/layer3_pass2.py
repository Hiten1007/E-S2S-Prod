import json
import os
import time
from groq import Groq
import httpx
from typing import List, Dict, Any

from dotenv import load_dotenv
load_dotenv(override=True)

MODEL_NAME = "llama-3.3-70b-versatile"

PASS_2_SYSTEM_PROMPT = """You are an expert intelligence analyst for a global Process Electrification and Industrial Decarbonization platform.
Do not summarize the whole text into one blob. If the text mentions a new grant AND a new project, extract two separate signals.

SECTORS:
Choose ONLY from: "MMM", "Consumer Packaged Goods", "Mobility", "Power & Grid", "Cloud & Service Providers", "Energy & Chemicals", "General"

SIGNAL TYPES:
- "Opportunity" -> Projects & Programs (Factory builds, infrastructure, missions)
- "Funding" -> Grants & Incentives (Subsidies, tax credits, funding calls)
- "Regulation" -> STRICT: Only use this if a specific law, decree, policy change, or hard compliance deadline is explicitly named. Do not use for general commentary.
- "Technology" -> Technology Signals (Breakthroughs, R&D milestones, technology trends, adoptions, and insights)
- "Market Signal" -> Market Signals (Broad policy commentary, adoption rates, think-tank analyses, cost curves, market trends, costs, and insights)

INSTRUCTIONS:
Return a JSON object containing exactly one key called "signals", which must be a JSON array of objects.
Each object must have:
- "sector": string
- "signal_type": string
- "headline": string (a clear, punchy title for this specific signal)
- "summary": string (a very concise summary, STRICTLY 20 words or less. This will be used in compact PDF reports instead of the full description.)
- "description": string (Detailed summary. YOU MUST BE EXHAUSTIVE. Use bullet points within this string to explicitly list EVERY SINGLE eligibility condition, excluded sector, deadline, and financial amount. CRITICAL FORMATTING: You MUST aggressively use Markdown bolding (**text**) to highlight all critical data points, numbers, currency amounts, and dates WITHIN your sentences.)
- "deadline": string (A concise deadline for the dashboard UI. If there is a single strict deadline, format it as "DD Month YYYY". If there are multiple stages, output the final deadline or "Multiple (see description)". If rolling/open, output "Rolling". If no deadline is mentioned, output "None".)
- "impacted_regions": array of strings. This is a unified field. If it applies to a specific country or cross-border deal, list the 2-letter ISO 3166-1 alpha-2 codes (e.g., "FR", "DE", "KR"). If it applies to a broader group, use ONLY these exact group codes: ["EU", "Europe", "North America", "APAC", "Global"]. Do NOT exhaustively list member states if a group code applies.

If no relevant signals are found, return: {"signals": []}
"""

def extract_signals_from_chunk(chunk_text: str, rotator) -> List[Dict[str, Any]]:
    try:
        messages = [
            {"role": "system", "content": PASS_2_SYSTEM_PROMPT},
            {"role": "user", "content": chunk_text}
        ]
        
        result = rotator.chat(messages, temperature=0.1)
        if result is None:
            return []
            
        return result.get("signals", [])
            
    except Exception as e:
        print(f"Error calling Rotator in Pass 2: {e}")
        return []

def process_articles_pass2(articles: List[Dict[str, Any]], rotator) -> List[Dict[str, Any]]:
    master_signals = []
    
    for article in articles:
        for chunk in article.get("surviving_chunks", []):
            time.sleep(1)
            signals = extract_signals_from_chunk(chunk["text"], rotator)
            
            for sig in signals:
                # Validate the date to prevent garbage scraper data like 'Subvention'
                scraper_date = article.get("published_date", "")
                llm_date = sig.get("announcement_date")
                
                # Prioritize LLM extracted date if available
                if llm_date and llm_date != "null":
                    pub_date = llm_date
                else:
                    pub_date = scraper_date
                    
                import re
                if pub_date and not re.search(r'\d', pub_date):
                    pub_date = "[DATE UNVERIFIED]"
                elif not pub_date:
                    pub_date = "[DATE UNVERIFIED]"
                    
                sig["source_url"] = article.get("url")
                sig["source_domain"] = article.get("source_domain")
                sig["published_date"] = pub_date
                
                # Cleanup internal fields
                if "announcement_date" in sig:
                    del sig["announcement_date"]
                    
                sig["chunk_index"] = chunk["chunk_index"]
                master_signals.append(sig)
                
    return master_signals
