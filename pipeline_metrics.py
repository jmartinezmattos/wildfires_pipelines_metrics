import os
from metrics.fwi import fwi
from metrics.ndvi import ndvi
from metrics.lst import download_modis_lst
from utils import move_data_from_gcs_to_local
from metrics.download_aqua import export_modis_aqua_rgb

def pipeline_metrics(download_to_local=False):

    gcs_paths = []

    print("Starting data exports to GCS bucket...")
    
    fwi_path = fwi()
    if fwi_path:
        gcs_paths.append(fwi_path)
        print("FWI exported to:", fwi_path)
    
    ndvi_path = ndvi()
    if ndvi_path:
        gcs_paths.append(ndvi_path)
        print("NDVI exported to:", ndvi_path)
    
    lst_path = download_modis_lst()
    if lst_path:
        gcs_paths.append(lst_path)
        print("LST exported to:", lst_path)
    
    aqua_rgb_path = export_modis_aqua_rgb()
    if aqua_rgb_path:
        gcs_paths.append(aqua_rgb_path)
        print("MODIS AQUA RGB exported to:", aqua_rgb_path)
    
    print("All exports completed.")

    if download_to_local:
        local_dir = "data"
        os.makedirs(local_dir, exist_ok=True)
        move_data_from_gcs_to_local(gcs_paths, local_dir)

if __name__ == "__main__":

    pipeline_metrics()