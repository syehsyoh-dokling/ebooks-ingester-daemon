import os
import sys
import time
import importlib.util
from pathlib import Path
from queue_client import send_to_queue

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Pastikan import plugins/base_plugin.py bisa dilakukan
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

PLUGINS_DIR = Path(__file__).parent.parent / "plugins"
OUT_DIR = Path(__file__).parent.parent / "hasil_buku"

def load_plugins() -> list:
    plugins = []
    if not PLUGINS_DIR.exists():
        return plugins

    for file in PLUGINS_DIR.glob("*.py"):
        if file.name == "base_plugin.py" or file.name == "__init__.py":
            continue
        
        module_name = file.stem
        spec = importlib.util.spec_from_file_location(module_name, file)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
                if hasattr(module, "Plugin"):
                    plugin_instance = module.Plugin()
                    plugins.append(plugin_instance)
                    print(f"[*] Berhasil memuat plugin: {plugin_instance.name}")
            except Exception as e:
                print(f"[!] Gagal memuat plugin {module_name}: {e}")
    return plugins

def run():
    print("========================================")
    print("[Ebooks-Ingester-Daemon] berjalan...")
    print("========================================")
    
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    plugins = load_plugins()
    if not plugins:
        print("[!] Tidak ada plugin yang ditemukan. Daemon berhenti.")
        return

    # Inisialisasi setiap plugin
    for p in plugins:
        p.initialize(str(OUT_DIR))

    batch_size = 5 # Uji coba: ambil 5 buku per batch
    
    while True:
        try:
            for p in plugins:
                print(f"\n[>] Menjalankan plugin '{p.name}' (Batch size: {batch_size})")
                results = p.run_batch(batch_size)
                
                for res in results:
                    if res.get("status") == "done" and res.get("pdf_path"):
                        # Tembak ke Universal Queue
                        success = send_to_queue(
                            title=res.get("title", "Unknown Title"),
                            source_url=res.get("source_url", ""),
                            pdf_path=res.get("pdf_path")
                        )
                        if success:
                            print(f"    -> [OK] Buku '{res.get('title')}' sukses dikirim ke antrean.")
                        else:
                            print(f"    -> [FAIL] Gagal mengirim buku '{res.get('title')}' ke antrean.")
            
            # Istirahat 1 jam (3600 detik) sebelum batch berikutnya
            print("\n[zzz] Batch selesai. Menunggu 1 jam untuk siklus berikutnya...")
            time.sleep(3600)
            
        except KeyboardInterrupt:
            print("\n[!] Daemon dihentikan oleh pengguna.")
            break
        except Exception as e:
            print(f"\n[!] Error pada loop utama daemon: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run()
