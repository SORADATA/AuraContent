import os
import requests
import random


class AssetManager:
    def __init__(self):
        self.api_key = "hZBjjYowDAauyvn9rioK5qYMHFdCq11rKnmWo4OQlXhZspsVuo2DkpCP"
        self.base_url = "https://api.pexels.com/videos/search"
        self.headers = {
            "Authorization": self.api_key
        }
        
        # Ensure download directory exists
        self.assets_dir = os.path.join(os.getcwd(), "assets", "video_clips")
        os.makedirs(self.assets_dir, exist_ok=True)

    def search_video(self, query, duration_min=5):
        """
        Searches Pexels for a portrait video matching the query.
        Returns the download URL or None.
        """
        print(f"🔍 Searching Pexels for: '{query}'...")
        
        params = {
            "query": query,
            "per_page": 5,        # Fetch top 5 results to pick from
            "orientation": "portrait",
            "size": "medium"      # 'medium' is usually HD ready, saves bandwidth
        }
        
        try:
            response = requests.get(self.base_url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('videos'):
                # Retry strategy: Simplify query if complex query fails
                # e.g., "fast red ferrari" -> "ferrari" -> "car"
                if " " in query:
                    simple_query = query.split()[-1]
                    print(f"⚠️ No results for '{query}'. Retrying with '{simple_query}'...")
                    return self.search_video(simple_query)
                return None
            
            # Filter logic: Prefer videos that aren't too short
            valid_videos = [v for v in data['videos'] if v['duration'] >= duration_min]
            
            if not valid_videos:
                # If all are too short, just take the longest one available
                valid_videos = data['videos']
                
            # Randomize selection so the channel doesn't feel robotic if you reuse topics
            selected_video = random.choice(valid_videos)
            
            # Get the best quality video file link (usually the first file in video_files list is best)
            # We explicitly look for a file that is approx 720p or 1080p
            video_files = selected_video['video_files']
            
            # Sort by resolution (width * height) descending to get best quality
            video_files.sort(key=lambda x: x['width'] * x['height'], reverse=True)
            
            download_link = video_files[0]['link']
            return download_link

        except Exception as e:
            print(f"❌ Error searching Pexels: {e}")
            return None

    def download_video(self, url, filename):
        """
        Downloads the video content to a local file.
        """
        save_path = os.path.join(self.assets_dir, filename)
        
        # Don't re-download if we already have it (Caching strategy)
        if os.path.exists(save_path):
            print(f"⚡ Cached found: {filename}")
            return save_path

        try:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            print(f"✅ Downloaded: {filename}")
            return save_path
        except Exception as e:
            print(f"❌ Error downloading: {e}")
            return None

    def get_stock_for_script(self, script_data):
        """
        Iterates through the script JSON and downloads assets for each scene.
        """
        assets_map = {}
        
        for scene in script_data:
            scene_id = scene['id']
            keywords = scene['keywords']
            
            video_url = self.search_video(keywords)
            
            if video_url:
                filename = f"scene_{scene_id}.mp4"
                local_path = self.download_video(video_url, filename)
                assets_map[scene_id] = local_path
            else:
                print(f"⚠️ Could not find video for scene {scene_id}")
                assets_map[scene_id] = None
                
        return assets_map

# --- TESTING THE MODULE ---
if __name__ == "__main__":
    # Test with dummy data
    manager = AssetManager()
    
    test_script = [
        {"id": 1, "keywords": "cyberpunk city neon rain"},
        {"id": 2, "keywords": "hacker typing computer"}
    ]
    
    results = manager.get_stock_for_script(test_script)
    print("🎥 Assets Downloaded:", results)