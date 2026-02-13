import os
import json
import threading
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, render_template_string, send_from_directory

# 导入现有的视频处理模块
from video_processor_v1 import process_single_video

app = Flask(__name__)

# 加载配置文件
def load_config():
    """加载配置文件"""
    config_file = "data/config.json"
    default_config = {
        "replace_original": False,
        "output_suffix": "_simplified",
        "backup_original": True,
        "max_file_size_mb": 500,
        "allowed_extensions": [".mkv", ".mp4", ".avi", ".mov"],
        "video_directory": "download",
        "api_settings": {
            "host": "0.0.0.0",
            "port": 5000,
            "debug": False
        },
        "parallel_settings": {
            "max_workers": 3
        },
        "smtp_settings": {
            "enable_email_notification": True,
            "smtp_server": "smtp.qq.com",
            "smtp_port": 465,
            "sender_email": "2306482889@qq.com",
            "sender_password": "skoqvmmlrbkudhhg",
            "use_ssl": True,
            "recipient_email": "1395278097@qq.com"
        }
    }
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 合并默认配置和用户配置
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
            return config
        except Exception as e:
            print(f"加载配置文件失败，使用默认配置: {str(e)}")
            return default_config
    else:
        print("配置文件不存在，使用默认配置")
        return default_config

# 加载配置
CONFIG = load_config()

# 处理配置
CONFIG["max_file_size"] = CONFIG["max_file_size_mb"] * 1024 * 1024
CONFIG["allowed_extensions"] = set(CONFIG["allowed_extensions"])
CONFIG.update(CONFIG["api_settings"])

# 处理状态存储
processing_status = {}

# 线程池执行器，用于并行处理
max_workers = CONFIG.get('parallel_settings', {}).get('max_workers', 3)
executor = ThreadPoolExecutor(max_workers=max_workers)

def is_allowed_file(filename):
    """检查文件扩展名是否允许（支持模糊匹配）"""
    # 如果文件名包含扩展名，检查扩展名
    if '.' in filename:
        ext = filename.rsplit('.', 1)[1].lower()
        return ext in [ext[1:] for ext in CONFIG['allowed_extensions']]
    
    # 如果没有扩展名，允许通过（用于模糊搜索）
    return True

