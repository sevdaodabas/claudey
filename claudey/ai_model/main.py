from fastapi import FastAPI, Request
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

model_id = "google/gemma-3-1b-it"
hf_token = os.getenv("HF_TOKEN")

tokenizer = AutoTokenizer.from_pretrained(model_id, token=hf_token)

model = AutoModelForCausalLM.from_pretrained(
    model_id, 
    device_map="cpu", 
    dtype=torch.float32, 
    token=hf_token,
    low_cpu_mem_usage=True
)

@app.post("/predict")
async def predict(request: Request):
    data = await request.json()
    prompt = data.get("prompt", "")
    
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        outputs = model.generate(
             **inputs, 
             max_new_tokens=10,
             do_sample=True,
             temperature=0.7,
             pad_token_id=tokenizer.eos_token_id
        )
    
    full_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    reply = full_text[len(prompt):].strip() if full_text.startswith(prompt) else full_text
    return {"reply": reply}