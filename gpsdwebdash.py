from flask import Flask, jsonify, render_template
import threading
import json
import time
import os
import configparser
from gps3 import gps3
from datetime import datetime
import RPi.GPIO as GPIO

CONFIG_FILE = '/etc/GPS_config.ini'
config = configparser.ConfigParser()
config.read(CONFIG_FILE)

LOG_FILE_PATH = config['SFTP_Config']['LOCAL_LOG_FILE_PATH']
SSID = config['SSID_Config']['SSID']
APRS_LOG_FILE = f"{LOG_FILE_PATH}/{datetime.now().strftime('%Y-%m-%d')}-GPS-{SSID}.log"

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO_STARTUP_PIN=21
GPIO_LOG_ERROR_PIN=16
GPIO.setup(GPIO_STARTUP_PIN, GPIO.OUT)
GPIO.setup(GPIO_LOG_ERROR_PIN, GPIO.OUT)

GPIO.output(GPIO_STARTUP_PIN, True)

app = Flask(__name__)

# 创建 GPSD 连接
gps_socket = gps3.GPSDSocket()
data_stream = gps3.DataStream()
gps_socket.connect()
gps_socket.watch()

def get_constellation(prn):
	# 定义PRN号与星座的对应关系
	constellation_map = {
		'GPS': range(1, 32),  # GPS uses PRNs from 1 to 32
		'GPS SBAS': range(33, 64),
		'GL': range(65, 97),  # GLONASS uses PRNs from 33 to 65
		'GA': range(301, 337),  # Galileo uses PRNs from 301 to 336
		'BD': range(401, 420),  # BeiDou uses PRNs from 201 to 236
		'QZSS': range(193, 198),  # QZSS uses PRNs from 193 to 197
		'IRNSS': range(401, 408),  # IRNSS uses PRNs from 401 to 407
		'WAAS': range(133, 139),  # WAAS (North America) uses PRNs from 133 to 138
		'EGNOS': range(120, 139),  # EGNOS (Europe) uses PRNs from 120 to 138
		'GAGAN': range(127, 129),  # GAGAN (India) uses PRNs 127 and 128
		'MSAS': range(129, 138)  # MSAS (Japan) uses PRNs from 129 to 137
	}

	# 遍历字典，找到相应的星座
	for constellation, prns in constellation_map.items():
		if prn in prns:
			return f"{constellation}_{prn}"
	return f"Unknow_{prn}"



# 定义全局缓存
gps_data_cache = {
	'SNR': {'satellites':[]},
	'TPV': {},
	'Path': {},
	'log_file_data': {}
}

def update_gps_data():
	while True:
		for new_data in gps_socket:
			if new_data:
				try:
					data_json = json.loads(new_data)
				except json.JSONDecodeError:
					print("GPSd received invalid JSON")
					continue

				# 更新SNR数据
				if data_json.get('class') == 'SKY' and 'satellites' in data_json:
					for i in data_json['satellites']:
						# 检查新的卫星数据是否存在
						exists = any(sat['PRN'] == get_constellation(i['PRN']) for sat in gps_data_cache['SNR']['satellites'])
						if not exists:
							gps_data_cache['SNR']['satellites'].append({'PRN': get_constellation(i['PRN']), 'ss': i['ss'], 'used': i['used']})
				
				# 更新TPV数据，保留了你的细节处理
				if data_json.get('class') == 'TPV':
					status_data={}
					status_data['Sat_Qty']=len(gps_data_cache['SNR']['satellites'])
					gps_data_cache['SNR']['satellites']=[]#每个周期更新TPV的时候清除缓存的SKY数据
					for i in ['alt', 'track', 'magtrack', 'magvar', 'time', 'speed']:
						if i in data_json:
							status_data[i]=data_json[i]
						else:
							status_data[i]=0
					# 处理 GNSS 状态
					mode_map={0: "Unknown",1: "no fix",2: "Normal Mode 2D",3: "Normal Mode 3D"}
					status_map = {0: "Unknown",1: "Normal",2: "DGPS",3: "RTK FIX",4: "RTK FLOAT",5: "DR FIX",6: "GNSSDR",7: "Time (surveyed)",8: "Simulated",9: "P(Y)",}
					if data_json.get('status',1) ==1:
						status_data['status'] = mode_map.get(data_json.get('mode',0), "Unknown")
					else:
						status_data['status'] = status_map.get(data_json.get('status',1), "Unknown")
					status_data['speed']="%.2f"%(status_data['speed']*3.6) #米/秒转公里/小时
					if status_data['time']!=0:
						status_data['time']=datetime.fromisoformat(status_data['time'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
					gps_data_cache['TPV'] = status_data
					#写入Path数据
					for i in ['lat', 'lon', 'speed']:
						if i in data_json:
							gps_data_cache['Path'][i]=data_json[i]
					#阶梯化speed，不连续变化，避免speed频繁变化影响地图缩放
					step=5
					#gps_data_cache['Path']['speed']=5 #test only
					if 'speed' not in gps_data_cache['Path']:
						gps_data_cache['Path']['speed']=0
					gps_data_cache['Path']['speed']=max((round(gps_data_cache['Path']['speed'] / step) * step),0.5)
		time.sleep(0.5)

def update_log_file_data():
	while True:
		try:
			if os.path.exists(APRS_LOG_FILE):
				log_file_update_time=os.path.getmtime(APRS_LOG_FILE)
				updatetime_diff=int(time.time()-log_file_update_time)
				#print(updatetime_diff)
				gps_data_cache['log_file_data']['更新时间']=datetime.fromtimestamp(log_file_update_time).strftime('%H:%M:%S')
				gps_data_cache['log_file_data']['更新延迟']=updatetime_diff
				LOG_ERROR_STATUS=True
				if updatetime_diff<10:
					if not LOG_ERROR_STATUS:
						GPIO.output(GPIO_LOG_ERROR_PIN, True)
						LOG_ERROR_STATUS=True
				else:
					GPIO.output(GPIO_LOG_ERROR_PIN, False)
					LOG_ERROR_STATUS=False
				#print(gps_data_cache['log_file_data'])
			else:
				gps_data_cache['log_file_data']['更新延迟']='No Log File'
				GPIO.output(GPIO_LOG_ERROR_PIN, False)
		except Exception as e:
			print(f"Error fetching log file data: {e}")
		time.sleep(0.5)  # Reduce CPU usage

# 启动后台线程更新数据
threading.Thread(target=update_gps_data, daemon=True).start()
threading.Thread(target=update_log_file_data, daemon=True).start()

@app.route('/')
def index():
	return render_template('index.html')

@app.route('/snr-data')
def snr_data():
	#print(gps_data_cache['SNR'])
	#print({'satellites': [{'PRN': prn, 'ss': ss} for prn, ss in gps_data_cache['SNR'].items()]})
	return jsonify(gps_data_cache['SNR'])

@app.route('/tpv-data')
def tpv_data():
	#print(gps_data_cache['TPV'])
	return jsonify(gps_data_cache['TPV'])

@app.route('/path-data')
def path_data():
	#print(gps_data_cache['Path'])
	return jsonify(gps_data_cache['Path'])

@app.route('/log-data')
def log_data():
	print(gps_data_cache['log_file_data'])
	return jsonify(gps_data_cache['log_file_data'])

if __name__ == '__main__':
	import logging
	log = logging.getLogger('werkzeug')
	log.setLevel(logging.ERROR)  # 只记录错误信息
	app.run(debug=False, host='0.0.0.0', port=5000)
