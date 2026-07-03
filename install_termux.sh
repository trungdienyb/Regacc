#!/data/data/com.termux/files/usr/bin/bash
set -e

APT_RETRY_OPTS="-o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60"

pkg update
apt $APT_RETRY_OPTS install -y x11-repo
apt $APT_RETRY_OPTS install -y python clang ffmpeg python-psutil python-lxml
apt $APT_RETRY_OPTS install -y chromium

python -m pip install --upgrade pip setuptools wheel
pip install -r requirements-termux.txt
pip install DrissionPage --no-deps

python -c "import psutil, lxml, DrissionPage, pydub, speech_recognition; print('OK')"
