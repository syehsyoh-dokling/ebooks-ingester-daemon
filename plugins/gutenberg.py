import os
import json
import urllib.request
import urllib.error
import re
import subprocess
from plugins.base_plugin import BasePlugin

class Plugin(BasePlugin):
    @property
    def name(self) -> str:
        return "project_gutenberg"

    def initialize(self, out_dir: str) -> None:
        self.out_dir = os.path.join(out_dir, "project_gutenberg")
        self.state_file = os.path.join(self.out_dir, "state.json")
        os.makedirs(self.out_dir, exist_ok=True)
        print(f"[{self.name}] Inisialisasi plugin. Folder output: {self.out_dir}")
        
        # Load state
        self.state = {"page": 1, "processed_books": []}
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
            except:
                pass

    def save_state(self):
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2)

    def fetch_html(self, url: str) -> str:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"[{self.name}] Gagal mengakses {url}: {e}")
            return ""

    def run_batch(self, batch_size: int) -> list[dict]:
        results = []
        page = self.state.get("page", 1)
        processed_count = 0

        while processed_count < batch_size:
            # Gutenberg search page by popularity
            url = f"https://www.gutenberg.org/ebooks/search/?sort_order=downloads&start_index={(page-1)*25 + 1}"
            print(f"[{self.name}] Membaca halaman {page} ({url})")
            
            html = self.fetch_html(url)
            if not html:
                break
                
            # Regex to find book links
            book_links = re.findall(r'href="/ebooks/(\d+)"', html)
            # Hilangkan duplikat dan pastikan unik sesuai urutan
            unique_ids = []
            for b in book_links:
                if b not in unique_ids:
                    unique_ids.append(b)
            
            if not unique_ids:
                print(f"[{self.name}] Tidak ada buku lagi di halaman {page}. Mengakhiri pencarian.")
                break

            for book_id in unique_ids:
                if processed_count >= batch_size:
                    break
                    
                if book_id in self.state.get("processed_books", []):
                    continue

                book_url = f"https://www.gutenberg.org/ebooks/{book_id}"
                print(f"[{self.name}] Memproses buku ID: {book_id}")
                
                book_html = self.fetch_html(book_url)
                
                # Ekstrak Judul
                title_match = re.search(r'<title>(.+?) - Project Gutenberg</title>', book_html, re.I)
                title = title_match.group(1).strip() if title_match else f"Gutenberg_Book_{book_id}"
                
                # Coba cari PDF asli terlebih dahulu (Gutenberg PDF First Logic)
                pdf_match = re.search(r'href="([^"]+\.pdf)"', book_html, re.I)
                epub_match = re.search(r'href="([^"]+\.epub3?\.images)"', book_html, re.I)
                if not epub_match:
                    epub_match = re.search(r'href="([^"]+\.epub3?\.noimages)"', book_html, re.I)

                book_dir = os.path.join(self.out_dir, book_id)
                os.makedirs(book_dir, exist_ok=True)
                pdf_path = os.path.join(book_dir, f"{book_id}.pdf")
                
                success = False

                if pdf_match:
                    pdf_url = "https://www.gutenberg.org" + pdf_match.group(1) if pdf_match.group(1).startswith("/") else pdf_match.group(1)
                    print(f"[{self.name}] PDF asli ditemukan! Mengunduh...")
                    try:
                        urllib.request.urlretrieve(pdf_url, pdf_path)
                        success = True
                    except Exception as e:
                        print(f"[{self.name}] Gagal unduh PDF: {e}")
                
                elif epub_match:
                    epub_url = "https://www.gutenberg.org" + epub_match.group(1) if epub_match.group(1).startswith("/") else epub_match.group(1)
                    epub_path = os.path.join(book_dir, f"{book_id}.epub")
                    print(f"[{self.name}] EPUB ditemukan. Mengunduh dan mengonversi ke PDF...")
                    try:
                        urllib.request.urlretrieve(epub_url, epub_path)
                        # Konversi menggunakan ebook-convert (Calibre)
                        subprocess.run(["ebook-convert", epub_path, pdf_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        success = True
                    except Exception as e:
                        print(f"[{self.name}] Gagal unduh/konversi EPUB: {e}")

                if success and os.path.exists(pdf_path):
                    results.append({
                        "status": "done",
                        "title": title,
                        "source_url": book_url,
                        "pdf_path": pdf_path
                    })
                    print(f"[{self.name}] ✅ Sukses: {title}")
                else:
                    results.append({
                        "status": "error",
                        "title": title,
                        "source_url": book_url
                    })
                    print(f"[{self.name}] ❌ Gagal memproses: {title}")

                self.state["processed_books"].append(book_id)
                self.save_state()
                processed_count += 1

            page += 1
            self.state["page"] = page
            self.save_state()

        return results
