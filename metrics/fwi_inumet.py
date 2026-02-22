import os
import requests
from datetime import datetime
from dotenv import load_dotenv
import subprocess
import platform
import rasterio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from rasterio.enums import Resampling

load_dotenv("./config/.env")

BUCKET = os.getenv("BUCKET_NAME")
GEE_PROJECT = os.getenv("GEE_PROJECT")
CLOUD_ENV = os.getenv("CLOUD_ENV", "0").lower() == "1"

base_url = "https://www.inumet.gub.uy/reportes/fwi/"
output_folder = "./data/fwi"

retries = 3
timeout = 15

def extract_band_inplace(input_path):

    band_number = 1
    temp_path = input_path.replace(".tif", "_cog.tif")

    with rasterio.open(input_path) as src:
        band = src.read(band_number)
        nodata = src.nodata

        if nodata is not None:
            alpha = np.where((band != nodata) & (band >= 0), 1, 0).astype("uint8")
        else:
            alpha = np.where(band >= 0, 1, 0).astype("uint8")

        profile = src.profile.copy()

        # Crear COG
        with rasterio.open(
            temp_path,
            "w",
            driver="COG",
            height=src.height,
            width=src.width,
            count=2,
            dtype=band.dtype,
            crs=src.crs,
            transform=src.transform,
            nodata=nodata,
            compress="deflate",     # o "lzw"
            blocksize=512,          # tiling interno
            overview_resampling=Resampling.average
        ) as dst:

            dst.write(band, 1)
            dst.write(alpha, 2)

            dst.set_band_description(1, "fwi")
            dst.set_band_description(2, "alpha")

    os.replace(temp_path, input_path)

    print(f"COG generated correctly: {input_path}")
    return input_path

def copy_gcs(path_from, path_to):

    is_windows = platform.system() == "Windows"

    if is_windows:
        command = f"gsutil -m cp -r {path_from} {path_to}"
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-Command",
            command
        ]
    else:
        cmd = [
            "gsutil",
            "-m",
            "cp",
            "-r",
            path_from,
            path_to
        ]

    try:
        subprocess.run(cmd, check=True)
        print(f"Files copied successfully from {path_from} to {path_to}")
        return True
    except Exception as e:
        print(f"Error copying files from {path_from} to {path_to}: {str(e)}")
        return False

def download_file(date_obj):
    
    os.makedirs(output_folder, exist_ok=True)

    date_str = date_obj.strftime("%Y_%m_%d")
    filename = f"FWI_{date_str}.tif"
    url = base_url + filename
    filepath = os.path.join(output_folder, filename)

    for attempt in range(retries):
        try:
            head = requests.head(url, timeout=timeout)

            if head.status_code != 200:
                print("File not available:", url, "Status code:", head.status_code)
                return None
            
            response = requests.get(url, timeout=timeout)

            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(response.content)
                print("File downloaded:", url, "Saved to:", filepath)
                return filepath
            else:
                print("File not available:", url, "Status code:", response.status_code)
                return None

        except Exception as e:
            if attempt == retries - 1:
                print("Error downloading file:", url, "Error:", str(e))
                return None

    print("Download failed after retries:", url)
    return filepath


def fwi(date: None | datetime = None):

    if date is None:
        input_date = datetime.today()

        tz_uy = ZoneInfo("America/Montevideo")
        now_uy = datetime.now(tz_uy)

        if now_uy.hour < 14:
            input_date = (now_uy - timedelta(days=1)).date()
        else:
            input_date = now_uy.date()
    else:
        input_date = date

    filepath = download_file(input_date)

    if filepath:
        extract_band_inplace(filepath)

        gcs_dir = f"gs://{BUCKET}/fwi_inumet"
        gcs_path = f"{gcs_dir}/{os.path.basename(filepath)}"

        r = copy_gcs(path_from=filepath, path_to=f"gs://{BUCKET}/fwi_inumet/")
        
        if r:
            return gcs_path, input_date
        else:
            return None, None
    else: 
        return None, None

fwi()