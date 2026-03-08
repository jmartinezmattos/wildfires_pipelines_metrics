# from metrics.fwi import fwi
from metrics.ndvi import ndvi
from metrics.lst2 import lst2
from metrics.lst3 import lst3
from metrics.download_aqua import rgb
from metrics.fwi_inumet import fwi
from db import wildfiresDB

wildfiresdb = wildfiresDB()

def pipeline_metrics():

    gcs_paths = []

    print("Starting data exports to GCS bucket...")
     
    fwi_path, fwi_date = fwi()
    print("starting FWI export...")
    if fwi_path:
        gcs_paths.append(fwi_path)
        print("FWI exported to: " + fwi_path)
        print("FWI date: " + str(fwi_date))
        wildfiresdb.insert_metric_register(
            gcs_path=fwi_path,
            acq_datetime=fwi_date,
            metric="FWI"
        )

    
        
    ndvi_path, ndvi_date = ndvi()
    print("starting NDVI export...")
    if ndvi_path:
        gcs_paths.append(ndvi_path)
        print("NDVI exported to:", ndvi_path)
        print("NDVI date:", ndvi_date)
        wildfiresdb.insert_metric_register(
            gcs_path=ndvi_path,
            acq_datetime=ndvi_date,
            metric="NDVI"
        )

    aqua_rgb_path, aqua_rgb_date = rgb()
    print("starting MODIS AQUA RGB export...")
    if aqua_rgb_path:
            gcs_paths.append(aqua_rgb_path)
            print("MODIS AQUA RGB exported to:", aqua_rgb_path)
            print("AQUA RGB date:", aqua_rgb_date)
            wildfiresdb.insert_metric_register(
                gcs_path=aqua_rgb_path,
                acq_datetime=aqua_rgb_date,
                metric="RGB"
        )
 
    # lst_path, lst_date = lst2()
    # print("starting LST export...")
    # if lst_path:
    #     gcs_paths.append(lst_path)
    #     print("LST exported to:", lst_path)
    #     wildfiresdb.insert_metric_register(
    #         gcs_path=lst_path,
    #         acq_datetime=lst_date,
    #         metric="LST"
    #     )
 
    lst_path, lst_date = lst3()
    print("starting LST export...")
    if lst_path:
        gcs_paths.append(lst_path)
        print("LST exported to:", lst_path)
        wildfiresdb.insert_metric_register(
            gcs_path=lst_path,
            acq_datetime=lst_date,
            metric="LST"
        )

    print("All exports completed.")

if __name__ == "__main__":

    pipeline_metrics()