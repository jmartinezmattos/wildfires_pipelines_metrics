import os
import ee
import datetime
import requests
from dotenv import load_dotenv
from utils import wait_for_task, uruguay, gee_authenticate

load_dotenv("./config/.env")
BUCKET = os.getenv("BUCKET_NAME")
GEE_PROJECT = os.getenv("GEE_PROJECT")
CLOUD_ENV = os.getenv("CLOUD_ENV", "1").lower() == "true"

gee_authenticate(cloud_env=CLOUD_ENV, gee_project=GEE_PROJECT)

def export_modis_aqua_rgb():
    
    # --- DATE RANGE: last 30 days ---
    end = datetime.date.today()
    start = end - datetime.timedelta(days=30)

    # --- MODIS AQUA Surface Reflectance ---
    collection = (
        ee.ImageCollection("MODIS/061/MYD09GA")  # AQUA
        .filterDate(str(start), str(end))
        .filterBounds(uruguay)
        .select(["sur_refl_b01", "sur_refl_b04", "sur_refl_b03"])  # R, G, B
        .sort("system:time_start", False)
    )

    size = collection.size().getInfo()
    if size == 0:
        print("No MODIS AQUA images found in the last 30 days.")
        return None

    image = ee.Image(collection.first())

    # Scale reflectance (MODIS scale factor = 0.0001)
    rgb = image.multiply(0.0001).clip(uruguay)

    today = datetime.datetime.now().strftime("%Y%m%d")
    prefix = f"modis_aqua_rgb/MODIS_AQUA_RGB_Uruguay_{today}"

    task = ee.batch.Export.image.toCloudStorage(
        image=rgb,
        description="MODIS_AQUA_RGB_Uruguay",
        bucket=BUCKET,
        fileNamePrefix=prefix,
        region=uruguay.bounds(),
        scale=500,
        crs="EPSG:4326",
        fileFormat="GeoTIFF",
        maxPixels=1e13
    )

    task.start()
    print("RGB Export started… waiting for completion.")

    success = wait_for_task(task)

    if not success:
        return None

    gcs_path = f"gs://{BUCKET}/{prefix}.tif"
    print("Export completed:", gcs_path)
    return gcs_path


if __name__ == "__main__":
    result = export_modis_aqua_rgb()
    print("Returned:", result)
