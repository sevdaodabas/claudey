#!/bin/bash

# Start Ollama server in background
ollama serve &

# Wait for Ollama server to be ready
echo "Waiting for Ollama server..."
until ollama list > /dev/null 2>&1; do
  sleep 2
done
echo "Ollama server is ready."

# Pull the Qwen2.5 model if not already downloaded
echo "Pulling Qwen2.5-3B-Instruct model..."
ollama pull qwen2.5:3b
echo "Model is ready."

# Pull the embedding model for ChromaDB
echo "Pulling Nomic Embedding model..."
ollama pull nomic-embed-text
echo "Embedding model is ready."

# Keep container running
wait
