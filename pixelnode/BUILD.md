# PixelNode — Nœud Android Pixel OS

Transformez un vieux smartphone en **nœud Pixel OS actif** : heartbeat, DHT, relai MQTT, light client Ethereum (Gnosis).

## Build
```bash
cd pixelnode
./gradlew assembleDebug
```

APK : `app/build/outputs/apk/debug/app-debug.apk`

## Fonctionnalités
- **PixelNodeService** (Foreground) : heartbeat UDP, DHT Kademlia, relai MQTT
- **EthLightClient** : synchronisation en-têtes Gnosis Chain, solde BITROOT
- **PixKeyManager** : identité stockée dans le Keystore Android (EC secp256k1)
- **BootReceiver** : démarrage automatique au boot
- **UI Compose** : statut en temps réel (pairs, bloc ETH, batterie)

## Structure
```
pixelnode/app/src/main/java/org/pixelos/node/
├── PixelNodeApp.kt          # Application + notifications
├── MainActivity.kt          # UI Compose
├── BootReceiver.kt          # Démarrage au boot
├── service/
│   ├── PixelNodeService.kt  # Foreground service principal
│   └── MqttRelayService.kt  # Relai MQTT
├── net/
│   ├── Heartbeat.kt         # UDP heartbeat (port 9100)
│   └── PixDht.kt            # DHT Kademlia simplifiée
├── eth/
│   └── EthLightClient.kt    # Light client Gnosis Chain
└── crypto/
    └── PixKeyManager.kt     # Keystore + clé Ed25519/EC
```
