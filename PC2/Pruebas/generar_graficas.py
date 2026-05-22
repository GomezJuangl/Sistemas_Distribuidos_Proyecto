"""
Lee PC2/Pruebas/resultados.csv y genera gráficas PNG en PC2/Pruebas/graficas/.

Gráficas principales:
  1. curva_inflexion_vd1.png  — LÍNEA: VD1 vs hilos por escenario (curva de inflexión)
  2. vd2_red_limpia_vs_congestionada.png — BARRAS: VD2 sin iperf vs con iperf, por hilos
  3. distribucion_vd2_boxplot.png — BOX PLOT: distribución de las 30 mediciones VD2

Auxiliares (si hay datos):
  4. solicitudes_por_escenario.png — Barras agrupadas VD1
  5. latencia_por_escenario.png   — Barras agrupadas VD2

Los diseños se detectan dinámicamente desde resultados.csv.

Uso:
    python3 generar_graficas.py
"""

import glob
import os
import re
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")

CSV_PATH     = os.path.join(os.path.dirname(__file__), "resultados.csv")
GRAFICAS_DIR = os.path.join(os.path.dirname(__file__), "graficas")

_PALETTE = [
    "#4C72B0", "#55A868", "#DD8452", "#C44E52",
    "#8172B2", "#937860", "#DA8BC3", "#8C8C8C",
    "#CCB974", "#64B5CD",
]

ESCENARIO_LABEL = {
    "A": "Escenario A\n(1 intersección, 10 s)",
    "B": "Escenario B\n(2 intersecciones, 5 s)",
}


def _num_hilos(diseno: str) -> int:
    if diseno == "original":
        return 1
    m = re.fullmatch(r"multihilo_(\d+)", diseno)
    return int(m.group(1)) if m else 0


def _label(diseno: str) -> str:
    if diseno == "original":
        return "Original (1 hilo)"
    m = re.fullmatch(r"multihilo_(\d+)", diseno)
    return f"{m.group(1)} hilos" if m else diseno


def _short(diseno: str) -> str:
    if diseno == "original":
        return "1"
    m = re.fullmatch(r"multihilo_(\d+)", diseno)
    return m.group(1) if m else diseno


def _ordenar_disenos(disenos):
    return sorted(disenos, key=_num_hilos)


def cargar_datos() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"No se encontró {CSV_PATH}. Ejecuta medir_rendimiento.py primero.")
    df = pd.read_csv(CSV_PATH)
    df["escenario"] = df["escenario"].str.upper()
    df["diseno"] = df["diseno"].str.lower().replace({"multihilo": "multihilo_4"})
    return df


def _build_meta(df):
    disenos = _ordenar_disenos(df["diseno"].unique().tolist())
    color = {d: _PALETTE[i % len(_PALETTE)] for i, d in enumerate(disenos)}
    return disenos, color


def _guardar(fig, nombre):
    ruta = os.path.join(GRAFICAS_DIR, nombre)
    fig.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Guardada: {ruta}")


