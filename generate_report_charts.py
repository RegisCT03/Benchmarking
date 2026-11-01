#!/usr/bin/env python3
"""
Generador de Gráficas y Análisis Estadístico para el Reporte de Métricas
Asignatura: Bases de Datos en la Nube - IT2iD (UP Chiapas)
Consolida results_mongo.csv y results_postgres.csv en results_final.csv
y genera las figuras requeridas por la sección 8.3 del Playbook.
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Configuración visual para publicaciones académicas
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['axes.edgecolor'] = '#cccccc'
plt.rcParams['axes.linewidth'] = 0.8


def consolidar_resultados(mongo_csv="results_mongo.csv", pg_csv="results_postgres.csv", final_csv="results_final.csv"):
    dfs = []
    if os.path.exists(mongo_csv):
        df_m = pd.read_csv(mongo_csv)
        dfs.append(df_m)
        print(f" -> Cargado {mongo_csv}: {len(df_m)} filas")
    else:
        print(f" [AVISO] No se encontró {mongo_csv}")

    if os.path.exists(pg_csv):
        df_p = pd.read_csv(pg_csv)
        dfs.append(df_p)
        print(f" -> Cargado {pg_csv}: {len(df_p)} filas")
    else:
        print(f" [AVISO] No se encontró {pg_csv}")

    if not dfs:
        print("[ERROR] No hay datos disponibles para consolidar.")
        sys.exit(1)

    df_final = pd.concat(dfs, ignore_index=True)
    df_final.to_csv(final_csv, index=False)
    print(f"[OK] Archivo consolidado guardado en {final_csv} con {len(df_final)} filas totales.")
    return df_final


def generar_grafica_p99_concurrencia(df, output_dir):
    """Figura 1: Latencia P99 vs Concurrencia por Perfil y Consulta."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharey=False)
    
    # Q1
    df_q1 = df[df['query_id'] == 'Q1'].copy()
    avg_q1 = df_q1.groupby(['engine', 'profile', 'concurrency'])['latency_p99_ms'].mean().reset_index()
    
    sns.lineplot(
        data=avg_q1, x='concurrency', y='latency_p99_ms', hue='engine', style='profile',
        markers=True, dashes=False, linewidth=2.2, markersize=8, ax=axes[0],
        palette={'mongodb': '#13aa52', 'postgresql': '#336791'}
    )
    axes[0].set_title("Q1: Unwind & Agrupación (CPU-Bound) - Latencia P99", fontsize=12, fontweight='bold', pad=10)
    axes[0].set_xlabel("Clientes Concurrentes", fontsize=11)
    axes[0].set_ylabel("Latencia P99 (ms)", fontsize=11)
    axes[0].set_xticks([1, 10, 50])
    axes[0].grid(True, linestyle="--", alpha=0.6)

    # Q2
    df_q2 = df[df['query_id'] == 'Q2'].copy()
    avg_q2 = df_q2.groupby(['engine', 'profile', 'concurrency'])['latency_p99_ms'].mean().reset_index()

    sns.lineplot(
        data=avg_q2, x='concurrency', y='latency_p99_ms', hue='engine', style='profile',
        markers=True, dashes=False, linewidth=2.2, markersize=8, ax=axes[1],
        palette={'mongodb': '#13aa52', 'postgresql': '#336791'}
    )
    axes[1].set_title("Q2: Sort Masivo & Top-K (Memory-Bound) - Latencia P99", fontsize=12, fontweight='bold', pad=10)
    axes[1].set_xlabel("Clientes Concurrentes", fontsize=11)
    axes[1].set_ylabel("Latencia P99 (ms)", fontsize=11)
    axes[1].set_xticks([1, 10, 50])
    axes[1].grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    path_out = os.path.join(output_dir, "p99_vs_concurrency.png")
    plt.savefig(path_out, dpi=300)
    plt.close()
    print(f" [OK] Gráfica generada: {path_out}")


