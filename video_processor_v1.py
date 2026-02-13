import subprocess
import json
import os
import sys
import re
import time
import random
import glob
# 改用zhconv替代pyzh，更稳定可靠
import zhconv

def cleanup_orphaned_temp_files():
    """清理可能遗留的临时文件"""
    try:
        # 查找所有临时文件
        temp_patterns = [
            "temp_traditional_*.srt",
            "temp_simplified_*.srt", 
            "temp_sample_*.srt",
            "*_temp_output.*"
        ]
        
        cleaned_count = 0
        for pattern in temp_patterns:
            for temp_file in glob.glob(pattern):
                try:
                    # 检查文件是否超过1小时（可能是遗留文件）
                    if os.path.getmtime(temp_file) < time.time() - 3600:
                        os.remove(temp_file)
                        cleaned_count += 1
                except Exception:
                    pass
        
        if cleaned_count > 0:
            print(f"- 清理了 {cleaned_count} 个遗留的临时文件")
            
    except Exception as e:
        print(f"清理临时文件时出错: {str(e)}")

def contains_traditional_chars(text):
    """检测文本中是否包含任何繁体字"""
    if not text or not text.strip():
        return False
    
    # 提取中文字符
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    if not chinese_chars:
        return False
    clean_text = ''.join(chinese_chars)
    
    # 将文本转换为简体
    simplified_text = zhconv.convert(clean_text, 'zh-cn')  # 使用zhconv的写法
    
    # 如果转换前后有差异，说明包含繁体字
    return clean_text != simplified_text