def send_email_notification(filename, status, message, config=None):
    """发送邮件通知"""
    try:
        # 使用传入的配置或默认配置
        if config is None:
            config = CONFIG
            
        smtp_config = config.get('smtp_settings', {})
        if not smtp_config:
            print("未配置SMTP设置，跳过邮件通知")
            return
        
        # 检查是否启用邮件通知
        if not smtp_config.get('enable_email_notification', False):
            print("邮件通知已禁用，跳过邮件发送")
            return
        
        # 只对"视频处理完成"状态发送邮件通知
        if status != 'completed' or message != '视频处理完成':
            print(f"跳过邮件通知: {filename} - 状态: {status}, 消息: {message}")
            return
        
        # 创建邮件内容
        msg = MIMEMultipart()
        msg['From'] = smtp_config['sender_email']
        msg['To'] = smtp_config['recipient_email']
        msg['Subject'] = f"视频处理完成通知 - {filename}"
        
        # 邮件正文
        body = f"""
视频处理完成通知

文件名: {filename}
处理状态: {status}
处理结果: {message}
处理时间: {time.strftime('%Y-%m-%d %H:%M:%S')}

---
视频处理系统
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # 连接SMTP服务器并发送邮件
        if smtp_config.get('use_ssl', True):
            server = smtplib.SMTP_SSL(smtp_config['smtp_server'], smtp_config['smtp_port'])
        else:
            server = smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port'])
            server.starttls()
        
        server.login(smtp_config['sender_email'], smtp_config['sender_password'])
        server.send_message(msg)
        server.quit()
        
        print(f"邮件通知已发送: {filename}")
        
    except Exception as e:
        print(f"发送邮件通知失败: {str(e)}")

def find_video_file(filename):
    """在download目录及其子目录中查找视频文件（支持模糊搜索）"""
    download_dir = CONFIG['video_directory']
    
    # 首先检查根目录（精确匹配）
    root_path = os.path.join(download_dir, filename)
    if os.path.exists(root_path):
        return root_path
    
    # 递归搜索子目录（精确匹配）
    for root, dirs, files in os.walk(download_dir):
        if filename in files:
            return os.path.join(root, filename)
    
    # 如果精确匹配失败，进行模糊搜索
    # 获取文件名（不含扩展名）用于模糊匹配
    base_name = os.path.splitext(filename)[0]
    
    # 模糊搜索：文件名匹配（忽略扩展名）
    for root, dirs, files in os.walk(download_dir):
        for file in files:
            file_base_name = os.path.splitext(file)[0]
            if file_base_name == base_name:
                # 检查文件扩展名是否在允许的格式中
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in [ext.lower() for ext in CONFIG['allowed_extensions']]:
                    return os.path.join(root, file)
    
    return None

def process_video_async(filename, frontend_config=None):
    """异步处理视频文件"""
    try:
        # 合并前端配置和默认配置
        if frontend_config is None:
            frontend_config = {}
        
        # 使用前端配置覆盖默认配置
        current_config = CONFIG.copy()
        
        # 处理邮件配置
        if 'smtp_settings' in frontend_config:
            # 合并SMTP设置
            current_smtp = current_config.get('smtp_settings', {}).copy()
            current_smtp.update(frontend_config['smtp_settings'])
            current_config['smtp_settings'] = current_smtp
        
        # 更新其他配置
        for key, value in frontend_config.items():
            if key != 'smtp_settings':
                current_config[key] = value
        # 在download目录及其子目录中查找文件
        video_path = find_video_file(filename)
        if not video_path:
            processing_status[filename] = {
                'status': 'error',
                'message': f'文件不存在: {filename}',
                'end_time': time.time()
            }
            return
        
        # 更新状态为处理中
        processing_status[filename] = {
            'status': 'processing',
            'start_time': time.time(),
            'message': f'开始处理视频文件: {video_path}'
        }
        
        # 检查文件大小
        file_size = os.path.getsize(video_path)
        if file_size > current_config['max_file_size']:
            processing_status[filename] = {
                'status': 'error',
                'message': f'文件过大: {file_size / (1024*1024):.1f}MB > {CONFIG["max_file_size"] / (1024*1024):.1f}MB',
                'end_time': time.time()
            }
            return
        
        # 执行视频处理，传递配置参数
        result = process_single_video(video_path, 
                                    replace_original=current_config.get('replace_original', False),
                                    output_suffix=current_config.get('output_suffix', '_simplified'),
                                    backup_original=current_config.get('backup_original', True))
        
        # 更新处理结果
        if result:
            processing_status[filename] = {
                'status': 'completed',
                'message': '视频处理完成',
                'end_time': time.time()
            }
            # 发送邮件通知（使用前端配置）
            send_email_notification(filename, 'completed', '视频处理完成', current_config)
        else:
            processing_status[filename] = {
                'status': 'skipped',
                'message': '视频无需处理（可能已包含简体字幕或无需转换）',
                'end_time': time.time()
            }
            # 跳过处理的文件不发送邮件通知（根据需求只对处理完成的文件发送邮件）
            print(f"文件 {filename} 无需处理，不发送邮件通知")
            
    except Exception as e:
        processing_status[filename] = {
            'status': 'error',
            'message': f'处理过程中发生错误: {str(e)}',
            'end_time': time.time()
        }
        # 错误情况下不发送邮件通知（根据需求只对处理完成的文件发送邮件）
        print(f"文件 {filename} 处理失败，不发送邮件通知")

@app.route('/process', methods=['POST'])
def process_video():
    """处理视频文件的API端点"""
    try:
        # 获取请求数据
        data = request.get_json()
        
        if not data or 'filename' not in data:
            return jsonify({
                'error': '缺少filename参数'
            }), 400
        
        filename = data['filename']
        
        # 获取前端传递的配置参数
        frontend_config = data.get('config', {})
        
        # 验证文件名
        if not filename or not isinstance(filename, str):
            return jsonify({
                'error': 'filename必须是非空字符串'
            }), 400
        
        # 安全检查文件名 - 允许中文字符
        # 检查是否包含路径遍历字符
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({
                'error': '文件名包含非法路径字符'
            }), 400
        
        # 检查文件扩展名
        if not is_allowed_file(filename):
            return jsonify({
                'error': f'不支持的文件类型，支持的格式: {", ".join(CONFIG["allowed_extensions"])}'
            }), 400
        
        # 检查文件是否存在（支持子目录搜索）
        video_path = find_video_file(filename)
        if not video_path:
            return jsonify({
                'error': f'文件不存在: {filename}'
            }), 404
        
        # 检查是否已在处理中
        if filename in processing_status and processing_status[filename]['status'] == 'processing':
            return jsonify({
                'error': '文件正在处理中'
            }), 409
        
        # 启动异步处理（使用线程池），传递前端配置
        future = executor.submit(process_video_async, filename, frontend_config)
        
        # 立即返回200状态
        return jsonify({
            'message': '视频处理请求已接受',
            'filename': filename,
            'status': 'accepted'
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': f'服务器内部错误: {str(e)}'
        }), 500

@app.route('/status/<filename>', methods=['GET'])
def get_status(filename):
    """获取文件处理状态"""
    if filename not in processing_status:
        return jsonify({
            'error': '文件未找到或未开始处理'
        }), 404
    
    status_info = processing_status[filename].copy()
    
    # 计算处理时间
    if 'start_time' in status_info:
        if 'end_time' in status_info:
            status_info['duration'] = round(status_info['end_time'] - status_info['start_time'], 2)
        else:
            status_info['duration'] = round(time.time() - status_info['start_time'], 2)
    
    return jsonify(status_info), 200

@app.route('/status', methods=['GET'])
def get_all_status():
    """获取所有文件处理状态和系统信息"""
    # 统计各状态的文件数量
    status_counts = {}
    for status_info in processing_status.values():
        status = status_info.get('status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
    
    return jsonify({
        'total_files': len(processing_status),
        'status_counts': status_counts,
        'max_parallel_workers': max_workers,
        'files': processing_status
    }), 200

@app.route('/queue', methods=['GET'])
def get_queue_info():
    """获取处理队列信息"""
    processing_count = sum(1 for status in processing_status.values() if status.get('status') == 'processing')
    pending_count = len(processing_status) - processing_count
    
    return jsonify({
        'max_workers': max_workers,
        'currently_processing': processing_count,
        'pending': pending_count,
        'available_slots': max_workers - processing_count
    }), 200

@app.route('/files', methods=['GET'])
def list_video_files():
    """列出download目录下所有视频文件"""
    try:
        download_dir = CONFIG['video_directory']
        video_files = []
        
        # 递归搜索所有视频文件
        for root, dirs, files in os.walk(download_dir):
            for file in files:
                if is_allowed_file(file):
                    # 计算相对路径
                    rel_path = os.path.relpath(os.path.join(root, file), download_dir)
                    full_path = os.path.join(root, file)
                    
                    # 获取文件信息
                    try:
                        file_size = os.path.getsize(full_path)
                        file_info = {
                            'filename': file,
                            'relative_path': rel_path,
                            'full_path': full_path,
                            'size_mb': round(file_size / (1024 * 1024), 2),
                            'directory': os.path.dirname(rel_path) if os.path.dirname(rel_path) else '.'
                        }
                        video_files.append(file_info)
                    except Exception as e:
                        print(f"获取文件信息失败 {file}: {str(e)}")
                        continue
        
        return jsonify({
            'total_files': len(video_files),
            'files': video_files
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': f'获取文件列表失败: {str(e)}'
        }), 500

def get_eligible_video_files():
    """获取所有符合条件的视频文件列表"""
    download_dir = CONFIG['video_directory']
    eligible_files = []
    
    # 递归搜索所有视频文件
    for root, dirs, files in os.walk(download_dir):
        for file in files:
            if is_allowed_file(file):
                full_path = os.path.join(root, file)
                
                # 检查文件大小
                try:
                    file_size = os.path.getsize(full_path)
                    if file_size <= CONFIG['max_file_size']:
                        # 计算相对路径
                        rel_path = os.path.relpath(full_path, download_dir)
                        eligible_files.append({
                            'filename': file,
                            'relative_path': rel_path,
                            'full_path': full_path,
                            'size_mb': round(file_size / (1024 * 1024), 2)
                        })
                except Exception as e:
                    print(f"检查文件大小失败 {file}: {str(e)}")
                    continue
    
    return eligible_files

def process_batch_convert_async(frontend_config=None):
    """异步批量处理所有符合条件的视频文件"""
    try:
        # 合并前端配置和默认配置
        if frontend_config is None:
            frontend_config = {}
        
        # 使用前端配置覆盖默认配置
        current_config = CONFIG.copy()
        
        # 处理邮件配置
        if 'smtp_settings' in frontend_config:
            current_smtp = current_config.get('smtp_settings', {}).copy()
            current_smtp.update(frontend_config['smtp_settings'])
            current_config['smtp_settings'] = current_smtp
        
        # 更新其他配置
        for key, value in frontend_config.items():
            if key != 'smtp_settings':
                current_config[key] = value
        
        # 获取所有符合条件的文件
        eligible_files = get_eligible_video_files()
        
        if not eligible_files:
            processing_status['batch_convert'] = {
                'status': 'completed',
                'message': '没有找到符合条件的文件',
                'total_files': 0,
                'processed_files': 0,
                'skipped_files': 0,
                'error_files': 0,
                'end_time': time.time()
            }
            return
        
        # 初始化批量处理状态
        processing_status['batch_convert'] = {
            'status': 'processing',
            'start_time': time.time(),
            'total_files': len(eligible_files),
            'processed_files': 0,
            'skipped_files': 0,
            'error_files': 0,
            'current_file': '',
            'message': f'开始批量处理 {len(eligible_files)} 个文件'
        }
        
        processed_count = 0
        skipped_count = 0
        error_count = 0
        
        # 逐个处理文件
        for i, file_info in enumerate(eligible_files):
            filename = file_info['filename']
            full_path = file_info['full_path']
            
            # 更新当前处理文件状态
            processing_status['batch_convert']['current_file'] = filename
            processing_status['batch_convert']['message'] = f'正在处理 {i+1}/{len(eligible_files)}: {filename}'
            
            try:
                # 检查文件是否已在处理中
                if filename in processing_status and processing_status[filename]['status'] == 'processing':
                    print(f"跳过正在处理中的文件: {filename}")
                    skipped_count += 1
                    continue
                
                # 执行视频处理
                result = process_single_video(
                    full_path,
                    replace_original=current_config.get('replace_original', False),
                    output_suffix=current_config.get('output_suffix', '_simplified'),
                    backup_original=current_config.get('backup_original', True)
                )
                
                if result:
                    processed_count += 1
                    # 更新单个文件状态
                    processing_status[filename] = {
                        'status': 'completed',
                        'message': '视频处理完成',
                        'end_time': time.time()
                    }
                else:
                    skipped_count += 1
                    # 更新单个文件状态
                    processing_status[filename] = {
                        'status': 'skipped',
                        'message': '视频无需处理（可能已包含简体字幕或无需转换）',
                        'end_time': time.time()
                    }
                
                # 发送邮件通知（只对处理完成的文件）
                if current_config.get('smtp_settings', {}).get('enable_email_notification', False):
                    if result:  # 只有处理成功时才发送邮件
                        send_email_notification(filename, 'completed', '视频处理完成', current_config)
                
            except Exception as e:
                error_count += 1
                print(f"处理文件 {filename} 时出错: {str(e)}")
                # 更新单个文件状态
                processing_status[filename] = {
                    'status': 'error',
                    'message': f'处理过程中发生错误: {str(e)}',
                    'end_time': time.time()
                }
                # 错误情况下不发送邮件通知（根据需求只对处理完成的文件发送邮件）
                print(f"文件 {filename} 处理失败，不发送邮件通知")
        
        # 更新最终批量处理状态
        processing_status['batch_convert'].update({
            'status': 'completed',
            'processed_files': processed_count,
            'skipped_files': skipped_count,
            'error_files': error_count,
            'end_time': time.time(),
            'message': f'批量处理完成: 成功 {processed_count} 个，跳过 {skipped_count} 个，错误 {error_count} 个'
        })
        
        print(f"批量处理完成: 总计 {len(eligible_files)} 个文件，成功 {processed_count} 个，跳过 {skipped_count} 个，错误 {error_count} 个")
        
    except Exception as e:
        processing_status['batch_convert'] = {
            'status': 'error',
            'message': f'批量处理过程中发生错误: {str(e)}',
            'end_time': time.time()
        }
        print(f"批量处理过程中发生错误: {str(e)}")

@app.route('/batch-convert', methods=['POST'])
def batch_convert():
    """批量转换所有符合条件的视频文件"""
    try:
        # 获取请求数据
        data = request.get_json() or {}
        
        # 获取前端传递的配置参数
        frontend_config = data.get('config', {})
        
        # 检查是否已有批量处理在进行中
        if 'batch_convert' in processing_status and processing_status['batch_convert']['status'] == 'processing':
            return jsonify({
                'error': '批量转换正在进行中，请等待完成后再试'
            }), 409
        
        # 获取符合条件的文件数量
        eligible_files = get_eligible_video_files()
        
        if not eligible_files:
            return jsonify({
                'message': '没有找到符合条件的文件',
                'total_files': 0
            }), 200
        
        # 启动异步批量处理
        future = executor.submit(process_batch_convert_async, frontend_config)
        
        return jsonify({
            'message': '批量转换请求已接受',
            'total_files': len(eligible_files),
            'status': 'accepted'
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': f'服务器内部错误: {str(e)}'
        }), 500

@app.route('/batch-status', methods=['GET'])
def get_batch_status():
    """获取批量转换状态"""
    if 'batch_convert' not in processing_status:
        return jsonify({
            'error': '没有批量转换任务'
        }), 404
    
    status_info = processing_status['batch_convert'].copy()
    
    # 计算处理时间
    if 'start_time' in status_info:
        if 'end_time' in status_info:
            status_info['duration'] = round(status_info['end_time'] - status_info['start_time'], 2)
        else:
            status_info['duration'] = round(time.time() - status_info['start_time'], 2)
    
    # 计算进度百分比
    if 'total_files' in status_info and status_info['total_files'] > 0:
        completed = status_info.get('processed_files', 0) + status_info.get('skipped_files', 0) + status_info.get('error_files', 0)
        status_info['progress_percentage'] = round((completed / status_info['total_files']) * 100, 1)
    else:
        status_info['progress_percentage'] = 0
    
    return jsonify(status_info), 200

@app.route('/')
def index():
    """提供前端界面"""
    try:
        # 读取index.html文件内容
        with open('index.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        return """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>视频转换系统</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                .error { color: #dc3545; background: #f8d7da; padding: 20px; border-radius: 5px; }
            </style>
        </head>
        <body>
            <div class="error">
                <h1>❌ 错误</h1>
                <p>找不到前端界面文件 index.html</p>
                <p>请确保 index.html 文件存在于服务器目录中</p>
            </div>
        </body>
        </html>
        """, 404
    except Exception as e:
        return f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>视频转换系统</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                .error { color: #dc3545; background: #f8d7da; padding: 20px; border-radius: 5px; }
            </style>
        </head>
        <body>
            <div class="error">
                <h1>❌ 错误</h1>
                <p>加载前端界面失败: {str(e)}</p>
            </div>
        </body>
        </html>
        """, 500

if __name__ == '__main__':
    # 确保data目录和download目录存在
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(CONFIG['video_directory']):
        os.makedirs(CONFIG['video_directory'])
    
    print(f"启动视频处理API服务器...")
    print(f"服务器地址: http://{CONFIG['host']}:{CONFIG['port']}")
    print(f"视频目录: {os.path.abspath(CONFIG['video_directory'])}")
    print(f"支持的视频格式: {', '.join(CONFIG['allowed_extensions'])}")
    print(f"最大文件大小: {CONFIG['max_file_size'] / (1024*1024):.0f}MB")
    print(f"最大并行处理数: {max_workers}")
    
    app.run(
        host=CONFIG['host'],
        port=CONFIG['port'],
        debug=CONFIG['debug']
    )