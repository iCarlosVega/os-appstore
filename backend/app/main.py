import logging
import secrets
import time
from contextlib import asynccontextmanager
from urllib.parse import urlencode
from uuid import uuid4
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from . import admin, auth, budget, db, search, store
from .config import config
from .models import AdminAction, AppRequest, DownloadRequest, InputError, repository_url

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app):
    await run_in_threadpool(store.initialize)
    yield

app = FastAPI(title="Free Software Store API", version="0.2.0", lifespan=lifespan, docs_url="/docs", redoc_url=None)

class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = 131072 if scope.get("path") == "/api/admin/actions" else 16000
        length = dict(scope.get("headers", [])).get(b"content-length", b"0")
        try:
            oversized = int(length) > limit
        except ValueError:
            oversized = True
        if oversized:
            return await JSONResponse({"error": "Request is too large."}, status_code=413)(scope, receive, send)
        total = 0
        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                raise HTTPException(413, "Request is too large.")
            return message
        await self.app(scope, bounded_receive, send)

app.add_middleware(BodyLimitMiddleware)

@app.exception_handler(StarletteHTTPException)
async def http_error(_request, error):
    return JSONResponse({"error": error.detail}, status_code=error.status_code, headers=error.headers)

@app.exception_handler(InputError)
async def input_error(_request, error):
    return JSONResponse({"error": str(error)}, status_code=400)

@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_error(_request, error):
    issues = [{"field": ".".join(str(part) for part in issue["loc"]), "message": issue["msg"]} for issue in error.errors()]
    return JSONResponse({"error": "Please check the submitted fields.", "issues": issues}, status_code=422)

@app.exception_handler(Exception)
async def unexpected_error(_request, error):
    logger.exception("Backend request failed", exc_info=error)
    return JSONResponse({"error": "The request could not be completed. Please try again."}, status_code=503)

@app.middleware("http")
async def response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

@app.get("/api/health", tags=["Operations"])
def health():
    db.query("SELECT 1 AS ready")
    return {"status": "ok", "backend": "FastAPI"}

@app.get("/api/config", tags=["Catalog"])
def public_config():
    settings = store.get_settings()
    return {"donationUrl": settings.donationUrl, "downloadsPaused": settings.downloadsPaused}

@app.get("/api/categories", tags=["Catalog"])
def get_categories():
    return store.categories()

@app.get("/api/catalog", tags=["Catalog"])
def catalog():
    return store.list_apps()

@app.get("/api/apps/{slug}", tags=["Catalog"])
def app_detail(slug: str):
    result = store.get_app(slug)
    if result is None:
        raise HTTPException(404, "This listing is unavailable.")
    return result

@app.get("/api/search", tags=["Catalog"])
def catalog_search(request: Request, q: str = Query(default="", max_length=200), category: str = Query(default="", max_length=200), platform: str = Query(default="", max_length=200), type: str = Query(default="", max_length=200), attribute: str = Query(default="", max_length=200), use_ai: bool = True):
    if not auth.rate_limit(request, "search", 30):
        raise HTTPException(429, "Please wait a minute before searching again.")
    allowed = auth.rate_limit(request, "search-ai", 10, 600) if use_ai and q else False
    return search.search_catalog(q, {"category": category, "platform": platform, "type": type, "attribute": attribute}, allowed)

@app.post("/api/download", tags=["Catalog"], dependencies=[Depends(auth.require_origin)])
def download(data: DownloadRequest, request: Request):
    if not auth.rate_limit(request, "download", 20):
        raise HTTPException(429, "Please wait before opening more downloads.")
    with db.transaction():
        settings = store.get_settings()
        listing = store.find_app(data.id)
        if not listing or not listing["published"]:
            raise HTTPException(404, "This listing is unavailable.")
        if settings.downloadsPaused or not listing["downloadsEnabled"]:
            raise InputError("Downloads are currently paused.")
        db.query("INSERT INTO clicks(app_id,day,total) VALUES($1,$2,1) ON CONFLICT(app_id,day) DO UPDATE SET total=clicks.total+1", [data.id, store.now()[:10]])
        return {"url": listing["repoUrl"]}

