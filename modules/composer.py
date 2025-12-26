import os
import random
import ffmpeg

class Composer:
    def __init__(self):
        self.temp_dir = os.path.join(os.getcwd(), "assets", "temp")
        self.final_dir = os.path.join(os.getcwd(), "assets", "final")
        self.avatar_path = os.path.join(os.getcwd(), "assets", "avatar", "avatars.mp4")
        
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        self.transitions = ['fade', 'diagbr', 'diagtl']

    def get_duration(self, filepath):
        try:
            probe = ffmpeg.probe(filepath)
            return float(probe['format']['duration'])
        except:
            return 0.0

    def process_scene(self, scene, video_pair, is_avatar=False):
        """
        Combines Audio with Visuals.
        - If Avatar: Loop single video.
        - If Stock: Split duration 50/50 between Video A and Video B.
        """
        scene_id = scene['id']
        audio_path = scene['audio_path']
        total_duration = scene['duration']
        output_path = os.path.join(self.temp_dir, f"scene_{scene_id}.mp4")

        try:
            input_audio = ffmpeg.input(audio_path)

            if is_avatar:
                # --- AVATAR MODE (Single Loop) ---
                print(f"   ⚙️ Processing Scene {scene_id}: 🤖 Avatar Mode")
                video_stream = (
                    ffmpeg.input(video_pair[0], stream_loop=-1) # Avatar is passed as item 0
                    .trim(duration=total_duration + 0.5)
                    .setpts('PTS-STARTPTS')
                    .filter('scale', 1080, 1920).filter('crop', 1080, 1920)
                    .filter('fps', fps=30, round='up')
                )
            else:
                # --- DUAL VIDEO MODE (50/50 Split) ---
                print(f"   ⚙️ Processing Scene {scene_id}: 🎞️ A/B Split Mode")
                path_a, path_b = video_pair
                
                # Calculate Split (Half duration)
                # We add buffer to Part B for the transition to the NEXT scene
                duration_a = total_duration / 2
                duration_b = (total_duration / 2) + 0.5 

                # Prepare Stream A
                stream_a = (
                    ffmpeg.input(path_a, stream_loop=-1) # Loop in case stock is short
                    .trim(duration=duration_a)
                    .setpts('PTS-STARTPTS')
                    .filter('scale', 1080, 1920).filter('crop', 1080, 1920)
                    .filter('fps', fps=30, round='up')
                )

                # Prepare Stream B
                stream_b = (
                    ffmpeg.input(path_b, stream_loop=-1)
                    .trim(duration=duration_b)
                    .setpts('PTS-STARTPTS')
                    .filter('scale', 1080, 1920).filter('crop', 1080, 1920)
                    .filter('fps', fps=30, round='up')
                )

                # Concatenate A + B (Hard Cut)
                video_stream = ffmpeg.concat(stream_a, stream_b, v=1, a=0)

            # Combine Video + Audio
            runner = ffmpeg.output(
                video_stream, 
                input_audio, 
                output_path, 
                vcodec='libx264', 
                acodec='aac', 
                pix_fmt='yuv420p',
                shortest=None
            )
            
            runner.run(overwrite_output=True, quiet=True)
            return output_path

        except ffmpeg.Error as e:
            print(f"❌ Render Fail Scene {scene_id}: {e.stderr.decode('utf8') if e.stderr else str(e)}")
            return None

    def render_all_scenes(self, script_data, video_pairs):
        rendered_paths = []
        
        # Determine Avatar Scene (Middle)
        avatar_index = -1
        if len(script_data) >= 3 and os.path.exists(self.avatar_path):
            avatar_index = random.randint(1, len(script_data) - 2)
            print(f"🎲 Avatar set for Scene {avatar_index + 1}")

        for i, scene in enumerate(script_data):
            current_pair = video_pairs[i]
            is_avatar = False

            if i == avatar_index:
                # For avatar, we just pass the avatar path in a tuple
                current_pair = (self.avatar_path, None)
                is_avatar = True
            elif current_pair is None:
                continue # Skip failed downloads

            output_path = self.process_scene(scene, current_pair, is_avatar)
            if output_path:
                rendered_paths.append(output_path)
        
        return rendered_paths

    def concatenate_with_transitions(self, video_paths, output_filename="final_short.mp4"):
        """
        Stitches rendered scenes together.
        INCLUDES FIXES FOR: Windows 0x80004005 Error & Playback Issues.
        """
        print("🎬 Stitching final video...")
        output_path = os.path.join(self.final_dir, output_filename)
        
        # 1. Safety: Delete old file so FFmpeg doesn't get permission errors
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                print("⚠️ Warning: Could not delete old file. It might be open in a player.")

        if not video_paths:
            return None

        # 2. Initialize Chain
        input1 = ffmpeg.input(video_paths[0])
        v_stream = input1.video
        a_stream = input1.audio
        
        # We need to track duration manually to calculate the offset for XFade
        current_dur = self.get_duration(video_paths[0])

        for i in range(1, len(video_paths)):
            next_clip = ffmpeg.input(video_paths[i])
            next_dur = self.get_duration(video_paths[i])
            
            # Transition Settings
            trans_dur = 0.5
            offset = current_dur - trans_dur
            
            effect = random.choice(self.transitions)
            print(f"   ✨ Transition {i}: '{effect}' at {offset:.2f}s")

            # Apply Video Transition (Xfade)
            v_stream = ffmpeg.filter(
                [v_stream, next_clip.video], 
                'xfade', 
                transition=effect, 
                duration=trans_dur, 
                offset=offset
            )
            
            # Apply Audio Transition (Acrossfade)
            a_stream = ffmpeg.filter(
                [a_stream, next_clip.audio], 
                'acrossfade', 
                d=trans_dur
            )
            
            # Update duration for the next loop
            current_dur = (current_dur + next_dur) - trans_dur

        # 3. Output with Windows-Safe Flags
        try:
            runner = ffmpeg.output(
                v_stream, 
                a_stream, 
                output_path, 
                vcodec='libx264',   # Standard H.264 video
                acodec='aac',       # Standard AAC audio
                
                # 🔥 FIX 1: Force standard pixel format (Windows needs this)
                pix_fmt='yuv420p',  
                
                # 🔥 FIX 2: Move metadata to front (Fixes "Corrupt File" / 0x80004005)
                movflags='faststart',
                
                # Optional: Ensure high quality
                preset='medium' 
            )
            
            # Run! (quiet=False allows you to see if it crashes)
            runner.run(overwrite_output=True, quiet=False)
            
            print(f"✅ FINAL VIDEO SAVED: {output_path}")
            return output_path

        except ffmpeg.Error as e:
            # Print the real error message from FFmpeg
            error_log = e.stderr.decode('utf8') if e.stderr else str(e)
            print(f"❌ Stitching Error: {error_log}")
            return None