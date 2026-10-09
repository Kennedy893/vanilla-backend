from fastapi import FastAPI

app = FastAPI(
    title="Vanilla Traceability API",
    description="API de traçabilité de la vanille",
    version="1.0.0",
)


@app.get("/")
def home():
    return {"message": "Bienvenue sur l'API de traçabilité de la vanille"}


@app.get("/health")
def health_check():
    return {"status": "ok"}