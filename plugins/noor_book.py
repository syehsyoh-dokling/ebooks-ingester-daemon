import os
import time
import json
from urllib.parse import urlparse
from plugins.base_plugin import BasePlugin

try:
    import cloudscraper
    from bs4 import BeautifulSoup
except ImportError:
    pass # Will be handled in initialize or handled by system

class Plugin(BasePlugin):
    @property
    def name(self) -> str:
        return "noor_book"

    def initialize(self, out_dir: str) -> None:
        self.out_dir = os.path.join(out_dir, "noor_book")
        self.state_file = os.path.join(self.out_dir, "state.json")
        os.makedirs(self.out_dir, exist_ok=True)
        print(f"[{self.name}] Inisialisasi plugin. Folder output: {self.out_dir}")
        
        # Load state
        self.state = {"processed_urls": []}
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
            except:
                pass
                
        # Initialize Scraper
        try:
            import cloudscraper
            self.scraper = cloudscraper.create_scraper(browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            })
        except ImportError:
            print(f"[{self.name}] ERROR: Modul cloudscraper atau beautifulsoup4 belum diinstal. Plugin tidak bisa berjalan.")
            self.scraper = None

    def save_state(self):
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2)

    def extract_download_url(self, book_url):
        from bs4 import BeautifulSoup
        try:
            res = self.scraper.get(book_url)
            if res.status_code != 200:
                return None
            
            soup = BeautifulSoup(res.text, 'html.parser')
            download_page_url = None
            for a in soup.find_all('a', href=True):
                if '/book/download/' in a['href']:
                    download_page_url = a['href']
                    break
                    
            if not download_page_url:
                return None
                
            if not download_page_url.startswith('http'):
                parsed_uri = urlparse(book_url)
                base_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}"
                download_page_url = base_url + download_page_url
                
            res2 = self.scraper.get(download_page_url)
            if "application/pdf" in res2.headers.get('Content-Type', '').lower():
                return download_page_url
                
            soup2 = BeautifulSoup(res2.text, 'html.parser')
            for a in soup2.find_all('a', href=True):
                if '.pdf' in a['href'].lower() or 'download' in a['href'].lower():
                    if a['href'] != download_page_url and 'http' in a['href']:
                        return a['href']
                        
            return download_page_url
            
        except Exception as e:
            return None

    def get_target_links(self):
        # Look for the source txt file in the old Import Tools folder
        import_tools_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Import Tools"))
        noor_folder = os.path.join(import_tools_dir, "noor_output")
        links = []
        if os.path.exists(noor_folder):
            files = [f for f in os.listdir(noor_folder) if f.endswith('.txt')]
            if files:
                target = 'ebook_links_final_clean.txt' if 'ebook_links_final_clean.txt' in files else files[0]
                filepath = os.path.join(noor_folder, target)
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip().startswith('http'):
                            links.append(line.strip())
        return list(set(links))

    def run_batch(self, batch_size: int) -> list[dict]:
        results = []
        if not self.scraper:
            print(f"[{self.name}] Scraper tidak siap. Pastikan cloudscraper terinstal.")
            return results

        links = self.get_target_links()
        if not links:
            print(f"[{self.name}] Tidak ada URL sumber ditemukan di Import Tools/noor_output/.")
            return results

        processed_count = 0
        for book_url in links:
            if processed_count >= batch_size:
                break
                
            if book_url in self.state.get("processed_urls", []):
                continue
                
            print(f"[{self.name}] Memproses: {book_url}")
            filename = book_url.rstrip('/').split('/')[-1]
            if not filename.endswith('.pdf'):
                filename += '.pdf'
                
            book_dir = os.path.join(self.out_dir, filename.replace('.pdf', ''))
            os.makedirs(book_dir, exist_ok=True)
            pdf_path = os.path.join(book_dir, filename)

            download_url = self.extract_download_url(book_url)
            
            success = False
            if download_url:
                try:
                    response = self.scraper.get(download_url, stream=True)
                    content_type = response.headers.get('Content-Type', '')
                    if 'text/html' not in content_type:
                        with open(pdf_path, 'wb') as file:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    file.write(chunk)
                        success = True
                except Exception as e:
                    print(f"[{self.name}] Gagal unduh file: {e}")
            
            if success and os.path.exists(pdf_path):
                results.append({
                    "status": "done",
                    "title": filename.replace('.pdf', ''),
                    "source_url": book_url,
                    "pdf_path": pdf_path
                })
                print(f"[{self.name}] ✅ Sukses mengunduh: {filename}")
            else:
                results.append({
                    "status": "error",
                    "title": filename.replace('.pdf', ''),
                    "source_url": book_url
                })
                print(f"[{self.name}] ❌ Gagal memproses: {filename}")

            self.state["processed_urls"].append(book_url)
            self.save_state()
            processed_count += 1
            
            # Beri jeda sesuai skrip asli
            time.sleep(3)

        return results
