#!/bin/bash

# Start Ollama server in background
ollama serve &

# Wait for Ollama server to be ready
echo "Waiting for Ollama server..."
until ollama list > /dev/null 2>&1; do
  sleep 2
done
echo "Ollama server is ready."

# Pull Qwen2.5 chat models. 3B is the default (fast, CPU-friendly);
# 7B is also pulled so it's available if MODEL_NAME is switched in views.py.
echo "Pulling Qwen2.5-3B-Instruct model (default)..."
ollama pull qwen2.5:3b
echo "Pulling Qwen2.5-7B-Instruct model (optional, for higher quality)..."
ollama pull qwen2.5:7b
echo "Model is ready."

# Pull the embedding model for ChromaDB
echo "Pulling Nomic Embedding model..."
ollama pull nomic-embed-text
echo "Embedding model is ready."

# Keep container running
wait
