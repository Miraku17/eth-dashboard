# Telegram setup (for alerts)

Five-minute bot setup so the alerts engine can DM you when a rule fires.

## 1. Create a bot

1. Open Telegram, message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`.
3. Pick a display name (e.g. *Etherscope Alerts*).
4. Pick a unique username ending in `bot` (e.g. `etherscope_alerts_bot`).
5. BotFather replies with a token like `123456789:AAE…xyz` — this is your `TELEGRAM_BOT_TOKEN`.

## 2. Get your chat ID

1. Open a chat with your new bot and send any message (e.g. `hi`).
2. In a browser, visit:

   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```

3. In the JSON, find `result[].message.chat.id` — that number is your `TELEGRAM_CHAT_ID`.

For a group chat: add the bot to the group, send a message, then use the
negative ID (`-100…`) from the same JSON.

## 3. Wire it up

Add to `.env`:

```
TELEGRAM_BOT_TOKEN=123456789:AAE…xyz
TELEGRAM_CHAT_ID=987654321
```

Restart the worker:

```
docker compose restart worker
```

Then create a Telegram-delivered rule:

```bash
curl -X POST http://localhost:8000/api/alerts/rules \
  -H 'content-type: application/json' \
  -d '{
    "name": "ETH > $4000",
    "params": {"rule_type": "price_above", "threshold": 4000},
    "channels": [{"type": "telegram"}]
  }'
```

When the rule fires you should get a DM within ~1 minute (the evaluator runs on
a 1-minute cron).
