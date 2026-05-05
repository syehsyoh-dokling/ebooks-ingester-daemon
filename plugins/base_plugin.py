from abc import ABC, abstractmethod
from typing import Dict, Any

class BasePlugin(ABC):
    """
    Interface wajib untuk semua plugin situs penyedia Ebook.
    Semua plugin (Standard Ebooks, Gutenberg, dll) HARUS mewarisi kelas ini.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Mengembalikan nama plugin (misal: 'standard_ebooks')"""
        pass

    @abstractmethod
    def initialize(self, out_dir: str) -> None:
        """
        Dijalankan sekali saat daemon dimuat.
        Bisa dipakai untuk inisialisasi state, db, atau folder output lokal.
        """
        pass

    @abstractmethod
    def run_batch(self, batch_size: int) -> list[Dict[str, Any]]:
        """
        Jalankan ekstraksi sebanyak `batch_size`.
        Mengembalikan daftar dictionary hasil ekstraksi/download (path PDF, judul, url sumber, dsb).
        Setiap item harus memiliki struktur minimal:
        {
            "status": "done" | "error",
            "title": "Judul Buku",
            "source_url": "https://...",
            "pdf_path": "/absolute/path/to/book.pdf" (Hanya wajib jika status == "done")
        }
        """
        pass
