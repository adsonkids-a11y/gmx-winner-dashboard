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

    print(f"HTTP status: {resp.status_code}")

    if resp.status_code != 200:
        print("レスポンスエラー:")
        print(resp.text)
        return {}

    data = resp.json()
    if "errors" in data:
        print("GraphQL エラー:")
        print(data["errors"])
        return {}

    return data.get("data", {})

def fetch_market_symbols() -> dict:
    """
    GMX v2 の markets 一覧を取得して、
    { market_id: "BTC", ... } みたいな辞書を作る
    """
    query = """
    query FetchMarkets($limit: Int!) {
      markets(limit: $limit) {
        id
        indexTokenSymbol
      }
    }
    """
    data = run_graphql(query, {"limit": 100})
    # run_graphql はすでに data["data"] を返しているので、そのまま使う
    markets = data.get("markets", [])
    symbol_map = {}
    for m in markets:
        mid = m.get("id")
        sym = m.get("indexTokenSymbol") or "UNKNOWN"
        if mid:
            symbol_map[mid] = sym
    return symbol_map




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


# ---------- A: market アドレス → 人間向けラベル ----------

def guess_market_label(market_id: str) -> str:
    """
    GMX v2 の market アドレスを「ざっくり銘柄ラベル」に変換。
    まだ正式なマッピングは取れていないので、現状は仮ラベル＋短縮アドレス。
    後でちゃんとした対応表をここに追記していけば OK。
    """
    mid = market_id.lower()

    # ★ここにわかっているものから少しずつ追記していくイメージ
    mapping = {
        # 例: mid: "0x47c0...." : "BTC/???"
        # 実際のシンボルが分かったらここを書き換える
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
        # ラベル不明なものはそのまま短縮アドレスで返す
        return short_addr


# ---------- アカウントランキング取得（すでに動いていた部分） ----------

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
    accounts = data.get("accountStats", [])
    if not accounts:
        print("アカウントデータがありません。")
    return accounts


def display_ranking(accounts: List[Dict[str, Any]]) -> None:
    """
    上位アカウントのランキングを表示（人間向けの数値）
    """
    print("\n=== 🚀 GMX v2 トレーダーランキング（確定利益順） ===\n")
    for i, acc in enumerate(accounts, start=1):
        realized = to_decimal(acc.get("realizedPnl"), 30)
        net_cap = to_decimal(acc.get("netCapital"), 30)
        wins = acc.get("wins", 0)
        losses = acc.get("losses", 0)

        print(f"#{i}")
        print(f"  アカウント: {acc.get('id')}")
        print(f"  realizedPnl: {format_usd(realized)} USD")
        print(f"  wins/losses: {wins} / {losses}")
        print(f"  netCapital: {format_usd(net_cap)} USD")
        print("-" * 40)


# ---------- 指定アカウントのオープンポジション取得 ----------

def fetch_open_positions(account_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    指定アカウントのポジション一覧を取得する（最新 limit 件）。
    ※ GMX Subsquid は positions が配列そのものを返すので items は存在しない。
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

    if data is None or "positions" not in data:
        return []

    # positions はそのまま配列
    return data["positions"]





def display_positions_for_account(rank: int, acc: Dict[str, Any], positions: List[Dict[str, Any]]) -> None:
    """
    単一アカウントのポジション一覧を表示（A: market ラベル付き）
    """
    realized = to_decimal(acc.get("realizedPnl"), 30)
    net_cap = to_decimal(acc.get("netCapital"), 30)
    wins = acc.get("wins", 0)
    losses = acc.get("losses", 0)

    print(f"\n=== 🏆 現在ポジションを持つ “勝者”（Rank #{rank}） ===")
    print(f"Wallet: {acc.get('id')}")
    print(f"Total realized PnL: {format_usd(realized)} USD")
    print(f"Wins/Losses: {wins} / {losses}")
    print(f"Net capital: {format_usd(net_cap)} USD\n")

    print("--- Positions（人間向けの数値 ＋ market ラベル付き） ---")
    for pos in positions:
        market_id = pos.get("market")
        market_label = guess_market_label(market_id)

        direction = "LONG" if pos.get("isLong") else "SHORT"
        size_usd = to_decimal(pos.get("sizeInUsd"), 30)
        # entryPrice は桁が違う可能性があるので、ざっくり 1e27 で割る前提
        entry_price = to_decimal(pos.get("entryPrice"), 27)

        realized_pnl = to_decimal(pos.get("realizedPnl"), 30)
        unrealized_pnl = to_decimal(pos.get("unrealizedPnl"), 30)

        print(f"- market: {market_label}")
        print(f"  direction: {direction}")
        print(f"  sizeInUsd: {format_usd(size_usd)} USD")
        print(f"  entryPrice: {entry_price:.4f}")
        print(
            f"  PnL (realized/unrealized): "
            f"{format_usd(realized_pnl)} / {format_usd(unrealized_pnl)} USD"
        )
        print("")


# ---------- B: 上位アカウントのオープンポジションを集計 ----------

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

    print("\n=== 🔍 上位アカウントのオープンポジションを集計中... ===")
    for i, acc in enumerate(accounts, start=1):
        acc_id = acc.get("id")
        print(f"  → Rank #{i} アカウント {acc_id} のポジション取得中...")
        positions = fetch_open_positions(acc_id)

        if not positions:
            print("    （オープンポジションなし）")
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


def display_aggregated_summary(summary: Dict[str, Dict[str, Any]]) -> None:
    """
    B: 集計結果をコンソールに表示
    """
    print("\n=== 📊 上位トレーダー全体のポジション集計 ===\n")

    if not summary:
        print("オープンポジションを持つアカウントがありませんでした。")
        return

    for market_id, info in summary.items():
        label = info["label"]
        long_size = info["long_size"]
        short_size = info["short_size"]
        long_count = info["long_count"]
        short_count = info["short_count"]

        print(f"Market: {label}")
        print(f"  LONG:  {format_usd(long_size)} USD ({long_count} ポジション)")
        print(f"  SHORT: {format_usd(short_size)} USD ({short_count} ポジション)")
        print("-" * 50)


# ---------- メイン処理 ----------

def main():
    # 1. ランキング取得＆表示
    accounts = fetch_top_accounts(limit=10)
    if not accounts:
        return

    display_ranking(accounts)

    # 2. 「現在ポジションを持っている勝者」を1名ピックアップして詳細表示（従来ロジック＋A対応）
    winner_account = None
    winner_positions: List[Dict[str, Any]] = []

    for i, acc in enumerate(accounts, start=1):
        acc_id = acc.get("id")
        print(f"\nChecking rank #{i}: {acc_id}")
        positions = fetch_open_positions(acc_id)

        if positions:
            print("  → 現在ポジションあり！")
            winner_account = (i, acc)
            winner_positions = positions
            break
        else:
            print("  → 現在ポジションなし")

    if winner_account:
        rank, acc = winner_account
        display_positions_for_account(rank, acc, winner_positions)
    else:
        print("\n※ 現在ポジションを持つアカウントは見つかりませんでした。")

    # 3. B: 上位アカウント全体のオープンポジションを集計して表示
    summary = aggregate_positions_for_accounts(accounts)
    display_aggregated_summary(summary)


if __name__ == "__main__":
    main()
