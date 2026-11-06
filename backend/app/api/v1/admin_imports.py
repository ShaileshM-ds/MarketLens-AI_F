"""Administrator-only import wizard. Imports always go to the Imported database."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder

from marketlens_core.importing import service
from marketlens_core.importing.parsing import FileFormatError
from marketlens_core.settings import DataMode

from ...auth import require_admin

router = APIRouter(prefix="/admin/imports", tags=["admin: imports"], dependencies=[Depends(require_admin)])


def _db(request: Request):
    settings = request.app.state.settings
    return request.app.state.mongo[settings.database_for(DataMode.IMPORTED)]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _view(run: dict) -> dict:
    out = {k: v for k, v in run.items() if k != "_id"}
    out["id"] = run["_id"]
    return jsonable_encoder(out)


def _raise(exc: service.ServiceError):
    detail = exc.message if not exc.problems else {"message": exc.message, "problems": exc.problems}
    raise HTTPException(exc.status, detail)


@router.get("/reference")
def reference() -> dict:
    return service.wizard_reference()


@router.get("")
def list_imports(request: Request) -> dict:
    return {"runs": [_view(r) for r in service.list_runs(_db(request))]}


@router.post("", status_code=201)
def upload(request: Request, file: UploadFile = File(...), user: dict = Depends(require_admin)) -> dict:
    settings = request.app.state.settings
    data = file.file.read(settings.import_max_bytes + 1)
    if len(data) > settings.import_max_bytes:
        raise HTTPException(413, f"The file is larger than the {settings.import_max_bytes / 1_000_000:g} MB import limit.")
    try:
        run = service.create_run(
            _db(request), filename=file.filename or "upload", data=data, user=user["username"], settings=settings, now=_now()
        )
    except FileFormatError as exc:
        raise HTTPException(400, str(exc))
    return _view(run)


@router.get("/{run_id}")
def get_import(run_id: str, request: Request) -> dict:
    try:
        return _view(service.get_run(_db(request), run_id))
    except service.ServiceError as exc:
        _raise(exc)


@router.put("/{run_id}/config")
def set_config(run_id: str, body: dict, request: Request) -> dict:
    try:
        run = service.update_config(_db(request), run_id, body, settings=request.app.state.settings, now=_now())
    except service.ServiceError as exc:
        _raise(exc)
    return _view(run)


@router.post("/{run_id}/confirm")
def confirm(run_id: str, request: Request, user: dict = Depends(require_admin)) -> dict:
    try:
        return _view(service.confirm_run(_db(request), run_id, user=user["username"], now=_now()))
    except service.ServiceError as exc:
        _raise(exc)


@router.get("/{run_id}/rejected")
def rejected(
    run_id: str, request: Request, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)
) -> dict:
    try:
        return jsonable_encoder(service.rejected_page(_db(request), run_id, page, page_size))
    except service.ServiceError as exc:
        _raise(exc)