def generar_grafica_throttling_qps(df, output_dir):
    """Figura 2: Throughput (QPS) vs CPU Throttled Seconds."""
    fig, ax = plt.subplots(figsize=(9, 5.5))

    sns.scatterplot(
        data=df, x='cpu_throttled_seconds', y='throughput_qps',
        hue='engine', style='profile', size='concurrency', sizes=(40, 200),
        alpha=0.85, ax=ax,
        palette={'mongodb': '#13aa52', 'postgresql': '#336791'}
    )
    
    ax.set_title("Impacto de CFS Throttling sobre Throughput (QPS)", fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel("Tiempo Acumulado Estrangulado por CPU (segundos)", fontsize=11)
    ax.set_ylabel("Throughput (QPS)", fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    path_out = os.path.join(output_dir, "throttling_vs_qps.png")
    plt.savefig(path_out, dpi=300)
    plt.close()
    print(f" [OK] Gráfica generada: {path_out}")


def generar_grafica_rss(df, output_dir):
    """Figura 3: Huella de Memoria Física Residente (max_rss_mb)."""
    fig, ax = plt.subplots(figsize=(10, 5))

    avg_rss = df.groupby(['engine', 'profile'])['max_rss_mb'].mean().reset_index()

    sns.barplot(
        data=avg_rss, x='profile', y='max_rss_mb', hue='engine',
        palette={'mongodb': '#13aa52', 'postgresql': '#336791'},
        ax=ax, edgecolor='black', linewidth=0.8, alpha=0.9
    )

    ax.set_title("Huella de Memoria Residente (RSS) por Perfil de Contención", fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel("Perfil de Recursos (cgroups v2)", fontsize=11)
    ax.set_ylabel("Memoria RAM Física Promedio (MB)", fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.5, axis='y')

    # Añadir etiquetas con los valores encima de cada barra
    for p in ax.patches:
        val = p.get_height()
        if val > 0:
            ax.annotate(f"{val:.1f} MB", (p.get_x() + p.get_width() / 2., val),
                        ha='center', va='bottom', fontsize=9, xytext=(0, 3),
                        textcoords='offset points', fontweight='semibold')

    plt.tight_layout()
    path_out = os.path.join(output_dir, "rss_memory_footprint.png")
    plt.savefig(path_out, dpi=300)
    plt.close()
    print(f" [OK] Gráfica generada: {path_out}")


def generar_grafica_throughput(df, output_dir):
    """Figura 4: Throughput por Motor, Perfil y Concurrencia."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharey=False)

    for idx, qid in enumerate(['Q1', 'Q2']):
        df_q = df[df['query_id'] == qid]
        avg_q = df_q.groupby(['engine', 'profile', 'concurrency'])['throughput_qps'].mean().reset_index()

        sns.barplot(
            data=avg_q, x='concurrency', y='throughput_qps', hue='engine',
            palette={'mongodb': '#13aa52', 'postgresql': '#336791'},
            ax=axes[idx], edgecolor='black', linewidth=0.6, alpha=0.88
        )
        axes[idx].set_title(f"Throughput {qid} vs Concurrencia", fontsize=12, fontweight='bold')
        axes[idx].set_xlabel("Clientes Concurrentes", fontsize=11)
        axes[idx].set_ylabel("Throughput Promedio (QPS)", fontsize=11)
        axes[idx].grid(True, linestyle="--", alpha=0.5, axis='y')

    plt.tight_layout()
    path_out = os.path.join(output_dir, "throughput_comparison.png")
    plt.savefig(path_out, dpi=300)
    plt.close()
    print(f" [OK] Gráfica generada: {path_out}")


def main():
    output_dir = os.path.join("reporte", "graficos")
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 65)
    print(" GENERADOR DE ANÁLISIS GRÁFICO - PLAYBOOK EXPERIMENTAL")
    print("=" * 65)

    df = consolidar_resultados()
    
    print("\nGenerando figuras visuales para el reporte...")
    generar_grafica_p99_concurrencia(df, output_dir)
    generar_grafica_throttling_qps(df, output_dir)
    generar_grafica_rss(df, output_dir)
    generar_grafica_throughput(df, output_dir)

    print("\n" + "=" * 65)
    print(" TODAS LAS GRÁFICAS SE HAN GENERADO CORRECTAMENTE EN:")
    print(f" {os.path.abspath(output_dir)}")
    print("=" * 65)


if __name__ == "__main__":
    main()
