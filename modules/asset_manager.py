import os
import requests
import random

class AssetManager:
    def __init__(self):
        # Your original API Key
        self.api_key = "hZBjjYowDAauyvn9rioK5qYMHFdCq11rKnmWo4OQlXhZspsVuo2DkpCP"
        self.base_url = "https://api.pexels.com/videos/search"
        self.headers = {
            "Authorization": self.api_key
        }
        
        # Ensure download directory exists
        self.assets_dir = os.path.join(os.getcwd(), "assets", "video_clips")
        os.makedirs(self.assets_dir, exist_ok=True)

    def search_video(self, query, duration_min=4):
        """
        Searches Pexels for a portrait video matching the query.
        Returns the download URL or None.
        """
        print(f"   🔍 Searching Pexels for: '{query}'...")
        
        params = {
            "query": query,
            "per_page": 5,        # Fetch top 5 results to pick from
            "orientation": "portrait",
            "size": "medium"      # 'medium' is usually HD ready, saves bandwidth
        }
        
        try:
            response = requests.get(self.base_url, headers=self.headers, params=params, timeout=10)
            if response.status_code != 200:
                print(f"      ⚠️ API Error: {response.status_code}")
                return None
                
            data = response.json()
            
            if not data.get('videos'):
                # Retry strategy: Simplify query if complex query fails
                if " " in query:
                    simple_query = query.split()[-1] # Try last word (usually the noun)
                    print(f"      ⚠️ No results. Retrying with '{simple_query}'...")
                    return self.search_video(simple_query)
                return None
            
            # Filter logic: Prefer videos that aren't too short (at least 4 seconds)
            valid_videos = [v for v in data['videos'] if v['duration'] >= duration_min]
            
            if not valid_videos:
                valid_videos = data['videos'] # Fallback to whatever exists
                
            # Randomize selection
            selected_video = random.choice(valid_videos)
            
            # Get best quality video file link
            video_files = selected_video['video_files']
            video_files.sort(key=lambda x: x['width'] * x['height'], reverse=True)
            
            download_link = video_files[0]['link']
            return download_link

        except Exception as e:
            print(f"      ❌ Error searching Pexels: {e}")
            return None

    def download_video(self, url, filename):
        """
        Downloads the video content to a local file.
        """
        save_path = os.path.join(self.assets_dir, filename)
        
        # Caching strategy
        if os.path.exists(save_path):
            return save_path

        try:
            with requests.get(url, stream=True, timeout=15) as r:
                r.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            return save_path
        except Exception as e:
            print(f"      ❌ Error downloading {filename}: {e}")
            return None

    def get_videos(self, script_data):
        """
        NEW LOGIC: Downloads TWO videos per scene (A and B).
        Returns a list of tuples: [(path_a, path_b), (path_a, path_b), ...]
        """
        print("🎥 Starting Double-Feature Video Download...")
        video_pairs = []

        for scene in script_data:
            scene_id = scene['id']
            
            # 1. Get Search Terms
            # Fallback to 'keywords' if visual_1/2 don't exist (compatibility mode)
            query_a = scene.get('visual_1', scene.get('keywords', 'abstract'))
            query_b = scene.get('visual_2', query_a) # Use A if B is missing
            
            # 2. Search & Download Clip A
            url_a = self.search_video(query_a)
            path_a = None
            if url_a:
                path_a = self.download_video(url_a, f"scene_{scene_id}_a.mp4")
            
            # 3. Search & Download Clip B
            url_b = self.search_video(query_b)
            path_b = None
            if url_b:
                path_b = self.download_video(url_b, f"scene_{scene_id}_b.mp4")
            
            # 4. Fallback Logic (Self-Healing)
            # If B fails, use A twice. If A fails, use B twice.
            if not path_a and path_b: 
                path_a = path_b
                print(f"      ⚠️ Scene {scene_id} Clip A missing. Using Clip B for both.")
            if not path_b and path_a: 
                path_b = path_a
                print(f"      ⚠️ Scene {scene_id} Clip B missing. Using Clip A for both.")

            # 5. Final Check
            if path_a and path_b:
                video_pairs.append((path_a, path_b))
                print(f"   ✅ Scene {scene_id} Ready (A + B).")
            else:
                print(f"   ❌ Scene {scene_id} Completely Failed (No videos found).")
                video_pairs.append(None)

        return video_pairs

# --- TESTING ---
if __name__ == "__main__":
    manager = AssetManager()
    
    # Test with new dual-visual format
    test_script = [
        {
            "id": 1, 
            "visual_1": "cyberpunk city neon", 
            "visual_2": "hacker typing computer"
        }
    ]
    
    results = manager.get_videos(test_script)
    print("🎥 Assets Downloaded:", results)