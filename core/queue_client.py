import json
import urllib.request
import urllib.error

# Konfigurasi Queue (Universal Queue Service kita berjalan di Node.js, misal port 3003)
QUEUE_API_URL = "http://localhost:3003/api/queue/add"

def send_to_queue(title: str, source_url: str, pdf_path: str) -> bool:
    """
    Mengirimkan payload buku ke Universal Queue Service agar dimasukkan
    ke dalam antrean AI-Book Translation Service.
    """
    payload = {
        "taskType": "translate_book",
        "data": {
            "title": title,
            "source_url": source_url,
            "pdf_path": pdf_path,
            "target_language": "id" # Default ke bahasa Indonesia
        }
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(QUEUE_API_URL, data=data, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = response.read()
            if response.status in (200, 201):
                print(f"[QueueClient] Berhasil mengirim '{title}' ke antrean!")
                return True
            else:
                print(f"[QueueClient] Gagal mengirim antrean. HTTP {response.status}: {res_data}")
                return False
    except urllib.error.URLError as e:
        print(f"[QueueClient] Error menghubungi Universal Queue Service: {e.reason}")
        return False
    except Exception as e:
        print(f"[QueueClient] Error tak terduga: {e}")
        return False