def extract_sample_subtitle_text(video_file, subtitle_index, sample_lines=300):
    """提取字幕的部分内容用于判断"""
    # 使用更唯一的临时文件名，避免并行处理时的冲突
    timestamp = int(time.time() * 1000)  # 毫秒时间戳
    random_id = random.randint(1000, 9999)
    temp_subtitle = f"temp_sample_{timestamp}_{random_id}_{subtitle_index}.srt"
    
    try:
        # 获取ffmpeg路径（兼容不同系统）
        ffmpeg_cmd = "ffmpeg.exe" if sys.platform.startswith('win') else "ffmpeg"
        
        # 提取字幕样本
        cmd = [
            ffmpeg_cmd,
            "-i", video_file,
            "-map", f"0:s:{subtitle_index}",
            "-c:s", "srt",
            "-f", "srt",
            "-y",  # 覆盖输出文件
            temp_subtitle
        ]
        
        # 执行命令，指定编码为utf-8解决Windows编码问题
        run_kwargs = {
            "capture_output": True,
            "timeout": 60,
            "text": True,
            "encoding": "utf-8"  # 明确指定编码
        }
        result = subprocess.run(cmd, **run_kwargs)
            
        if result.returncode != 0:
            return ""
        
        # 检查文件是否存在且不为空
        if not os.path.exists(temp_subtitle) or os.path.getsize(temp_subtitle) == 0:
            return ""
        
        # 读取样本内容
        with open(temp_subtitle, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        # 只取字幕文本部分（跳过时间戳和序号）
        subtitle_text = ""
        valid_line_count = 0
        
        for line in lines:
            stripped_line = line.strip()
            # 跳过空行、数字行和时间戳行
            if (stripped_line and 
                not stripped_line.isdigit() and 
                '-->' not in stripped_line and
                not re.match(r'^\d{2}:\d{2}:\d{2},\d{3}', stripped_line) and
                not re.match(r'^\d{1,2}:\d{2}:\d{2}.\d{2}$', stripped_line)):
                subtitle_text += stripped_line + "\n"
                valid_line_count += 1
                if valid_line_count >= sample_lines:
                    break
        
        return subtitle_text
        
    except Exception as e:
        print(f"提取字幕样本出错: {str(e)}")
        return ""
    finally:
        # 清理临时文件
        if os.path.exists(temp_subtitle):
            try:
                os.remove(temp_subtitle)
            except Exception:
                pass

def is_traditional_subtitle(video_file, subtitle_index):
    """判断指定字幕流是否包含繁体字"""
    try:
        sample_text = extract_sample_subtitle_text(video_file, subtitle_index, sample_lines=200)
        if not sample_text or len(sample_text.strip()) < 30:  # 文本太短无法准确判断
            return False
            
        return contains_traditional_chars(sample_text)
    except Exception as e:
        print(f"判断字幕类型出错: {str(e)}")
        return False

def has_simplified_subtitle(video_file, subtitle_index):
    """判断指定字幕流是否为简体字幕（不包含任何繁体字）"""
    try:
        sample_text = extract_sample_subtitle_text(video_file, subtitle_index, sample_lines=200)
        if not sample_text or len(sample_text.strip()) < 30:
            return False
            
        return not contains_traditional_chars(sample_text)
    except Exception:
        return False

def analyze_subtitle_streams(video_file):
    """分析视频文件中的字幕流"""
    try:
        # 获取ffprobe路径
        ffprobe_cmd = "ffprobe.exe" if sys.platform.startswith('win') else "ffprobe"
        
        # 获取所有流信息
        cmd = [
            ffprobe_cmd, 
            "-v", "quiet", 
            "-print_format", "json", 
            "-show_streams", 
            video_file
        ]
        
        # 执行命令，指定编码为utf-8
        result = subprocess.run(cmd, capture_output=True, timeout=30, text=True, encoding="utf-8")
            
        if result.returncode != 0:
            raise subprocess.SubprocessError(f"ffprobe执行失败: {result.stderr}")
        
        output = result.stdout if hasattr(result, 'stdout') else ""
        if not output or not output.strip():
            raise ValueError("ffprobe未返回有效数据")
        
        try:
            streams_info = json.loads(output)
        except json.JSONDecodeError:
            # 尝试清理输出后再解析
            cleaned_output = output.strip()
            if cleaned_output.startswith('\ufeff'):  # BOM标记
                cleaned_output = cleaned_output[1:]
            streams_info = json.loads(cleaned_output)
        
        # 查找字幕流
        subtitle_streams = []
        for stream in streams_info.get("streams", []):
            if stream.get("codec_type") == "subtitle":
                subtitle_streams.append(stream)
        
        if not subtitle_streams:
            return [], False, []
        
        # 分析每个字幕流
        has_simplified = False
        traditional_indices = []
        
        for i, stream in enumerate(subtitle_streams):
            try:
                # 首先检查语言标记
                language = stream.get("tags", {}).get("language", "").lower()
                if language in ["zh", "zho", "chi", "chs"]:
                    # 标记为简体，但仍需验证
                    if has_simplified_subtitle(video_file, i):
                        has_simplified = True
                        continue
                elif language in ["cht", "zh-tw", "zh-hk"]:
                    traditional_indices.append(i)
                    continue
                
                # 检查是否为繁体字幕（包含任何繁体字）
                if is_traditional_subtitle(video_file, i):
                    traditional_indices.append(i)
                else:
                    # 检查是否为简体字幕
                    if has_simplified_subtitle(video_file, i):
                        has_simplified = True
                            
            except Exception as e:
                print(f"分析字幕流 {i} 时出错: {str(e)}")
                continue  # 继续分析其他流
        
        return subtitle_streams, has_simplified, traditional_indices
        
    except Exception as e:
        print(f"分析字幕流时出错: {str(e)}")
        return [], False, []

def convert_traditional_to_simplified(input_file, output_file):
    """将繁体字幕转换为简体字幕，使用zhconv库"""
    try:
        # 检查输入文件
        if not os.path.exists(input_file):
            print(f"输入文件不存在: {input_file}")
            return False
            
        if os.path.getsize(input_file) == 0:
            print("输入文件为空")
            return False
        
        with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if not content.strip():
            print("输入文件内容为空")
            return False
            
        # 使用zhconv进行繁体转简体
        simplified_content = zhconv.convert(content, 'zh-cn')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(simplified_content)
            
        return True
    except Exception as e:
        print(f"转换失败: {str(e)}")
        return False

def process_single_video(video_file, replace_original=False, output_suffix="_simplified", backup_original=True):
    """处理单个视频文件
    
    Args:
        video_file: 视频文件路径
        replace_original: 是否替换原文件
        output_suffix: 输出文件后缀
        backup_original: 是否备份原文件
    """
    # 检查文件是否存在
    if not os.path.exists(video_file):
        print(f"文件不存在: {video_file}")
        return False
    
    # 检查是否为文件
    if not os.path.isfile(video_file):
        print(f"不是有效文件: {video_file}")
        return False
    
    print(f"正在处理: {os.path.basename(video_file)}")
    
    # 清理可能遗留的临时文件
    cleanup_orphaned_temp_files()
    
    # 临时文件名（使用时间戳和随机数避免冲突）
    timestamp = int(time.time() * 1000)  # 毫秒时间戳
    random_id = random.randint(1000, 9999)
    temp_traditional_subtitle = f"temp_traditional_{timestamp}_{random_id}.srt"
    temp_simplified_subtitle = f"temp_simplified_{timestamp}_{random_id}.srt"
    
    try:
        # 分析字幕流
        subtitle_streams, has_simplified, traditional_indices = analyze_subtitle_streams(video_file)
        
        if not subtitle_streams:
            print("- 未找到字幕流，无需处理")
            return False
        
        print(f"- 发现 {len(subtitle_streams)} 个字幕流")
        
        # 如果已有简体字幕，跳过处理
        if has_simplified:
            print("- 已包含简体中文字幕，跳过处理")
            return False
        
        # 如果没有繁体字幕，也跳过处理
        if not traditional_indices:
            print("- 未发现包含繁体字的字幕流，跳过处理")
            return False
        
        print(f"- 发现 {len(traditional_indices)} 个包含繁体字的字幕流")
        
        # 选择第一个繁体字幕流进行处理
        traditional_index = traditional_indices[0]
        print(f"- 选择字幕流 {traditional_index} 进行转换")
        
        # 获取ffmpeg路径
        ffmpeg_cmd = "ffmpeg.exe" if sys.platform.startswith('win') else "ffmpeg"
        
        # 提取繁体字幕
        cmd = [
            ffmpeg_cmd,
            "-i", video_file,
            "-map", f"0:s:{traditional_index}",
            "-y",  # 覆盖输出
            temp_traditional_subtitle
        ]
        
        # 执行命令，指定编码为utf-8
        result = subprocess.run(cmd, capture_output=True, timeout=120, text=True, encoding="utf-8")
            
        if result.returncode != 0:
            print(f"- 提取字幕失败: {result.stderr}")
            print(f"- 命令: {' '.join(cmd)}")
            return False
            
        if not os.path.exists(temp_traditional_subtitle) or os.path.getsize(temp_traditional_subtitle) == 0:
            print("- 提取的字幕文件为空或不存在")
            return False
        
        print("- 繁体字幕提取完成")
        
        # 转换为简体
        if not convert_traditional_to_simplified(temp_traditional_subtitle, temp_simplified_subtitle):
            print("- 字幕转换失败")
            return False
        
        # 验证转换后的文件是否存在且不为空
        if not os.path.exists(temp_simplified_subtitle) or os.path.getsize(temp_simplified_subtitle) == 0:
            print("- 转换后的字幕文件为空或不存在")
            return False
        
        print("- 简体字幕转换完成")
        
        # 创建新的视频文件名
        base_name = os.path.splitext(video_file)[0]
        file_ext = os.path.splitext(video_file)[1]
        
        if replace_original:
            # 如果要替换原文件，先备份原文件
            if backup_original:
                backup_file = f"{base_name}_backup{file_ext}"
                if not os.path.exists(backup_file):
                    try:
                        import shutil
                        shutil.copy2(video_file, backup_file)
                        print(f"- 已备份原文件: {os.path.basename(backup_file)}")
                    except Exception as e:
                        print(f"- 备份原文件失败: {str(e)}")
                        return False
                else:
                    print(f"- 备份文件已存在: {os.path.basename(backup_file)}")
            
            # 使用临时文件名，避免FFmpeg无法覆盖原文件的问题
            temp_output_file = f"{base_name}_temp_output{file_ext}"
            new_video_file = video_file  # 最终目标文件名
        else:
            # 创建带后缀的新文件名
            new_video_file = f"{base_name}{output_suffix}{file_ext}"
            temp_output_file = new_video_file
        
        # 检查输出文件是否已存在
        if os.path.exists(new_video_file) and not replace_original:
            print(f"- 输出文件已存在，跳过: {os.path.basename(new_video_file)}")
            return False
        
        # 获取视频和音频流信息，用于保留这些流
        video_audio_maps = []
        try:
            ffprobe_cmd = "ffprobe.exe" if sys.platform.startswith('win') else "ffprobe"
            cmd = [
                ffprobe_cmd, 
                "-v", "quiet", 
                "-print_format", "json", 
                "-show_streams", 
                video_file
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30, text=True, encoding="utf-8")
            streams_info = json.loads(result.stdout)
            
            for i, stream in enumerate(streams_info.get("streams", [])):
                if stream.get("codec_type") in ["video", "audio"]:
                    video_audio_maps.extend(["-map", f"0:{i}"])
        except Exception as e:
            print(f"- 获取音视频流信息出错: {str(e)}")
            return False
        
        # 添加新的简体中文字幕
        video_audio_maps.extend(["-map", "1:s"])
        
        # 重新封装视频 - 删除所有原有字幕流，只保留音视频流和新的简体字幕
        cmd = [
            ffmpeg_cmd,
            "-i", video_file,
            "-i", temp_simplified_subtitle
        ] + video_audio_maps + [
            "-c", "copy",   # 复制所有流，不重新编码
            "-metadata:s:s:0", "language=chi",  # 设置字幕语言为中文
            "-y",  # 覆盖输出
            temp_output_file
        ]
        
        print("- 正在封装视频（删除原有字幕，添加简体字幕）...")
        # 执行命令，指定编码为utf-8
        result = subprocess.run(cmd, capture_output=True, timeout=300, text=True, encoding="utf-8")
            
        if result.returncode != 0:
            print(f"- 视频封装失败: {result.stderr}")
            print(f"- 命令: {' '.join(cmd)}")
            return False
        
        # 如果需要替换原文件，先删除原文件，然后重命名临时文件
        if replace_original:
            try:
                import shutil
                # 删除原文件
                os.remove(video_file)
                # 将临时文件重命名为原文件名
                shutil.move(temp_output_file, new_video_file)
                print(f"- 完成: 已替换原文件 {os.path.basename(new_video_file)}")
            except Exception as e:
                print(f"- 替换原文件失败: {str(e)}")
                # 清理临时文件
                if os.path.exists(temp_output_file):
                    try:
                        os.remove(temp_output_file)
                    except:
                        pass
                return False
        else:
            print(f"- 完成: {os.path.basename(new_video_file)}")
        return True
        
    except Exception as e:
        print(f"- 处理文件时发生错误: {str(e)}")
        return False
    finally:
        # 确保清理临时文件
        temp_files_to_clean = [temp_traditional_subtitle, temp_simplified_subtitle]
        if replace_original and 'temp_output_file' in locals():
            temp_files_to_clean.append(temp_output_file)
        
        for temp_file in temp_files_to_clean:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f"清理临时文件失败 {temp_file}: {str(e)}")

