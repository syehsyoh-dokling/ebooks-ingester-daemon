import os
from plugins.base_plugin import BasePlugin

class Plugin(BasePlugin):
    @property
    def name(self) -> str:
        return "standard_ebooks"

    def initialize(self, out_dir: str) -> None:
        self.out_dir = os.path.join(out_dir, "standard_ebooks")
        os.makedirs(self.out_dir, exist_ok=True)
        print(f"[{self.name}] Inisialisasi plugin. Folder output: {self.out_dir}")

    def run_batch(self, batch_size: int) -> list[dict]:
        print(f"[{self.name}] Mencari {batch_size} buku terbaru di Standard Ebooks...")
        
        # Di sini kita letakkan logika asli memanggil `standard_ebooks_downloader.py`
        # Untuk demo arsitektur, kita gunakan mock data
        dummy_book_path = os.path.join(self.out_dir, "wuthering_heights.pdf")
        
        # Membuat file PDF bohongan (dummy) untuk testing
        if not os.path.exists(dummy_book_path):
            with open(dummy_book_path, "w") as f:
                f.write("DUMMY PDF CONTENT DARI STANDARD EBOOKS")

        results = []
        results.append({
            "status": "done",
            "title": "Wuthering Heights",
            "source_url": "https://standardebooks.org/ebooks/emily-bronte/wuthering-heights",
            "pdf_path": dummy_book_path
        })

        return results
