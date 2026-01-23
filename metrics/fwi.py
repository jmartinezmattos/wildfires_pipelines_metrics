import os
import ee
import datetime
from gee_fwi.FWI import FWICalculator
from gee_fwi.FWIInputs import FWI_GFS_GSMAP
from dotenv import load_dotenv
from utils import wait_for_task, uruguay, gee_authenticate

load_dotenv("./config/.env")
BUCKET = os.getenv("BUCKET_NAME")
GEE_PROJECT = os.getenv("GEE_PROJECT")
CLOUD_ENV = os.getenv("CLOUD_ENV", "0").lower() == "1"

gee_authenticate(cloud_env=CLOUD_ENV, gee_project=GEE_PROJECT)

def fwi():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    #obs = yesterday - datetime.timedelta(days=2)
    dfyesterday = today - datetime.timedelta(days=2)
    obs = dfyesterday
    # todo REVISAR TEMA DE FECHAS
    timezone = 'America/Montevideo'

    bounds = ee.Geometry.BBox(-60, -35, -50, -30)

    inputs = FWI_GFS_GSMAP(obs, timezone, bounds)
    calculator = FWICalculator(obs, inputs)
    calculator.set_previous_codes()
    fwi = calculator.compute()

    fwi_uruguay = fwi.clip(uruguay)
    alpha = ee.Image.constant(1).clip(uruguay).rename('alpha')
    out = fwi_uruguay.toFloat().addBands(alpha.toFloat())  # add alpha band

    file_name = 'fwi/FWI_Uruguay_' + obs.strftime('%Y%m%d')

    task = ee.batch.Export.image.toCloudStorage(
        image=out,
        description='FWI_Uruguay_Export',
        outputBucket=BUCKET,
        fileNamePrefix='fwi/FWI_Uruguay_' + obs.strftime('%Y%m%d'),
        region=uruguay.bounds(),
        scale=500,
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
        return None, None

    gcs_path = f"gs://{BUCKET}/{file_name}.tif"
    print("Export completed:", gcs_path)
    return gcs_path, obs

if __name__ == "__main__":
    fwi()