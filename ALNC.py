from urllib.parse import quote
import subprocess
import logging
import requests
from win10toast import ToastNotifier
import socket
import re
import configparser
import ctypes
import time
import hashlib
import os
import configparser

# 打包命令 pyinstaller --onefile --copy-metadata=win10toast --name=校园网自动登录_v1.0 ALNC.py

# 初始化自定义通知器并设置默认图标路径
toaster = ToastNotifier(
    # icon_path="icon.ico"
)

## 日志配置 将日志文件保存在脚本所在目录
script_dir = os.path.dirname(os.path.abspath(__file__))
log_path = os.path.join(script_dir, "ALNC.log")

logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8",
)

result = subprocess.run(
    ["netsh", "wlan", "show", "interfaces"],
    capture_output=True,
    check=True,
    timeout=5,
    encoding="utf-8",  # 明确指定编码为UTF-8
    errors="replace",
)


# 定义日志记录函数
def log(message):
    """记录日志信息"""
    logging.info(message)


# 获取当前工作目录
current_dir = os.getcwd()

# 构造配置文件的完整路径
config_path = os.path.join(current_dir, "必读-配置文件.ini")

# 使用相对路径读取配置文件
config = configparser.ConfigParser()
config.read(config_path, encoding="utf-8")


# 动态配置部分
POST_URL = "http://219.231.219.88/eportal/InterFace.do?method=login"
headers = {
    "Accept": "*/*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0",
    "Referer": "http://219.231.219.88/eportal/index.jsp",
    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
}


def double_sha256_hash(input_string):
    # 第一次哈希计算
    first_hash = hashlib.sha256(input_string.encode()).hexdigest()
    # 第二次哈希计算
    second_hash = hashlib.sha256(first_hash.encode()).hexdigest()
    # 拼接两次哈希结果
    result = first_hash + second_hash
    return result


data_template = {
    "userId": config["Credentials"]["username"].strip(),
    "password": config["Credentials"]["password"].strip(),
    "service": config["Credentials"]["service"].strip(),  # 中国移动
    "queryString": "",  # 动态填充
    "operatorPwd": "",
    "operatorUserId": "",
    "validcode": "",
    "passwordEncrypt": "true",
}


def get_local_ip(target_gateway="219.231.219.1"):
    """获取与目标网关同网段的本地IP"""
    try:
        # 创建UDP套接字探测网关
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((target_gateway, 80))
        local_ip = s.getsockname()[0]
        s.close()

        # 验证IP格式 (例如 172.18.x.x)
        if not re.match(r"^172\.18\.\d+\.\d+$", local_ip):
            raise ValueError("IP不在校园网段内")
        return local_ip
    except Exception as e:
        logging.error(f"获取校园网IP失败: {str(e)}")
        return None


def build_dynamic_data():
    """动态生成请求参数"""
    current_ip = get_local_ip()
    if not current_ip:
        return None

    # 构造动态queryString（示例，需根据实际参数调整）
    query_params = {
        "wlanuserip": current_ip,
        "wlanacname": "3e7688f1cfd7a67a96e2e9bb498044b7",
        # 其他固定参数...
    }
    encoded_query = "&".join([f"{k}={quote(v)}" for k, v in query_params.items()])

    data = data_template.copy()
    data["queryString"] = encoded_query
    return data


def get_wifi_info():
    """获取无线网络接口信息"""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            check=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
        log("原始命令输出:\n" + result.stdout)
        return result.stdout
    except Exception as e:
        log(f"命令执行异常: {str(e)}")
        return None


def analyze_data(data):
    """分析无线网络接口数据，获取当前连接的SSID"""
    state_pattern = re.compile(r"状态\s*:\s*(.*?)(\n|$)", re.IGNORECASE | re.MULTILINE)
    ssid_pattern = re.compile(r"SSID\s*:\s*(.*?)(\n|$)", re.IGNORECASE | re.MULTILINE)

    interfaces = re.split(r"\n\s*\n", data)
    log(f"发现 {len(interfaces)} 个网络接口")

    for interface in interfaces:
        if "无线" not in interface and "wlan" not in interface.lower():
            continue

        state_match = state_pattern.search(interface)
        if state_match:
            status = state_match.group(1).strip()
            if any(
                x in status
                for x in ["已连接", "已连线", "关联", "connected", "associated"]
            ):
                ssid_match = ssid_pattern.search(interface)
                if ssid_match:
                    return ssid_match.group(1).strip()
    return None


