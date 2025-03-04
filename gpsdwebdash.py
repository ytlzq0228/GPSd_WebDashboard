from flask import Flask, jsonify, render_template
import threading
import json
import time
import os
import configparser
from gps3 import gps3
from datetime import datetime

CONFIG_FILE = '/etc/GPS_config.ini'
config = configparser.ConfigParser()
config.read(CONFIG_FILE)

LOG_FILE_PATH = config['SFTP_Config']['LOCAL_LOG_FILE_PATH']
SSID = config['SSID_Config']['SSID']
APRS_LOG_FILE = f"{LOG_FILE_PATH}/{datetime.now().strftime('%Y-%m-%d')}-GPS-{SSID}.log"

app = Flask(__name__)

# 创建 GPSD 连接
gps_socket = gps3.GPSDSocket()
data_stream = gps3.DataStream()
gps_socket.connect()
gps_socket.watch()

# 定义全局缓存
gps_data_cache = {
    'SNR': {},
    'TPV': {},
    'Path': {},
    'Log': {}
}

def update_gps_data():
    while True:
        for new_data in gps_socket:
            if new_data:
                data_stream.unpack(new_data)
                # 更新SNR数据
                if 'satellites' in data_stream.SKY:
                    gps_data_cache['SNR'] = {
                        get_constellation(sat['PRN']): sat['ss'] for sat in data_stream.SKY['satellites'] if 'ss' in sat
                    }
                # 更新TPV数据，保留了你的细节处理
                if data_stream.TPV['class'] == 'TPV':
                    status_data = {key: data_stream.TPV[key] for key in ['alt', 'lat', 'lon', 'track', 'magtrack', 'magvar', 'time', 'speed'] if key in data_stream.TPV}
                    mode_map = {0: "Unknown", 1: "no fix", 2: "Normal Mode 2D", 3: "Normal Mode 3D"}
                    status_map = {0: "Unknown", 1: "Normal", 2: "DGPS", 3: "RTK FIX", 4: "RTK FLOAT", 5: "DR FIX", 6: "GNSSDR", 7: "Time (surveyed)", 8: "Simulated", 9: "P(Y)"}
                    status_data['status'] = mode_map.get(data_stream.TPV.get('mode', 0), "Unknown") if data_stream.TPV.get('status', 1) == 1 else status_map.get(data_stream.TPV.get('status', 1), "Unknown")
                    status_data['speed'] = f"{float(status_data['speed'])*3.6:.2f}" if 'speed' in status_data else "N/A"
                    gps_data_cache['TPV'] = status_data
        time.sleep(1)  # Reduce CPU usage

# 启动后台线程更新数据
threading.Thread(target=update_gps_data, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/snr-data')
def snr_data():
    return jsonify({'satellites': [{'PRN': prn, 'ss': ss} for prn, ss in gps_data_cache['SNR'].items()]})

@app.route('/tpv-data')
def tpv_data():
    return jsonify(gps_data_cache['TPV'])

@app.route('/path-data')
def path_data():
    return jsonify(gps_data_cache['Path'])

@app.route('/log-data')
def log_data():
    log_file_update_time = os.path.getmtime(APRS_LOG_FILE)
    return jsonify({
        '更新时间': datetime.fromtimestamp(log_file_update_time).strftime('%Y-%m-%d %H:%M:%S'),
        '更新延迟': int(time.time() - log_file_update_time)
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)