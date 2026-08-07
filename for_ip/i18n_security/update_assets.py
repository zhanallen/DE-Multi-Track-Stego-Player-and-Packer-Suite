import os
import gzip
import shutil
import ipaddress
import requests
import maxminddb

# Target directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CF_IPV4_URL = "https://www.cloudflare.com/ips-v4"
CF_IPV6_URL = "https://www.cloudflare.com/ips-v6"
DBIP_MMDB_GZ_URL = "https://cdn.jsdelivr.net/npm/dbip-city-lite/dbip-city-lite.mmdb.gz"

def update_cloudflare_ips():
    print("Updating Cloudflare IP lists...")
    try:
        r4 = requests.get(CF_IPV4_URL, timeout=30)
        r4.raise_for_status()
        r6 = requests.get(CF_IPV6_URL, timeout=30)
        r6.raise_for_status()
        
        ipv4_lines = [line.strip() for line in r4.text.splitlines() if line.strip()]
        ipv6_lines = [line.strip() for line in r6.text.splitlines() if line.strip()]
        
        all_lines = ipv4_lines + ipv6_lines
        
        # Verify they are all valid CIDRs
        valid_cidrs = []
        for line in all_lines:
            try:
                ipaddress.ip_network(line)
                valid_cidrs.append(line)
            except ValueError:
                print(f"Warning: Invalid CIDR ignored: {line}")
                
        if len(valid_cidrs) < 5:
            raise ValueError("Too few valid CIDRs downloaded. Update aborted to prevent empty whitelist.")
            
        # Write to temp file first
        os.makedirs(DATA_DIR, exist_ok=True)
        temp_file_path = os.path.join(DATA_DIR, "cloudflare_ips.tmp")
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(valid_cidrs) + "\n")
            
        # Rename to final target
        target_path = os.path.join(DATA_DIR, "cloudflare_ips.txt")
        shutil.move(temp_file_path, target_path)
        print(f"Cloudflare IP list updated successfully: {len(valid_cidrs)} ranges saved to {target_path}")
    except Exception as e:
        print(f"Error updating Cloudflare IPs: {e}. Keeping existing list if any.")

def update_dbip_database():
    print("Updating DB-IP database...")
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        temp_gz_path = os.path.join(DATA_DIR, "dbip-city-lite.mmdb.gz.tmp")
        temp_mmdb_path = os.path.join(DATA_DIR, "dbip-city-lite.mmdb.tmp")
        
        # Download gzipped file
        print(f"Downloading from {DBIP_MMDB_GZ_URL}...")
        response = requests.get(DBIP_MMDB_GZ_URL, stream=True, timeout=120)
        response.raise_for_status()
        
        with open(temp_gz_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        # Unpack gzip
        print("Decompressing database...")
        with gzip.open(temp_gz_path, "rb") as f_in:
            with open(temp_mmdb_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
                
        # Verify the mmdb file
        print("Verifying downloaded database...")
        try:
            # We explicitly use maxminddb.MODE_MMAP (pure Python) because the C extension (MODE_MMAP_EXT)
            # has encoding bugs on Windows when file paths contain non-ASCII characters.
            with maxminddb.open_database(temp_mmdb_path, maxminddb.MODE_MMAP) as reader:
                # Try a test lookup (Google DNS)
                test_res = reader.get("8.8.8.8")
                if test_res and isinstance(test_res, dict):
                    print("Database verification successful. Valid lookup structure returned.")
                else:
                    raise ValueError("Database returned invalid structure on test lookup.")
        except Exception as ve:
            raise ValueError(f"Database verification failed: {ve}")
            
        # If valid, rename to target
        target_path = os.path.join(DATA_DIR, "dbip-city-lite.mmdb")
        shutil.move(temp_mmdb_path, target_path)
        
        # Clean up gz temp file
        if os.path.exists(temp_gz_path):
            os.remove(temp_gz_path)
            
        print(f"DB-IP database updated successfully: {target_path}")
    except Exception as e:
        print(f"Error updating DB-IP database: {e}. Keeping existing database if any.")
        # Cleanup temp files if they exist
        for p in [os.path.join(DATA_DIR, "dbip-city-lite.mmdb.gz.tmp"), os.path.join(DATA_DIR, "dbip-city-lite.mmdb.tmp")]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

if __name__ == "__main__":
    update_cloudflare_ips()
    update_dbip_database()
