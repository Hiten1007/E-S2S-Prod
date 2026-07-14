import json
import re
import os
from pathlib import Path
from typing import List, Dict, Any

def count_words(text: str) -> int:
    """Accurate word counting."""
    return len(text.split())

def semantic_chunk_text(text: str, max_words: int = 3000, overlap_words: int = 200) -> List[str]:
    """
    Splits text into chunks of ~max_words, ensuring splits only happen at paragraph
    or heading boundaries. Each subsequent chunk includes ~overlap_words from the
    end of the previous chunk.
    """
    if not text:
        return []
        
    total_words = count_words(text)
    if total_words <= max_words + 500: # Give some leeway for articles slightly over
        return [text]

    # Pre-process text into manageable units (guaranteed <= max_words)
    raw_paragraphs = re.split(r'\n+', text.strip())
    units = []
    
    for para in raw_paragraphs:
        para = para.strip()
        if not para:
            continue
            
        if count_words(para) <= max_words:
            units.append(para)
        else:
            # Force split massive paragraph by sentences
            sentences = [s + "." for s in para.split(". ") if s]
            for sentence in sentences:
                if count_words(sentence) <= max_words:
                    units.append(sentence)
                else:
                    # Hard split by words as absolute fallback
                    words = sentence.split()
                    for j in range(0, len(words), max_words):
                        units.append(" ".join(words[j:j+max_words]))
                        
    chunks = []
    current_chunk_units = []
    current_word_count = 0
    
    for unit in units:
        unit_word_count = count_words(unit)
        
        # If adding this unit exceeds max_words and we already have content
        if current_word_count + unit_word_count > max_words and current_word_count > 0:
            chunks.append("\n\n".join(current_chunk_units))
            
            # Start new chunk with overlap
            overlap_units = []
            overlap_count = 0
            for prev_unit in reversed(current_chunk_units):
                overlap_count += count_words(prev_unit)
                overlap_units.insert(0, prev_unit)
                if overlap_count >= overlap_words:
                    break
            
            current_chunk_units = overlap_units + [unit]
            current_word_count = overlap_count + unit_word_count
        else:
            current_chunk_units.append(unit)
            current_word_count += unit_word_count
            
    # Add the last chunk if it has content
    if current_chunk_units:
        chunks.append("\n\n".join(current_chunk_units))
        
    return chunks

def process_article(item: Dict[str, Any], source_domain: str, source_scope: str) -> Dict[str, Any]:
    """
    Extracts canonical text from an article item and chunks it.
    """
    # Prefer full_payload, fallback to snippet
    text = item.get("full_payload")
    if not text or len(text.strip()) < 50:
        text = item.get("snippet", "")
        
    chunks = semantic_chunk_text(text)
    
    return {
        "item_hash": item.get("item_hash"),
        "title": item.get("title"),
        "url": item.get("url"),
        "published_date": item.get("published_date"),
        "source_domain": source_domain,
        "source_scope": source_scope,
        "total_words": count_words(text),
        "chunk_count": len(chunks),
        "chunks": chunks
    }

def process_harvester_file(filepath: str, source_scope: str) -> List[Dict[str, Any]]:
    """
    Reads a standard harvester JSON output file and chunks all valid articles.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Ensure it's a standard harvester envelope
        if not isinstance(data, dict) or "new_items" not in data:
            print(f"Skipping {os.path.basename(filepath)}: Not a standard harvester envelope.")
            return []
            
        source_domain = data.get("source_domain", "unknown")
        items = data.get("new_items", [])
        
        processed_articles = []
        for item in items:
            processed = process_article(item, source_domain, source_scope)
            if processed["total_words"] > 50: # Skip empty/junk items
                processed_articles.append(processed)
                
        return processed_articles
        
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return []

if __name__ == "__main__":
    # Quick local test on a known file
    test_file = r"C:\Users\hiten\PE-Screener\data\raw\country\france\les_aides_fr__aides_delta_batch.json"
    articles = process_harvester_file(test_file, "country")
    print(f"Processed {len(articles)} articles from {test_file}")
    if articles:
        print(f"Sample article '{articles[0]['title']}' has {articles[0]['chunk_count']} chunks.")
