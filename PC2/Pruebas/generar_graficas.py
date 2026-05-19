"""
Lee PC2/Pruebas/resultados.csv y genera 4 gráficas PNG en PC2/Pruebas/graficas/.

Gráficas:
  1. Barras agrupadas — Solicitudes almacenadas en 2 min (por escenario y diseño)
  2. Barras agrupadas — Latencia de control de semáforos en ms (por escenario y diseño)
  3. Barras — Factor de escala Escenario 1 → Escenario 2 (cuánto creció cada diseño)
  4. Box plot — Distribución de VD2 por caso (consistencia de cada diseño)

Uso:
    python3 generar_graficas.py
"""

import glob
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")

CSV_PATH     = os.path.join(os.path.dirname(__file__), "resultados.csv")
GRAFICAS_DIR = os.path.join(os.path.dirname(__file__), "graficas")

# ─── Etiquetas de presentación ────────────────────────────────────────────────
DISENOS = ["original", "multihilo_2", "multihilo_4", "multihilo_8"]
DISENO_LABEL = {
    "original": "Diseño Original",
    "multihilo_2": "Multihilo 2 hilos",
    "multihilo_4": "Multihilo 4 hilos",
    "multihilo_8": "Multihilo 8 hilos",
}
DISENO_SHORT = {
    "original": "Orig",
    "multihilo_2": "MT-2",
    "multihilo_4": "MT-4",
    "multihilo_8": "MT-8",
}
DISENO_COLOR = {
    "original": "#4C72B0",
    "multihilo_2": "#55A868",
    "multihilo_4": "#DD8452",
    "multihilo_8": "#C44E52",
}
ESCENARIO_LABEL = {
    "A": "Escenario 1\n(1 sensor, 10 s)",
    "B": "Escenario 2\n(2 sensores, 5 s)",
}
# ──────────────────────────────────────────────────────────────────────────────


def cargar_datos() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(
            f"No se encontró {CSV_PATH}. Ejecuta medir_rendimiento.py primero."
        )
    df = pd.read_csv(CSV_PATH)
    df["escenario"] = df["escenario"].str.upper()
    df["diseno"]    = df["diseno"].str.lower().replace({"multihilo": "multihilo_4"})
    return df


def _guardar(fig, nombre):
    ruta = os.path.join(GRAFICAS_DIR, nombre)
    fig.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Guardada: {ruta}")


