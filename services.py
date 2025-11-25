# services.py
import requests
from typing import List, Dict, Any, Optional

# GMX v2 (Arbitrum) Subsquid のエンドポイント
SUBSQUID_URL = "https://gmx.squids.live/gmx-synthetics-arbitrum:prod/api/graphql"


# ---------- 共通ユーティリティ ----------

def run_graphql(query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Subsquid に GraphQL リクエストを投げる共通関数"""
    resp = requests.post(
        SUBSQUID_URL,
        json={"query": query, "variables": variables or {}},
        timeout=20,
    )

    # デバッグ用にステータスだけ表示
    print(f"[GraphQL] HTTP status: {resp.status_code}")

    if resp.status_code != 200:
        print("レスポンスエラー:")
        print(resp.text)
        return {}

    data = resp.json()
    if "errors" in data:
        print("GraphQL エラー:")
        print(data["errors"])
        return {}

    # GraphQL の data 部分だけ返す
    return data.get("data", {})


def to_decimal(raw_value: Optional[str], decimals: int = 30) -> float:
    """GMX の超デカ整数文字列を「人間向けの小数」に変換"""
    if raw_value is None:
        return 0.0
    try:
        iv = int(raw_value)
        return iv / (10 ** decimals)
    except Exception:
        return 0.0


def format_usd(value: float) -> str:
    """USD の数値を 2 桁小数＋カンマ区切りで整形"""
    return f"{value:,.2f}"


# ---------- market アドレス → 人間向けラベル ----------

def guess_market_label(market_id: str) -> str:
    """
    GMX v2 の market アドレスを「ざっくり銘柄ラベル」に変換。
    ここは少しずつ正しいシンボルに更新していけば OK。
    """
    mid = market_id.lower()

    mapping = {
        "0x47c031236e19d024b42f8ae6780e44a573170703".lower(): "BTC 系？",
        "0x70d95587d40a2caf56bd97485ab3eec10bee6336".lower(): "ETH 系？",
        "0x7c11f78ce78768518d743e81fdfa2f860c6b9a77".lower(): "SOL 系？",
        "0xbd48149673724f9caee647bb4e9d9ddaf896efeb".lower(): "？系",
    }

    label = mapping.get(mid)
    short_addr = f"{market_id[:6]}...{market_id[-4:]}"
    if label:
        return f"{label} ({short_addr})"
    else:
        return short_addr


# ---------- 上位アカウント取得 ----------

def fetch_top_accounts(limit: int = 10) -> List[Dict[str, Any]]:
    """
    realizedPnl が大きい順にアカウントを取得
    """
    query = """
    query TopAccounts($limit: Int!) {
      accountStats(orderBy: realizedPnl_DESC, limit: $limit) {
        id
        wins
        losses
        realizedPnl
        netCapital
      }
    }
    """
    data = run_graphql(query, {"limit": limit})
    # run_graphql は data["data"] を返しているので、ここは data["accountStats"]
    accounts = data.get("accountStats", [])
    if not accounts:
        print("アカウントデータがありません。")
    return accounts


# ---------- 指定アカウントのオープンポジション取得 ----------

def fetch_open_positions(account_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    指定アカウントのポジション一覧を取得する（最新 limit 件）。
    """
    query = """
    query OpenPositions($account: String!, $limit: Int!) {
      positions(
        where: {
          account_eq: $account
          isSnapshot_eq: false
        }
        limit: $limit
      ) {
        id
        market
        isLong
        sizeInUsd
        entryPrice
        realizedPnl
        unrealizedPnl
        realizedFees
        realizedPriceImpact
        unrealizedFees
        unrealizedPriceImpact
        leverage
        openedAt
      }
    }
    """

    variables = {
        "account": account_id,
        "limit": limit,
    }

    data = run_graphql(query, variables)
    return data.get("positions", [])


# ---------- 上位アカウント全体のポジション集計 ----------

def aggregate_positions_for_accounts(accounts: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    上位アカウントのオープンポジションを全部集計する。
    戻り値:
    {
      market_id: {
        "label": "BTC 系？ (0x47c0...0703)",
        "long_size": float,
        "short_size": float,
        "long_count": int,
        "short_count": int,
      },
      ...
    }
    """
    summary: Dict[str, Dict[str, Any]] = {}

    for acc in accounts:
        acc_id = acc.get("id")
        if not acc_id:
            continue

        positions = fetch_open_positions(acc_id)
        if not positions:
            continue

        for pos in positions:
            market_id = pos.get("market")
            if not market_id:
                continue

            direction = "LONG" if pos.get("isLong") else "SHORT"
            size_usd = to_decimal(pos.get("sizeInUsd"), 30)

            if market_id not in summary:
                summary[market_id] = {
                    "label": guess_market_label(market_id),
                    "long_size": 0.0,
                    "short_size": 0.0,
                    "long_count": 0,
                    "short_count": 0,
                }

            entry = summary[market_id]
            if direction == "LONG":
                entry["long_size"] += size_usd
                entry["long_count"] += 1
            else:
                entry["short_size"] += size_usd
                entry["short_count"] += 1

    return summary
