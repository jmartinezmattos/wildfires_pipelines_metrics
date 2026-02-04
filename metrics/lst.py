#Land Surface Temperature (LST)
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
def get_valid_image(collection, scale=1000):
    """
    Verifica si la colección tiene imágenes y si la primera tiene píxeles reales sobre Uruguay.
    """
    if collection.size().getInfo() == 0:
        return None
    
    img = ee.Image(collection.first())
    # Contar píxeles no enmascarados en Uruguay
    count = img.clip(uruguay).reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=uruguay,
        scale=scale,
        maxPixels=1e8
    ).values().get(0).getInfo()
    
    return img if (count is not None and count > 0) else None

def get_collections(start_str, end_str):
    """
    Define and return the image collections for MODIS, VIIRS, and GOES.
    """
    modis_coll = ee.ImageCollection("MODIS/061/MOD11A1").filterDate(start_str, end_str).filterBounds(uruguay).select("LST_Day_1km")
    viirs_coll = ee.ImageCollection("NASA/VIIRS/002/VNP21A1D").filterDate(start_str, end_str).filterBounds(uruguay).select("LST_1KM")
    goes_coll = ee.ImageCollection("NOAA/GOES/16/MCMIPF").filterDate(start_str, end_str).filterBounds(uruguay).select("CMI_C13")
    return modis_coll, viirs_coll, goes_coll

def select_base_image(modis_coll, viirs_coll, goes_coll):
    """
    Perform cascade selection: MODIS -> VIIRS -> GOES.
    Returns img_base, source_name, img_modis, img_viirs, goes_coll
    """
    img_modis = get_valid_image(modis_coll)
    img_viirs = get_valid_image(viirs_coll)
    # For GOES, we'll use the collection later

    img_base = None
    source_name = ""

    if img_modis:
        img_base = img_modis.multiply(0.02)
        source_name = "MODIS"
    elif img_viirs:
        img_base = img_viirs.multiply(0.02)
        source_name = "VIIRS"
    elif goes_coll.size().getInfo() > 0:
        img_base = goes_coll.median()
        source_name = "GOES"

    return img_base, source_name, img_modis, img_viirs, goes_coll

def gap_fill(img_base, source_name, img_viirs, goes_coll):
    """
    Perform gap filling (unmasking) with other sources.
    """
    img_final = img_base

    if source_name == "MODIS" and img_viirs:
        v_fill = img_viirs.multiply(0.02)
        mask= v_fill.gt(270).And(v_fill.lt(330))
        v_fill= v_fill.updateMask(mask)
        img_final = img_final.unmask(v_fill.resample('bilinear').reproject(crs=img_final.projection()))

 # 2. Intentar rellenar con GOES (siempre disponible pero menor resolución)
    # Verificamos si la colección GOES tiene imágenes

    if goes_coll.size().getInfo() > 0:
        g_fill = goes_coll.median()
        mask= g_fill.gt(270).And(g_fill.lt(330))
        g_fill= g_fill.updateMask(mask)
        g_resampled = g_fill.resample('bilinear').reproject(crs=img_final.projection(), scale=1000)
        img_final = img_final.unmask(g_resampled)

    return img_final

def post_process(img_final):
    """
    Perform post-processing: masking, focal mean, conversion to Celsius, add alpha band.
    """
    img_final = img_final.updateMask(img_final.gt(260).And(img_final.lt(340)))
    img_filled = img_final.focal_mean(radius=2000, units='meters').blend(img_final)

    lst_celsius = img_filled.clip(uruguay).subtract(273.15).rename("LST_Final")
    alpha = ee.Image.constant(1).clip(uruguay).rename("alpha")
    out = lst_celsius.toFloat().addBands(alpha.toFloat())
    return out

def export_lst_image(out, target_date, description_prefix):
    """
    Export the LST image to Cloud Storage and return the task.
    """
    date_str = target_date.strftime('%Y%m%d')
    file_name = f"lst/LST_Uruguay_{date_str}"

    task = ee.batch.Export.image.toCloudStorage(
        image=out,
        description=f"{description_prefix}_{date_str}",
        bucket=BUCKET,
        fileNamePrefix=file_name,
        region=uruguay.bounds(),
        scale=1000,
        crs="EPSG:4326",
        fileFormat="GeoTIFF",
        formatOptions={'cloudOptimized': True} if description_prefix == "LST_Single_Export" else {},
        maxPixels=1e13 if description_prefix == "LST_Single_Export" else None
    )
    task.start()
    return task, file_name

def download_super_hybrid_lst(days):
    tasks = []
    processedLST = []

    for i in range(days):
        target_date = datetime.date.today() - datetime.timedelta(days=i+1)
        start_str, end_str = str(target_date), str(target_date + datetime.timedelta(days=1))

        # 1. Definir Colecciones
        modis_coll, viirs_coll, goes_coll = get_collections(start_str, end_str)

        # 2. Cascada de Selección con Validación de Píxeles
        img_base, source_name, img_modis, img_viirs, goes_coll = select_base_image(modis_coll, viirs_coll, goes_coll)

        if img_base is None:
            print(f"ERROR: Sin datos válidos para {target_date}. Saltando...")
            continue

        print(f"[{target_date}] Base: {source_name}")

        # 3. Relleno de huecos
        img_final = gap_fill(img_base, source_name, img_viirs, goes_coll)

        # 4. Post-procesamiento
        out = post_process(img_final)

        # 5. Exportación
        task, file_name = export_lst_image(out, target_date, "LST_Multi")
        tasks.append({"task_obj": task, "prefix": file_name, "image_date": target_date})

    # --- Espera Paralela ---
    print("--- Todas las tareas enviadas. Esperando finalización... ---")
    for item in tasks:
        success = wait_for_task(item["task_obj"])
        if success:
            gcs_path = f"gs://{BUCKET}/{item['prefix']}.tif"
            processedLST.append((gcs_path, item["image_date"]))
            print(f"Completado: {item['image_date']}")
        else:
            print(f"Fallo: {item['image_date']}")

    return processedLST


def lst():
    """
    Download LST for the last 1 day using cascade: MODIS -> VIIRS -> GOES
    """
    for i in range(7):
    # --- DATE RANGE: LAST 1 DAY ---
        target_date = datetime.date.today() - datetime.timedelta(days=i+1)
        start_str = str(target_date)
        end_str = str(target_date + datetime.timedelta(days=1))

        # 1. Definir Colecciones
        modis_coll, viirs_coll, goes_coll = get_collections(start_str, end_str)

        # 2. Cascada de Selección con Validación de Píxeles
        img_base, source_name, img_modis, img_viirs, goes_coll = select_base_image(modis_coll, viirs_coll, goes_coll)

        if img_base is None:
            raise ValueError(f"ERROR CRÍTICO: No se encontraron píxeles válidos en ninguna fuente para el día {start_str}")

        print(f"Fuente principal seleccionada: {source_name}")

        # 3. Relleno de huecos
        img_final = gap_fill(img_base, source_name, img_viirs, goes_coll)

        # 4. Post-procesamiento
        out = post_process(img_final)

        # 5. Exportación
        task, file_name = export_lst_image(out, target_date, "LST_Single_Export")

        print(f"Exportación iniciada para {start_str}... esperando completion.")

        success = wait_for_task(task)

        if not success:
            return None, None

        gcs_path = f"gs://{BUCKET}/{file_name}.tif"
        print(f"Proceso finalizado con éxito: {gcs_path}")
    return gcs_path, target_date

if __name__ == "__main__":
    result = lst()
    print("Returned:", result)
