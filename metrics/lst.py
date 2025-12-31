#Land Surface Temperature (LST)
import os
import ee
import datetime
from dotenv import load_dotenv
from utils import wait_for_task, uruguay, gee_authenticate

load_dotenv("./config/.env")
BUCKET = os.getenv("BUCKET_NAME")
GEE_PROJECT = os.getenv("GEE_PROJECT")
CLOUD_ENV = os.getenv("CLOUD_ENV", "1").lower() == "true"

gee_authenticate(cloud_env=CLOUD_ENV, gee_project=GEE_PROJECT)

def download_modis_lst():

    # --- DATE RANGE: LAST 1 DAY ---
    end = datetime.date.today()
    start = end - datetime.timedelta(days=3)

    # MODIS Terra LST daily
    collection = (
        ee.ImageCollection("MODIS/061/MOD11A1")
        .filterDate(str(start), str(end))
        .filterBounds(uruguay)
        .sort("system:time_start", False)
    )

    image = ee.Image(collection.first())

    if image is None:
        print("No MODIS LST image found for the period.")
        return None

    # --- Extract day LST band and scale ---
    # LST = DN * 0.02  → Kelvin
    lst_day = image.select("LST_Day_1km").multiply(0.02).rename("LST_Day_K")

    lst_clipped = lst_day.clip(uruguay)

    today = datetime.datetime.now().strftime("%Y%m%d")
    prefix = f"lst/MODIS_LST_Uruguay_{today}"

    task = ee.batch.Export.image.toCloudStorage(
        image=lst_clipped,
        description="MODIS_LST_Uruguay",
        bucket=BUCKET,
        fileNamePrefix=prefix,
        region=uruguay.bounds(),
        scale=1000,
        crs="EPSG:4326",
        fileFormat="GeoTIFF",
        maxPixels=1e13
    )

    task.start()
    print("Export started… waiting for completion.")

    success = wait_for_task(task)

    if not success:
        print("LST export failed.")
        return None

    gcs_path = f"gs://{BUCKET}/{prefix}.tif"
    print("Export completed:", gcs_path)
    return gcs_path

if __name__ == "__main__":
    result = download_modis_lst()
    print("Returned:", result)
