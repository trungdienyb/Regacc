#!/data/data/com.termux/files/usr/bin/bash
set -e

pkg update
pkg install -y x11-repo
pkg install -y python clang ffmpeg chromium python-psutil python-lxml

python -m pip install --upgrade pip setuptools wheel
pip install -r requirements-termux.txt
pip install DrissionPage --no-deps

python -c "import psutil, lxml, DrissionPage, pydub, speech_recognition; print('OK')"
