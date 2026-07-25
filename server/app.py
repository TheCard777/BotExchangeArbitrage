"""FastAPI app: the platform users log into to connect their exchange keys
and let the bot scan for arbitrage on their behalf.

Endpoints (all JSON, token auth via 'Authorization: Bearer <token>'):

    POST   /api/register              {email, password}
    POST   /api/login                 {email, password}          -> {token}
    POST   /api/logout                                            (auth)
    GET    /api/exchanges                                         (auth)
    PUT    /api/exchanges/{exchange}   {api_key, secret, passphrase?} (auth)
    DELETE /api/exchanges/{exchange}                              (auth)
    GET    /api/config                                            (auth)
    PUT    /api/config                 {dry_run, pairs, ...}      (auth)
    POST   /api/bot/start                                         (auth)
    POST   /api/bot/stop                                          (auth)
    GET    /api/bot/status                                        (auth)

Design notes / honesty:
  * This is a Phase-1 foundation. It stores users' exchange API keys
    (encrypted) and runs one scanner per user in dry-run by default.
  * Handling other people's keys/funds carries real security AND legal
    weight — see server/README.md before exposing this to anyone.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

_INDEX_HTML = Path(__file__).parent / "static" / "index.html"

from server.crypto_box import SecretConfigError
from server.engine import BotManager
from server.store import DEFAULT_CONFIG, Store


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: str
    password: str


class ExchangeKeyIn(BaseModel):
    api_key: str = Field(min_length=1)
    secret: str = Field(min_length=1)
    passphrase: str = ""


class ConfigIn(BaseModel):
    dry_run: bool | None = None
    pairs: list[str] | None = None
    min_profit_threshold: float | None = None
    max_trade_size_quote: float | None = None
    top_movers: int | None = None


def create_app(store: Store | None = None, manager: BotManager | None = None) -> FastAPI:
    """Build the app. Tests pass their own Store/BotManager (fake engine)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await app.state.manager.shutdown()
        app.state.store.close()

    app = FastAPI(title="Plateforme Arbitrage", version="1", lifespan=lifespan)
    app.state.store = store or Store()
    app.state.manager = manager or BotManager(app.state.store)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _INDEX_HTML.read_text(encoding="utf-8")

    def current_user(authorization: str = Header(default="")) -> int:
        token = ""
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        user_id = app.state.store.user_for_token(token)
        if user_id is None:
            raise HTTPException(status_code=401, detail="Non authentifie. Reconnecte-toi.")
        return user_id

    # --- auth ---------------------------------------------------------------
    @app.post("/api/register")
    def register(body: RegisterIn):
        try:
            user_id = app.state.store.create_user(body.email, body.password)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"user_id": user_id}

    @app.post("/api/login")
    def login(body: LoginIn):
        token = app.state.store.login(body.email, body.password)
        if not token:
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect.")
        return {"token": token}

    @app.post("/api/logout")
    def logout(authorization: str = Header(default="")):
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        app.state.store.logout(token)
        return {"ok": True}

    # --- exchange keys ------------------------------------------------------
    @app.get("/api/exchanges")
    def list_exchanges(user_id: int = Depends(current_user)):
        return {"exchanges": app.state.store.list_exchanges(user_id)}

    @app.put("/api/exchanges/{exchange}")
    def set_exchange(exchange: str, body: ExchangeKeyIn, user_id: int = Depends(current_user)):
        try:
            app.state.store.set_exchange_key(
                user_id, exchange, body.api_key, body.secret, body.passphrase
            )
        except SecretConfigError as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"exchanges": app.state.store.list_exchanges(user_id)}

    @app.delete("/api/exchanges/{exchange}")
    def delete_exchange(exchange: str, user_id: int = Depends(current_user)):
        app.state.store.delete_exchange_key(user_id, exchange)
        return {"exchanges": app.state.store.list_exchanges(user_id)}

    # --- config -------------------------------------------------------------
    @app.get("/api/config")
    def get_config(user_id: int = Depends(current_user)):
        return app.state.store.get_config(user_id)

    @app.put("/api/config")
    def set_config(body: ConfigIn, user_id: int = Depends(current_user)):
        patch = {k: v for k, v in body.model_dump().items() if v is not None and k in DEFAULT_CONFIG}
        return app.state.store.set_config(user_id, patch)

    # --- bot ----------------------------------------------------------------
    @app.post("/api/bot/start")
    async def bot_start(user_id: int = Depends(current_user)):
        if len(app.state.store.list_exchanges(user_id)) < 2:
            raise HTTPException(
                status_code=400,
                detail="Ajoute au moins 2 exchanges (cles API) avant de lancer le bot.",
            )
        try:
            engine = await app.state.manager.start(user_id)
        except SecretConfigError as e:
            raise HTTPException(status_code=500, detail=str(e))
        return engine.snapshot()

    @app.post("/api/bot/stop")
    async def bot_stop(user_id: int = Depends(current_user)):
        await app.state.manager.stop(user_id)
        return {"ok": True}

    @app.get("/api/bot/status")
    def bot_status(user_id: int = Depends(current_user)):
        return app.state.manager.snapshot(user_id)

    return app


app = None


def get_app() -> FastAPI:
    """Lazy singleton for `uvicorn server.app:get_app --factory`."""
    global app
    if app is None:
        app = create_app()
    return app
