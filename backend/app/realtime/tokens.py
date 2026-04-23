"""Token metadata for whale-tracking. ERC-20 Transfer topic + contract addresses."""
from dataclasses import dataclass

# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


@dataclass(frozen=True)
class Token:
    symbol: str
    address: str  # lowercase 0x…
    decimals: int


STABLES: tuple[Token, ...] = (
    Token("USDT", "0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
    Token("USDC", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
    Token("DAI", "0x6b175474e89094c44da98b954eedeac495271d0f", 18),
)

STABLES_BY_ADDRESS: dict[str, Token] = {t.address: t for t in STABLES}
