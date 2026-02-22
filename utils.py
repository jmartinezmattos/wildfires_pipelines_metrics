import ee
import time
import os
from dotenv import load_dotenv

load_dotenv("./config/.env")
GEE_PROJECT = os.getenv("GEE_PROJECT")
CLOUD_ENV = os.getenv("CLOUD_ENV", "False").lower() == "true"

def gee_authenticate(cloud_env: bool, gee_project: str):

    if cloud_env:
        print("Ejecutando en Cloud Run Job: inicializando con Service Account del job")
        ee.Initialize(project=gee_project)
    else:
        print("Ejecutando en entorno local: autenticación interactiva")
        ee.Authenticate()
        ee.Initialize(project=gee_project)

gee_authenticate(cloud_env=True, gee_project=GEE_PROJECT)

gaul = ee.FeatureCollection("FAO/GAUL/2015/level0")
uruguay = gaul.filter(ee.Filter.eq("ADM0_NAME", "Uruguay")).geometry()

def wait_for_task(task, poll=10):
    while True:
        status = task.status()
        state = status["state"]

        if state == "COMPLETED":
            return True
        elif state in ["FAILED", "CANCELLED"]:
            print("Task failed:", status.get("error_message"))
            return False

        time.sleep(poll)