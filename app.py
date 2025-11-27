from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone


from services import (
    fetch_top_accounts,
    fetch_open_positions,
    aggregate_positions_for_accounts,
    to_decimal,
    format_usd,
    guess_market_label,
)

app = FastAPI()
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):

    # 1. 上位アカウント取得
    accounts = fetch_top_accounts(limit=10)

    # 2. ポジション保有アカウント（最初の1名だけ）
    winner = None
    winner_positions = []

    for i, acc in enumerate(accounts, start=1):
        pos = fetch_open_positions(acc["id"])
        if pos:
            winner = {"rank": i, "account": acc}
            winner_positions = pos
            break

    # 3. 全体のポジション集計
    summary = aggregate_positions_for_accounts(accounts)
    updated_at = datetime.now(timezone.utc).astimezone()

    # 4. HTML に渡す
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "accounts": accounts,
            "winner": winner,
            "winner_positions": winner_positions,
            "summary": summary,
            "to_decimal": to_decimal,
            "format_usd": format_usd,
            "guess_market_label": guess_market_label,
            "updated_at": updated_at,
        },
    )
