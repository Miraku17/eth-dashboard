"""Hardcoded address labels for well-known CEX deposit / hot wallets.

Small curated list so whale transfers can be annotated without an external
label API. All addresses are lowercase (EVM checksum-insensitive lookup).
Extend as needed; upgrade to Etherscan / Dune label lookup in a later milestone.
"""

_LABELS: dict[str, str] = {
    # Binance
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance 14",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance 15",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance 16",
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Binance 17",
    "0x9696f59e4d72e237be84ffd425dcad154bf96976": "Binance 18",
    "0x4976a4a02f38326660d17bf34b431dc6e2eb2327": "Binance 19",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance 8",
    # Coinbase
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase 1",
    "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase 2",
    "0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740": "Coinbase 3",
    "0x3cd751e6b0078be393132286c442345e5dc49699": "Coinbase 4",
    "0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511": "Coinbase 5",
    "0xeb2629a2734e272bcc07bda959863f316f4bd4cf": "Coinbase 6",
    "0xa090e606e30bd747d4e6245a1517ebe430f0057e": "Coinbase 10",
    # Kraken
    "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken 1",
    "0x0a869d79a7052c7f1b55a8ebabbea3420f0d1e13": "Kraken 2",
    "0xe853c56864a2ebe4576a807d26fdc4a0ada51919": "Kraken 3",
    "0x53d284357ec70ce289d6d64134dfac8e511c8a3d": "Kraken 4",
    # OKX
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX 1",
    "0x236f9f97e0e62388479bf9e5ba4889e46b0273c3": "OKX 2",
    "0xa7efae728d2936e78bda97dc267687568dd593f3": "OKX 3",
    # Bitfinex
    "0x1151314c646ce4e0efd76d1af4760ae66a9fe30f": "Bitfinex 2",
    "0x876eabf441b2ee5b5b0554fd502a8e0600950cfa": "Bitfinex 3",
    # Bybit
    "0xf89d7b9c864f589bbf53a82105107622b35eaa40": "Bybit",
}


def label_for(address: str | None) -> str | None:
    if not address:
        return None
    return _LABELS.get(address.lower())
