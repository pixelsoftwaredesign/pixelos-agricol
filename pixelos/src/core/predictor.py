"""Moteur de prédiction IA pour l'irrigation intelligente.

Utilise les séries temporelles MongoDB pour prédire :
  - Taux d'humidité futur (prochaines 6h/12h/24h)
  - Quantité d'eau nécessaire
  - Probabilité de pluie imminente (via météo + historique)
  - Détection d'anomalies (fuites, dérive capteur, vanne bloquée)

Modèle : RandomForestRegressor (scikit-learn) léger, ré-entraînable.
Stockage : MongoDB (historique) + SQLite/modèles pickle (modèle entraîné).
"""

import os
import io
import json
import pickle
import structlog
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from collections import deque


log = structlog.get_logger()


class PredictorEngine:
    """Moteur d'inférence IA pour PixelOS."""

    MODELS_DIR = Path("./models")
    MODELS_DIR.mkdir(exist_ok=True)

    # Seuils pour la détection d'anomalies
    ANOMALY_THRESHOLDS = {
        "humidity_drop_rate": 15.0,   # %/h chute anormale (fuite)
        "flow_sudden": 50.0,          # L/h au-dessus de la moyenne
        "temp_deviation": 10.0,       # °C écart à la moyenne saisonnière
        "valve_cycle_short": 120,     # secondes : cycle vanne trop court
    }

    def __init__(self, db=None):
        self.model = None
        self.feature_names = [
            "hour", "minute", "day_of_year", "month",
            "temp_air", "humidity_air", "pressure",
            "humidity_soil_lag1", "humidity_soil_lag3", "humidity_soil_lag6",
            "rain_last_3h", "wind_speed",
        ]
        self.target_name = "humidity_soil_6h"
        self.model_path = self.MODELS_DIR / "irrigation_model.pkl"
        self.scaler_path = self.MODELS_DIR / "scaler.pkl"
        self._load_model()

    # ========================================
    #  Persistance du modèle
    # ========================================

    def _load_model(self):
        if self.model_path.exists():
            try:
                with open(self.model_path, "rb") as f:
                    self.model = pickle.load(f)
                log.info("Modèle chargé", path=str(self.model_path))
            except Exception as e:
                log.warning("Échec chargement modèle", error=str(e))
                self.model = None
        else:
            log.info("Aucun modèle existant, mode prediction désactivé")

    def _save_model(self):
        with open(self.model_path, "wb") as f:
            pickle.dump(self.model, f)
        log.info("Modèle sauvegardé", path=str(self.model_path))

    # ========================================
    #  Extraction des features depuis MongoDB
    # ========================================

    def _load_historical_data(self, days: int = 30,
                               zone: str = "sol_serre") -> tuple:
        """Charge l'historique depuis MongoDB et prépare X, y."""
        try:
            from pymongo import MongoClient
            client = MongoClient("mongodb://localhost:27017/")
            db = client["agricol_ts"]
            collection = db["mesures_capteurs"]

            since = datetime.utcnow() - timedelta(days=days)
            cursor = collection.find({
                "zone": zone,
                "timestamp": {"$gte": since},
            }).sort("timestamp", 1)

            records = list(cursor)
            if len(records) < 50:
                log.warning("Pas assez de données", count=len(records))
                return np.array([]), np.array([])

            # Feature engineering
            X, y = [], []
            for i, r in enumerate(records):
                ts = r.get("timestamp", datetime.utcnow())
                features = [
                    ts.hour, ts.minute, ts.timetuple().tm_yday, ts.month,
                    r.get("temperature", 20),   # temp_air
                    r.get("humidite", 50),       # humidity_air
                    r.get("pression", 1013),     # pressure
                ]

                # Lags d'humidité sol
                for lag in [1, 3, 6]:
                    if i >= lag:
                        features.append(records[i-lag].get("humidite_sol", 0))
                    else:
                        features.append(records[0].get("humidite_sol", 0))

                # Pluie cumulée 3h
                rain_3h = 0
                for j in range(max(0, i-18), i):
                    rain_3h += records[j].get("pluie", 0)
                features.append(rain_3h)

                features.append(r.get("vent", 0))

                # Target : humidité dans 6h (si disponible)
                future_idx = i + 36  # ~6h à 10min d'intervalle
                if future_idx < len(records):
                    y.append(records[future_idx].get("humidite_sol", 0))
                    X.append(features)

            return np.array(X), np.array(y)

        except Exception as e:
            log.error("Erreur chargement historique", error=str(e))
            return np.array([]), np.array([])

    # ========================================
    #  Entraînement
    # ========================================

    def train(self, days: int = 30, zone: str = "sol_serre",
              force: bool = False) -> dict:
        """Entraîne un modèle RandomForest sur l'historique."""
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_absolute_error, r2_score

        log.info("Entraînement...", days=days, zone=zone)
        X, y = self._load_historical_data(days, zone)

        if len(X) < 50:
            return {"status": "error", "message":
                    f"Pas assez de données: {len(X)} échantillons"}

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42)

        self.model = RandomForestRegressor(
            n_estimators=100, max_depth=12, min_samples_leaf=5,
            n_jobs=-1, random_state=42)
        self.model.fit(X_train, y_train)

        y_pred = self.model.predict(X_test)
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)

        self._save_model()

        # Feature importance
        importances = sorted(zip(self.feature_names, self.model.feature_importances_),
                             key=lambda x: -x[1])

        result = {
            "status": "ok",
            "samples": len(X),
            "mae": round(mae, 2),
            "r2_score": round(r2, 3),
            "accuracy_pct": round(max(0, 100 - (mae / np.mean(y) * 100)), 1),
            "features": [{"name": n, "importance": round(v, 3)}
                         for n, v in importances[:8]],
            "zone": zone,
        }
        log.info("Entraînement terminé", **result)
        return result

    # ========================================
    #  Prédiction
    # ========================================

    def predict(self, current_data: dict) -> dict:
        """Prédit l'humidité future et les besoins en irrigation."""
        if self.model is None:
            return {"status": "error", "message": "Modèle non entraîné"}

        try:
            features = self._extract_features(current_data)
            features_2d = np.array(features).reshape(1, -1)

            pred_humidity = self.model.predict(features_2d)[0]
            current_hum = current_data.get("humidite_sol", 50)
            threshold = current_data.get("seuil_secheresse", 30)

            # Temps estimé avant seuil critique
            drop_rate = max(0.5, (current_hum - pred_humidity) / 6.0)  # %/h
            if drop_rate > 0:
                hours_to_critical = max(0, (current_hum - threshold) / drop_rate)
            else:
                hours_to_critical = 999

            # Quantité d'eau recommandée (L/m²)
            water_needed = max(0, (current_hum - threshold) * 0.3)

            # Confiance
            confidence = min(95, max(50, 100 - abs(pred_humidity - current_hum) * 2))

            result = {
                "status": "ok",
                "current_humidity": round(current_hum, 1),
                "predicted_humidity_6h": round(pred_humidity, 1),
                "drop_rate_pct_per_h": round(drop_rate, 2),
                "hours_to_critical_threshold": round(hours_to_critical, 1),
                "water_needed_l_per_m2": round(water_needed, 2),
                "confidence_pct": round(confidence, 1),
                "should_irrigate": hours_to_critical < 4 and current_hum > threshold,
                "irrigate_urgency": "immédiate" if hours_to_critical < 2
                    else "dans_quelques_heures" if hours_to_critical < 6
                    else "non_urgent",
                "recommendation": self._generate_recommendation(
                    current_hum, pred_humidity, threshold, hours_to_critical),
                "timestamp": datetime.now().isoformat(),
            }
            return result

        except Exception as e:
            log.error("Erreur prédiction", error=str(e))
            return {"status": "error", "message": str(e)}

    def _extract_features(self, data: dict) -> list:
        now = datetime.now()
        return [
            now.hour, now.minute, now.timetuple().tm_yday, now.month,
            data.get("temperature", 20),
            data.get("humidite", 50),
            data.get("pression", 1013),
            data.get("humidite_sol_lag1", data.get("humidite_sol", 50)),
            data.get("humidite_sol_lag3", data.get("humidite_sol", 50)),
            data.get("humidite_sol_lag6", data.get("humidite_sol", 50)),
            data.get("pluie_3h", 0),
            data.get("vent", 0),
        ]

    def _generate_recommendation(self, current: float, predicted: float,
                                  threshold: float, hours: float) -> str:
        if current <= threshold:
            return "IRRIGUER IMMÉDIATEMENT - Humidité sous le seuil critique"
        if hours < 2:
            return f"Irrigation urgente dans {hours:.0f}h - {current}% → {predicted:.0f}%"
        if hours < 6:
            return f"Prévoir irrigation dans ~{hours:.0f}h ({predicted:.0f}% attendu)"
        if predicted > threshold + 10:
            return f"Aucune irrigation nécessaire ({predicted:.0f}% dans 6h)"
        return f"Surveiller - humidité stable à {current}%"

    # ========================================
    #  Détection d'anomalies
    # ========================================

    def detect_anomalies(self, telemetry: dict) -> list[dict]:
        """Détecte les anomalies en temps réel."""
        anomalies = []

        # 1. Chute d'humidité anormale (fuite probable)
        if all(k in telemetry for k in ("humidite_sol", "humidite_sol_lag1")):
            drop = telemetry["humidite_sol_lag1"] - telemetry["humidite_sol"]
            if drop > self.ANOMALY_THRESHOLDS["humidity_drop_rate"]:
                anomalies.append({
                    "type": "FUITE",
                    "severity": "critical",
                    "message": f"Chute humidité {drop:.1f}%/h - fuite possible",
                    "value": drop,
                    "threshold": self.ANOMALY_THRESHOLDS["humidity_drop_rate"],
                })

        # 2. Débit anormal
        if "debit" in telemetry and "debit_moyen" in telemetry:
            ratio = telemetry["debit"] / max(0.1, telemetry["debit_moyen"])
            if ratio > 1.5:
                anomalies.append({
                    "type": "DEBIT_ANORMAL",
                    "severity": "warning",
                    "message": f"Débit x{ratio:.1f} au-dessus de la moyenne",
                    "value": telemetry["debit"],
                    "threshold": telemetry["debit_moyen"] * 1.5,
                })

        # 3. Cycle vanne trop court (usure / blocage)
        if "vanne_cycles" in telemetry:
            cycle_time = telemetry.get("vanne_cycle_time", 0)
            if 0 < cycle_time < self.ANOMALY_THRESHOLDS["valve_cycle_short"]:
                anomalies.append({
                    "type": "VANNE_CYCLE_COURT",
                    "severity": "warning",
                    "message": f"Cycle vanne trop court: {cycle_time}s",
                    "value": cycle_time,
                    "threshold": self.ANOMALY_THRESHOLDS["valve_cycle_short"],
                })

        # 4. Température anormale (capteur défaillant)
        if "temperature" in telemetry and "temp_moy_saison" in telemetry:
            deviation = abs(telemetry["temperature"] - telemetry["temp_moy_saison"])
            if deviation > self.ANOMALY_THRESHOLDS["temp_deviation"]:
                anomalies.append({
                    "type": "TEMP_ANORMALE",
                    "severity": "warning",
                    "message": f"Écart température {deviation:.1f}°C",
                    "value": telemetry["temperature"],
                    "expected": telemetry["temp_moy_saison"],
                })

        return anomalies

    # ========================================
    #  Statistiques du modèle
    # ========================================

    def stats(self) -> dict:
        if self.model is None:
            return {"status": "no_model"}
        return {
            "status": "ok",
            "model_type": type(self.model).__name__,
            "n_estimators": self.model.n_estimators,
            "max_depth": self.model.max_depth,
            "n_features": self.model.n_features_in_,
            "features": self.feature_names,
            "model_path": str(self.model_path),
            "model_size_kb": round(self.model_path.stat().st_size / 1024, 1)
                if self.model_path.exists() else 0,
        }


