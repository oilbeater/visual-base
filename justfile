default:
    @just --list

setup:
    uv sync
    uv tool install --python 3.13 kimi-cli

upgrade-kimi:
    uv tool upgrade kimi-cli
