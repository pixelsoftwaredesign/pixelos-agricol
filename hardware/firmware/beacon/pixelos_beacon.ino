// PixelOS - Beacon BLE + Wi-Fi AP pour découverte automatique
// ESP32 : diffuse son identité pour être détecté par le scanneur PixelOS
//
// Au démarrage :
//   1. BLE beacon broadcast : "PIXL" + type + addr (manufacturer data)
//   2. Wi-Fi AP (si configuré) : SSID "PIXELOS-TYPE-NOM"
//   3. MQTT enrollment request sur "pixelos/enroll"
//
// Le scanner PixelOS détecte le beacon et enregistre automatiquement
// le capteur dans la zone appropriée.

// IMPORTANT : Configurer TYPE et NOM pour chaque nœud
#define NODE_TYPE   "SOL"     // SOL, VANNE, METEO, DEBIT, PIR, POMPE
#define NODE_NAME   "serre_nord" // Identifiant unique
#define NODE_ADDR   10          // Adresse Modbus (0 si non-RS485)

// BLE
#include <BLEDevice.h>
#include <BLEBeacon.h>
#include <BLEAdvertising.h>

// Wi-Fi (mode AP si aucun réseau configuré)
#include <WiFi.h>

// Pour l'enrollment MQTT
#include <WiFiClient.h>
#include <PubSubClient.h>

// ─── Configuration Wi-Fi ───
// Mettre à blanc = mode AP uniquement
#define WIFI_SSID     ""
#define WIFI_PASSWORD ""

const char *MQTT_BROKER   = "10.0.100.1";
const int   MQTT_PORT     = 1883;

// ─── Identité PixelOS ───
// Génère le SSID AP : "PIXELOS-SOL-SERRE_NORD"
#define SSID_AP  "PIXELOS-" NODE_TYPE "-" NODE_NAME

WiFiClient wifi_client;
PubSubClient mqtt(wifi_client);

bool enrolled = false;
unsigned long last_beacon = 0;
unsigned long last_enroll_attempt = 0;

// ========================================
//  BLE Beacon
// ========================================
void startBLEBeacon() {
    BLEDevice::init(SSID_AP);

    BLEAdvertising *adv = BLEDevice::getAdvertising();
    BLEAdvertisementData data;

    // Manufacturer data : PIXL + type + addr
    // Format : 4 bytes prefix "PIXL" + 1 byte type + 1 byte addr
    uint8_t mfg_data[8];
    mfg_data[0] = 'P';
    mfg_data[1] = 'I';
    mfg_data[2] = 'X';
    mfg_data[3] = 'L';

    // Type mapping
    if (strcmp(NODE_TYPE, "SOL") == 0)       mfg_data[4] = 0;
    else if (strcmp(NODE_TYPE, "VANNE") == 0) mfg_data[4] = 1;
    else if (strcmp(NODE_TYPE, "METEO") == 0) mfg_data[4] = 2;
    else if (strcmp(NODE_TYPE, "DEBIT") == 0) mfg_data[4] = 3;
    else if (strcmp(NODE_TYPE, "PIR") == 0)   mfg_data[4] = 4;
    else if (strcmp(NODE_TYPE, "POMPE") == 0) mfg_data[4] = 5;
    else                                      mfg_data[4] = 0xFF;

    mfg_data[5] = NODE_ADDR;  // Adresse Modbus
    mfg_data[6] = 0;          // Réservé
    mfg_data[7] = 0;          // Réservé

    data.addData(BLEAdvertisementData::type(BLE_GAP_AD_TYPE_MANUFACTURER_SPECIFIC),
                 std::string((char*)mfg_data, 8));

    // Ajouter le nom complet dans le scan response
    BLEAdvertisementData scanResp;
    scanResp.setName(SSID_AP);
    adv->setAdvertisementData(data);
    adv->setScanResponseData(scanResp);

    // Intervalle de broadcast : 100ms pour découverte rapide
    adv->setMinPreferred(0x064);
    adv->setMaxPreferred(0x0C8);

    BLEDevice::startAdvertising();
    Serial.printf("[BLE] Beacon démarré: %s\n", SSID_AP);
}

