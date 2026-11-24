# discord-bot-render-template

A minimal scaffold for deploying a Python Discord bot (discord.py) to Render's free Web Service.

## What's included

`render.yaml` is a Render Blueprint: Python 3.11.9, free plan, auto-deploy on every push.

`requirements.txt` pins discord.py>=2.3.2.

`.gitignore` covers Python and environment files.

## Configuration

Start command: `python main.py`

Health check path: `/health`

Environment variable: `DISCORD_TOKEN`. Set it in the Render dashboard and never commit it.

## Getting started

Step 1. Click "Use this template" to create your own repository.

Step 2. Add a `main.py` that starts your bot and serves a `/health` endpoint so the free Web Service stays healthy.

Step 3. In Render, create a new Blueprint from your repository.

Step 4. Set `DISCORD_TOKEN` and deploy.

## Notes

`main.py` is intentionally not included. Bring your own bot code.
