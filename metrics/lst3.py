#Land Surface Temperature (LST)
import os
import ee
import datetime
from dotenv import load_dotenv
from metrics.lst import gap_fill
from utils import wait_for_task, uruguay, gee_authenticate
from db import wildfiresDB


load_dotenv("./config/.env")
# BUCKET = os.getenv("PRUEBAS_LST") or os.getenv("pruebas_lst") or os.getenv("BUCKET_NAME")
BUCKET = os.getenv("BUCKET_NAME")
GEE_PROJECT = os.getenv("GEE_PROJECT")
CLOUD_ENV = os.getenv("CLOUD_ENV", "0").lower() == "1"

gee_authenticate(cloud_env=CLOUD_ENV, gee_project=GEE_PROJECT)

if not BUCKET:
    raise RuntimeError(
        "No bucket configured. Set PRUEBAS_LST (recommended) or BUCKET_NAME in config/.env."
    )
def get_valid_image(collection, quality_band, scale=5000):
    """
    Verifica si la colección tiene imágenes y selecciona usando qualityMosaic.
    quality_band: nombre de la banda de calidad a usar (ej: "QC_Day", "QC")
    """
    if collection.size().getInfo() == 0:
        return None
    
    img = ee.Image(collection.qualityMosaic(quality_band))
    # img = ee.Image(collection.mosaic())

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
    terra_coll = ee.ImageCollection("MODIS/061/MOD11A1").filterDate(start_str, end_str).filterBounds(uruguay).select(["LST_Day_1km", "QC_Day"])
    aqua_coll = ee.ImageCollection("MODIS/061/MYD11A1").filterDate(start_str, end_str).filterBounds(uruguay).select(["LST_Day_1km", "QC_Day"])
    viirs_coll = ee.ImageCollection("NASA/VIIRS/002/VNP21A1D").filterDate(start_str, end_str).filterBounds(uruguay).select(["LST_1KM", "QC"])
    return terra_coll, aqua_coll, viirs_coll

def mask_modis_qa(img):
    """
    Keep only good-quality MODIS LST pixels.
    Extract bits 0-1 from QC_Day (mandatory QA) which indicates pixel quality.
    """
    qc = img.select("QC_Day")

    # Extract bits 0-1: mandatory QA (values 0-3)
    # 0 = Ideal, 1 = Good, 2 = Acceptable, 3 = poor/degraded
    mandatory_qa = qc.bitwiseAnd(3)

    # Keep quality 0-3 (inclusive - all quality levels) for maximum coverage
    # Filtering by temperature range in post_process() is more effective
    mask = mandatory_qa.lte(3)

    return img.updateMask(mask).select("LST_Day_1km")

def mask_viirs_qa(img):
    """
    Keep only good-quality VIIRS LST pixels.
    Extract bits 0-1 from QC which indicates pixel quality.
    """
    qc = img.select("QC")

    # Extract bits 0-1: quality indicator (values 0-3)
    # 0 = Good, 1 = Acceptable, 2 = Questionable, 3 = Poor/Missing
    quality = qc.bitwiseAnd(3)

    # Keep quality 0-3 (inclusive - all quality levels) for maximum coverage
    # Filtering by temperature range in post_process() is more effective
    mask = quality.lte(3)

    return img.updateMask(mask).select("LST_1KM")

def add_valid_count(img):
    count = img.mask().rename("valid_count")
    return img.addBands(count)


def has_valid_data(img, region):
    stats = img.reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=region,
        scale=1000,
        maxPixels=1e13
    )
    
    count = stats.values().get(0)
    return ee.Number(count).gt(0)


def process_final_lst(img_kelvin, region):
    """
    Unifica conversión, filtrado y preparación de bandas.
    """
    # 1. Convertir a Celsius
    celsius = img_kelvin.subtract(273.15).rename("LST_Celsius")
    
    # 2. Definir máscara de calidad (rango lógico)
    # Importante: No aplicamos updateMask todavía para no perder la geometría
    valid_range_mask = celsius.gt(-30).And(celsius.lt(70))
    
    # 3. Crear banda Alpha (1 donde hay datos válidos, 0 donde no)
    # Usamos .unmask(0) para asegurarnos de que la banda alpha tenga valores reales 0 o 1
    alpha = valid_range_mask.rename("alpha").toFloat()
    
    # 4. Preparar LST con valor NoData para el GeoTIFF
    # Llenamos los huecos con -9999 para que el archivo sea "sólido" 
    # pero el software sepa que eso no es temperatura real
    lst_final = celsius.updateMask(valid_range_mask)
    
    # 5. Combinar bandas
    # Usamos cast a float32 para evitar problemas de compatibilidad en el TIFF
    return lst_final.addBands(alpha).toFloat().clip(region)

# Elimina o reemplaza las funciones post_process, alpha_band y prepare_output_with_nodata 
# por esta única función para evitar redundancias.

def reproject(img):
    """
    Reproject to EPSG:4326 with 1km scale.
    """
    return img.reproject(crs="EPSG:4326", scale=1000)

