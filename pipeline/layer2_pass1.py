"""
Layer 2 — Pass 1: France Relevance Filter

Evaluates article chunks to determine if they concern France and are
within scope (electrification, decarbonization, grants, regulations, etc.).

Can be used standalone or called by run_pass1.py with an LLMRotator instance.
"""

import json
import time
import os
from typing import List, Dict, Any, Optional


PASS_1_SYSTEM_PROMPT = """You are a relevance filter for a Process Electrification and Industrial Decarbonization intelligence platform.

SCOPE KEEP CRITERIA:
- Projects, programs, or missions for electrification/decarbonization
- Grants, subsidies, incentives, tax credits explicitly tied to industrial infrastructure
- Regulatory rule changes, quotas, compliance deadlines
- Technology breakthroughs, efficiency milestones, technology trends, adoptions, and insights
- Market adoption data, cost shifts, supply chain signals, market trends, costs, and insights

SCOPE DROP CRITERIA:
- Irrelevant Sectors & Black Zones: Drop any financial support or initiative with no direct link to electrification, decarbonization, or energy infrastructure — regardless of funding size or target audience. Common examples include: consumer/household subsidies, fuel allowances, tax rebates for citizens, healthcare, pharmaceuticals, pure agriculture (farming, vineyards), retail, micro-enterprises, tourism, education, maritime, and social security. Exception: Keep grants in any of these sectors ONLY if the text explicitly mandates heavy electrical infrastructure upgrades or industrial decarbonization.
- Generic corporate deals unrelated to physical infrastructure or electrification

INSTRUCTIONS:
Analyze the chunk and return a JSON object with exactly two keys:
- "is_relevant": true or false
- "reasoning": A brief 1-sentence explanation of why it was kept or dropped.
"""


def evaluate_chunk(chunk_text: str, rotator) -> Dict[str, Any]:
    """
    Evaluate a single chunk for France relevance using the LLM rotator.
    
    Args:
        chunk_text: The article text chunk to evaluate
        rotator: An LLMRotator instance
    
    Returns:
        Dict with 'is_relevant' (bool) and 'reasoning' (str)
    """
    messages = [
        {"role": "system", "content": PASS_1_SYSTEM_PROMPT},
        {"role": "user", "content": chunk_text}
    ]
    
    result = rotator.chat(messages, temperature=0.1)
    
    if result is None:
        return {"is_relevant": False, "reasoning": "API Error: All keys exhausted or request too large"}
    
    return {
        "is_relevant": result.get("is_relevant", False),
        "reasoning": result.get("reasoning", "")
    }


def process_articles_pass1(articles: List[Dict[str, Any]], rotator=None, checkpoint_file="layer2_pass1_checkpoint.jsonl") -> List[Dict[str, Any]]:
    """
    Process a list of articles through Pass 1 relevance filtering, with local checkpointing.
    
    If no rotator is provided, creates a default one (backward compatibility).
    """
    if rotator is None:
        from llm_rotator import LLMRotator
        rotator = LLMRotator()
    
    processed_urls = set()
    surviving_articles = []
    
    # Load checkpoint if it exists
    if os.path.exists(checkpoint_file):
        print(f"Loading checkpoint from {checkpoint_file}...")
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line)
                        processed_urls.add(record.get('url', ''))
                        if record.get('is_relevant', False):
                            surviving_articles.append(record.get('article'))
        except Exception as e:
            print(f"Error loading checkpoint: {e}")
            
    # Open checkpoint file for appending
    with open(checkpoint_file, 'a', encoding='utf-8') as ckpt_f:
        for article in articles:
            # Use 'url' or 'source_url' or headline as unique ID
            article_id = article.get("url") or article.get("source_url") or article.get("headline", "")
            
            if article_id in processed_urls:
                # We already processed this article successfully in a previous run
                continue
                
            surviving_chunks = []
            if "chunks" in article:
                for chunk_idx, chunk_text in enumerate(article["chunks"]):
                    time.sleep(1)
                    
                    evaluation = evaluate_chunk(chunk_text, rotator)
                    if evaluation["is_relevant"]:
                        surviving_chunks.append({
                            "chunk_index": chunk_idx,
                            "text": chunk_text,
                            "pass1_reasoning": evaluation["reasoning"]
                        })
                    else:
                        print(f"[Dropped] {evaluation['reasoning']}")
                        
            is_relevant = False
            surviving_article = None
            if surviving_chunks:
                surviving_article = dict(article)
                surviving_article["surviving_chunks"] = surviving_chunks
                if "chunks" in surviving_article:
                    del surviving_article["chunks"]
                surviving_articles.append(surviving_article)
                is_relevant = True
                
            # Save to checkpoint immediately
            record = {
                "url": article_id,
                "is_relevant": is_relevant,
                "article": surviving_article
            }
            ckpt_f.write(json.dumps(record, ensure_ascii=False) + "\\n")
            ckpt_f.flush()
            
    return surviving_articles