def network_test(url="http://www.baidu.com"):
    """测试网络连通性"""
    try:
        response = requests.get(url, timeout=0.5)
        response.encoding = "utf-8"
        if response.status_code == 200:
            if "百度一下，你就知道" in response.text:
                log("HTTP测试成功")
                return True
            else:
                log(f"HTTP测试失败，状态码: {response.status_code}")
                return False
        else:
            log(f"HTTP测试失败，状态码: {response.status_code}")
            return False
    except Exception as e:
        log(f"HTTP测试异常: {str(e)}")
        return False


def verify_network():
    """验证网络连接"""
    try:
        response = subprocess.run(
            ["netsh", "wlan", "connect", 'name="SDTBU-STU"'],
            capture_output=True,
            check=True,
            timeout=1,
            encoding="utf-8",
            errors="replace",
        )
        log("网络验证结果:\n" + response.stdout)
        return True
    except Exception as e:
        log(f"网络验证异常: {str(e)}")
        return False


def silent_login():
    try:
        data = build_dynamic_data()
        if not data:
            raise ValueError("无法生成动态请求参数")

        session = requests.Session()
        session.headers.update(headers)

        # 发送POST请求（禁用自动重定向）
        response = session.post(POST_URL, data=data, timeout=3, allow_redirects=False)
        response.encoding = "utf-8"
        logging.info(f"登录响应: {response.text}")

        # 处理JavaScript重定向
        if "script" in response.text:
            redirect_url = re.search(
                r"window\.location\.href='(.*?)'", response.text
            ).group(1)
            logging.info(f"触发重定向: {redirect_url}")
            redirect_resp = session.get(redirect_url, timeout=3)
            if "success" in redirect_resp.text:
                toaster.show_toast("校园网登录", "登录成功", duration=5)
                return True

        # 直接检查登录结果
        if "success" in response.text.lower():
            toaster.show_toast("校园网登录", "登录成功", duration=5)
            return True

        toaster.show_toast("校园网登录", "登录失败", duration=5)
        return False

    except Exception as e:
        logging.error(f"登录异常: {str(e)}")
        toaster.show_toast("校园网登录", f"异常: {str(e)}", duration=0.5)
        return False


# 主函数和其他辅助函数保持不变（需确保调用silent_login）


def main(self=None):
    """主函数"""

    # 找到当前窗口的句柄
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    # 最小化窗口
    ctypes.windll.user32.ShowWindow(hwnd, 6)  # 6 是最小化的标志
    last_connected_ssid = None  # 用于记录上次连接的SSID
    while True:
        log(
            "================================== 诊断开始 ==================================="
        )
        log(config["Credentials"]["username"])
        log(config["Credentials"]["password"])
        raw_data = get_wifi_info()
        if raw_data:
            ssid = analyze_data(raw_data)
            log(f"解析结果: {ssid if ssid else '未连接'}")
            print(f"当前状态: {'已连接: ' + ssid if ssid else '未连接'}")
            toaster.show_toast(
                "网络状态", "已连接: " + ssid if ssid else "未连接", duration=0.5
            )
            if ssid == "SDTBU-STU":
                if network_test():
                    print("网络可用，程序进入休眠状态...")
                    toaster.show_toast(
                        "网络状态", "网络可用✅ ，进入休眠模式", duration=1
                    )

                    # 记录当前连接的SSID
                    last_connected_ssid = ssid
                    # 进入休眠状态，直到WiFi状态更改
                    while True:
                        time.sleep(3)
                        current_raw_data = get_wifi_info()
                        if current_raw_data:
                            current_ssid = analyze_data(current_raw_data)
                            if current_ssid != last_connected_ssid:
                                print("WiFi连接状态已更改，程序唤醒...")
                                toaster.show_toast(
                                    "网络状态",
                                    "WiFi连接状态已更改，程序唤醒中",
                                    duration=1,
                                )
                                last_connected_ssid = current_ssid
                                break
                else:
                    print("网络不可用，进行自动登录...")
                    toaster.show_toast(
                        "网络状态", "网络不可用，进行自动登录...", duration=0.5
                    )
                    silent_login()
            else:
                last_connected_ssid = None  # 清空记录的SSID
        time.sleep(3)
        log(
            "============结束====================结束======================== 结束 ===========================结束=========================="
        )


if __name__ == "__main__":
    main()
