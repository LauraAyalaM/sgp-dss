"""Servicios de ML para análisis predictivo y segmentación.

Usa el dataset real CRISP-DM: bd_desayunos_sorpresa_stella_2025_limpio.csv
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    classification_report,
    mean_absolute_error,
    roc_auc_score,
    silhouette_score,
)
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier

# ── Rutas ──────────────────────────────────────────────────────────────────────
_ROOT       = Path(__file__).resolve().parent.parent
MODELS_DIR  = _ROOT / "models"
CSV_PATH    = _ROOT / "data" / "bd_desayunos_sorpresa_stella_2025_limpio.csv"
MODELS_DIR.mkdir(exist_ok=True)


# ── Carga del dataset real ─────────────────────────────────────────────────────
def _cargar_dataset() -> pd.DataFrame:
    """Carga el CSV limpio de CRISP-DM."""
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"Dataset no encontrado en {CSV_PATH}. "
            "Copia bd_desayunos_sorpresa_stella_2025_limpio.csv a la carpeta data/"
        )
    df = pd.read_csv(CSV_PATH)
    df["fecha_pedido"] = pd.to_datetime(df["fecha_pedido"])
    return df


# ══════════════════════════════════════════════════════════════════════════════
# ENTRENAMIENTO PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def entrenar_y_guardar_modelos() -> None:
    """Entrena y guarda los 5 modelos ML con el dataset real."""
    print("=== Entrenamiento de Modelos — Dataset Real CRISP-DM ===\n")

    try:
        df = _cargar_dataset()
        print(f"Dataset cargado: {len(df)} pedidos | "
              f"{df['cliente_id'].nunique()} clientes | "
              f"{df['fecha_pedido'].nunique()} fechas\n")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return

    _entrenar_rf_demanda(df)
    _entrenar_kmeans_clientes(df)
    _entrenar_dt_cancelacion(df)
    _entrenar_apriori(df)
    _entrenar_rf_pago(df)

    print("\n=== ✅ Todos los modelos entrenados y guardados ===")


# ── Modelo 1: RandomForestRegressor — Pronóstico de demanda ───────────────────
def _entrenar_rf_demanda(df: pd.DataFrame) -> None:
    print("1. Entrenando RandomForestRegressor — pronóstico de demanda diaria...")
    try:
        demanda = (
            df.groupby(df["fecha_pedido"].dt.date)
            .agg(
                pedidos        = ("id", "count"),
                dia_semana     = ("dia_semana", "first"),
                mes            = ("mes", "first"),
                es_fin_semana  = ("es_fin_semana", "first"),
                es_fecha_esp   = ("es_fecha_especial", "first"),
                trimestre      = ("trimestre", "first"),
            )
            .reset_index()
        )

        FEATURES = ["dia_semana", "mes", "es_fin_semana", "es_fecha_esp", "trimestre"]
        X = demanda[FEATURES]
        y = demanda["pedidos"]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        rf = RandomForestRegressor(n_estimators=200, random_state=42)
        rf.fit(X_train, y_train)

        mae = mean_absolute_error(y_test, rf.predict(X_test))
        r2  = rf.score(X_test, y_test)

        joblib.dump(rf, MODELS_DIR / "rf_demanda.pkl")
        print(f"   MAE : {mae:.4f}  (objetivo ≤ 3)")
        print(f"   R²  : {r2:.4f}")
        print(f"   ✅ Guardado: models/rf_demanda.pkl")
        if mae <= 3:
            print("   ✅ Métrica objetivo CUMPLIDA")
        else:
            print("   ⚠️  MAE superior al objetivo — se necesitan más datos")
    except Exception as e:
        print(f"   ❌ Error: {e}")


# ── Modelo 2: KMeans — Segmentación de clientes ───────────────────────────────
def _entrenar_kmeans_clientes(df: pd.DataFrame) -> None:
    print("2. Entrenando KMeans — segmentación de clientes...")
    try:
        df_stats = (
            df[df["es_cancelado"] == 0]
            .groupby("cliente_id")
            .agg(
                total_compras      = ("total", "sum"),
                frecuencia_pedidos = ("id", "count"),
                antiguedad_cliente = ("antiguedad_cliente", "mean"),
                ticket_promedio    = ("ticket_por_item", "mean"),
            )
            .reset_index()
        )

        FEATURES = ["total_compras", "frecuencia_pedidos",
                    "antiguedad_cliente", "ticket_promedio"]
        X = df_stats[FEATURES]

        kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)

        score = silhouette_score(X, labels)

        joblib.dump(
            {"modelo": kmeans, "features": FEATURES, "stats": df_stats},
            MODELS_DIR / "kmeans_clientes.pkl",
        )

        print(f"   Silhouette Score : {score:.4f}  (objetivo ≥ 0.40)")
        print(f"   Clientes segmentados: {len(df_stats)}")
        print(f"   ✅ Guardado: models/kmeans_clientes.pkl")
        if score >= 0.40:
            print("   ✅ Métrica objetivo CUMPLIDA")
        else:
            print("   ⚠️  Silhouette inferior al objetivo")
    except Exception as e:
        print(f"   ❌ Error: {e}")


# ── Modelo 3: DecisionTreeClassifier — Predicción de cancelación ──────────────
def _entrenar_dt_cancelacion(df: pd.DataFrame) -> None:
    print("3. Entrenando DecisionTreeClassifier — predicción de cancelación...")
    try:
        FEATURES = [
            "dia_semana", "mes", "es_fin_semana", "es_fecha_especial",
            "trimestre", "hora_entrega_num", "n_items", "total",
            "antiguedad_cliente", "origen_cod", "canal_cliente_cod",
            "tipo_cliente_cod",
        ]
        X = df[FEATURES].copy()
        y = df["es_cancelado"]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        dt = DecisionTreeClassifier(
            max_depth=6, min_samples_leaf=5, random_state=42
        )
        dt.fit(X_train, y_train)

        y_pred = dt.predict(X_test)
        report = classification_report(
            y_test, y_pred,
            target_names=["No cancelado", "Cancelado"],
            output_dict=True,
            zero_division=0,
        )
        f1 = report["weighted avg"]["f1-score"]

        joblib.dump({"modelo": dt, "features": FEATURES}, MODELS_DIR / "dt_cancelacion.pkl")

        print(f"   F1-Score (weighted): {f1:.4f}  (objetivo ≥ 0.70)")
        print(f"   ✅ Guardado: models/dt_cancelacion.pkl")
        if f1 >= 0.70:
            print("   ✅ Métrica objetivo CUMPLIDA")
        else:
            print("   ⚠️  F1 inferior al objetivo")
    except Exception as e:
        print(f"   ❌ Error: {e}")


# ── Modelo 4: Apriori — Reglas de asociación de productos ─────────────────────
def _entrenar_apriori(df: pd.DataFrame) -> None:
    print("4. Entrenando Apriori — reglas de asociación de productos...")
    try:
        # Reconstruir transacciones desde n_productos_dist y productos en el CSV
        # Usamos numero_pedido + metodo_pago_prin como proxy de combinaciones
        # Si tienes Detalle_Pedido real, reemplaza aquí.
        transacciones = (
            df.groupby("numero_pedido")["metodo_pago_prin"]
            .apply(lambda x: list(x.astype(str)))
            .tolist()
        )

        # Simulamos combinaciones de características por pedido
        def pedido_a_items(row: pd.Series) -> list[str]:
            items = [
                f"dia_{row['dia_semana']}",
                f"mes_{row['mes']}",
                f"tipo_{row['tipo_cliente']}",
                f"canal_{row['canal_cliente']}",
                f"pago_{row['metodo_pago_prin']}",
            ]
            if row["es_fecha_especial"]:
                items.append("fecha_especial")
            if row["es_fin_semana"]:
                items.append("fin_semana")
            return items

        transacciones = df.apply(pedido_a_items, axis=1).tolist()

        te = TransactionEncoder()
        te_array = te.fit(transacciones).transform(transacciones)
        df_encoded = pd.DataFrame(te_array, columns=te.columns_)

        frequent_itemsets = apriori(
            df_encoded, min_support=0.05, use_colnames=True
        )

        if frequent_itemsets.empty:
            print("   No se encontraron itemsets frecuentes.")
            return

        reglas = association_rules(
            frequent_itemsets, metric="confidence", min_threshold=0.60
        )
        reglas = reglas.sort_values("confidence", ascending=False).head(20)

        reglas["antecedents"] = reglas["antecedents"].apply(
            lambda x: ", ".join(list(x))
        )
        reglas["consequents"] = reglas["consequents"].apply(
            lambda x: ", ".join(list(x))
        )

        joblib.dump(reglas, MODELS_DIR / "reglas_apriori.pkl")
        print(f"   {len(reglas)} reglas generadas (confianza ≥ 0.60)")
        print(f"   ✅ Guardado: models/reglas_apriori.pkl")
        if len(reglas) > 0:
            print("   ✅ Métrica objetivo CUMPLIDA")
    except Exception as e:
        print(f"   ❌ Error: {e}")


# ── Modelo 5: RandomForestClassifier — Predicción estado de pago ──────────────
def _entrenar_rf_pago(df: pd.DataFrame) -> None:
    print("5. Entrenando RandomForestClassifier — predicción estado de pago...")
    try:
        df_pago = df[df["estado_pago_fin"].isin(["confirmado", "pendiente"])].copy()
        df_pago["es_confirmado"] = (df_pago["estado_pago_fin"] == "confirmado").astype(int)

        FEATURES = [
            "total", "n_pagos", "es_pago_digital", "diferencia_pago",
            "dia_semana", "mes", "es_fin_semana", "es_fecha_especial",
            "tipo_cliente_cod", "canal_cliente_cod", "origen_cod",
            "antiguedad_cliente", "n_items", "riesgo_cobro",
        ]
        X = df_pago[FEATURES].fillna(0)
        y = df_pago["es_confirmado"]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        rf = RandomForestClassifier(n_estimators=200, random_state=42)
        rf.fit(X_train, y_train)

        y_prob = rf.predict_proba(X_test)[:, 1]
        auc    = roc_auc_score(y_test, y_prob)

        joblib.dump({"modelo": rf, "features": FEATURES}, MODELS_DIR / "rf_pago.pkl")

        print(f"   AUC-ROC : {auc:.4f}  (objetivo ≥ 0.75)")
        print(f"   ✅ Guardado: models/rf_pago.pkl")
        if auc >= 0.75:
            print("   ✅ Métrica objetivo CUMPLIDA")
        else:
            print("   ⚠️  AUC inferior al objetivo")
    except Exception as e:
        print(f"   ❌ Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE INFERENCIA PARA STREAMLIT
# ══════════════════════════════════════════════════════════════════════════════

def segmentar_clientes() -> pd.DataFrame:
    """Carga KMeans y retorna clientes segmentados con etiqueta descriptiva."""
    modelo_path = MODELS_DIR / "kmeans_clientes.pkl"
    if not modelo_path.exists():
        return pd.DataFrame()
    try:
        data    = joblib.load(modelo_path)
        kmeans  = data["modelo"]
        features = data["features"]
        df_stats = data["stats"]

        X      = df_stats[features]
        labels = kmeans.predict(X)
        df_stats = df_stats.copy()
        df_stats["segmento"] = labels

        # Etiqueta por valor promedio de compras
        medias = df_stats.groupby("segmento")["total_compras"].mean()
        orden  = medias.sort_values(ascending=False).index.tolist()
        mapa   = {
            orden[0]: "Cliente frecuente de alto valor",
            orden[1]: "Cliente ocasional",
            orden[2]: "Cliente nuevo o bajo consumo",
        }
        df_stats["etiqueta"] = df_stats["segmento"].map(mapa)
        return df_stats
    except Exception as e:
        print(f"Error al segmentar: {e}")
        return pd.DataFrame()


def pronostico_demanda(periodos: int = 90) -> pd.DataFrame:
    """Retorna pronóstico de pedidos para los próximos N días."""
    modelo_path = MODELS_DIR / "rf_demanda.pkl"
    if not modelo_path.exists():
        return pd.DataFrame(columns=["fecha", "pedidos_estimados"])
    try:
        rf = joblib.load(modelo_path)
        fechas = pd.date_range(start=datetime.now(), periods=periodos, freq="D")
        df_f = pd.DataFrame({"fecha": fechas})
        df_f["dia_semana"]    = df_f["fecha"].dt.dayofweek
        df_f["mes"]           = df_f["fecha"].dt.month
        df_f["es_fin_semana"] = df_f["dia_semana"].isin([5, 6]).astype(int)
        df_f["es_fecha_esp"]  = df_f["mes"].isin([5, 6, 9, 12]).astype(int)
        df_f["trimestre"]     = df_f["fecha"].dt.quarter

        X = df_f[["dia_semana", "mes", "es_fin_semana", "es_fecha_esp", "trimestre"]]
        df_f["pedidos_estimados"] = rf.predict(X).clip(0).astype(int)
        return df_f[["fecha", "pedidos_estimados"]]
    except Exception as e:
        print(f"Error al pronosticar: {e}")
        return pd.DataFrame(columns=["fecha", "pedidos_estimados"])


def obtener_reglas_asociacion() -> pd.DataFrame:
    """Retorna las top 10 reglas de asociación más confiantes."""
    modelo_path = MODELS_DIR / "reglas_apriori.pkl"
    if not modelo_path.exists():
        return pd.DataFrame()
    try:
        reglas = joblib.load(modelo_path)
        return reglas.head(10) if not reglas.empty else pd.DataFrame()
    except Exception as e:
        print(f"Error al cargar reglas: {e}")
        return pd.DataFrame()


if __name__ == "__main__":
    entrenar_y_guardar_modelos()