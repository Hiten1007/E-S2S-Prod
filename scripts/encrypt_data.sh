#!/bin/bash
# Encrypt data files after pipeline run.
# DATA_KEY must be set as environment variable or GitHub Secret.

set -e

echo "Encrypting signals.json..."
openssl aes-256-cbc -pbkdf2 \
  -in data/signals.json \
  -out data/signals.json.enc \
  -k "$DATA_KEY"

echo "Encrypting sbti_targets.json..."
openssl aes-256-cbc -pbkdf2 \
  -in data/sbti_targets.json \
  -out data/sbti_targets.json.enc \
  -k "$DATA_KEY"

echo "✓ Data encrypted successfully."
