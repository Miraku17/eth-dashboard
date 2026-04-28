"""Decode ERC-20 transfer(address,uint256) calldata.

Used by the mempool listener: pending txs have no event logs yet, so we
decode the input data of `transfer(...)` calls directly to identify
ERC-20 token movements before they're mined.
"""

# keccak256("transfer(address,uint256)")[:8] = "a9059cbb"
TRANSFER_SELECTOR = "a9059cbb"


def decode_erc20_transfer(data: str | None) -> tuple[str, int] | None:
    """Return (to_addr, amount) for a `transfer(...)` call, else None.

    Accepts hex with or without `0x` prefix, any case. Returns None if the
    selector doesn't match transfer(), or if the data is too short.
    """
    if not data:
        return None
    s = data.lower()
    if s.startswith("0x"):
        s = s[2:]
    # selector (8 hex) + to (64) + amount (64) = 136 hex chars
    if len(s) < 136:
        return None
    if s[:8] != TRANSFER_SELECTOR:
        return None
    # The `to` address is right-padded into the 32-byte slot — last 40 hex chars are the address
    to_addr = "0x" + s[8 + 24 : 8 + 64]
    amount = int(s[8 + 64 : 8 + 128], 16)
    return to_addr, amount
