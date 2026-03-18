import os
import ee
import datetime
from db import wildfiresDB
from dotenv import load_dotenv
from utils import wait_for_task, uruguay, gee_authenticate

load_dotenv("./config/.env")
BUCKET = os.getenv("BUCKET_NAME")
GEE_PROJECT = os.getenv("GEE_PROJECT")
CLOUD_ENV = os.getenv("CLOUD_ENV", "0").lower() == "1"

gee_authenticate(cloud_env=CLOUD_ENV, gee_project=GEE_PROJECT)

def process_and_export_rgb(target_date, is_single=False):
    """
    Función interna para validar, procesar y exportar la imagen de un día específico.
    """
    start_str = str(target_date)
    end_str = str(target_date + datetime.timedelta(days=1))
    
    collection = (
        ee.ImageCollection("MODIS/061/MYD09GA")  # MODIS Aqua primero
        .filterDate(start_str, end_str)
        .filterBounds(uruguay)
        .sort("system:time_start", False)
    )

    source_name = "MODIS_AQUA"
    if collection.size().getInfo() == 0:
        print(f"No MODIS Aqua para {start_str}, intentando VIIRS...")
        
        collection = (
            ee.ImageCollection("NASA/VIIRS/002/VNP09GA")
            .filterDate(start_str, end_str)
            .filterBounds(uruguay)
            .sort("system:time_start", False)
        )
        source_name = "VIIRS"
        
        if collection.size().getInfo() == 0:
            print(f"No hay imágenes RGB en catálogo para {start_str}")
            return None

    image = ee.Image(collection.first())
    actual_date_ms = image.get('system:time_start').getInfo()
    actual_date = datetime.datetime.fromtimestamp(actual_date_ms / 1000.0).date()
    actual_date_str = actual_date.strftime("%Y%m%d")

    wildfiresdb = wildfiresDB()
    try:
        if wildfiresdb.metric_exists(actual_date, "rgb"):
            print(f"RGB ya existe en DB para {actual_date_str}. Se omite exportación.")
            return None
    finally:
        wildfiresdb.close()

    # --- PROCESAMIENTO ---
    if source_name == "MODIS_AQUA":
        image = image.select(["sur_refl_b01", "sur_refl_b04", "sur_refl_b03"]).multiply(0.0001) # R,G,B MODIS
    else:  # VIIRS
        image = image.select(["M5","M4","M3"]).multiply(0.0001)  # R,G,B VIIRS 500m

    rgb = image.clip(uruguay)

    stats = rgb.reduceRegion(
    reducer=ee.Reducer.count(),
    geometry=uruguay,
    scale=1000,
    maxPixels=1e13
    )

    valid_pixels = ee.Number(stats.get("I1" if source_name == "VIIRS" else "sur_refl_b01", 0))
    pixel_count = valid_pixels.getInfo() or 0

    if pixel_count is None or pixel_count < 100:
        print(f"SALTANDO: {start_str} sin suficiente cobertura RGB válida.")
        return None

    alpha = ee.Image.constant(1).clip(uruguay).rename("alpha")
    out = rgb.toFloat().addBands(alpha.toFloat())

    date_str = target_date.strftime("%Y%m%d")
    prefix = f"rgb/MODIS_AQUA_RGB_Uruguay_{actual_date_str}"
    
    task = ee.batch.Export.image.toCloudStorage(
        image=out,
        description=f"MODIS_AQUA_RGB_{actual_date_str}",
        bucket=BUCKET,
        fileNamePrefix=prefix,
        region=uruguay.bounds(),
        scale=500,
        crs="EPSG:4326",
        fileFormat="GeoTIFF",
        formatOptions={'cloudOptimized': True},
        maxPixels=1e13
    )

    task.start()
    print(f"Exportación iniciada para {actual_date_str}...")
    success = wait_for_task(task)

    if success:
        return f"gs://{BUCKET}/{prefix}.tif", actual_date_str
    return None

def rgb():
    """Exporta la imagen más reciente válida de los últimos 7 días."""
    print("Buscando imagen más reciente en los últimos 7 días...")
    for i in range(7):
        target_date = datetime.date.today() - datetime.timedelta(days=i)
        result = process_and_export_rgb(target_date)
        if result:
            print(f"Imagen encontrada y exportada: {result[0]}")
            return result
    print("No se encontró ninguna imagen válida en los últimos 7 días.")
    return None, None

def export_modis_aqua_rgb_multiple_days(num_days):
    """Exporta imágenes para un rango de días, saltando las vacías."""
    results = []
    for i in range(num_days):
        target_date = datetime.date.today() - datetime.timedelta(days=i)
        result = process_and_export_rgb(target_date)
        if result:
            results.append(result)
    return results

if __name__ == "__main__":
    rgb()
