from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from metrics.fwi_inumet import fwi
from db import wildfiresDB

tz_uy = ZoneInfo("America/Montevideo")
today_uy = datetime.now(tz_uy).date()

print("Starting FWI export (last 10 days)...")

wildfiresdb = wildfiresDB()

for i in range(10):

    target_date = today_uy - timedelta(days=i)
    print(f"\nProcessing FWI for date: {target_date}")

    fwi_path, fwi_date = fwi(target_date)

    if fwi_path:

        print("FWI exported to: " + fwi_path)
        print("FWI date: " + str(fwi_date))

        wildfiresdb.insert_metric_register(
            gcs_path=fwi_path,
            acq_datetime=fwi_date,
            metric="FWI"
        )
    else:
        print(f"FWI failed for date: {target_date}")