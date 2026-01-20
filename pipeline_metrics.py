import os
from metrics.fwi import fwi
from metrics.ndvi import ndvi
from metrics.lst import download_modis_lst
from utils import move_data_from_gcs_to_local
from metrics.download_aqua import export_modis_aqua_rgb
from db import wildfiresDB

wildfiresdb = wildfiresDB()

def pipeline_metrics(download_to_local=False):

    gcs_paths = []

    print("Starting data exports to GCS bucket...")
    
    fwi_path, fwi_date = fwi()
    if fwi_path:
        gcs_paths.append(fwi_path)
        print("FWI exported to:", fwi_path)
        print("FWI date:", fwi_date)
        wildfiresdb.insert_metric_register(
            gcs_path=fwi_path,
            acq_datetime=fwi_date,
            metric="FWI"
        )
    
    ndvi_path, ndvi_date = ndvi()
    if ndvi_path:
        gcs_paths.append(ndvi_path)
        print("NDVI exported to:", ndvi_path)
        print("NDVI date:", ndvi_date)
        wildfiresdb.insert_metric_register(
            gcs_path=ndvi_path,
            acq_datetime=ndvi_date,
            metric="NDVI"
        )
    
    lst_path, lst_date = download_modis_lst()
    if lst_path:
        gcs_paths.append(lst_path)
        print("LST exported to:", lst_path)
        wildfiresdb.insert_metric_register(
            gcs_path=lst_path,
            acq_datetime=lst_date,
            metric="LST"
        )
    
    aqua_rgb_path, aqua_rgb_date = export_modis_aqua_rgb()
    if aqua_rgb_path:
        gcs_paths.append(aqua_rgb_path)
        print("MODIS AQUA RGB exported to:", aqua_rgb_path)
        print("AQUA RGB date:", aqua_rgb_date)
        wildfiresdb.insert_metric_register(
            gcs_path=aqua_rgb_path,
            acq_datetime=aqua_rgb_date,
            metric="RGB"
        )
    
    print("All exports completed.")

    if download_to_local:
        local_dir = "data"
        os.makedirs(local_dir, exist_ok=True)
        move_data_from_gcs_to_local(gcs_paths, local_dir)

if __name__ == "__main__":

    pipeline_metrics()