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

def _process_and_export_fwi(obs, bounds, timezone):
    """
    Lógica centralizada para calcular y exportar FWI.
    """
    print(f"Calculando FWI para la fecha: {obs.strftime('%Y-%m-%d')}...")
    
    try:
        # 1. Preparar entradas y calcular
        inputs = FWI_GFS_GSMAP(obs, timezone, bounds)
        calculator = FWICalculator(obs, inputs)
        calculator.set_previous_codes()
        fwi_img = calculator.compute()
        
        # 2. VALIDACIÓN: Verificar si la imagen resultante tiene datos
        # En FWI, un conteo de píxeles es la mejor forma de saber si el modelo falló
        pixel_count = fwi_img.clip(uruguay).reduceRegion(
            reducer=ee.Reducer.count(),
            geometry=uruguay,
            scale=5000, # Escala gruesa para rapidez
            maxPixels=1e8
        ).values().get(0).getInfo()
        
        print(f"Conteo de píxeles para FWI en {obs}: {pixel_count}")
        if not pixel_count or pixel_count == 0:
            print(f"SALTANDO: El cálculo de FWI para {obs} no devolvió píxeles válidos.")
            return None

        # 3. Preparar imagen para exportar
        fwi_uruguay = fwi_img.clip(uruguay)
        alpha = ee.Image.constant(1).clip(uruguay).rename('alpha')
        out = fwi_uruguay.toFloat().addBands(alpha.toFloat())

        date_str = obs.strftime('%Y%m%d')
        file_name = f'fwi/FWI_Uruguay_{date_str}'

        # 4. Exportación
        task = ee.batch.Export.image.toCloudStorage(
            image=out,
            description=f'FWI_Uruguay_{date_str}',
            outputBucket=BUCKET,
            fileNamePrefix=file_name,
            region=uruguay.bounds(),
            scale=500,
            crs='EPSG:4326',
            fileFormat='GeoTIFF',
            formatOptions={'cloudOptimized': True},
            maxPixels=1e13
        )

        task.start()
        success = wait_for_task(task)

        if success:
            return f"gs://{BUCKET}/{file_name}.tif", obs
        return None

    except Exception as e:
        print(f"Error procesando FWI para {obs}: {e}")
        return None

def fwi():
    """Ejecución para un solo día (2 días atrás por defecto por disponibilidad GFS)."""
    obs = datetime.date.today() - datetime.timedelta(days=2)
    bounds = ee.Geometry.BBox(-60, -35, -50, -30)
    timezone = 'America/Montevideo'
    
    result = _process_and_export_fwi(obs, bounds, timezone)
    return result if result else (None, None)

def fwi_multiple_days(num_days):
    """Ejecución para múltiples días."""
    today = datetime.date.today()
    timezone = 'America/Montevideo'
    bounds = ee.Geometry.BBox(-60, -35, -50, -30)
    results = []
    
    for i in range(num_days):
        # Mantenemos tu lógica original de i+2 para asegurar datos históricos
        obs = today - datetime.timedelta(days=i+2)
        result = _process_and_export_fwi(obs, bounds, timezone)
        if result:
            results.append(result)
            
    return results

if __name__ == "__main__":
    fwi()