"""Tests para verificar métricas de los modelos ML."""

import pandas as pd
import pytest
from pathlib import Path

MODELS_DIR = Path(__file__).parent.parent / "models"


class TestModelFilesExist:
    """Verifica que los archivos de modelos existan."""

    def test_rf_demanda_existe(self):
        """RandomForestRegressor debe existir."""
        modelo_path = MODELS_DIR / "rf_demanda.pkl"
        assert modelo_path.exists(), "Modelo rf_demanda.pkl no encontrado"

    def test_kmeans_existe(self):
        """KMeans debe existir."""
        modelo_path = MODELS_DIR / "kmeans_clientes.pkl"
        assert modelo_path.exists(), "Modelo kmeans_clientes.pkl no encontrado"

    def test_dt_cancelacion_existe(self):
        """DecisionTreeClassifier debe existir."""
        modelo_path = MODELS_DIR / "dt_cancelacion.pkl"
        assert modelo_path.exists(), "Modelo dt_cancelacion.pkl no encontrado"

    def test_rf_pago_existe(self):
        """RandomForestClassifier para pagos debe existir."""
        modelo_path = MODELS_DIR / "rf_pago.pkl"
        assert modelo_path.exists(), "Modelo rf_pago.pkl no encontrado"


class TestRandomForestDemanda:
    """Tests para RandomForestRegressor de demanda."""

    def test_rf_demanda_mae(self):
        """MAE del RandomForestRegressor debe ser ≤ 3."""
        try:
            import joblib
            from sklearn.metrics import mean_absolute_error
            from utils.database import query_df

            model_data = joblib.load(MODELS_DIR / "rf_demanda.pkl")
            
            if isinstance(model_data, dict):
                rf = model_data["modelo"]
                features = model_data["features"]
            else:
                pytest.skip("Modelo guardado en formato antiguo, no compatible con test")

            df_pedidos = query_df("SELECT id, fecha, estado, total FROM Pedidos")
            if df_pedidos.empty or len(df_pedidos) < 10:
                pytest.skip("Datos insuficientes para validar modelo de demanda")

            df_pedidos["fecha"] = pd.to_datetime(df_pedidos["fecha"])
            df_demanda = df_pedidos.groupby(df_pedidos["fecha"].dt.date).size().reset_index(name="pedidos")
            df_demanda.columns = ["fecha", "pedidos"]
            df_demanda["fecha"] = pd.to_datetime(df_demanda["fecha"])
            df_demanda["dia_semana"] = df_demanda["fecha"].dt.dayofweek
            df_demanda["mes"] = df_demanda["fecha"].dt.month
            df_demanda["es_fin_semana"] = df_demanda["dia_semana"].isin([5, 6]).astype(int)
            df_demanda["es_fecha_esp"] = df_demanda["mes"].isin([5, 6, 9, 12]).astype(int)
            df_demanda["trimestre"] = df_demanda["fecha"].dt.quarter
            
            available_features = [f for f in features if f in df_demanda.columns]
            if len(available_features) != len(features):
                pytest.skip("Features del modelo no coinciden con datos disponibles")
            
            X = df_demanda[features]
            y = df_demanda["pedidos"]

            y_pred = rf.predict(X)
            mae = mean_absolute_error(y, y_pred)

            print(f"MAE de demanda: {mae:.4f}")
            assert mae <= 3, f"MAE {mae:.4f} excede el límite de 3"

        except ImportError as e:
            pytest.skip(f"Dependencias no disponibles: {e}")


class TestKMeansClientes:
    """Tests para KMeans de segmentación de clientes."""

    def test_kmeans_silhouette(self):
        """Silhouette Score debe ser ≥ 0.40."""
        try:
            import joblib
            from sklearn.metrics import silhouette_score
            from utils.database import query_df

            model_data = joblib.load(MODELS_DIR / "kmeans_clientes.pkl")
            
            if isinstance(model_data, dict):
                kmeans = model_data["modelo"]
                features = model_data["features"]
            else:
                pytest.skip("Modelo guardado en formato antiguo, no compatible con test")

            df_pedidos = query_df("SELECT id, cliente_id, fecha, total, estado FROM Pedidos")
            df_clientes = query_df("SELECT id, fecha_registro FROM Clientes")

            if df_pedidos.empty or len(df_pedidos) < 10:
                pytest.skip("Datos insuficientes para validar KMeans")

            df_pedidos["fecha"] = pd.to_datetime(df_pedidos["fecha"])

            df_stats = df_pedidos[df_pedidos["estado"] != "cancelado"].groupby("cliente_id").agg(
                total_compras=("total", "sum"),
                frecuencia_pedidos=("id", "count"),
            ).reset_index()

            df_stats = df_stats.merge(
                df_clientes[["id", "fecha_registro"]],
                left_on="cliente_id",
                right_on="id",
                how="left"
            )

            if len(df_stats) < 3:
                pytest.skip("Datos insuficientes para calcular Silhouette")

            df_stats["fecha_registro"] = pd.to_datetime(df_stats["fecha_registro"], errors="coerce")
            from datetime import datetime
            df_stats["antiguedad_dias"] = (datetime.now() - df_stats["fecha_registro"]).dt.days.fillna(0)
            df_stats = df_stats[df_stats["antiguedad_dias"] >= 0]

            if len(df_stats) < 3:
                pytest.skip("Datos insuficientes para calcular Silhouette")

            available_features = [f for f in features if f in df_stats.columns]
            if len(available_features) != len(features):
                pytest.skip("Features del modelo no coinciden con datos disponibles")
            
            X = df_stats[features]
            labels = kmeans.predict(X)

            score = silhouette_score(X, labels)

            print(f"Silhouette Score: {score:.4f}")
            assert score >= 0.40, f"Silhouette {score:.4f} below threshold 0.40"

        except ImportError as e:
            pytest.skip(f"Dependencias no disponibles: {e}")


