import os
import datetime
from zoneinfo import ZoneInfo
import ee
from dotenv import load_dotenv


load_dotenv("./config/.env")
GEE_PROJECT = os.getenv("GEE_PROJECT")
CLOUD_ENV = os.getenv("CLOUD_ENV", "0").lower() == "1"


def gee_authenticate(cloud_env: bool, gee_project: str) -> None:
    if cloud_env:
        print("Ejecutando en Cloud Run Job: inicializando con Service Account del job")
        ee.Initialize(project=gee_project)
    else:
        print("Ejecutando en entorno local: autenticación interactiva")
        ee.Authenticate()
        ee.Initialize(project=gee_project)


def main() -> None:
    gee_authenticate(cloud_env=CLOUD_ENV, gee_project=GEE_PROJECT)

    uruguay = (
        ee.FeatureCollection("FAO/GAUL/2015/level0")
        .filter(ee.Filter.eq("ADM0_NAME", "Uruguay"))
        .geometry()
    )

    # Cambiar esto a MYD11A1 (MODIS/Aqua)
    coll = (
        ee.ImageCollection("MODIS/061/MYD11A1")
        .filterBounds(uruguay)
        .sort("system:time_start", False)
        .limit(10)
    )
    images = coll.toList(10)
    uy_tz = ZoneInfo("America/Montevideo")
    # Aproximación: usar longitud del centroide de Uruguay para pasar de hora solar local a UTC.
    lon_uy = ee.Geometry(uruguay).centroid(1000).coordinates().get(0).getInfo()

    for i in range(10):
        img = ee.Image(images.get(i))
        if img is None:
            continue

        index = img.get("system:index").getInfo()
        product_date = index.replace("_", "-") if isinstance(index, str) else "unknown_date"

        # En MYD11A1 hay 'Day_view_time' (LST diurna) y 'Night_view_time' (LST nocturna)
        # Aquí tomamos la diurna como ejemplo
        band_name = "Day_view_time"

        view_time = img.select(band_name).reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=uruguay,
            scale=1000,
            maxPixels=1e9,
        ).get(band_name).getInfo()

        if view_time is None:
            print(f"{product_date} no_{band_name}")
            continue

        # Day_view_time está en [0, 240] unidades de 0.1 h → 0.0 a 24.0 h
        solar_local_hours = float(view_time) * 0.1
        utc_hours = solar_local_hours - (float(lon_uy) / 15.0)

        d = datetime.datetime.strptime(product_date, "%Y-%m-%d").date()
        dt_utc = datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc) + datetime.timedelta(
            hours=utc_hours
        )
        dt_uy = dt_utc.astimezone(uy_tz)
        print(dt_uy.strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
