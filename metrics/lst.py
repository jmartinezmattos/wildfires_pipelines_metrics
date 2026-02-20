#Land Surface Temperature (LST)
import os
import ee
import datetime
from dotenv import load_dotenv
from utils import wait_for_task, uruguay, gee_authenticate
from db import wildfiresDB


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
    Define and return the image collections for MODIS TERRA, AQUA AND VIIRS.
    """
    terra_coll = ee.ImageCollection("MODIS/061/MOD11A1").filterDate(start_str, end_str).filterBounds(uruguay).select("LST_Day_1km")
    aqua_coll = ee.ImageCollection("MODIS/061/MYD11A1").filterDate(start_str, end_str).filterBounds(uruguay).select("LST_Day_1km")
    viirs_coll = ee.ImageCollection("NASA/VIIRS/002/VNP21A1D").filterDate(start_str, end_str).filterBounds(uruguay).select("LST_1KM")
    return terra_coll, aqua_coll, viirs_coll

def select_base_image(terra_coll, aqua_coll, viirs_coll, target_date):
    """
    Perform cascade selection: MODIS TERRA-> VIIRS
    Returns img_base, source_name, img_terra, img_viirs, aqua_coll
    """
    img_terra = get_valid_image(terra_coll)
    img_aqua = get_valid_image(aqua_coll)
    img_viirs = get_valid_image(viirs_coll)

    img_base = None
    source_name = ""
    actual_date = target_date

    if img_terra:
        img_base = img_terra.multiply(0.02)
        source_name = "MODIS"
        ts = img_terra.get('system:time_start').getInfo()
        actual_date = datetime.datetime.fromtimestamp(ts / 1000.0).date()
    elif img_aqua:
        img_base = img_aqua.multiply(0.02)
        source_name = "MODIS_AQUA" #check
        ts = img_aqua.get('system:time_start').getInfo()
        actual_date = datetime.datetime.fromtimestamp(ts / 1000.0).date()
    elif img_viirs:
        img_base = img_viirs.multiply(0.02)
        source_name = "VIIRS"
        ts = img_viirs.get('system:time_start').getInfo()
        actual_date = datetime.datetime.fromtimestamp(ts / 1000.0).date()


    return img_base, source_name, actual_date, img_terra, img_aqua, img_viirs

def gap_fill(img_base, source_name, img_viirs, img_aqua, img_terra):
    """
    Perform gap filling (unmasking) with other sources.
    """
    img_final = img_base

    if source_name == "MODIS" and img_viirs:
        v_fill = img_viirs.multiply(0.02)
        mask= v_fill.gt(270).And(v_fill.lt(330))
        v_fill= v_fill.updateMask(mask)
        img_final = img_final.unmask(v_fill.resample('bilinear').reproject(crs=img_final.projection()))
    elif source_name == "MODIS_AQUA" and img_aqua:
        a_fill = img_aqua.multiply(0.02)
        mask= a_fill.gt(270).And(a_fill.lt(330))
        a_fill= a_fill.updateMask(mask)
        img_final = img_final.unmask(a_fill.resample('bilinear').reproject(crs=img_final.projection()))
    elif source_name == "MODIS" and img_terra:
        t_fill = img_terra.multiply(0.02)
        mask= t_fill.gt(270).And(t_fill.lt(330))
        t_fill= t_fill.updateMask(mask)
        img_final = img_final.unmask(t_fill.resample('bilinear').reproject(crs=img_final.projection()))

    return img_final

def merge_sources(img_terra, img_aqua, img_viirs):

    images = []

    if img_viirs:
        images.append(img_viirs.multiply(0.02))

    if img_terra:
        images.append(img_terra.multiply(0.02))

    if img_aqua:
        images.append(img_aqua.multiply(0.02))

    if not images:
        return None

    img_final = images[0]
    for img in images[1:]:
        img_final = img_final.unmask(img)

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
        target_date = datetime.date.today() - datetime.timedelta(days=i + 1)
        start_str, end_str = str(target_date), str(target_date + datetime.timedelta(days=1))

        # 1. Definir Colecciones
        terra_coll,  aqua_coll, viirs_coll = get_collections(start_str, end_str)

        # 2. Cascada de Seleccion con Validacion de Pixeles
        # img_base, source_name, actual_date, img_terra, img_aqua, img_viirs = select_base_image(terra_coll, aqua_coll, viirs_coll, target_date)
        """ 
        if img_base is None:
            print(f"ERROR: Sin datos validos para {target_date}. Saltando...")
            continue

        wildfiresdb = wildfiresDB()
        try:
            if wildfiresdb.metric_exists(target_date, "lst"):
                print(f"LST ya existe en DB para {target_date}. Se omite exportacion.")
                continue
        finally:
            wildfiresdb.close()

        print(f"[{target_date}] Base: {source_name}")

        # 3. Relleno de huecos
        img_final = gap_fill(img_base, source_name, img_viirs, aqua_coll)
         """        
        img_terra = get_valid_image(terra_coll)
        img_aqua  = get_valid_image(aqua_coll)
        img_viirs = get_valid_image(viirs_coll)

        img_final = merge_sources(img_terra, img_aqua, img_viirs)

        if img_final is None:
            continue

        
        # 4. Post-procesamiento
        out = post_process(img_final)

        # 5. Exportacion
        task, file_name = export_lst_image(out, actual_date, "LST_Multi")
        tasks.append({"task_obj": task, "prefix": file_name, "image_date": actual_date})

    # --- Espera Paralela ---
    print("--- Todas las tareas enviadas. Esperando finalizacion... ---")
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
        target_date = datetime.date.today() - datetime.timedelta(days=i + 1)

        start_str, end_str = str(target_date), str(target_date + datetime.timedelta(days=1))
        terra_coll,  aqua_coll, viirs_coll = get_collections(start_str, end_str)

        # Obtener imagen y su FECHA REAL
        #img_base, source_name, actual_date, img_terra, img_aqua, img_viirs = select_base_image(terra_coll, aqua_coll, viirs_coll, target_date)


        if img_base is None:
            print(f"ERROR: Sin datos para {target_date}")
            continue

        wildfiresdb = wildfiresDB()
        try:
            if wildfiresdb.metric_exists(target_date, "lst"):
                print(f"LST ya existe en DB para {target_date}. Se omite exportacion.")
                continue
        finally:
            wildfiresdb.close()

        # 3. Relleno de huecos
        img_final = gap_fill(img_base, source_name, img_viirs, aqua_coll)

        # 4. Post-procesamiento
        out = post_process(img_final)

        # 5. Exportacion
        task, file_name = export_lst_image(out, actual_date, "LST_Single_Export")

        print(f"Exportacion iniciada para {start_str}... esperando completion.")

        success = wait_for_task(task)

        if not success:
            return None, None

        gcs_path = f"gs://{BUCKET}/{file_name}.tif"
        print(f"Proceso finalizado con exito: {gcs_path}")
        return gcs_path, target_date

    return None, None

if __name__ == "__main__":
    result = lst()
    print("Returned:", result)
