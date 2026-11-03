#!/bin/bash
# getting latest updates from github
git fetch --all
git reset --hard origin/main
git pull origin main

# building the rust binaries
if ! command -v cargo >/dev/null 2>&1; then
    echo "cargo not found; install Rust from https://rustup.rs and re-run" >&2
    exit 1
fi
cargo build --release

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