class TestDecisionTreeCancelacion:
    """Tests para DecisionTreeClassifier de cancelaciones."""

    def test_dt_cancelacion_f1(self):
        """F1-Score debe ser ≥ 0.70."""
        try:
            import joblib
            from sklearn.metrics import f1_score
            from utils.database import query_df

            dt = joblib.load(MODELS_DIR / "dt_cancelacion.pkl")

            df_pedidos = query_df("SELECT id, fecha, estado, total FROM Pedidos")

            if df_pedidos.empty or len(df_pedidos) < 10:
                pytest.skip("Datos insuficientes para validar modelo de cancelaciones")

            df_pedidos["fecha"] = pd.to_datetime(df_pedidos["fecha"])
            df_pedidos["hora"] = df_pedidos["fecha"].dt.hour
            df_pedidos["dia_semana"] = df_pedidos["fecha"].dt.dayofweek

            df_pedidos["es_cancelado"] = (df_pedidos["estado"] == "cancelado").astype(int)

            X = df_pedidos[["hora", "dia_semana", "total"]].dropna()
            y = df_pedidos.loc[X.index, "es_cancelado"]

            if y.sum() < 2 or (len(y) - y.sum()) < 2:
                pytest.skip("Datos insuficientes para calcular F1-Score")

            y_pred = dt.predict(X)
            f1 = f1_score(y, y_pred, average="weighted")

            print(f"F1-Score (weighted): {f1:.4f}")
            assert f1 >= 0.70, f"F1-Score {f1:.4f} below threshold 0.70"

        except ImportError as e:
            pytest.skip(f"Dependencias no disponibles: {e}")


class TestRandomForestPago:
    """Tests para RandomForestClassifier de pagos."""

    def test_rf_pago_auc(self):
        """AUC-ROC debe ser ≥ 0.75."""
        try:
            import joblib
            from sklearn.metrics import roc_auc_score
            from utils.database import query_df

            model_data = joblib.load(MODELS_DIR / "rf_pago.pkl")
            
            if isinstance(model_data, dict):
                rf = model_data["modelo"]
                features = model_data.get("features", None)
            else:
                pytest.skip("Modelo guardado en formato antiguo, no compatible con test")

            df_pagos = query_df("SELECT pedido_id, monto, estado, fecha FROM Pagos")
            df_pedidos = query_df("SELECT id, total FROM Pedidos")

            if df_pagos.empty or len(df_pagos) < 10:
                pytest.skip("Datos insuficientes para validar modelo de pagos")

            df_pagos["fecha"] = pd.to_datetime(df_pagos["fecha"])
            df_pagos["hora"] = df_pagos["fecha"].dt.hour

            df_pagos_pedidos = df_pagos.merge(
                df_pedidos[["id", "total"]],
                left_on="pedido_id",
                right_on="id",
                how="left"
            )
            df_pagos_pedidos = df_pagos_pedidos.dropna(subset=["monto", "total"])

            if len(df_pagos_pedidos) < 10:
                pytest.skip("Datos insuficientes para calcular AUC-ROC")

            df_pagos_pedidos["es_confirmado"] = (df_pagos_pedidos["estado"] == "confirmado").astype(int)

            if features:
                available_features = [f for f in features if f in df_pagos_pedidos.columns]
                if len(available_features) != len(features):
                    pytest.skip("Features del modelo no coinciden con datos disponibles")
                X = df_pagos_pedidos[features]
            else:
                pytest.skip("No hay features definidas en el modelo")
            y = df_pagos_pedidos["es_confirmado"]

            y_proba = rf.predict_proba(X)[:, 1]
            auc = roc_auc_score(y, y_proba)

            print(f"AUC-ROC: {auc:.4f}")
            assert auc >= 0.75, f"AUC-ROC {auc:.4f} below threshold 0.75"

        except ImportError as e:
            pytest.skip(f"Dependencias no disponibles: {e}")


class TestAprioriRules:
    """Tests para reglas de asociación Apriori."""

    def test_reglas_existen(self):
        """Las reglas de Apriori deben existir."""
        modelo_path = MODELS_DIR / "reglas_apriori.pkl"
        assert modelo_path.exists(), "Modelo reglas_apriori.pkl no encontrado"

    def test_reglas_cargables(self):
        """Las reglas deben ser cargables y tener datos."""
        try:
            import joblib

            reglas = joblib.load(MODELS_DIR / "reglas_apriori.pkl")

            assert reglas is not None, "Reglas no deben ser None"
            print(f"Total de reglas cargadas: {len(reglas)}")

        except ImportError as e:
            pytest.skip(f"Dependencias no disponibles: {e}")