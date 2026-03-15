#!/bin/bash
# getting latest updates from github
git fetch --all
git reset --hard origin/main
git pull origin main

# activating virtual environment
source .venv/bin/activate

# installing dependencies
pip install -r requirements.txt

# setting up user service
mkdir -p ~/.config/systemd/user
cp tradingbot.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable tradingbot

# restarting service
systemctl --user restart tradingbot
