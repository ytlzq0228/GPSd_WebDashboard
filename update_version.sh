#!/bin/bash


mount -o remount,rw / ; sudo mount -o remount,rw /boot

git reset --hard
git pull origin main
echo "Code pulled on $(date)"
cp -r * /etc/GPSd_WebDashboard
echo "Copy to /etc finished"

systemctl restart aprs_reporter.service

sync ; sudo sync ; sudo sync ; sudo mount -o remount,ro / ; sudo mount -o remount,ro /boot

