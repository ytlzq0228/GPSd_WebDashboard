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

def get_constellation(prn):
	# 定义PRN号与星座的对应关系
	constellation_map = {
		'GPS': range(1, 33),  # GPS uses PRNs from 1 to 32
		'GLONASS': range(33, 66),  # GLONASS uses PRNs from 33 to 65
		'Galileo': range(301, 337),  # Galileo uses PRNs from 301 to 336
		'BeiDou': range(201, 237),  # BeiDou uses PRNs from 201 to 236
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
				try:
					data_json = json.loads(new_data)
				except json.JSONDecodeError:
					print("GPSd received invalid JSON")
					continue
				# 更新TPV数据，保留了你的细节处理
				if data_json.get('class') == 'TPV':
					status_data={}
					for i in ['alt', 'track', 'magtrack', 'magvar', 'time', 'speed']:
						if i in data_json:
							status_data[i]=data_json[i]
					# 处理 GNSS 状态
					mode_map={0: "Unknown",1: "no fix",2: "Normal Mode 2D",3: "Normal Mode 3D"}
					status_map = {0: "Unknown",1: "Normal",2: "DGPS",3: "RTK FIX",4: "RTK FLOAT",5: "DR FIX",6: "GNSSDR",7: "Time (surveyed)",8: "Simulated",9: "P(Y)",}
					if data_json.get('status',1) ==1:
						status_data['status'] = mode_map.get(data_json.get('mode',0), "Unknown")
					else:
						status_data['status'] = status_map.get(data_json.get('status',1), "Unknown")
					status_data['speed']="%.2f"%(status_data['speed']*3.6) #米/秒转公里/小时
					status_data['time']=datetime.fromisoformat(status_data['time'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
					status_data['Sat_Qty']=len(gps_data_cache['SNR'])
					gps_data_cache['TPV'] = status_data
					for i in ['lat', 'lon']:
						if i in data_json:
							gps_data_cache['Path'][i]=data_json[i]
		time.sleep(0.5)  # Reduce CPU usage

# 启动后台线程更新数据
threading.Thread(target=update_gps_data, daemon=True).start()

@app.route('/')
def index():
	return render_template('index.html')

@app.route('/snr-data')
def snr_data():
	#print(len(gps_data_cache['SNR']))
	#print({'satellites': [{'PRN': prn, 'ss': ss} for prn, ss in gps_data_cache['SNR'].items()]})
	return jsonify({'satellites': [{'PRN': prn, 'ss': ss} for prn, ss in gps_data_cache['SNR'].items()]})

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
	try:
		log_file_update_time=os.path.getmtime(APRS_LOG_FILE)
		updatetime_diff=int(time.time()-log_file_update_time)
		#print(updatetime_diff)
		log_file_data={}
		log_file_data['更新时间']=datetime.fromtimestamp(log_file_update_time).strftime('%H:%M:%S')
		log_file_data['更新延迟']=updatetime_diff
		#print(log_file_data)
		return jsonify(log_file_data)
	except Exception as e:
		print(f"Error fetching log file data: {e}")
		return None

if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=5000)