import os
import ee
import datetime
import db
from dotenv import load_dotenv
from db import wildfiresDB
from utils import wait_for_task, uruguay, gee_authenticate

load_dotenv("./config/.env")
BUCKET = os.getenv("BUCKET_NAME")
GEE_PROJECT = os.getenv("GEE_PROJECT")
CLOUD_ENV = os.getenv("CLOUD_ENV", "0").lower() == "1"

gee_authenticate(cloud_env=CLOUD_ENV, gee_project=GEE_PROJECT)

def _process_and_export_ndvi(target_date):
    """
    Función interna para validar la existencia de datos, calcular NDVI y exportar.
    """
    start_str = str(target_date)
    end_str = str(target_date + datetime.timedelta(days=1))

    # 1. Definir colección para el día exacto
    col = (
        ee.ImageCollection("MODIS/061/MOD09GA")
        .filterBounds(uruguay)
        .filterDate(start_str, end_str)
        .sort("system:time_start", False)
    )

    if col.size().getInfo() == 0:
        print(f"No hay imágenes NDVI en catálogo para {start_str}")
        return None

    img = ee.Image(col.first())
    actual_date_timestamp = img.get('system:time_start').getInfo()
    actual_date = datetime.datetime.fromtimestamp(actual_date_timestamp / 1000.0).date()
    actual_date_str = actual_date.strftime('%Y%m%d')

    # 2. Chequear si ya existe en DB antes de procesar/exportar
    wildfiresdb = wildfiresDB()
    try:
        if wildfiresdb.metric_exists(actual_date, "ndvi"):
            print(f"NDVI ya existe en DB para {actual_date_str}. Se omite exportación.")
            return None
    finally:
        wildfiresdb.close()


    # 3. PROCESAMIENTO
    ndvi_img = img.normalizedDifference(["sur_refl_b02", "sur_refl_b01"]).rename("NDVI").clip(uruguay)

    stats = ndvi_img.reduceRegion(
    reducer=ee.Reducer.count(),
    geometry=uruguay,
    scale=1000,
    maxPixels=1e13
)

    valid_pixels = stats.get("NDVI")
    valid_pixels = ee.Number(valid_pixels)

    pixel_count = valid_pixels.getInfo()

    if pixel_count is None or pixel_count < 100:
        print(f"SALTANDO: {start_str} sin suficiente cobertura NDVI válida.")
        return None

    alpha = ee.Image.constant(1).clip(uruguay).rename('alpha')
    out = ndvi_img.toFloat().addBands(alpha.toFloat())

    date_str = target_date.strftime('%Y%m%d')
    file_name = f'ndvi/NDVI_Uruguay_{actual_date_str}'
    
    if not BUCKET:
        raise ValueError("BUCKET_NAME no configurado en .env")

    # 4. EXPORTACIÓN
    task = ee.batch.Export.image.toCloudStorage(
        image=out,
        description=f'NDVI_Uruguay_{actual_date_str}',
        outputBucket=BUCKET,
        fileNamePrefix=file_name,
        region=uruguay,
        #scale=500,
        scale=1000,
        crs='EPSG:4326',
        fileFormat='GeoTIFF',
        formatOptions={'cloudOptimized': True},
        maxPixels=1e13
    )

    task.start()
    print(f"Exportación NDVI iniciada para {actual_date_str}...")
    success = wait_for_task(task)

    if success:
        return f"gs://{BUCKET}/{file_name}.tif", target_date
    return None

def ndvi():
    """Busca y exporta el NDVI válido más reciente de los últimos 5 días."""
    print("Buscando NDVI más reciente (ventana 5 días)...")
    for i in range(5):
        target_date = datetime.date.today() - datetime.timedelta(days=i)
        result = _process_and_export_ndvi(target_date)
        if result:
            print(f"NDVI completado: {result[0]}")
            return result
    print("No se encontró NDVI válido en la última semana.")
    return None, None

def ndvi_multiple_days(num_days):
    """Exporta NDVI para múltiples días, ignorando los que no tengan datos."""
    print("Exportando NDVI para múltiples días...")
    results = []
    for i in range(num_days):
        target_date = datetime.date.today() - datetime.timedelta(days=i)
        result = _process_and_export_ndvi(target_date)
        if result:
            results.append(result)
    return results

if __name__ == "__main__":
    ndvi()