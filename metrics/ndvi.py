import os
import ee
import datetime
from dotenv import load_dotenv
from utils import wait_for_task, uruguay, gee_authenticate

load_dotenv("./config/.env")
BUCKET = os.getenv("BUCKET_NAME")
GEE_PROJECT = os.getenv("GEE_PROJECT")
CLOUD_ENV = os.getenv("CLOUD_ENV", "0").lower() == "1"

gee_authenticate(cloud_env=CLOUD_ENV, gee_project=GEE_PROJECT)

def ndvi():

    end = datetime.date.today()
    start = end - datetime.timedelta(days=7)
    start2 = end - datetime.timedelta(days=14)

    col = (
        ee.ImageCollection("MODIS/061/MOD09GA")
        .filterBounds(uruguay)
        .filterDate(str(start), str(end))
        .sort("system:time_start", False)
    )

    img = ee.Image(col.first())

    ndvi = img.normalizedDifference(["sur_refl_b02", "sur_refl_b01"]).rename("NDVI").clip(
        uruguay)  # propagate original data mask
    alpha = ee.Image.constant(1).clip(uruguay).rename('alpha')
    out = ndvi.toFloat().addBands(alpha.toFloat())  # add alpha band

    today_str = datetime.datetime.now().strftime('%Y%m%d')

    file_name = f'ndvi/NDVI_Uruguay_{today_str}'

    if not BUCKET:
        raise ValueError("BUCKET_NAME environment variable is not set in ./config/.env")
    
    task = ee.batch.Export.image.toCloudStorage(
        image=out,
        description='NDVI_Uruguay_Export',
        outputBucket=BUCKET,            
        #bucket=BUCKET,            
        fileNamePrefix=file_name,
        #region=uruguay.bounds(),
        region=uruguay,
        scale=500,
        crs='EPSG:4326',
        fileFormat='GeoTIFF',
        formatOptions= {
            'cloudOptimized': True,
        },
        maxPixels=1e13
    )

    task.start()
    print("NDVI export started… waiting for completion.")
    success = wait_for_task(task)

    if not success:
        return None, None

    gcs_path = f"gs://{BUCKET}/{file_name}.tif"
    print("Export completed:", gcs_path)
    ndvi_date = datetime.datetime.strptime(today_str, '%Y%m%d').date()
    return gcs_path, ndvi_date

if __name__ == "__main__":
    ndvi()
