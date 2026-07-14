import os
import json
import numpy as np
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from groq import Groq
import httpx

from dotenv import load_dotenv
load_dotenv(override=True)

MERGE_MODEL_NAME = "llama-3.3-70b-versatile"

MERGE_SYSTEM_PROMPT = """You are a deduplication engine for an intelligence platform.
You will be given a JSON array of signals that describe the exact same event from different sources.
Your job is to MERGE them into a single, comprehensive signal.

RULES:
1. Keep EVERY unique detail, amount, date, and eligibility criteria from all sources.
2. If there are contradictions (e.g. one source says €500M, another says €300M), explicitly mention BOTH and cite the sources.
3. Return the merged output as a JSON object matching the input schema exactly.
"""

def compute_similarity(emb1, emb2):
    return np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

def deduplicate_within_section(signals: List[Dict[str, Any]], rotator, threshold: float = 0.85) -> List[Dict[str, Any]]:
    if not signals:
        return []
        
    print("Loading embedding model (all-MiniLM-L6-v2)...")
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    
    texts_to_embed = [
        f"{s.get('headline', '')} {s.get('description', '')}"
        for s in signals
    ]
    
    print(f"Computing embeddings for {len(signals)} signals...")
    embeddings = embedder.encode(texts_to_embed)
    
    clusters = []
    assigned = set()
    
    for i in range(len(signals)):
        if i in assigned:
            continue
            
        current_cluster = [i]
        assigned.add(i)
        
        for j in range(i + 1, len(signals)):
            if j in assigned:
                continue
                
            sim = compute_similarity(embeddings[i], embeddings[j])
            if sim > threshold:
                current_cluster.append(j)
                assigned.add(j)
                
        clusters.append(current_cluster)
        
    print(f"Found {len(clusters)} unique clusters (from {len(signals)} original signals).")
    
    final_signals = []
    
    for cluster_indices in clusters:
        if len(cluster_indices) == 1:
            final_signals.append(signals[cluster_indices[0]])
        else:
            cluster_signals = [signals[idx] for idx in cluster_indices]
            merged_signal = merge_signals_llm(cluster_signals, rotator)
            
            merged_signal["source_urls"] = list(set([s.get("source_url") for s in cluster_signals if s.get("source_url")]))
            merged_signal["source_domain"] = "multiple"
            final_signals.append(merged_signal)
            
    return final_signals

def merge_signals_llm(cluster_signals: List[Dict[str, Any]], rotator) -> Dict[str, Any]:
    try:
        prompt = json.dumps(cluster_signals, indent=2)
        messages = [
            {"role": "system", "content": MERGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        merged = rotator.chat(messages, temperature=0.1)
        if merged is None:
            return cluster_signals[0]
            
        merged["sector"] = cluster_signals[0].get("sector", "General")
        merged["signal_type"] = cluster_signals[0].get("signal_type", "Unknown")
        return merged
        
    except Exception as e:
        print(f"Error merging signals via Rotator: {e}")
        return cluster_signals[0]

def process_dedup_layer(master_signals: List[Dict[str, Any]], rotator) -> List[Dict[str, Any]]:
    sections = {}
    for sig in master_signals:
        sec = sig.get("signal_type", "Unknown")
        if sec not in sections:
            sections[sec] = []
        sections[sec].append(sig)
        
    final_deduped = []
    for sec_name, sec_signals in sections.items():
        print(f"--- Deduplicating section: {sec_name} ({len(sec_signals)} signals) ---")
        deduped = deduplicate_within_section(sec_signals, rotator)
        final_deduped.extend(deduped)
        
    return final_deduped
