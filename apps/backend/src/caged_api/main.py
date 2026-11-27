import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from caged_api.data import get_data
from caged_api.routes import router

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Carrega a planilha uma vez, na subida (leva ~15 s), e nao a cada requisicao."""
    try:
        get_data()
    except Exception as exc:  # a API sobe mesmo assim; as rotas respondem 503
        log.warning("Dados do CAGED nao carregados: %s", getattr(exc, "detail", exc))
    yield


app = FastAPI(title="CAGED API", version="0.1.0", lifespan=lifespan)

# Front (Vite) em outra porta = outra origem; sem isto o navegador bloqueia as chamadas.
_origins = os.environ.get("CAGED_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
