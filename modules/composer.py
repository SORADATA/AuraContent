import os
import random
import ffmpeg

class Composer:
    def __init__(self):
        self.temp_dir = os.path.join(os.getcwd(), "assets", "temp")
        self.final_dir = os.path.join(os.getcwd(), "assets", "final")
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        
        # 🎨 RESTRICTED TRANSITION LIST
        # Only 'fade', 'diagbr' (Diagonal Bottom-Right), 'diagtl' (Diagonal Top-Left)
        self.transitions = ['fade', 'diagbr', 'diagtl']

    def get_duration(self, filepath):
        """
        Helper to get exact duration of a video file using ffprobe.
        """
        try:
            probe = ffmpeg.probe(filepath)
            return float(probe['format']['duration'])
        except Exception as e:
            print(f"❌ Error probing duration for {filepath}: {e}")
            return 0.0

    def process_scene(self, scene, stock_video_path):
        """
        Prepares a single scene. Standardizes Framerate and Resolution.
        """
        scene_id = scene['id']
        audio_path = scene['audio_path']
        duration = scene['duration']
        
        output_path = os.path.join(self.temp_dir, f"scene_{scene_id}.mp4")
        print(f"   ⚙️ Processing Scene {scene_id}...")

        try:
            input_stock = ffmpeg.input(stock_video_path) 
            input_audio = ffmpeg.input(audio_path)

            # 1. Trim video (Add 0.5s buffer for the transition overlap!)
            video_track = input_stock.trim(duration=duration + 0.5).setpts('PTS-STARTPTS')
            
            # 2. Standardization filters (Required for xfade)
            video_track = (
                video_track
                .filter('scale', 1080, 1920)
                .filter('crop', 1080, 1920)
                .filter('fps', fps=30, round='up') # Force 30fps
            )

            runner = ffmpeg.output(
                video_track, 
                input_audio, 
                output_path, 
                vcodec='libx264', 
                acodec='aac', 
                pix_fmt='yuv420p' 
            )
            
            runner.run(overwrite_output=True, quiet=True)
            return output_path

        except ffmpeg.Error as e:
            print(f"❌ FFmpeg Error Scene {scene_id}: {e.stderr.decode('utf8')}")
            return None

    def concatenate_with_transitions(self, video_paths, output_filename="final_short.mp4"):
        """
        Chains videos together with restricted Xfade transitions.
        """
        print("🎬 Stitching with custom transitions (fade, diagbr, diagtl)...")
        output_path = os.path.join(self.final_dir, output_filename)
        
        if not video_paths:
            return None
        
        # Initialize chain
        input1 = ffmpeg.input(video_paths[0])
        v_stream = input1.video
        a_stream = input1.audio
        
        current_duration = self.get_duration(video_paths[0])
        
        for i in range(1, len(video_paths)):
            next_path = video_paths[i]
            input_next = ffmpeg.input(next_path)
            
            next_duration = self.get_duration(next_path)
            transition_duration = 0.5 
            offset = current_duration - transition_duration
            
            # Pick from our restricted list
            effect = random.choice(self.transitions)
            print(f"   ✨ Transition {i}: '{effect}' at {offset:.2f}s")

            # Apply XFADE (Video)
            v_stream = ffmpeg.filter(
                [v_stream, input_next.video], 
                'xfade', 
                transition=effect, 
                duration=transition_duration, 
                offset=offset
            )
            
            # Apply ACROSSFADE (Audio)
            a_stream = ffmpeg.filter(
                [a_stream, input_next.audio], 
                'acrossfade', 
                d=transition_duration
            )
            
            current_duration = (current_duration + next_duration) - transition_duration

        try:
            runner = ffmpeg.output(
                v_stream, 
                a_stream, 
                output_path, 
                vcodec='libx264', 
                acodec='aac', 
                pix_fmt='yuv420p'
            )
            runner.run(overwrite_output=True, quiet=True)
            print(f"✅ FINAL VIDEO SAVED: {output_path}")
            return output_path
            
        except ffmpeg.Error as e:
            print(f"❌ Transition Error: {e.stderr.decode('utf8')}")
            return None