def batch_process_videos(folder_path):
    """批量处理文件夹中的MKV文件"""
    # 检查文件夹是否存在
    if not os.path.exists(folder_path):
        print(f"错误: 文件夹不存在: {folder_path}")
        return
    
    if not os.path.isdir(folder_path):
        print(f"错误: 路径不是文件夹: {folder_path}")
        return
    
    # 获取所有MKV文件
    mkv_files = []
    for file in os.listdir(folder_path):
        if file.lower().endswith('.mkv'):
            mkv_files.append(os.path.join(folder_path, file))
    
    if not mkv_files:
        print(f"在文件夹 {folder_path} 中未找到MKV文件")
        return
    
    print(f"找到 {len(mkv_files)} 个MKV文件")
    
    # 检查ffmpeg和ffprobe是否存在
    try:
        ffmpeg_cmd = "ffmpeg.exe" if sys.platform.startswith('win') else "ffmpeg"
        ffprobe_cmd = "ffprobe.exe" if sys.platform.startswith('win') else "ffprobe"
        
        subprocess.run([ffmpeg_cmd, "-version"], check=True, capture_output=True, timeout=10, encoding="utf-8")
        subprocess.run([ffprobe_cmd, "-version"], check=True, capture_output=True, timeout=10, encoding="utf-8")
    except Exception as e:
        print(f"错误: 未找到 ffmpeg 或 ffprobe，请确保它们已安装并添加到系统PATH中: {str(e)}")
        return
    
    # 处理每个文件
    processed_count = 0
    error_count = 0
    
    for i, mkv_file in enumerate(mkv_files, 1):
        print(f"\n[{i}/{len(mkv_files)}] ", end="")
        try:
            if process_single_video(mkv_file):
                processed_count += 1
        except KeyboardInterrupt:
            print("\n用户中断操作")
            break
        except Exception as e:
            print(f"处理文件时出错 ({mkv_file}): {str(e)}")
            error_count += 1
    
    print(f"\n批量处理完成:")
    print(f"- 成功处理: {processed_count} 个文件")
    if error_count > 0:
        print(f"- 处理失败: {error_count} 个文件")

def main():
    if len(sys.argv) != 2:
        script_name = os.path.basename(__file__)
        print(f"使用方法: python {script_name} <文件夹路径>")
        print(f"例如: python {script_name} /path/to/videos")
        print(f"例如: python {script_name} C:\\Videos")
        return
    
    folder_path = sys.argv[1]
    batch_process_videos(folder_path)

if __name__ == "__main__":
    main()
    
