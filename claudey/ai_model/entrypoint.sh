#!/bin/bash

# Ollama sunucusunu arka planda başlat
ollama serve &

# Ollama sunucusu hazır olana kadar bekle
echo "Ollama sunucusu bekleniyor..."
until ollama list > /dev/null 2>&1; do
  sleep 2
done
echo "Ollama sunucusu hazır."

# Qwen2.5 modeli indirilmediyse indir
echo "Qwen2.5 modeli indiriliyor..."
ollama pull qwen2.5:7b
echo "Model hazır."

# ChromaDB için embedding modelini indir
echo "Nomic Embedding modeli indiriliyor..."
ollama pull nomic-embed-text
echo "Embedding modeli hazır."

# Container'ı çalışır durumda tut
wait
