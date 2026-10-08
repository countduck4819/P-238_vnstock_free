from dotenv import load_dotenv
from fastapi import FastAPI
from openai import OpenAI

load_dotenv()

app = FastAPI()
client = OpenAI()


@app.post("/chat")
def chat(prompt: str):
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    return {"answer": response.output_text}