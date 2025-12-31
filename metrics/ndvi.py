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

def ndvi():

    end = datetime.date.today()
    start = end - datetime.timedelta(days=7)

    col = (
        ee.ImageCollection("MODIS/061/MOD09GA")
        .filterBounds(uruguay)
        .filterDate(str(start), str(end))
        .sort("system:time_start", False)
    )

    img = ee.Image(col.first())

    ndvi = img.normalizedDifference(["sur_refl_b02", "sur_refl_b01"]).rename("NDVI")
    ndvi = ndvi.clip(uruguay)

    today_str = datetime.datetime.now().strftime('%Y%m%d')

    file_name = f'ndvi/NDVI_Uruguay_{today_str}'

    task = ee.batch.Export.image.toCloudStorage(
        image=ndvi,
        description='NDVI_Uruguay_Export',
        bucket=BUCKET,            
        fileNamePrefix=file_name,
        region=uruguay.bounds(),
        scale=500,
        crs='EPSG:4326',
        fileFormat='GeoTIFF',
        maxPixels=1e13
    )

    task.start()
    print("NDVI export started… waiting for completion.")
    success = wait_for_task(task)

    if not success:
        return None

    gcs_path = f"gs://{BUCKET}/{file_name}.tif"
    print("Export completed:", gcs_path)
    return gcs_path

if __name__ == "__main__":
    ndvi()
