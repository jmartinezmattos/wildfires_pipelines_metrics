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

def process_and_export_rgb(target_date, is_single=False):
    """
    Función interna para validar, procesar y exportar la imagen de un día específico.
    """
    start_str = str(target_date)
    end_str = str(target_date + datetime.timedelta(days=1))
    
    collection = (
        ee.ImageCollection("MODIS/061/MYD09GA")
        .filterDate(start_str, end_str)
        .filterBounds(uruguay)
        .select(["sur_refl_b01", "sur_refl_b04", "sur_refl_b03"])
        .sort("system:time_start", False)
    )
    if collection.size().getInfo() == 0:
        print(f"No hay imágenes RGB en catálogo para {start_str}")
        return None

    image = ee.Image(collection.first())

    # --- VALIDACIÓN DE PÍXELES VACÍOS ---
    # Contamos píxeles en la banda 1. Usamos una escala de 2000 para que sea rápido.
    pixel_count = image.clip(uruguay).reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=uruguay,
        scale=2000,
        maxPixels=1e8
    ).values().get(0).getInfo()

    print(f"Conteo de píxeles para RGB en {start_str}: {pixel_count}")
    if not pixel_count or pixel_count < 10: # Si hay menos de 10 píxeles, está vacío
        print(f"SALTANDO: Imagen de {start_str} sin datos válidos (posibles nubes o fuera de órbita).")
        return None

    # --- PROCESAMIENTO ---
    rgb = image.multiply(0.0001).clip(uruguay)
    alpha = ee.Image.constant(1).clip(uruguay).rename("alpha")
    out = rgb.toFloat().addBands(alpha.toFloat())

    date_str = target_date.strftime("%Y%m%d")
    prefix = f"rgb/MODIS_AQUA_RGB_Uruguay_{date_str}"
    
    task = ee.batch.Export.image.toCloudStorage(
        image=out,
        description=f"MODIS_AQUA_RGB_{date_str}",
        bucket=BUCKET,
        fileNamePrefix=prefix,
        region=uruguay.bounds(),
        #scale=500,
        scale=500,
        crs="EPSG:4326",
        fileFormat="GeoTIFF",
        formatOptions={'cloudOptimized': True},
        maxPixels=1e13
    )

    task.start()
    print(f"Exportación iniciada para {start_str}...")
    success = wait_for_task(task)

    if success:
        return f"gs://{BUCKET}/{prefix}.tif", start_str
    return None

def rgb():
    """Exporta la imagen más reciente válida de los últimos 30 días."""
    print("Buscando imagen más reciente en los últimos 30 días...")
    for i in range(30):
        target_date = datetime.date.today() - datetime.timedelta(days=i)
        result = process_and_export_rgb(target_date)
        if result:
            print(f"Imagen encontrada y exportada: {result[0]}")
            return result
    print("No se encontró ninguna imagen válida en los últimos 30 días.")
    return None

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