# ═══════════════════════════════════════════════════════════════════════════════
# GRÁFICA 1: CURVA DE INFLEXIÓN VD1 (la más importante)
# ═══════════════════════════════════════════════════════════════════════════════
def grafica_curva_inflexion_vd1(df):
    """Línea: eje X = hilos, eje Y = VD1 (solicitudes/2min), una línea por escenario.
    
    Muestra cómo el throughput sube con más hilos hasta un pico (punto óptimo)
    y luego baja por overhead de sincronización. Marca el punto máximo.
    """
    col = "vd1_mediana_registros_2min"
    if col not in df.columns:
        print("  [SKIP] No hay datos de VD1 para curva de inflexión.")
        return

    escenarios = sorted(df["escenario"].unique())
    esc_colors = {"A": "#4C72B0", "B": "#C44E52"}
    esc_markers = {"A": "o", "B": "s"}
    esc_labels = {
        "A": "Escenario A (1 intersección, 10 s)",
        "B": "Escenario B (2 intersecciones, 5 s)",
    }

    fig, ax = plt.subplots(figsize=(9, 5.5))
    todos_y = []

    for esc in escenarios:
        df_esc = df[df["escenario"] == esc].copy()
        df_esc["n_hilos"] = df_esc["diseno"].apply(_num_hilos)
        df_esc = df_esc[df_esc["n_hilos"] > 0].sort_values("n_hilos")
        if df_esc.empty:
            continue

        hilos = df_esc["n_hilos"].tolist()
        y = df_esc[col].tolist()
        c = esc_colors.get(esc, "#333")
        m = esc_markers.get(esc, "o")

        ax.plot(hilos, y, marker=m, linewidth=2.2, markersize=9,
                color=c, label=esc_labels.get(esc, esc), zorder=3)
        todos_y.extend(y)

        # Marcar el pico (máximo)
        if y:
            idx_max = y.index(max(y))
            ax.annotate(
                f"Pico: {y[idx_max]:.0f}\n({hilos[idx_max]} hilos)",
                xy=(hilos[idx_max], y[idx_max]),
                xytext=(15, 15), textcoords="offset points",
                ha="left", fontsize=9, fontweight="bold", color=c,
                arrowprops=dict(arrowstyle="->", color=c, lw=1.5),
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=c, alpha=0.8),
            )

    ax.set_title("Curva de Inflexión — Throughput VD1 vs Número de Hilos del Broker",
                 fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Número de hilos del broker", fontsize=11)
    ax.set_ylabel("Solicitudes almacenadas en BD / 2 min (mediana)", fontsize=11)
    ax.legend(title="Escenario", fontsize=10, loc="best")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.grid(axis="x", linestyle=":", alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)

    # Eje Y desde 0 para mostrar la magnitud real
    if todos_y:
        ax.set_ylim(0, max(todos_y) * 1.15)

    fig.tight_layout()
    _guardar(fig, "curva_inflexion_vd1.png")


# ═══════════════════════════════════════════════════════════════════════════════
# GRÁFICA 2: VD2 RED LIMPIA vs CONGESTIONADA
# ═══════════════════════════════════════════════════════════════════════════════
def grafica_vd2_red(df):
    """Barras agrupadas: VD2 sin iperf vs con iperf, para cada número de hilos.
    
    Si la columna 'red' existe en resultados.csv (valores: 'limpia' o 'congestionada'),
    muestra la comparación. Si no existe, muestra solo los datos disponibles como
    'red limpia' (que es el default).
    
    Los hilos que se muestran: original(1), 4, 32, 64 (selección representativa).
    """
    col = "vd2_mediana_ms"
    if col not in df.columns:
        print("  [SKIP] No hay datos de VD2.")
        return

    tiene_red = "red" in df.columns

    if tiene_red:
        estados_red = sorted(df["red"].unique())
    else:
        df = df.copy()
        df["red"] = "limpia"
        estados_red = ["limpia"]

    # Seleccionar un escenario para esta gráfica (B tiene más carga, más interesante)
    esc_preferido = "B" if "B" in df["escenario"].values else df["escenario"].iloc[0]
    df_esc = df[df["escenario"] == esc_preferido].copy()
    df_esc["n_hilos"] = df_esc["diseno"].apply(_num_hilos)
    df_esc = df_esc.sort_values("n_hilos")

    hilos_disponibles = sorted(df_esc["n_hilos"].unique())
    if not hilos_disponibles:
        print("  [SKIP] No hay datos para gráfica VD2 red.")
        return

    red_colors = {"limpia": "#55A868", "congestionada": "#C44E52"}
    red_labels = {"limpia": "Sin iperf3 (red limpia)", "congestionada": "Con iperf3 (red congestionada)"}

    fig, ax = plt.subplots(figsize=(max(8, len(hilos_disponibles) * 1.8), 5.5))

    x = list(range(len(hilos_disponibles)))
    n_grupos = len(estados_red)
    ancho = 0.35

    for i, red in enumerate(estados_red):
        valores = []
        for h in hilos_disponibles:
            fila = df_esc[(df_esc["n_hilos"] == h) & (df_esc["red"] == red)]
            valores.append(fila[col].values[0] if not fila.empty else 0)
        offset = (i - (n_grupos - 1) / 2) * ancho
        bars = ax.bar(
            [xi + offset for xi in x], valores, ancho,
            label=red_labels.get(red, red),
            color=red_colors.get(red, _PALETTE[i]),
            edgecolor="white", linewidth=0.8,
        )
        ax.bar_label(bars, fmt="%.1f", padding=4, fontsize=9, fontweight="bold")

    esc_txt = ESCENARIO_LABEL.get(esc_preferido, esc_preferido).replace("\n", " ")
    ax.set_title(f"Latencia VD2 — Red Limpia vs Congestionada\n({esc_txt})",
                 fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Número de hilos del broker", fontsize=11)
    ax.set_ylabel("Latencia VD2 — mediana (ms)", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([str(h) for h in hilos_disponibles], fontsize=10)
    ax.legend(fontsize=10, loc="upper left")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    _guardar(fig, "vd2_red_limpia_vs_congestionada.png")


# ═══════════════════════════════════════════════════════════════════════════════
# GRÁFICA 3: BOX PLOT VD2
# ═══════════════════════════════════════════════════════════════════════════════
def grafica_boxplot_vd2(df, disenos, color):
    """Box plot de la distribución de VD2 por caso (escenario × diseño)."""
    ORDEN = [(esc, dis) for esc in ["A", "B"] for dis in disenos
             if not df[(df["escenario"] == esc) & (df["diseno"] == dis)].empty]
    if not ORDEN:
        print("  [SKIP] No hay datos para box plot VD2.")
        return

    etiquetas = []
    for esc, dis in ORDEN:
        pref = "A" if esc == "A" else "B"
        etiquetas.append(f"{pref}\n{_short(dis)}h")
    colores = [color.get(dis, "#999") for _, dis in ORDEN]

    datos = []
    for esc, dis in ORDEN:
        patron = os.path.join(os.path.dirname(__file__), f"detalle_{esc}_{dis}.csv")
        archivos = glob.glob(patron)
        if archivos:
            df_d = pd.read_csv(archivos[0])
            valores = df_d[df_d["tipo"] == "vd2_ms"]["valor"].astype(float)
            valores = valores[valores >= 0].tolist()
        else:
            valores = []
        datos.append(valores)

    if not any(datos):
        print("  [SKIP] No se encontraron archivos detalle_*.csv para box plot.")
        return

    fig, ax = plt.subplots(figsize=(max(10, len(ORDEN) * 1.2), 5))
    bp = ax.boxplot(
        [d if d else [0] for d in datos],
        patch_artist=True,
        medianprops=dict(color="black", linewidth=2),
        whiskerprops=dict(linewidth=1.2),
        capprops=dict(linewidth=1.2),
        flierprops=dict(marker="o", markersize=4, alpha=0.5),
        widths=0.5,
    )
    for patch, c in zip(bp["boxes"], colores):
        patch.set_facecolor(c)
        patch.set_alpha(0.75)

    todos_vals = [v for d in datos for v in d]
    if todos_vals:
        import numpy as np
        p95 = float(np.percentile(todos_vals, 95))
        clip_max = max(p95 * 1.5, 10.0)
        ax.set_ylim(0, clip_max)

    ax.set_title("Distribución de Latencia VD2 por Caso\n(30 mediciones por caso)",
                 fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Escenario / Hilos", fontsize=11)
    ax.set_ylabel("Latencia (ms)", fontsize=11)
    ax.set_xticks(range(1, len(ORDEN) + 1))
    ax.set_xticklabels(etiquetas, fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    _guardar(fig, "distribucion_vd2_boxplot.png")


# ═══════════════════════════════════════════════════════════════════════════════
# GRÁFICAS AUXILIARES (barras por escenario)
# ═══════════════════════════════════════════════════════════════════════════════
def grafica_barras(df, disenos, color, columna, titulo, ylabel, nombre):
    escenarios = sorted(df["escenario"].unique())
    x = list(range(len(escenarios)))
    ancho = 0.8 / max(len(disenos), 1)

    fig, ax = plt.subplots(figsize=(max(7, len(disenos) * 1.5), 5))
    for i, diseno in enumerate(disenos):
        valores = []
        for esc in escenarios:
            fila = df[(df["escenario"] == esc) & (df["diseno"] == diseno)]
            valores.append(fila[columna].values[0] if not fila.empty else 0)
        offset = (i - (len(disenos) - 1) / 2) * ancho
        bars = ax.bar(
            [xi + offset for xi in x], valores, ancho,
            label=_label(diseno), color=color[diseno],
            edgecolor="white", linewidth=0.8,
        )
        ax.bar_label(bars, fmt="%.0f", padding=4, fontsize=9, fontweight="bold")

    ax.set_title(titulo, fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Escenario de carga", fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([ESCENARIO_LABEL.get(e, e) for e in escenarios], fontsize=10)
    ax.legend(title="Diseño del broker", fontsize=8)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    _guardar(fig, nombre)


def main():
    os.makedirs(GRAFICAS_DIR, exist_ok=True)
    df = cargar_datos()
    disenos, color = _build_meta(df)
    print(f"\n[OK] Datos cargados: {len(df)} filas")
    print(f"     Diseños: {disenos}")
    print("[...] Generando gráficas...\n")

    # Gráfica principal 1: curva de inflexión VD1
    grafica_curva_inflexion_vd1(df)

    # Gráfica principal 2: VD2 red limpia vs congestionada
    grafica_vd2_red(df)

    # Gráfica principal 3: box plot VD2
    grafica_boxplot_vd2(df, disenos, color)

    # Auxiliares
    if "vd1_mediana_registros_2min" in df.columns:
        grafica_barras(df, disenos, color,
                       "vd1_mediana_registros_2min",
                       "Solicitudes Almacenadas en la BD en 2 Minutos",
                       "Solicitudes almacenadas",
                       "solicitudes_por_escenario.png")
    if "vd2_mediana_ms" in df.columns:
        grafica_barras(df, disenos, color,
                       "vd2_mediana_ms",
                       "Latencia de Control de Semáforos (Mediana)",
                       "Latencia — mediana (ms)",
                       "latencia_por_escenario.png")

    print(f"\n[OK] Gráficas guardadas en {GRAFICAS_DIR}/")


if __name__ == "__main__":
    main()