def grafica_barras(df, columna, titulo, ylabel, nombre):
    """Barras agrupadas: eje X = escenarios, barras = diseños."""
    escenarios = sorted(df["escenario"].unique())
    disenos    = DISENOS
    x          = list(range(len(escenarios)))
    ancho      = 0.8 / max(len(disenos), 1)

    fig, ax = plt.subplots(figsize=(7, 5))

    for i, diseno in enumerate(disenos):
        valores = []
        for esc in escenarios:
            fila = df[(df["escenario"] == esc) & (df["diseno"] == diseno)]
            valores.append(fila[columna].values[0] if not fila.empty else 0)
        offset = (i - (len(disenos) - 1) / 2) * ancho
        bars = ax.bar(
            [xi + offset for xi in x], valores, ancho,
            label=DISENO_LABEL[diseno], color=DISENO_COLOR[diseno],
            edgecolor="white", linewidth=0.8,
        )
        ax.bar_label(bars, fmt="%.0f", padding=4, fontsize=10, fontweight="bold")

    ax.set_title(titulo, fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Escenario de carga", fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([ESCENARIO_LABEL.get(e, e) for e in escenarios], fontsize=10)
    ax.legend(title="Diseño del broker", fontsize=10)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    _guardar(fig, nombre)


def grafica_escala(df, columna, titulo, ylabel, nombre):
    """Barras del factor de escala Escenario 1 → Escenario 2 para cada diseño."""
    disenos = DISENOS
    factores = []
    for diseno in disenos:
        val_a = df[(df["escenario"] == "A") & (df["diseno"] == diseno)][columna]
        val_b = df[(df["escenario"] == "B") & (df["diseno"] == diseno)][columna]
        if not val_a.empty and not val_b.empty and val_a.values[0] != 0:
            factores.append(val_b.values[0] / val_a.values[0])
        else:
            factores.append(0)

    fig, ax = plt.subplots(figsize=(6, 5))
    bars = ax.bar(
        [DISENO_LABEL[d] for d in disenos],
        factores,
        color=[DISENO_COLOR[d] for d in disenos],
        width=0.55,
        edgecolor="white", linewidth=0.8,
    )
    ax.bar_label(bars, fmt="%.2f×", padding=5, fontsize=11, fontweight="bold")
    ax.axhline(y=1, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)

    ax.set_title(titulo, fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Diseño del broker", fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    max_factor = max(factores) if any(factores) else 1
    ax.set_ylim(0, max_factor * 1.25)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    _guardar(fig, nombre)


def grafica_boxplot_vd2():
    """Box plot de la distribución de VD2 por caso, usando los detalle_*.csv."""
    ORDEN = [(esc, dis) for esc in ["A", "B"] for dis in DISENOS]
    ETIQUETAS = []
    for esc in ["A", "B"]:
        pref = "E1" if esc == "A" else "E2"
        for dis in DISENOS:
            ETIQUETAS.append(f"{pref}\n{DISENO_SHORT[dis]}")
    COLORES = [DISENO_COLOR[dis] for _, dis in ORDEN]

    datos = []
    disponibles = []
    for esc, dis in ORDEN:
        patron = os.path.join(os.path.dirname(__file__), f"detalle_{esc}_{dis}.csv")
        archivos = glob.glob(patron)
        if not archivos and dis == "multihilo_4":
            archivos = glob.glob(
                os.path.join(os.path.dirname(__file__), f"detalle_{esc}_multihilo.csv")
            )
        if archivos:
            df_d = pd.read_csv(archivos[0])
            valores = df_d[df_d["tipo"] == "vd2_ms"]["valor"].astype(float)
            valores = valores[valores >= 0].tolist()
        else:
            valores = []
        datos.append(valores)
        disponibles.append(bool(valores))

    if not any(disponibles):
        print("  [SKIP] No se encontraron archivos detalle_*.csv para el box plot.")
        return

    fig, ax = plt.subplots(figsize=(11, 5))

    bp = ax.boxplot(
        [d if d else [0] for d in datos],
        patch_artist=True,
        medianprops=dict(color="black", linewidth=2),
        whiskerprops=dict(linewidth=1.2),
        capprops=dict(linewidth=1.2),
        flierprops=dict(marker="o", markersize=4, alpha=0.5),
        widths=0.5,
    )

    for patch, color in zip(bp["boxes"], COLORES):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)
    for flier, color in zip(bp["fliers"], COLORES):
        flier.set_markerfacecolor(color)
        flier.set_markeredgecolor(color)

    ax.set_title(
        "Distribución de Latencia VD2 por Caso\n(30 mediciones por caso)",
        fontsize=13, fontweight="bold", pad=12,
    )
    ax.set_xlabel("Caso", fontsize=11)
    ax.set_ylabel("Latencia (ms)", fontsize=11)
    ax.set_xticks(range(1, len(ORDEN) + 1))
    ax.set_xticklabels(ETIQUETAS, fontsize=10)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.spines[["top", "right"]].set_visible(False)

    # Leyenda manual para diseños
    from matplotlib.patches import Patch
    leyenda = [
        Patch(facecolor=DISENO_COLOR[dis], alpha=0.75, label=DISENO_LABEL[dis])
        for dis in DISENOS
    ]
    ax.legend(handles=leyenda, title="Diseño del broker", fontsize=10, loc="upper right")

    fig.tight_layout()
    _guardar(fig, "distribucion_vd2_boxplot.png")


def imprimir_tabla(df):
    print("\n" + "=" * 70)
    print(f"  {'Escenario':<22} {'Diseño':<18} {'Solicitudes/2 min':<20} {'Latencia (ms)'}")
    print("=" * 70)
    orden = [(esc, dis) for esc in ["A", "B"] for dis in DISENOS]
    for esc, dis in orden:
        fila = df[(df["escenario"] == esc) & (df["diseno"] == dis)]
        if not fila.empty:
            esc_label = "Escenario 1 (1s, 10s)" if esc == "A" else "Escenario 2 (2s, 5s)"
            print(f"  {esc_label:<22} {DISENO_LABEL[dis]:<18} "
                  f"{fila['vd1_mediana_registros_2min'].values[0]:<20.0f} "
                  f"{fila['vd2_mediana_ms'].values[0]:.1f}")
    print("=" * 70)


def main():
    os.makedirs(GRAFICAS_DIR, exist_ok=True)
    df = cargar_datos()
    print(f"\n[OK] Datos cargados: {len(df)} combinaciones\n[...] Generando gráficas...\n")

    grafica_barras(
        df, "vd1_mediana_registros_2min",
        "Solicitudes Almacenadas en la BD en 2 Minutos",
        "Solicitudes almacenadas",
        "solicitudes_por_escenario.png",
    )
    grafica_barras(
        df, "vd2_mediana_ms",
        "Latencia de Control de Semáforos (Mediana)",
        "Latencia — mediana (ms)",
        "latencia_por_escenario.png",
    )
    grafica_escala(
        df, "vd1_mediana_registros_2min",
        "Factor de Escala Escenario 1 → Escenario 2\n(Solicitudes almacenadas)",
        "Factor de incremento (×)",
        "factor_escala_solicitudes.png",
    )
    grafica_boxplot_vd2()

    imprimir_tabla(df)
    print(f"\n[OK] 4 gráficas guardadas en {GRAFICAS_DIR}/")


if __name__ == "__main__":
    main()
