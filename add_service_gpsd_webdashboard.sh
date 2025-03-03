#!/bin/bash
mount -o remount,rw / ; sudo mount -o remount,rw /boot

# 写入服务文件内容
echo "Creating systemd service file..."
cat <<EOF | sudo tee /etc/systemd/system/gpsd_webdashboard.service
[Unit]
Description=gpsd_webdashboard
After=network.target gpsd.service

[Service]
ExecStart=/etc/GPSd_WebDashboard/gpsdwebdash.sh
ExecStop=/usr/bin/pkill -f gpsdwebdash.py
Restart=always
RestartSec=5
User=root
WorkingDirectory=/etc/GPSd_WebDashboard/
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gpsd_webdashboard.service
systemctl start gpsd_webdashboard.service
systemctl status gpsd_webdashboard.service
sync ; sudo sync ; sudo sync ; sudo mount -o remount,ro / ; sudo mount -o remount,ro /boot