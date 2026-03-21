from google.cloud import run_v2
import pandas as pd

# ==============================
# CONFIG
# ==============================

PROJECT_ID = "wildfires-479718"
REGION = "europe-west1"
JOB_NAME = "wildfires-pipeline-metrics"

# Precios aproximados Cloud Run (USD)
CPU_PRICE = 0.000024      # por vCPU-segundo
MEM_PRICE = 0.0000025     # por GB-segundo

#TODO agregar GPU para calcular el del pipeline inferences

# ==============================
# PARSERS
# ==============================

def parse_cpu(cpu_str):
    """Convierte CPU tipo '1000m' -> 1.0"""
    if cpu_str.endswith("m"):
        return float(cpu_str.replace("m", "")) / 1000
    return float(cpu_str)


def parse_memory(memory_str):
    """Convierte memoria a GB"""
    if "Mi" in memory_str:
        return float(memory_str.replace("Mi", "")) / 1024
    elif "Gi" in memory_str:
        return float(memory_str.replace("Gi", ""))
    return 0.5  # fallback


# ==============================
# OBTENER RECURSOS DEL JOB
# ==============================

def get_job_resources(project_id, region, job_name):
    client = run_v2.JobsClient()

    job_path = f"projects/{project_id}/locations/{region}/jobs/{job_name}"
    job = client.get_job(name=job_path)

    container = job.template.template.containers[0]

    cpu_str = container.resources.limits.get("cpu", "1000m")
    memory_str = container.resources.limits.get("memory", "512Mi")

    cpu = parse_cpu(cpu_str)
    memory_gb = parse_memory(memory_str)

    task_count = job.template.task_count or 1

    return cpu, memory_gb, task_count


# ==============================
# COSTO ESTIMADO
# ==============================

def estimate_cost(duration_seconds, cpu, memory_gb, task_count):
    if duration_seconds is None:
        return None

    total_cpu_cost = cpu * duration_seconds * CPU_PRICE * task_count
    total_mem_cost = memory_gb * duration_seconds * MEM_PRICE * task_count

    return total_cpu_cost + total_mem_cost


# ==============================
# EJECUCIONES
# ==============================

def get_job_executions(project_id, region, job_name, cpu, memory_gb, task_count):
    client = run_v2.ExecutionsClient()

    parent = f"projects/{project_id}/locations/{region}/jobs/{job_name}"

    executions = list(client.list_executions(parent=parent))

    print(f"Se encontraron {len(executions)} ejecuciones")

    data = []

    for exec in executions:
        exec_id = exec.name.split("/")[-1]

        start_time = exec.start_time
        end_time = exec.completion_time

        duration = None
        if start_time and end_time:
            duration = (end_time - start_time).total_seconds()

        estimated_cost = estimate_cost(duration, cpu, memory_gb, task_count)

        data.append({
            "execution_id": exec_id,
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration,
            "cpu": cpu,
            "memory_gb": memory_gb,
            "task_count": task_count,
            "estimated_cost_usd": estimated_cost
        })

    return pd.DataFrame(data)


# ==============================
# MAIN
# ==============================

def main():
    print("🔧 Obteniendo configuración del job...")

    cpu, memory_gb, task_count = get_job_resources(PROJECT_ID, REGION, JOB_NAME)

    print(f"CPU: {cpu}")
    print(f"Memoria (GB): {memory_gb}")
    print(f"Task count: {task_count}")

    print("\n🔎 Obteniendo ejecuciones...")

    df = get_job_executions(PROJECT_ID, REGION, JOB_NAME, cpu, memory_gb, task_count)

    if df.empty:
        print("⚠️ No se encontraron ejecuciones")
        return

    # ordenar por fecha
    df = df.sort_values(by="start_time", ascending=False)

    # exportar CSV
    output_file = f"cloud_run_jobs_with_estimated_cost_{JOB_NAME}.csv"
    df.to_csv(output_file, index=False)

    print(f"\n✅ CSV generado: {output_file}")
    print(df.head())


if __name__ == "__main__":
    main()