class PredictorCLI:
    """Interface CLI pour le moteur de prédiction."""

    @staticmethod
    def handle(args):
        engine = PredictorEngine()

        if args.action == "train":
            result = engine.train(days=args.days or 30, zone=args.zone or "sol_serre")
            print(f"\n📊 Entraînement terminé :")
            print(f"   Échantillons : {result.get('samples', 'N/A')}")
            print(f"   MAE          : {result.get('mae', 'N/A')}%")
            print(f"   R²           : {result.get('r2_score', 'N/A')}")
            print(f"   Précision    : {result.get('accuracy_pct', 'N/A')}%")
            print(f"\n🧬 Features importantes :")
            for f in result.get("features", []):
                bar = "█" * int(f["importance"] * 40)
                print(f"   {f['name']:<20} {bar} {f['importance']:.1%}")

        elif args.action == "predict":
            data = {"humidite_sol": args.humidity or 45}
            if args.temp: data["temperature"] = args.temp
            if args.hum: data["humidite"] = args.hum
            if args.pression: data["pression"] = args.pression

            result = engine.predict(data)
            if result.get("status") == "error":
                print(f"❌ {result['message']}")
                return

            print(f"\n🔮 Prédiction humidité (6h) :")
            print(f"   Actuelle     : {result['current_humidity']}%")
            print(f"   Prédite (6h) : {result['predicted_humidity_6h']}%")
            print(f"   Taux chute   : {result['drop_rate_pct_per_h']}%/h")
            print(f"   Seuil        : dans {result['hours_to_critical_threshold']}h")
            print(f"   Eau nécessaire : {result['water_needed_l_per_m2']} L/m²")
            print(f"   Confiance    : {result['confidence_pct']}%")
            print(f"\n💡 {result['recommendation']}")

        elif args.action == "stats":
            s = engine.stats()
            if s["status"] == "no_model":
                print("❌ Aucun modèle entraîné. Lancer 'pixelos predict train'")
                return
            print(f"\n🧠 Modèle : {s['model_type']}")
            print(f"   Estimators : {s['n_estimators']}")
            print(f"   Features   : {s['n_features']}")
            print(f"   Taille     : {s['model_size_kb']} Ko")
            print(f"   Path       : {s['model_path']}")

        elif args.action == "anomaly":
            telemetry = {
                "humidite_sol": args.humidity or 45,
                "humidite_sol_lag1": (args.humidity or 45) + 8,
                "debit": args.debit or 30,
                "debit_moyen": 15,
                "temperature": args.temp or 35,
                "temp_moy_saison": 22,
            }
            anomalies = engine.detect_anomalies(telemetry)
            if not anomalies:
                print("✅ Aucune anomalie détectée")
                return
            print(f"\n🚨 {len(anomalies)} anomalie(s) détectée(s) :")
            for a in anomalies:
                icon = {"critical": "🔴", "warning": "🟡"}.get(a["severity"], "⚪")
                print(f"   {icon} [{a['type']}] {a['message']}")