def prepare_output_with_nodata(lst_celsius_img):
    # Máscara de datos válidos de LST
    valid_mask = lst_celsius_img.mask().reduce(ee.Reducer.min())

    # LST con NoData explícito
    lst_filled = lst_celsius_img.rename("LST_Celsius").toFloat()

    # Alpha: 1 = válido, 0 = no data
    alpha = valid_mask.unmask(0).rename("alpha").toFloat()

    return lst_filled.addBands(alpha).select(["LST_Celsius", "alpha"])


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
        #region=uruguay.bounds(),
        region=uruguay,
        scale=1000,
        crs="EPSG:4326",
        fileFormat="GeoTIFF",
        # formatOptions={'cloudOptimized': True} if description_prefix == "LST_Single_Export" else {},
        formatOptions={'cloudOptimized': True},
        maxPixels=1e13 if description_prefix == "LST_Single_Export" else None
    )
    task.start()
    return task, file_name

def lst3():
    for i in range(7):
        # --- DATE RANGE: LAST 1 DAY ---
        target_date = datetime.date.today() - datetime.timedelta(days=i + 2)

        start_str, end_str = str(target_date), str(target_date + datetime.timedelta(days=1))
        terra_coll,  aqua_coll, viirs_coll = get_collections(start_str, end_str)
     
        wildfiresdb = wildfiresDB()
        try:
            if wildfiresdb.metric_exists(target_date, "lst"):
                print(f"LST ya existe en DB para {target_date}. Se omite exportacion.")
                continue
        finally:
            wildfiresdb.close()


        img_terra = get_valid_image(terra_coll, "QC_Day")
        if img_terra:
            img_terra = mask_modis_qa(img_terra)  # MODIS scale (Kelvin)
            img_terra = img_terra.select("LST_Day_1km").multiply(0.02).rename("LST")  # MODIS scale (Kelvin)

        img_aqua = get_valid_image(aqua_coll, "QC_Day")
        if img_aqua:
            img_aqua = mask_modis_qa(img_aqua)  # MODIS scale (Kelvin)
            img_aqua = img_aqua.select("LST_Day_1km").multiply(0.02).rename("LST")  # MODIS scale (Kelvin)

        img_viirs = get_valid_image(viirs_coll, "QC")
        if img_viirs:
            img_viirs = mask_viirs_qa(img_viirs)  # VIIRS QA mask
            img_viirs = img_viirs.select("LST_1KM").multiply(0.00341802).rename("LST")  # VIIRS scale (Kelvin)
            # img_viirs = img_viirs.multiply(0.02).rename("LST")  # VIIRS scale (Kelvin)


        # Build a list of available images along with their pixel counts
        available = []
        for name, raw_img in [("terra", img_terra), ("aqua", img_aqua), ("viirs", img_viirs)]:
            if raw_img is None: continue
            # count non-masked pixels over Uruguay at 1 km
            processed_candidate = process_final_lst(raw_img, uruguay)
            # 2. Contamos solo píxeles que sobrevivieron al filtro (alpha == 1)
            valid_pixels = processed_candidate.select("alpha").reduceRegion(
                reducer=ee.Reducer.sum(), # Sumamos los '1', eso nos da el conteo real
                geometry=uruguay,
                scale=1000,
                maxPixels=1e13
            ).values().get(0)
            
            try:
                count_val = valid_pixels.getInfo() or 0
            except:
                count_val = 0
                
            if count_val > 0:
                available.append((processed_candidate, count_val, name))

        if not available:
            print(f"No hay datos de superficie despejada para {target_date} en ningún sensor.")
            continue

        # Choose the image with the highest pixel count (no merging anymore)
        out, max_count, best_name = max(available, key=lambda t: t[1])
        print(f"Seleccionada imagen de {best_name} con {max_count} píxeles para {target_date}.")

        # out = process_final_lst(img_final_kelvin, uruguay)
        valid = has_valid_data(out.select("LST_Celsius").updateMask(out.select("alpha").eq(1)), uruguay)
        
        if not valid:
            print(f"No hay píxeles válidos dentro del rango térmico para {target_date}.")
            continue

        
        is_valid_python = out.select("alpha").reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=uruguay,
            scale=1000,
            maxPixels=1e8
        ).values().get(0).getInfo()

        if not is_valid_python or is_valid_python == 0:
            print(f"No hay píxeles válidos dentro del rango térmico para {target_date}. Saltando...")
            continue
                
        task, file_name = export_lst_image(out, target_date, "LST_Single_Export")

        print(f"Exportacion iniciada para {start_str}... esperando completion.")

        success = wait_for_task(task)

        if not success:
            return None, None

        gcs_path = f"gs://{BUCKET}/{file_name}.tif"
        print(f"Proceso finalizado con exito: {gcs_path}")
        return gcs_path, target_date

    return None, None

if __name__ == "__main__":
    result = lst3()
    print("Returned:", result)
