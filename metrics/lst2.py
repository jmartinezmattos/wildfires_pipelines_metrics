#Land Surface Temperature (LST)
import os
import ee
import datetime
from dotenv import load_dotenv
from metrics.lst import gap_fill
from utils import wait_for_task, uruguay, gee_authenticate
from db import wildfiresDB


load_dotenv("./config/.env")
BUCKET = os.getenv("BUCKET_NAME")
GEE_PROJECT = os.getenv("GEE_PROJECT")
CLOUD_ENV = os.getenv("CLOUD_ENV", "0").lower() == "1"

gee_authenticate(cloud_env=CLOUD_ENV, gee_project=GEE_PROJECT)
def get_valid_image(collection, scale=5000):
    """
    Verifica si la colección tiene imágenes y si la primera tiene píxeles reales sobre Uruguay.
    """
    if collection.size().getInfo() == 0:
        return None
    
    # img = ee.Image(collection.first())
    img = ee.Image(collection.mosaic())
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


def merge_sources(img_terra, img_aqua, img_viirs, source_terra, source_aqua, source_viirs):
    """
    Priority gap filling:
    Terra (base) → Aqua fills → VIIRS fills
    All images must already be scaled to Kelvin.
    """
    # img_final = None
    imgs = []
    sources = []
    
    # Priority: Terra first
    if img_terra is not None:
        # img_final = img_terra
        # source_final = source_terra
        imgs.append(img_terra)
        sources.append(source_terra)
    
    # Fill gaps with Aqua
    if img_aqua is not None:
        # if img_final:
        #     img_final = img_final.unmask(img_aqua)
        #     source_final = source_final.unmask(source_aqua)
        # else:
        #     img_final = img_aqua
        #     source_final = source_aqua
        imgs.append(img_aqua)
        sources.append(source_aqua)

    # Fill remaining gaps with VIIRS
    if img_viirs:
        # if img_final:
        #     img_final = img_final.unmask(img_viirs)
        #     source_final = source_final.unmask(source_viirs)
        # else:
        #     img_final = img_viirs
        #     source_final = source_viirs
        imgs.append(img_viirs)
        sources.append(source_viirs)
    if len(imgs) == 0:
        return None, None
    img_final = imgs[0]
    source_final = sources[0]
    for i in range(1, len(imgs)):
        img_final = img_final.unmask(imgs[i])
        source_final = source_final.unmask(sources[i])
    
    return img_final, source_final


def has_valid_data(img, region):
    stats = img.reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=region,
        scale=1000,
        maxPixels=1e13
    )
    
    count = stats.values().get(0)
    return ee.Number(count).gt(0)


def post_process(img):
    """
    Convert Kelvin → Celsius.
    """
    # img_cleaned=img.updateMask(img.gt(200))
    # img_cleaned=img.updateMask(img.gt(0))
    # img_cleaned=img.updateMask(img.neq(0))
    img_cleaned=img.subtract(273.15).rename("LST_Celsius")
    
    return img_cleaned.updateMask(img_cleaned.gt(-30).And(img_cleaned.lt(70)))
def alpha_band(img):

    mask = img.select("LST_Celsius").mask()
    #out = img.toFloat().addBands(mask.rename("alpha").toFloat())
    alpha = ee.Image.constant(1).clip(uruguay).rename("alpha")
    out = img.toFloat().addBands(alpha.toFloat())
    return out

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

def lst2():
    """
    Download LST for the last 1 day using cascade: MODIS -> VIIRS -> GOES
    """
    for i in range(7):
        # --- DATE RANGE: LAST 1 DAY ---
        target_date = datetime.date.today() - datetime.timedelta(days=i + 4)

        start_str, end_str = str(target_date), str(target_date + datetime.timedelta(days=1))
        terra_coll,  aqua_coll, viirs_coll = get_collections(start_str, end_str)
     
        # wildfiresdb = wildfiresDB()
        # try:
        #     if wildfiresdb.metric_exists(target_date, "lst"):
        #         print(f"LST ya existe en DB para {target_date}. Se omite exportacion.")
        #         continue
        # finally:
        #     wildfiresdb.close()


        img_terra = get_valid_image(terra_coll)
        if img_terra:
            img_terra = mask_modis_qa(img_terra)  # MODIS scale (Kelvin)
            img_terra = img_terra.select("LST_Day_1km").multiply(0.02).rename("LST")  # MODIS scale (Kelvin)
            source_terra = ee.Image.constant(1).updateMask(img_terra.mask()).rename("source_id")

        img_aqua = get_valid_image(aqua_coll)
        if img_aqua:
            img_aqua = mask_modis_qa(img_aqua)  # MODIS scale (Kelvin)
            img_aqua = img_aqua.select("LST_Day_1km").multiply(0.02).rename("LST")  # MODIS scale (Kelvin)
            source_aqua = ee.Image.constant(2).updateMask(img_aqua.mask()).rename("source_id")

        img_viirs = get_valid_image(viirs_coll)
        if img_viirs:
            img_viirs = mask_viirs_qa(img_viirs)  # VIIRS QA mask
            img_viirs = img_viirs.select("LST_1KM").multiply(0.00341802).rename("LST")  # VIIRS scale (Kelvin)
            source_viirs = ee.Image.constant(3).updateMask(img_viirs.mask()).rename("source_id")

        images_list = [img for img in [img_terra, img_aqua, img_viirs] if img is not None]

        if not images_list:
            print(f"No hay imágenes válidas para {target_date}. Saltando...")
            continue

        # # Merge usando prioridad: Terra > Aqua > VIIRS con unmask para máxima cobertura
        # img_final_kelvin = None
        # for img in images_list:
        #     if img_final_kelvin is None:
        #         img_final_kelvin = img
        #     else:
        #         img_final_kelvin = img_final_kelvin.unmask(img)
        

        img_final_kelvin, source_final = merge_sources(
            img_terra if img_terra else None,
            img_aqua if img_aqua else None,
            img_viirs if img_viirs else None,
            source_terra if img_terra else None,
            source_aqua if img_aqua else None,
            source_viirs if img_viirs else None,
        )

        lst_celsius = post_process(img_final_kelvin).clip(uruguay
        )
        if lst_celsius is None:
            print("No valid LST images found (Terra/Aqua/VIIRS). Skipping.")
            return None, None
        
                        
        stats = lst_celsius.reduceRegion(
            reducer=ee.Reducer.percentile([2, 98]),
            geometry=uruguay,
            scale=1000,
            maxPixels=1e8
        ).getInfo()

        # p2 = stats.get("LST_Celsius_p2")
        # p98 = stats.get("LST_Celsius_p98")
        # print("p2 es: ", p2)
        # print("p98 es: ", p98)


        lst_prepared = prepare_output_with_nodata(lst_celsius)
        
        valid = has_valid_data(lst_prepared, uruguay)
        
        if not valid or not valid.getInfo():
            print("No data available.")
            continue
        
        # 4. Post-procesamiento
        # out = post_process(img_final).clip(uruguay)

        
        out = alpha_band(lst_prepared)
        out = out.addBands(source_final.toFloat().clip(uruguay))
        # out = reproject(out)
        out = out.select(["LST_Celsius", "alpha", "source_id"])
        # 5. Exportacion
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
    result = lst2()
    print("Returned:", result)
