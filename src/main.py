from fastapi import FastAPI

app = FastAPI(title="Arxiv Paper Curator")

@app.get("/api/v1/health")
def health():
    return {"status": "ok"}