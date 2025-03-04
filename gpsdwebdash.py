from flask import Flask, jsonify, render_template
from gps3 import gps3
import json
import time
import os
import configparser
from save_log import save_log
from datetime import datetime

CONFIG_FILE='/etc/GPS_config.ini'
config = configparser.ConfigParser()
config.read(CONFIG_FILE)

LOG_FILE_PATH=config['SFTP_Config']['LOCAL_LOG_FILE_PATH']
SSID=config['SSID_Config']['SSID']
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


def get_last_modified_time(file_path):
    try:
        # 获取文件的最后修改时间戳
        modification_time = os.path.getmtime(file_path)
        # 将时间戳转换为可读的格式
        readable_time = datetime.fromtimestamp(modification_time)
        return readable_time
    except FileNotFoundError:
        return "File not found"

# 指定文件路径


@app.route('/')
def index():
	return render_template('index.html')

#@app.route('/snr-data')
#def snr_data():
#	# 这里直接返回模拟数据
#	return jsonify(data)


@app.route('/snr-data')
def snr_data():
	satellites_data = {}
	try:
		start_time = time.time()
		while True:
			new_data = gps_socket.next()  # 使用 next() 从 socket 获取数据
			if new_data:
				data_stream.unpack(new_data)
				if 'satellites' in data_stream.SKY:
					for sat in data_stream.SKY['satellites']:
						if 'ss' in sat:
							sat_name=get_constellation(sat['PRN'])
							satellites_data[sat_name] = sat['ss']
			if time.time() - start_time > 2:  # 设置10秒超时，避免无限循环
				break
		satellites_data={'satellites': [{'PRN': prn, 'ss': ss} for prn, ss in satellites_data.items()]}
		return jsonify(satellites_data)
	except Exception as e:
		print(f"Error: {str(e)}")  # 打印错误
		return jsonify({'error': str(e)})

@app.route('/tpv-data')
def tpv_data():
	try:
		for new_data in gps_socket:
			if not new_data:  # 跳过空数据
				continue

			try:
				data = json.loads(new_data)
			except json.JSONDecodeError:
				print("GPSd received invalid JSON")
				continue

			if data.get('class') == 'TPV':
				tpv_data=data
				break
			time.sleep(0.01)  # 避免 CPU 100% 占用
		print()
		status_data={}
		for i in ['alt', 'class', 'lat', 'lon', 'track', 'magtrack', 'magvar', 'time', 'speed']:
			if i in tpv_data:
				status_data[i]=tpv_data[i]
		# 处理 GNSS 状态
		mode_map={0: "Unknown",1: "no fix",2: "Normal Mode 2D",3: "Normal Mode 3D"}
		status_map = {
			0: "Unknown",
			1: "Normal",
			2: "DGPS",
			3: "RTK FIX",
			4: "RTK FLOAT",
			5: "DR FIX",
			6: "GNSSDR",
			7: "Time (surveyed)",
			8: "Simulated",
			9: "P(Y)",
		}
		if tpv_data.get('status',1) ==1:
			status_data['status'] = mode_map.get(tpv_data.get('mode',0), "Unknown")
		else:
			status_data['status'] = status_map.get(tpv_data.get('status',1), "Unknown")
		#status_data['speed']=100 #test speed only
		return jsonify(status_data)
	except Exception as e:
		print(f"Error fetching GPSd data: {e}")
		return None

@app.route('/log_data')
def log_data():
	try:
		log_file_update_time=get_last_modified_time(APRS_LOG_FILE)
		updatetime_diff=time.time()-log_file_update_time
		log_file_data={}
		log_file_data['更新时间']=log_file_update_time
		log_file_data['更新延迟']=updatetime_diff
		print(jsonify(log_file_data))
		return jsonify(log_file_data)
	except Exception as e:
		print(f"Error fetching log file data: {e}")
		return None

if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=5000)