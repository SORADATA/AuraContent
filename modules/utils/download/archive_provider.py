import os
import time
import requests
from modules.utils.download.utils_assets import is_used, mark_used, calculate_relevance, download_file


class ArchiveProvider:
    def __init__(self, history):
        contact = os.getenv("WIKIMEDIA_CONTACT", "https://github.com/tonuser")
        self.wiki_headers = {"User-Agent": f"AuraContent/2.0 ({contact}) requests/{requests.__version__}"}
        self.history = history

    def get_openverse(self, query, output_path, min_relevance=0.3):
        print(f"🌍 Recherche Openverse (Archives mondiales) : '{query}'...")
        url = "https://api.openverse.org/v1/images/"
        params = {"q": query, "license_type": "commercial,modification", "page_size": 10}
        
        try:
            # Timeout augmenté à 25 secondes pour éviter l'erreur "Read timed out"
            r = requests.get(url, params=params, timeout=25)
            if r.status_code == 200:
                candidates = []
                for item in r.json().get("results", []):
                    img_id = item.get("id")
                    if is_used(self.history, "openverse", img_id): 
                        continue
                    
                    tags = " ".join([t.get("name", "") for t in item.get("tags", [])])
                    score = calculate_relevance(query, f"{item.get('title', '')} {tags}")
                    
                    if item.get("url"):
                        candidates.append((score, img_id, item.get("url")))
                        
                candidates.sort(key=lambda x: x[0], reverse=True)
                if candidates and candidates[0][0] >= min_relevance:
                    if download_file(candidates[0][2], output_path, headers=self.wiki_headers):
                        mark_used(self.history, "openverse", candidates[0][1])
                        print(f"✅ Openverse OK (Score {candidates[0][0]:.2f})")
                        return True
        except Exception as e:
            print(f"❌ Openverse Erreur: {e}")
        return False

    def _wiki_api(self, params):
        url = "https://commons.wikimedia.org/w/api.php"
        for _ in range(2):
            try:
                # Timeout augmenté à 25 secondes ici aussi par précaution
                r = requests.get(url, params=params, headers=self.wiki_headers, timeout=25)
                if r.status_code == 200: 
                    return r
                if r.status_code == 429: 
                    time.sleep(int(r.headers.get("Retry-After", 5)))
            except:
                pass
        return None

    def _process_wiki_pages(self, pages, output_path, query, min_relevance):
        for page_id, info in pages.items():
            img_infos = info.get("imageinfo", [])
            if not img_infos: 
                continue
            
            img_url = img_infos[0].get("url", "")
            title = info.get("title", "")
            
            if not img_url or "pdf" in img_url.lower(): 
                continue
            if is_used(self.history, "wikimedia", page_id): 
                continue
            
            score = calculate_relevance(query, title)
            if score >= min_relevance:
                if download_file(img_url, output_path, headers=self.wiki_headers):
                    mark_used(self.history, "wikimedia", page_id)
                    print(f"✅ Wikimedia OK (Score {score:.2f})")
                    return True
        return False

    def get_wikimedia(self, query, output_path):
        # 1. Catégorie exacte (pas de filtre)
        cat = f"Catégorie:{query}" if not query.startswith("Category:") and not query.startswith("Catégorie:") else query
        r = self._wiki_api({"action": "query", "format": "json", "generator": "categorymembers", "gcmtitle": cat, "gcmtype": "file", "gcmlimit": "3", "prop": "imageinfo", "iiprop": "url"})
        if r and self._process_wiki_pages(r.json().get("query", {}).get("pages", {}), output_path, query, min_relevance=0.0):
            return True

        # 2. Openverse intercalaire (souvent plus propre que la recherche Wikimedia floue)
        if self.get_openverse(query, output_path): 
            return True
        time.sleep(0.5)

        # 3. Plein texte wikimedia
        print(f"🏛️ Recherche Wikimedia plein texte : '{query}'...")
        r = self._wiki_api({"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": "6", "gsrlimit": "5", "prop": "imageinfo", "iiprop": "url"})
        if r and self._process_wiki_pages(r.json().get("query", {}).get("pages", {}), output_path, query, min_relevance=0.3):
            return True

        return False