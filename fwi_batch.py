from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from metrics.fwi_inumet import fwi
from db import wildfiresDB
from tqdm.auto import tqdm
import os


def process_day(target_date):
    """
    Worker function executed in parallel.
    Returns errors instead of crashing the pool.
    """
    try:
        fwi_path, fwi_date = fwi(target_date)
        return target_date, fwi_path, fwi_date, None
    except Exception as e:
        return target_date, None, None, str(e)


if __name__ == "__main__":

    # ---- Config ----
    N_DAYS = 1100
    MAX_WORKERS = min(6, os.cpu_count() or 4)  # Safe default for Windows
    # -----------------

    tz_uy = ZoneInfo("America/Montevideo")
    today_uy = datetime.now(tz_uy).date()

    print(f"Starting FWI export (last {N_DAYS} days)...")
    print(f"Using {MAX_WORKERS} workers\n")

    # Generate date list
    dates = [
        today_uy - timedelta(days=N_DAYS - i)
        for i in range(N_DAYS)
    ]

    # Create DB connection in main thread only
    wildfiresdb = wildfiresDB()

    success_count = 0
    error_count = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        futures = [executor.submit(process_day, d) for d in dates]

        for future in tqdm(as_completed(futures),
                           total=len(futures),
                           desc="Processing FWI",
                           unit="day"):

            target_date, fwi_path, fwi_date, error = future.result()

            if error:
                error_count += 1
                print(f"\nError on {target_date}: {error}")
                continue

            if fwi_path:
                try:
                    wildfiresdb.insert_metric_register(
                        gcs_path=fwi_path,
                        acq_datetime=fwi_date,
                        metric="FWI"
                    )
                    success_count += 1
                except Exception as db_error:
                    error_count += 1
                    print(f"\nDB error on {target_date}: {db_error}")
            else:
                error_count += 1
                print(f"\nFWI returned empty for {target_date}")

    print("\n----------------------------")
    print(f"Finished.")
    print(f"Successful: {success_count}")
    print(f"Errors:     {error_count}")
    print("----------------------------")