@app.post("/api/requests", status_code=201, tags=["Catalog"], dependencies=[Depends(auth.require_origin)])
def app_request(data: AppRequest, request: Request, response: Response):
    from . import community_requests, github, request_identity
    if not auth.rate_limit(request, "request", 5, 3600):
        raise HTTPException(429, "Please wait before submitting more requests.")
    repository = repository_url(data.repoUrl) if data.repoUrl else ""
    if not repository:
        db.query("INSERT INTO app_requests(id,name,repo_url,status,created_at) VALUES($1,$2,$3,'pending',$4)", [str(uuid4()), data.name, "", store.now()])
        return {"ok": True, "status": "recorded", "suggestionCount": None}
    try:
        verified = github.fetch_repository(repository)
    except github.MissingRepository:
        raise HTTPException(404, "Repository is missing or inaccessible.") from None
    except github.GithubError:
        raise HTTPException(503, "GitHub repository verification is unavailable. Please try again later.") from None
    visitor_key = request_identity.visitor_identity(request, response)
    return community_requests.record_suggestion(verified, visitor_key)

@app.get("/api/auth/status", tags=["Owner"])
def owner_status(request: Request):
    return {"owner": auth.current_owner(request), "configured": auth.configured()}

@app.get("/api/auth/login", tags=["Owner"])
def login():
    if not auth.configured():
        raise HTTPException(503, "Owner authentication is not configured.")
    state, cookie = auth.state()
    params = urlencode({"client_id": config.github_client_id, "redirect_uri": f"{config.app_url}/api/auth/callback", "scope": "read:user", "state": state})
    response = RedirectResponse(f"https://github.com/login/oauth/authorize?{params}", status_code=302)
    response.set_cookie("store_oauth", cookie, max_age=600, **auth.cookie_options())
    return response

class GithubIdentity(BaseModel):
    id: int

@app.get("/api/auth/callback", tags=["Owner"])
def callback(request: Request, state: str = "", code: str = ""):
    def fail(status):
        response = JSONResponse({"error": "Owner sign-in could not be completed. Start sign-in again."}, status_code=status)
        response.delete_cookie("store_oauth", path="/")
        return response
    saved = auth.verify(request.cookies.get("store_oauth"))
    if not auth.configured() or not saved or not state or not code or not secrets.compare_digest(str(saved.get("state", "")), state):
        return fail(403)
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            exchange = client.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"}, json={"client_id": config.github_client_id, "client_secret": config.github_client_secret, "code": code, "redirect_uri": f"{config.app_url}/api/auth/callback"})
            if not exchange.is_success:
                return fail(502)
            token = exchange.json().get("access_token")
            if not isinstance(token, str):
                return fail(403)
            lookup = client.get("https://api.github.com/user", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
            if not lookup.is_success:
                return fail(502)
            identity = GithubIdentity.model_validate(lookup.json())
            if str(identity.id) != config.owner_id:
                return fail(403)
        response = RedirectResponse(f"{config.app_url}/admin", status_code=302)
        response.delete_cookie("store_oauth", path="/")
        response.set_cookie("store_session", auth.sign({"owner": config.owner_id, "exp": int(time.time() * 1000) + 86400000}), max_age=86400, **auth.cookie_options())
        return response
    except (httpx.HTTPError, ValueError, AttributeError):
        return fail(502)

@app.post("/api/auth/logout", tags=["Owner"], dependencies=[Depends(auth.require_origin)])
def logout():
    response = RedirectResponse(f"{config.app_url}/admin", status_code=303)
    response.delete_cookie("store_session", path="/")
    return response

@app.get("/api/admin/dashboard", tags=["Owner"], dependencies=[Depends(auth.require_owner)])
def dashboard():
    return admin.dashboard()

@app.post("/api/admin/actions", tags=["Owner"], dependencies=[Depends(auth.require_mutation)])
def admin_action(data: AdminAction):
    return admin.action(data.operation, data.fields)
