from google.cloud import run_v2
import pandas as pd
import os

# ==============================
# CONFIG
# ==============================

PROJECT_ID = "wildfires-479718"
REGION = "europe-west1"
JOB_NAME = "wildfires-pipeline-metrics"
#JOB_NAME = "wildfires-pipeline-batch-download"
JOB_NAME = "wildfires-pipeline-inference-multiband"
#JOB_NAME = "wildfires-pipeline-inference"
JOB_NAME = "wildfires-pipeline-batch-region-no-gpu"

# Precios aproximados Cloud Run (USD)
CPU_PRICE = 0.000018      # por vCPU-segundo
MEM_PRICE = 0.000002     # por GB-segundo
GPU_PRICE = 0.0001867       # por GPU-segundo

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


def parse_gpu(gpu_str):
    """Convierte GPU a float"""
    if gpu_str is None:
        return 0
    return float(gpu_str)


# ==============================
# OBTENER RECURSOS DEL JOB
# ==============================

def get_job_resources(project_id, region, job_name):
    client = run_v2.JobsClient()

    job_path = f"projects/{project_id}/locations/{region}/jobs/{job_name}"
    job = client.get_job(name=job_path)

    container = job.template.template.containers[0]

    limits = container.resources.limits

    cpu_str = limits.get("cpu", "1000m")
    memory_str = limits.get("memory", "512Mi")
    gpu_str = limits.get("nvidia.com/gpu", "0")

    cpu = parse_cpu(cpu_str)
    memory_gb = parse_memory(memory_str)
    gpu = parse_gpu(gpu_str)

    task_count = job.template.task_count or 1

    return cpu, memory_gb, gpu, task_count


# ==============================
# COSTO ESTIMADO
# ==============================

def estimate_costs(duration_seconds, cpu, memory_gb, gpu, task_count):
    if duration_seconds is None:
        return None, None, None, None

    cost_cpu = cpu * duration_seconds * CPU_PRICE * task_count
    cost_memory = memory_gb * duration_seconds * MEM_PRICE * task_count
    cost_gpu = gpu * duration_seconds * GPU_PRICE * task_count

    total_cost = cost_cpu + cost_memory + cost_gpu

    return cost_cpu, cost_memory, cost_gpu, total_cost


# ==============================
# EJECUCIONES
# ==============================

def get_job_executions(project_id, region, job_name, cpu, memory_gb, gpu, task_count):
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

        cost_cpu, cost_memory, cost_gpu, total_cost = estimate_costs(
            duration, cpu, memory_gb, gpu, task_count
        )

        # obtener args
        try:
            args = exec.template.template.containers[0].args
            args_str = " ".join(args) if args else ""
        except Exception:
            args_str = ""

        data.append({
            "execution_id": exec_id,
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration,
            "cpu": cpu,
            "memory_gb": memory_gb,
            "gpu": gpu,
            "task_count": task_count,
            "args": args_str,
            "cost_cpu": cost_cpu,
            "cost_memory": cost_memory,
            "cost_gpu": cost_gpu,
            "estimated_cost_usd": total_cost
        })

    return pd.DataFrame(data)


# ==============================
# MAIN
# ==============================

def main():
    print("🔧 Obteniendo configuración del job...")

    cpu, memory_gb, gpu, task_count = get_job_resources(
        PROJECT_ID, REGION, JOB_NAME
    )

    print(f"CPU: {cpu}")
    print(f"Memoria (GB): {memory_gb}")
    print(f"GPU: {gpu}")
    print(f"Task count: {task_count}")

    print("\n🔎 Obteniendo ejecuciones...")

    df = get_job_executions(
        PROJECT_ID, REGION, JOB_NAME, cpu, memory_gb, gpu, task_count
    )

    if df.empty:
        print("⚠️ No se encontraron ejecuciones")
        return

    # ordenar por fecha
    df = df.sort_values(by="start_time", ascending=False)

    # exportar CSV
    output_dir = "data/costs"
    os.makedirs(output_dir, exist_ok=True)

    output_file = f"{output_dir}/cloud_run_jobs_with_estimated_cost_{JOB_NAME}.csv"
    df.to_csv(output_file, index=False)

    print(f"\n✅ CSV generado: {output_file}")
    print(df.head())


if __name__ == "__main__":
    main()