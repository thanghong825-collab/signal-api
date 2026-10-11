# ---------- part32: v2.19.0 - /dataset.csv: export of the labelled dataset collected by part24 (admin only) ----------
# Loads before part7. Each judged verdict leaves one row: the numbers the verdict was based on, our labels, and what happened
# after 1h, 6h and 24h. No mint and no token name. Needs ADMIN_SECRET; without it the routes answer 404 as if they did not exist.
import csv
import hmac
import io
import json

VERSION = "2.19.0"
app.version = VERSION
app.openapi_schema = None

_DS_FIXED = ["ts", "src", "verdict", "risk", "flags", "shadow", "ret_h1", "ret_h6", "ret_24h", "liq_ratio", "bad"]


def _ds_allowed(request: Request) -> bool:
    secret = (os.getenv("ADMIN_SECRET") or "").strip()
    if not secret:
        return False
    given = request.headers.get("x-admin-key") or request.query_params.get("key") or ""  # the header is safer; ?key= is for a phone browser
    return hmac.compare_digest(given.encode(), secret.encode())


def _ds_guard(request: Request) -> None:
    if not _ds_allowed(request):
        raise HTTPException(status_code=404, detail="Not found")  # same answer for "off" and "wrong key"
    wait = rate_limited(client_ip(request), cost=5)
    if wait:
        raise HTTPException(status_code=429, detail="rate limited", headers={"Retry-After": str(wait)})


async def _ds_rows(request: Request, limit: int) -> list:
    got = await redis_pipe(request.app.state.client, [["LRANGE", "ds:rows", 0, limit - 1]])
    rows = []
    for raw in (got or [[]])[0] or []:
        try:
            row = json.loads(raw)
            if isinstance(row, dict):
                rows.append(row)
        except ValueError:
            continue
    return rows


def _ds_limit(request: Request) -> int:
    try:
        return max(1, min(2000, int(request.query_params.get("limit") or 500)))
    except ValueError:
        return 500


def _ds_cell(v: Any) -> Any:
    if isinstance(v, str) and v[:1] in ("=", "+", "@", "\t", "\r"):
        return "'" + v  # a spreadsheet must never treat our text as a formula
    return "" if v is None else v


def rows_to_csv(rows: list) -> str:
    feats = sorted({k for r in rows for k in (r.get("feat") or {})})
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(_DS_FIXED + [f"f.{k}" for k in feats])
    for r in rows:
        feat = r.get("feat") or {}
        fixed = [_ds_cell("|".join(r.get("flags") or [])) if k == "flags" else _ds_cell(r.get(k)) for k in _DS_FIXED]
        w.writerow(fixed + [_ds_cell(feat.get(k)) for k in feats])
    return out.getvalue()


@app.get("/dataset", include_in_schema=False)
async def dataset_json(request: Request):
    _ds_guard(request)
    rows = await _ds_rows(request, _ds_limit(request))
    return JSONResponse(content={"count": len(rows), "rows": rows}, headers={"Cache-Control": "no-store"})


@app.get("/dataset.csv", include_in_schema=False)
async def dataset_csv(request: Request):
    _ds_guard(request)
    rows = await _ds_rows(request, _ds_limit(request))
    return PlainTextResponse(rows_to_csv(rows), media_type="text/csv; charset=utf-8",
                             headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="tvibe-dataset.csv"'})


print(f"[part32] v{VERSION} /dataset.csv ready ({'admin key set' if os.getenv('ADMIN_SECRET') else 'off: set ADMIN_SECRET'})")
