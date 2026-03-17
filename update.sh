#!/bin/bash
# getting latest updates from github
git fetch --all
git reset --hard origin/main
git pull origin main

# activating virtual environment
rm -fr .venv
python3 -m venv .venv
source .venv/bin/activate

# installing dependencies
pip install -r requirements.txt

# setting up user service
mkdir -p ~/.config/systemd/user
cp -f config/tradingbot.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable tradingbot

# create logs folder if it doesn't exist
if [ ! -d "logs" ]; then
    mkdir logs
fi

# create ops folder if it doesn't exist
if [ ! -d "ops" ]; then
    mkdir ops
fi

# create config folder if it doesn't exist
if [ ! -d "config" ]; then
    mkdir config
fi

# restarting service
systemctl --user restart tradingbot