// ========================================
//  Wi-Fi AP (fallback si pas de réseau)
// ========================================
void startWiFiAP() {
    WiFi.mode(WIFI_AP);
    WiFi.softAP(SSID_AP, "pixelos2026", 6, 0, 1);
    Serial.printf("[AP] Point d'accès créé: %s\n", SSID_AP);
    Serial.printf("[AP] IP: %s\n", WiFi.softAPIP().toString().c_str());
}

// ========================================
//  MQTT Enrollment
// ========================================
void enrollMQTT() {
    if (enrolled) return;

    if (!mqtt.connected()) {
        if (WiFi.status() != WL_CONNECTED) return;
        mqtt.connect(("pixelos-" NODE_NAME));
    }

    mqtt.loop();

    // Publier la demande d'enregistrement
    char topic[64];
    char payload[256];

    snprintf(topic, sizeof(topic), "pixelos/enroll");
    snprintf(payload, sizeof(payload),
        "{"
        "\"type\":\"%s\","
        "\"name\":\"%s\","
        "\"addr\":%d,"
        "\"mac\":\"%s\","
        "\"ssid\":\"%s\""
        "}",
        NODE_TYPE, NODE_NAME, NODE_ADDR,
        WiFi.macAddress().c_str(),
        SSID_AP);

    if (mqtt.publish(topic, payload)) {
        Serial.printf("[ENROLL] Demande envoyée: %s\n", payload);
        enrolled = true;
    }
}

// ========================================
//  MQTT Callback : confirmation enrollment
// ========================================
void mqttCallback(char *topic, byte *payload, unsigned int len) {
    char cmd[len + 1];
    memcpy(cmd, payload, len);
    cmd[len] = '\0';

    Serial.printf("[MQTT] %s: %s\n", topic, cmd);

    // pixelos/enroll/confirm/<name>
    char expected[64];
    snprintf(expected, sizeof(expected), "pixelos/enroll/confirm/" NODE_NAME);
    if (strcmp(topic, expected) == 0) {
        if (strcmp(cmd, "OK") == 0) {
            Serial.println("[ENROLL] ✅ Enregistrement confirmé par PixelOS");
            enrolled = true;
        }
    }

    // pixelos/commande/beacon/<name>
    snprintf(expected, sizeof(expected), "pixelos/commande/beacon/" NODE_NAME);
    if (mqtt.topic_matches_sub("pixelos/commande/beacon/+", topic)) {
        if (strcmp(cmd, "STATUS") == 0) {
            enrollMQTT(); // Renvoyer les infos
        }
    }
}

// ========================================
//  Setup
// ========================================
void setup() {
    Serial.begin(115200);
    Serial.printf("\n[PixelOS] Beacon %s-%s (adr %d)\n",
                  NODE_TYPE, NODE_NAME, NODE_ADDR);
    Serial.printf("[PixelOS] SSID AP: %s\n", SSID_AP);

    // 1. Démarrer le BLE beacon immédiatement
    startBLEBeacon();

    // 2. Wi-Fi : client si réseau configuré, sinon AP
    if (strlen(WIFI_SSID) > 0) {
        Serial.printf("[WiFi] Connexion à %s...\n", WIFI_SSID);
        WiFi.mode(WIFI_STA);
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

        mqtt.setServer(MQTT_BROKER, MQTT_PORT);
        mqtt.setCallback(mqttCallback);
        mqtt.subscribe("pixelos/enroll/confirm/+");
        mqtt.subscribe("pixelos/commande/beacon/+");
    } else {
        // Mode AP : le scanner Wi-Fi détecte le SSID "PIXELOS-..."
        startWiFiAP();
    }
}

// ========================================
//  Loop
// ========================================
void loop() {
    // Rafraîchir le BLE beacon périodiquement
    unsigned long now = millis();
    if (now - last_beacon > 30000) {  // Toutes les 30s
        BLEDevice::startAdvertising();
        last_beacon = now;
    }

    // Tentative d'enrollment MQTT toutes les 10s
    if (!enrolled && strlen(WIFI_SSID) > 0) {
        if (now - last_enroll_attempt > 10000) {
            enrollMQTT();
            last_enroll_attempt = now;
        }
        mqtt.loop();
    }

    delay(100);
}
