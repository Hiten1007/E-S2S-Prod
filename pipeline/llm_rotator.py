"""
LLM Rotator — Multi-provider API key load balancer.

Cycles through multiple API keys across Cerebras and Groq to bypass
free-tier rate limits. Automatically handles:
  - 429 (Quota Exceeded): Marks key as dead, rotates to next key
  - 413 (Request Too Large): Returns None (caller should skip this chunk)
  - 503 (Server Overloaded): Waits and retries same key
  - Connection errors: Rotates to next key

Usage:
    rotator = LLMRotator()
    result = rotator.chat(
        messages=[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
        temperature=0.1
    )
"""

import os
import json
import time
import httpx
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv(override=True)


class LLMProvider:
    """Represents a single API key on a specific provider."""
    
    def __init__(self, provider: str, key: str, base_url: str, model: str):
        self.provider = provider
        self.key = key
        self.base_url = base_url
        self.model = model
        self.is_dead = False
        self.death_reason = ""
        self.requests_made = 0
        self.key_short = f"{key[:6]}...{key[-4:]}"
    
    def __repr__(self):
        status = "DEAD" if self.is_dead else "ALIVE"
        return f"[{self.provider}] {self.key_short} ({status}, {self.requests_made} reqs)"


class LLMRotator:
    """Round-robin load balancer across multiple LLM API keys and providers."""
    
    def __init__(self):
        self.providers: List[LLMProvider] = []
        self.current_index = 0
        self.http_client = httpx.Client(verify=False, timeout=60)
        
        self._load_cerebras_keys()
        self._load_groq_keys()
        self._load_scaleway_keys()
        
        if not self.providers:
            raise ValueError("No API keys found! Set CEREBRAS_KEYS and/or GROQ_KEYS in .env")
        
        total_cerebras = sum(1 for p in self.providers if p.provider == "cerebras")
        total_groq = sum(1 for p in self.providers if p.provider == "groq")
        print(f"[Rotator] Loaded {len(self.providers)} keys: {total_cerebras} Cerebras, {total_groq} Groq")
    
    def _load_cerebras_keys(self):
        keys_str = os.environ.get("CEREBRAS_KEYS", "")
        if keys_str:
            for key in keys_str.split(","):
                key = key.strip()
                if key:
                    self.providers.append(LLMProvider(
                        provider="cerebras",
                        key=key,
                        base_url="https://api.cerebras.ai/v1/chat/completions",
                        model="gpt-oss-120b"
                    ))
    
    def _load_groq_keys(self):
        keys_str = os.environ.get("GROQ_KEYS", "")
        if keys_str:
            for key in keys_str.split(","):
                key = key.strip()
                if key:
                    self.providers.append(LLMProvider(
                        provider="groq",
                        key=key,
                        base_url="https://api.groq.com/openai/v1/chat/completions",
                        model="llama-3.3-70b-versatile"
                    ))
    
    def _load_scaleway_keys(self):
        keys_str = os.environ.get("SCALEWAY_KEYS", "")
        if keys_str:
            for key in keys_str.split(","):
                key = key.strip()
                if key:
                    self.providers.append(LLMProvider(
                        provider="scaleway",
                        key=key,
                        base_url="https://api.scaleway.ai/9bb50997-3e2e-4f5b-9147-5cd8b02e5e49/v1/chat/completions",
                        model="llama-3.3-70b-instruct"
                    ))
    
    def _get_next_alive_provider(self) -> Optional[LLMProvider]:
        """Find the next alive provider, starting from current_index."""
        total = len(self.providers)
        for _ in range(total):
            provider = self.providers[self.current_index]
            if not provider.is_dead:
                return provider
            self.current_index = (self.current_index + 1) % total
        return None  # All keys are dead
    
    def _advance_to_next(self):
        """Move to the next provider in the round-robin."""
        self.current_index = (self.current_index + 1) % len(self.providers)
    
    def get_status(self) -> Dict[str, Any]:
        """Return current status of all keys."""
        alive = [p for p in self.providers if not p.is_dead]
        dead = [p for p in self.providers if p.is_dead]
        return {
            "total_keys": len(self.providers),
            "alive_keys": len(alive),
            "dead_keys": len(dead),
            "current_provider": str(self.providers[self.current_index]),
            "dead_details": [f"{p} - {p.death_reason}" for p in dead]
        }
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.1) -> Optional[Dict[str, Any]]:
        """
        Send a chat completion request, rotating through providers on failure.
        
        Returns:
            Parsed JSON dict from the LLM response, or None if all keys exhausted
            or the request is too large for any provider.
        """
        attempts = 0
        max_attempts = len(self.providers) * 2  # Allow retries for 503s
        
        while attempts < max_attempts:
            provider = self._get_next_alive_provider()
            if provider is None:
                print("[Rotator] ALL KEYS EXHAUSTED. Cannot process more today.")
                return None
            
            try:
                payload = {
                    "model": provider.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 4000,
                    "response_format": {"type": "json_object"}
                }
                
                headers = {
                    "Authorization": f"Bearer {provider.key}",
                    "Content-Type": "application/json"
                }
                
                response = self.http_client.post(
                    provider.base_url,
                    json=payload,
                    headers=headers
                )
                
                provider.requests_made += 1
                data = response.json()
                
                # --- Success ---
                if response.status_code == 200:
                    if "choices" in data:
                        msg = data["choices"][0]["message"]
                        text = msg.get("content")
                        if not text:
                            # It's a reasoning model that failed to finish
                            print(f"[Rotator] {provider.key_short} hit token limit while reasoning. Retrying...")
                            self._advance_to_next()
                            attempts += 1
                            continue
                            
                        self._advance_to_next()
                        return json.loads(text)
                    else:
                        print(f"[Rotator] Unexpected response from {provider}: {data}")
                        self._advance_to_next()
                        attempts += 1
                        continue
                
                # --- 429: Quota Exceeded ---
                elif response.status_code == 429:
                    print(f"[Rotator] {provider.key_short} hit rate limit. Waiting 5s...")
                    time.sleep(5)
                    self._advance_to_next()
                    attempts += 1
                    continue
                
                # --- 413: Request Too Large ---
                elif response.status_code == 413:
                    print(f"[Rotator] Request too large for {provider.key_short}. Skipping this chunk.")
                    self._advance_to_next()
                    return None  # Caller should skip this chunk
                
                # --- 503: Server Overloaded ---
                elif response.status_code == 503:
                    print(f"[Rotator] {provider.key_short} server overloaded. Waiting 5s and retrying...")
                    time.sleep(5)
                    attempts += 1
                    continue
                
                # --- Other errors ---
                else:
                    error_msg = data.get("error", {}).get("message", f"HTTP {response.status_code}")
                    print(f"[Rotator] {provider.key_short} error: {error_msg}")
                    self._advance_to_next()
                    attempts += 1
                    continue
                    
            except json.JSONDecodeError as e:
                print(f"[Rotator] JSON decode error from {provider.key_short}: {e}")
                if 'text' in locals():
                    with open('scratch/crash_dump.json', 'w', encoding='utf-8') as f:
                        f.write(text)
                self._advance_to_next()
                attempts += 1
                continue
                
            except httpx.ReadTimeout:
                print(f"[Rotator] Timeout from {provider.key_short}. Rotating...")
                self._advance_to_next()
                attempts += 1
                continue
                
            except Exception as e:
                print(f"[Rotator] Unexpected error from {provider.key_short}: {e}")
                self._advance_to_next()
                attempts += 1
                continue
        
        print("[Rotator] Max attempts exceeded. Could not complete request.")
        return None
