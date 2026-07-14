#!/bin/bash
# Decrypt data files into the site directory for serving.
# DATA_KEY must be set as a Vercel environment variable.

set -e

echo "Decrypting signals.json..."
openssl aes-256-cbc -d -pbkdf2 \
  -in data/signals.json.enc \
  -out site/signals.json \
  -k "$DATA_KEY"

echo "Decrypting sbti_targets.json..."
openssl aes-256-cbc -d -pbkdf2 \
  -in data/sbti_targets.json.enc \
  -out site/sbti_targets.json \
  -k "$DATA_KEY"

echo "✓ Data decrypted successfully."
