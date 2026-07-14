import os
import glob
import json
import logging
from datetime import datetime
from llm_rotator import LLMRotator
import layer1_chunker
import layer2_pass1
import layer3_pass2
import layer4_dedup

# Set up clean logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def run_pipeline():
    start_time = datetime.now()
    logger.info("========================================")
    logger.info("  PE-SCREENER PIPELINE STARTED")
    logger.info("========================================")

    # 1. Init APIs
    rotator = LLMRotator()

    # 2. Gather Raw Data
    raw_files = glob.glob("data/raw/**/*.json", recursive=True)
    if not raw_files:
        logger.warning("No raw JSON files found in data/raw/. Nothing to do.")
        return

    logger.info(f"[STEP 1] Found {len(raw_files)} raw files to process.")
    
    # Process Layer 1 (Chunking)
    all_articles = []
    for fpath in raw_files:
        articles = layer1_chunker.process_harvester_file(fpath, "country")
        all_articles.extend(articles)
    
    logger.info(f"[STEP 1] ✓ Chunked into {len(all_articles)} total articles.")
    if not all_articles:
        return

    # Process Layer 2 (Relevance Pass)
    logger.info(f"[STEP 2] Running Pass 1 Relevance on {len(all_articles)} articles...")
    surviving_articles = layer2_pass1.process_articles_pass1(
        all_articles, 
        rotator=rotator, 
        checkpoint_file="logs/pass1_checkpoint.jsonl"
    )
    logger.info(f"[STEP 2] ✓ {len(surviving_articles)} articles survived relevance filtering.")
    if not surviving_articles:
        return

    # Process Layer 3 (Extraction Pass)
    logger.info(f"[STEP 3] Running Pass 2 Extraction on {len(surviving_articles)} articles...")
    new_signals = layer3_pass2.process_articles_pass2(
        surviving_articles,
        rotator=rotator,
        checkpoint_file="logs/pass2_checkpoint.jsonl"
    )
    logger.info(f"[STEP 3] ✓ Extracted {len(new_signals)} raw signals.")
    if not new_signals:
        return

    # Process Layer 4 (Deduplication)
    logger.info(f"[STEP 4] Deduplicating new signals against existing database...")
    existing_file = "data/signals.json"
    existing_signals = []
    if os.path.exists(existing_file):
        try:
            with open(existing_file, 'r', encoding='utf-8') as f:
                existing_signals = json.load(f)
            logger.info(f"[DATA] Loaded {len(existing_signals)} existing signals.")
        except Exception as e:
            logger.error(f"Error loading existing signals: {e}")

    # Note: Layer 4 logic assumes a deduplicate() function.
    # We pass existing signals and new signals.
    try:
        final_unique_signals, duplicates = layer4_dedup.deduplicate(new_signals, existing_signals, rotator)
        logger.info(f"[STEP 4] ✓ Removed {len(duplicates)} duplicates. Found {len(final_unique_signals)} completely new signals.")
    except AttributeError:
        # Fallback if layer4_dedup doesn't match this exact signature
        logger.warning("Layer 4 signature mismatch. Skipping dedup for POC.")
        final_unique_signals = new_signals

    # Save to disk (Append)
    if final_unique_signals:
        # Prepend new signals to the top of the file
        combined_signals = final_unique_signals + existing_signals
        
        with open(existing_file, 'w', encoding='utf-8') as f:
            json.dump(combined_signals, f, indent=2, ensure_ascii=False)
            
        logger.info(f"[SUCCESS] Appended {len(final_unique_signals)} new signals to {existing_file}.")
        logger.info(f"[SUCCESS] Database now contains {len(combined_signals)} total signals.")
    else:
        logger.info("[END] No new unique signals to add.")

    duration = datetime.now() - start_time
    logger.info("========================================")
    logger.info(f"  PIPELINE FINISHED in {duration}")
    logger.info("========================================")

if __name__ == "__main__":
    # Ensure logs dir exists
    os.makedirs("logs", exist_ok=True)
    run_pipeline()
