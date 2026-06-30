package org.pixelos.node

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.pixelos.node.service.PixelNodeService

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { PixelNodeScreen() }
    }
}

@Composable
fun PixelNodeScreen() {
    var isRunning by remember { mutableStateOf(PixelNodeService.isRunning) }
    var peers by remember { mutableStateOf(PixelNodeService.peersCount) }
    var ethBlock by remember { mutableStateOf(PixelNodeService.ethBlock) }
    val app = PixelNodeApp.instance

    LaunchedEffect(Unit) {
        while (true) {
            isRunning = PixelNodeService.isRunning
            peers = PixelNodeService.peersCount
            ethBlock = PixelNodeService.ethBlock
            delay(3_000)
        }
    }

    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = androidx.compose.ui.graphics.Color(0xFF66BB6A),
            secondary = androidx.compose.ui.graphics.Color(0xFF2E7D32),
            surface = androidx.compose.ui.graphics.Color(0xFF1B1B1B),
            background = androidx.compose.ui.graphics.Color(0xFF121212),
            onPrimary = androidx.compose.ui.graphics.Color.White,
            onSurface = androidx.compose.ui.graphics.Color.White,
        )
    ) {
        Scaffold(
            modifier = Modifier.fillMaxSize(),
            topBar = {
                TopAppBar(title = { Text("PixelNode") })
            }
        ) { padding ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text("Nœud Pixel OS", style = MaterialTheme.typography.headlineMedium)
                Spacer(Modifier.height(8.dp))
                Text(app.pixKey.nodeId(), style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.primary)

                Spacer(Modifier.height(32.dp))

                if (isRunning) {
                    StatusCard("Statut", "Actif", MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.height(12.dp))
                    StatusCard("Pairs connectés", "$peers", MaterialTheme.colorScheme.secondary)
                    Spacer(Modifier.height(12.dp))
                    StatusCard("Dernier bloc ETH", "$ethBlock", MaterialTheme.colorScheme.tertiary)
                } else {
                    Text("Nœud arrêté", color = MaterialTheme.colorScheme.error, fontSize = 18.sp)
                }

                Spacer(Modifier.weight(1f))

                Button(
                    onClick = {
                        if (isRunning) {
                            PixelNodeService.stop(this@PixelNodeScreen)
                        } else {
                            PixelNodeService.start(this@PixelNodeScreen)
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isRunning) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary
                    )
                ) {
                    Text(if (isRunning) "Arrêter le nœud" else "Démarrer le nœud", fontSize = 18.sp)
                }

                Spacer(Modifier.height(16.dp))

                Text("v1.0.0 · Pixel OS Mobile Node", style = MaterialTheme.typography.bodySmall)
                Text("© 2026 Pixel Software Design", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
fun StatusCard(label: String, value: String, color: androidx.compose.ui.graphics.Color) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.1f))
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(label, fontWeight = FontWeight.Medium)
            Text(value, fontWeight = FontWeight.Bold, fontSize = 18.sp)
        }
    }
}
