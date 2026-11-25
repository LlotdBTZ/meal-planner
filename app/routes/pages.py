"""HTML pages: recipes, add, review, recipe view/edit, and this week."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from app import jobs, recipes
from app.auth import require_login, safe_next
from app.deps import Db
from app.editor import parse_editor_form, safe_thumbnail
from app.grocery import combine
from app.listtext import to_notes_text
from app.recipes import Recipe
from app.templating import templates

router = APIRouter(dependencies=[Depends(require_login)])


def render(
    request: Request, conn, template: str, context: dict[str, Any], status: int = 200
) -> Response:
    context = {
        "week_count": len(recipes.week_recipe_ids(conn)),
        "path": request.url.path,
        **context,
    }
    return templates.TemplateResponse(request, template, context, status_code=status)


def back(request: Request, default: str = "/") -> Response:
    """After a form POST: 204 for fetch() callers, otherwise redirect back."""
    if request.headers.get("x-requested-with") == "fetch":
        return Response(status_code=204)
    return RedirectResponse(safe_next(request.query_params.get("next") or default), 303)


def _recipe_or_404(conn, recipe_id: int) -> Recipe:
    recipe = recipes.get_recipe(conn, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


# --- Recipes ---------------------------------------------------------------


@router.get("/")
def home(request: Request, conn: Db, q: str = "") -> Response:
    items = recipes.list_recipes(conn, search=q)
    return render(request, conn, "home.html", {"recipes": items, "q": q})


@router.get("/thumbs/{name}")
def thumbnail(request: Request, name: str) -> Response:
    safe = safe_thumbnail(name)
    path = request.app.state.settings.thumbnails_dir / safe if safe else None
    if not path or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.get("/recipe/{recipe_id}")
def recipe_view(request: Request, conn: Db, recipe_id: int) -> Response:
    recipe = _recipe_or_404(conn, recipe_id)
    in_week = recipe_id in recipes.week_recipe_ids(conn)
    return render(request, conn, "recipe.html", {"recipe": recipe, "in_week": in_week})


@router.get("/recipe/{recipe_id}/edit")
def recipe_edit(request: Request, conn: Db, recipe_id: int) -> Response:
    recipe = _recipe_or_404(conn, recipe_id)
    return render(
        request,
        conn,
        "editor.html",
        {"recipe": recipe, "action": f"/recipe/{recipe_id}/edit", "mode": "edit", "errors": []},
    )


@router.post("/recipe/{recipe_id}/edit")
async def recipe_edit_save(request: Request, conn: Db, recipe_id: int) -> Response:
    existing = _recipe_or_404(conn, recipe_id)
    async with request.form() as form:  # closes any uploaded files
        result = parse_editor_form(form)
    # source details aren't editable; keep what was saved
    result.recipe.source_url = existing.source_url
    result.recipe.platform = existing.platform
    result.recipe.thumbnail_path = existing.thumbnail_path
    result.recipe.steps = existing.steps
    if result.errors:
        return render(
            request,
            conn,
            "editor.html",
            {
                "recipe": result.recipe,
                "action": f"/recipe/{recipe_id}/edit",
                "mode": "edit",
                "errors": result.errors,
            },
            status=400,
        )
    recipes.update_recipe(conn, recipe_id, result.recipe)
    return RedirectResponse(f"/recipe/{recipe_id}", 303)


@router.post("/recipe/{recipe_id}/delete")
def recipe_delete(request: Request, conn: Db, recipe_id: int) -> Response:
    recipe = _recipe_or_404(conn, recipe_id)
    recipes.delete_recipe(conn, recipe_id)
    thumb = safe_thumbnail(recipe.thumbnail_path)
    if thumb:
        (request.app.state.settings.thumbnails_dir / thumb).unlink(missing_ok=True)
    return RedirectResponse("/", 303)


# --- Add and review ----------------------------------------------------------


@router.get("/add")
def add(request: Request, conn: Db, url: str = "") -> Response:
    return render(
        request, conn, "add.html", {"source": url.strip(), "autostart": bool(url.strip())}
    )


@router.get("/review/{job_id}")
def review(request: Request, conn: Db, job_id: int) -> Response:
    job = jobs.get_job(conn, job_id)
    if job is None or job.status != "done" or job.result is None:
        return RedirectResponse("/add", 303)
    draft = job.result
    recipe = Recipe(
        name=draft.name,
        servings=draft.servings,
        ingredients=draft.ingredients,
        source_url=draft.source_url,
        platform=draft.platform,
        thumbnail_path=draft.thumbnail_path,
        steps=draft.steps or None,
    )
    return render(
        request,
        conn,
        "editor.html",
        {
            "recipe": recipe,
            "action": f"/review/{job_id}",
            "mode": "review",
            "warnings": draft.warnings,
            "errors": [],
        },
    )


@router.post("/review/{job_id}")
async def review_save(request: Request, conn: Db, job_id: int) -> Response:
    async with request.form() as form:  # closes any uploaded files
        result = parse_editor_form(form)
    if result.errors:
        return render(
            request,
            conn,
            "editor.html",
            {
                "recipe": result.recipe,
                "action": f"/review/{job_id}",
                "mode": "review",
                "errors": result.errors,
            },
            status=400,
        )
    recipe_id = recipes.create_recipe(conn, result.recipe)
    return RedirectResponse(f"/recipe/{recipe_id}", 303)


# --- This week ---------------------------------------------------------------


@router.get("/week")
def week(request: Request, conn: Db) -> Response:
    meals = recipes.week_recipes(conn)
    lines = combine(i for r in meals for i in r.ingredients)
    checked = recipes.checked_items(conn)
    sections: dict[str, list] = {}
    for line in lines:
        sections.setdefault(line.section, []).append(line)
    return render(
        request,
        conn,
        "week.html",
        {
            "meals": meals,
            "sections": sections,
            "checked": checked,
            "notes_text": to_notes_text(lines, checked),
        },
    )


@router.post("/week/add/{recipe_id}")
def week_add(request: Request, conn: Db, recipe_id: int) -> Response:
    if not recipes.add_to_week(conn, recipe_id):
        raise HTTPException(status_code=404, detail="Recipe not found")
    return back(request)


@router.post("/week/remove/{recipe_id}")
def week_remove(request: Request, conn: Db, recipe_id: int) -> Response:
    recipes.remove_from_week(conn, recipe_id)
    return back(request)


@router.post("/week/clear")
def week_clear(request: Request, conn: Db) -> Response:
    recipes.clear_week(conn)
    return back(request, "/week")


@router.post("/week/check")
def week_check(
    request: Request, conn: Db, item_key: str = Form(...), checked: str = Form("")
) -> Response:
    recipes.set_checked(conn, item_key[:200], checked in ("1", "on", "true"))
    return back(request, "/week")
