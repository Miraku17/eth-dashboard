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
