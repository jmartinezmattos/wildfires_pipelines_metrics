import os
from metrics.fwi import fwi, fwi_multiple_days
from metrics.ndvi import ndvi, ndvi_multiple_days
from metrics.lst import lst, download_super_hybrid_lst
from metrics.lst2 import lst2
from metrics.download_aqua import rgb, export_modis_aqua_rgb_multiple_days
from utils import move_data_from_gcs_to_local
from db import wildfiresDB

wildfiresdb = wildfiresDB()

def pipeline_metrics(download_to_local=False):

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
 
    
    # lst_path, lst_date = lst()
    # print("starting LST export...")
    # if lst_path:
    #     gcs_paths.append(lst_path)
    #     print("LST exported to:", lst_path)
    #     wildfiresdb.insert_metric_register(
    #         gcs_path=lst_path,
    #         acq_datetime=lst_date,
    #         metric="LST"
    #     )
   
    lst_path, lst_date = lst2()
    print("starting LST export...")
    if lst_path:
        gcs_paths.append(lst_path)
        print("LST exported to:", lst_path)
        wildfiresdb.insert_metric_register(
            gcs_path=lst_path,
            acq_datetime=lst_date,
            metric="LST"
        )
    # resultadosLST = download_super_hybrid_lst(7)
    # lst_path, lst_date = lst()
    # print("LST multiple days export")
    # for lst_path, lst_date in resultadosLST:
    #     if lst_path:
    #         gcs_paths.append(lst_path)
    #         print("LST exported to:", lst_path)
    #         wildfiresdb.insert_metric_register(
    #             gcs_path=lst_path,
    #             acq_datetime=lst_date,
    #             metric="LST"
    #         )


    """
    # Exportar FWI para varios días y poblar la base de datos
      # Cambia este valor según lo que necesites poblar
    fwi_results = fwi_multiple_days(7)
    fwi_path, fwi_date = fwi()
    print("FWI multiple days export")
    for fwi_path, fwi_date in fwi_results:
        if fwi_path:
            gcs_paths.append(fwi_path)
            print("FWI exported to:", fwi_path)
            print("FWI date:", fwi_date)
            wildfiresdb.insert_metric_register(
                gcs_path=fwi_path,
                acq_datetime=fwi_date,
                metric="FWI"
            )
    
    # Exportar NDVI para varios días y poblar la base de datos
    ndvi_results = ndvi_multiple_days(7)
    ndvi_path, ndvi_date = ndvi()
    print("NDVI multiple days export")
    for ndvi_path, ndvi_date in ndvi_results:
        if ndvi_path:
            gcs_paths.append(ndvi_path)
            print("NDVI exported to:", ndvi_path)
            print("NDVI date:", ndvi_date)
            wildfiresdb.insert_metric_register(
                gcs_path=ndvi_path,
                acq_datetime=ndvi_date,
                metric="NDVI"
            )
    

    
    # Exportar RGB para varios días y poblar la base de datos
    aqua_rgb_results = export_modis_aqua_rgb_multiple_days(7)
    aqua_rgb_path, aqua_rgb_date = rgb()
    print("MODIS AQUA RGB multiple days export")
    for aqua_rgb_path, aqua_rgb_date in aqua_rgb_results:
        if aqua_rgb_path:
            gcs_paths.append(aqua_rgb_path)
            print("MODIS AQUA RGB exported to:", aqua_rgb_path)
            print("AQUA RGB date:", aqua_rgb_date)
            wildfiresdb.insert_metric_register(
                gcs_path=aqua_rgb_path,
                acq_datetime=aqua_rgb_date,
                metric="RGB"
            )
    
    resultadosLST = download_super_hybrid_lst(7)
    lst_path, lst_date = lst()
    print("LST multiple days export")
    for lst_path, lst_date in resultadosLST:
        if lst_path:
            gcs_paths.append(lst_path)
            print("LST exported to:", lst_path)
            wildfiresdb.insert_metric_register(
                gcs_path=lst_path,
                acq_datetime=lst_date,
                metric="LST"
            )

    
    """
    print("All exports completed.")

    if download_to_local:
        local_dir = "data"
        os.makedirs(local_dir, exist_ok=True)
        move_data_from_gcs_to_local(gcs_paths, local_dir)

if __name__ == "__main__":

    pipeline_metrics()