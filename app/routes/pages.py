"""HTML pages. Placeholders until plan task 8 builds the real screens."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.auth import require_login
from app.templating import templates

router = APIRouter(dependencies=[Depends(require_login)])


def _placeholder(request: Request, title: str) -> Response:
    return templates.TemplateResponse(request, "placeholder.html", {"title": title})


@router.get("/")
def home(request: Request) -> Response:
    return _placeholder(request, "Recipes")


@router.get("/add")
def add(request: Request) -> Response:
    return _placeholder(request, "Add recipe")


@router.get("/week")
def week(request: Request) -> Response:
    return _placeholder(request, "This week")
