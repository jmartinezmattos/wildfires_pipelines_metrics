import numpy as np
import mysql.connector
from mysql.connector import errorcode
import os
from dotenv import load_dotenv

load_dotenv("./config/.env")

METRICS_TABLE = "metrics"

DB_CONFIG = {
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "database": os.getenv("MYSQL_DB"),
    }

if os.getenv("MYSQL_CONNECTION_NAME"):
    DB_CONFIG['connection_name'] = os.getenv("MYSQL_CONNECTION_NAME")
elif os.getenv("MYSQL_HOST") and os.getenv("MYSQL_PORT"):
    DB_CONFIG['host'] = os.getenv("MYSQL_HOST")
    DB_CONFIG['port'] = int(os.getenv("MYSQL_PORT"))
else:
    raise ValueError("Database connection information is incomplete.")

class wildfiresDB:
    def __init__(self):
        if DB_CONFIG.get("connection_name"):
            self.db_config = {
                "user": DB_CONFIG.get("user"),
                "password": DB_CONFIG.get("password"),
                "database": DB_CONFIG.get("database"),
                "unix_socket": f"/cloudsql/{DB_CONFIG.get('connection_name')}",
            }
        else:
            self.db_config = {
                "user": DB_CONFIG.get("user"),
                "password": DB_CONFIG.get("password"),
                "database": DB_CONFIG.get("database"),
                "host": DB_CONFIG.get("host"),
                "port": DB_CONFIG.get("port"),
            }

        try:
            self.conn = mysql.connector.connect(**self.db_config)
            self.cursor = self.conn.cursor()
            print("Conexión a la base de datos establecida.")
        except mysql.connector.Error as err:
            print(f"No se pudo conectar a la base de datos: {err}")
            self.conn = None
            self.cursor = None

    def metric_exists(self, acq_datetime, metric_name):
        """Verifica si ya existe un registro para esa fecha y métrica."""
        if not self.conn or not self.cursor:
            return False
        
        sql = f"SELECT id FROM {METRICS_TABLE} WHERE acq_datetime = %s AND gcs_path LIKE %s LIMIT 1"
        # Usamos LIKE para verificar si el nombre de la métrica está en el path
        try:
            self.cursor.execute(sql, (acq_datetime, f"%/{metric_name}/%"))
            return self.cursor.fetchone() is not None
        except mysql.connector.Error as err:
            print(f"Error al verificar existencia: {err}")
            return False
        
    def insert_metric_register(self, gcs_path, acq_datetime, metric):

        if not self.conn or not self.cursor:
            print("Conexión a la base de datos no disponible.")
            return

        sql = f"""
        INSERT INTO {METRICS_TABLE} (
            acq_datetime,
            gcs_path,
            metric
        )
        VALUES (%s, %s, %s)
        """
        values = (acq_datetime, gcs_path, metric)

        try:
            self.cursor.execute(sql, values)
            self.conn.commit()
            print(f"Inserted metric {metric} record into database.")
        except mysql.connector.Error as err:
            print(f"Error MySQL: {err}")

    def close(self):
        """Cierra la conexión a la base de datos."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            print("Conexión a la base de datos cerrada.")