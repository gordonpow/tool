from PyQt6.QtCore import QThread, pyqtSignal
from core.converter import Converter
import os
import concurrent.futures

class ConversionWorker(QThread):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)
    item_status_signal = pyqtSignal(str, str) # file_path, status
    
    def __init__(self, video_paths, settings):
        super().__init__()
        # Ensure it's a list
        if isinstance(video_paths, str):
            self.video_paths = [video_paths]
        else:
            self.video_paths = video_paths
        self.settings = settings
        self._is_running = True
        
    def stop(self):
        self._is_running = False
        
    def run(self):
        results = []
        total_files = len(self.video_paths)
        
        # Determine max workers: Use full CPU core count as requested
        max_workers = os.cpu_count() or 1
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Create a dict mapping future to index (for potential order tracking if needed, 
            # though we just strictly count completed tasks for progress here)
            future_to_file = {
                executor.submit(self.process_single_file, vid_path): vid_path 
                for vid_path in self.video_paths
            }
            
            completed_count = 0
            for future in concurrent.futures.as_completed(future_to_file):
                if not self._is_running:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                    
                try:
                    success, message = future.result()
                    results.append((success, message))
                except Exception as e:
                    results.append((False, str(e)))
                
                completed_count += 1
                progress_pct = int((completed_count / total_files) * 100)
                self.progress_signal.emit(progress_pct)
        
        # Report final status
        all_success = all(r[0] for r in results)
        if all_success:
            self.finished_signal.emit(True, f"Processed {len(results)} files.")
        else:
            # Just report first error
            first_fail = next((r for r in results if not r[0]), (False, "Unknown Error"))
            self.finished_signal.emit(False, first_fail[1])

    def process_single_file(self, vid_path):
        # Notify start
        self.item_status_signal.emit(vid_path, "⏳ Converting...")
        
        # Determine output path
        custom_dir = self.settings.get('output_dir')
        base_name = os.path.splitext(os.path.basename(vid_path))[0]
        
        if custom_dir and os.path.exists(custom_dir):
            output_path = os.path.join(custom_dir, f"{base_name}.gif")
        else:
             output_dir = os.path.dirname(vid_path)
             output_path = os.path.join(output_dir, f"{base_name}.gif")
        
        # Create a callback to update status granularly
        status_cb = lambda status: self.item_status_signal.emit(vid_path, status)
        
        success, msg = Converter.convert_to_gif(vid_path, output_path, self.settings, status_callback=status_cb)
        
        # Notify end
        if success:
            self.item_status_signal.emit(vid_path, "✅ Done")
        else:
            self.item_status_signal.emit(vid_path, "❌ Error")
            
        return success, msg
