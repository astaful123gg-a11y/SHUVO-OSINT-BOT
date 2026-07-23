# SHUVO BOT — Full Backup

## Quick Start

### Local
```bash
pip install -r requirements.txt
cd mc_node && npm install && cd ..
python3 run.py
```

### Railway / Render / Heroku
1. Push to GitHub
2. Set env vars: BOT_TOKEN, OWNER_ID, ADMIN_ID, CONTROLLER_TOKEN
3. Deploy — nixpacks.toml handles the rest

### Docker
```bash
docker build -t shuvobot .
docker run -d --env-file .env shuvobot
```

## Env vars needed
- BOT_TOKEN         — Main bot token (@BotFather)
- OWNER_ID          — Your Telegram user ID
- ADMIN_ID          — Admin Telegram user ID
- CONTROLLER_TOKEN  — Controller bot token (@BotFather)

## File map
| File              | Purpose                          |
|-------------------|----------------------------------|
| main.py           | Main bot — all features          |
| controller.py     | Controller bot                   |
| run.py            | Process manager (starts both)    |
| mc_manager.py     | Minecraft bot manager            |
| mc_node/mc_bot.js | Minecraft bot (Node.js/mineflayer)|
| bot/config.json   | Bot configuration                |
| bot/insta_cookies.json | Instagram session cookies   |

## Dev: @Shuvobhai
