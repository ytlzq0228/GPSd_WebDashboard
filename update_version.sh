#!/bin/bash


mount -o remount,rw / ; sudo mount -o remount,rw /boot

git reset --hard
git pull origin main

python3 /home/pi-star/GPSd_WebDashboard/webdash.py

sync ; sudo sync ; sudo sync ; sudo mount -o remount,ro / ; sudo mount -o remount,ro /boot

