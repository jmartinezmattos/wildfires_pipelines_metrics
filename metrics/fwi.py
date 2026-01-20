import os
import ee
import datetime
from gee_fwi.FWI import FWICalculator
from gee_fwi.FWIInputs import FWI_GFS_GSMAP
from dotenv import load_dotenv
from utils_temp import wait_for_task, uruguay, gee_authenticate

load_dotenv("./config/.env")
BUCKET = os.getenv("BUCKET_NAME")
GEE_PROJECT = os.getenv("GEE_PROJECT")
CLOUD_ENV = os.getenv("CLOUD_ENV", "0").lower() == "1"

gee_authenticate(cloud_env=CLOUD_ENV, gee_project=GEE_PROJECT)

def fwi():

    obs = datetime.date.today() - datetime.timedelta(days=1)
    timezone = 'America/Montevideo'

    bounds = ee.Geometry.BBox(-60, -35, -50, -30)

    inputs = FWI_GFS_GSMAP(obs, timezone, bounds)
    calculator = FWICalculator(obs, inputs)
    calculator.set_previous_codes()
    fwi = calculator.compute()

    fwi_uruguay = fwi.clip(uruguay)
    alpha = fwi_uruguay.mask().unmask(0).rename("alpha")

    fwi_uruguay = fwi_uruguay.toFloat()
    alpha = alpha.toFloat()
    out =fwi_uruguay.toFloat().addBands(alpha.toFloat()) # add alpha band to FWI
    # Obtener URL de descarga del GeoTIFF
    # url = fwi_uruguay.getDownloadURL({
    #     'name': 'FWI_Uruguay_' + obs.strftime('%Y%m%d'),
    #     'scale': 1000,           # resolución en metros
    #     'region': uruguay.geometry().bounds().getInfo(),
    #     'crs': 'EPSG:4326',
    #     'fileFormat': 'GeoTIFF'
    # })

    file_name = 'fwi/FWI_Uruguay_' + obs.strftime('%Y%m%d')

    task = ee.batch.Export.image.toCloudStorage(
        image=fwi_uruguay,
        description='FWI_Uruguay_Export',
        outputBucket=BUCKET,
        fileNamePrefix='fwi/FWI_Uruguay_' + obs.strftime('%Y%m%d'),
        region=uruguay.bounds(),
        scale=1000,
        crs='EPSG:4326',
        fileFormat='GeoTIFF',
        formatOptions={
        'cloudOptimized': True,
        },
        maxPixels=1e13
    )

    task.start()

    print("FWI export started… waiting for completion.")
    success = wait_for_task(task)

    if not success:
        return None

    gcs_path = f"gs://{BUCKET}/{file_name}.tif"
    print("Export completed:", gcs_path)
    return gcs_path

if __name__ == "__main__":
    fwi()