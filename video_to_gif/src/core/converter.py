import os
import subprocess
import uuid

class Converter:
    @staticmethod
    def get_video_info(file_path):
        try:
            with VideoFileClip(file_path) as clip:
                return {
                    "duration": clip.duration,
                    "fps": clip.fps,
                    "resolution": clip.size
                }
        except Exception as e:
            print(f"Error getting info: {e}")
            return None

    @staticmethod
    def convert_to_gif(video_path, output_path, settings, progress_callback=None, status_callback=None):
        temp_video = None
        try:
            if status_callback: status_callback("⏳ Preparing...")
            from moviepy import VideoFileClip
            clip = VideoFileClip(video_path)
            
            # 1. Trim
            start = settings.get('start_time', 0)
            end = settings.get('end_time', clip.duration)
            if start < 0: start = 0
            if end > clip.duration: end = clip.duration
            if start < end:
                clip = clip.subclipped(start, end)
            
            # 2. Speed
            speed = settings.get('speed', 1.0)
            if speed != 1.0:
                if hasattr(clip, 'multiplied_speed'):
                     clip = clip.multiplied_speed(speed)
                elif hasattr(clip, 'with_speed_scaled'):
                     clip = clip.with_speed_scaled(speed)
                else:
                     clip = clip.speedx(speed)
            
            # 3. Resize
            resize_val = settings.get('resize')
            if resize_val:
                 if status_callback: status_callback(f"📏 Resizing to {resize_val}px...")
                 if hasattr(clip, 'resized'):
                     clip = clip.resized(width=resize_val)
                 elif hasattr(clip, 'resize'):
                     clip = clip.resize(width=resize_val)
                 else:
                     print("Warning: Could not resize, method not found.")
            
            # 4. Write to Temp Video (Fast)
            if status_callback: status_callback("🎥 Rendering Temp Video...")
            temp_filename = f"temp_{uuid.uuid4().hex}.mp4"
            temp_video = os.path.join(os.path.dirname(output_path), temp_filename)
            
            # Use ultrafast preset for intermediate file
            clip.write_videofile(temp_video, codec='libx264', preset='ultrafast', logger=None, audio=False)
            clip.close()
            
            # 5. Convert Temp Video to GIF using FFmpeg
            if status_callback: status_callback("⚙️ Encoding GIF...")
            fps = settings.get('fps', 15)
            
            # Palettegen + Paletteuse for high quality
            # "fps={fps},split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
            filter_complex = f"fps={fps},split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
            
            cmd = [
                'ffmpeg', '-y',
                '-i', temp_video,
                '-vf', filter_complex,
                output_path
            ]
            
            # Run FFmpeg
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            return True, "Conversion Complete"
            
        except subprocess.CalledProcessError as e:
            return False, f"FFmpeg Error: {e}"
        except Exception as e:
            return False, str(e)
        finally:
            # Cleanup temp file
            if temp_video and os.path.exists(temp_video):
                try:
                    os.remove(temp_video)
                except:
                    pass
