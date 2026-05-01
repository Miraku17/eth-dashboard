from sqlalchemy import inspect


def test_all_v1_tables_exist(migrated_engine):
    insp = inspect(migrated_engine)
    names = set(insp.get_table_names())
    expected = {
        "price_candles",
        "onchain_volume",
        "exchange_flows",
        "stablecoin_flows",
        "network_activity",
        "watched_wallets",
        "transfers",
        "alert_rules",
        "alert_events",
    }
    missing = expected - names
    assert not missing, f"missing tables: {missing}"


def test_smart_money_leaderboard_table_exists(migrated_engine):
    from sqlalchemy import inspect
    insp = inspect(migrated_engine)
    cols = {c["name"] for c in insp.get_columns("smart_money_leaderboard")}
    assert cols == {
        "id", "run_id", "snapshot_at", "window_days", "rank",
        "wallet_address", "label",
        "realized_pnl_usd", "unrealized_pnl_usd", "win_rate",
        "trade_count", "volume_usd", "weth_bought", "weth_sold",
    }
    idx = {i["name"] for i in insp.get_indexes("smart_money_leaderboard")}
    assert "ix_leaderboard_latest" in idx


def test_wallet_clusters_table_exists(migrated_engine):
    insp = inspect(migrated_engine)
    assert "wallet_clusters" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("wallet_clusters")}
    assert cols == {"address", "computed_at", "ttl_expires_at", "payload"}
    idx = {i["name"] for i in insp.get_indexes("wallet_clusters")}
    assert "ix_wallet_clusters_ttl_expires_at" in idx
