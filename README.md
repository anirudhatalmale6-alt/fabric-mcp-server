# Fabric MCP Server

Servidor MCP que conecta Claude Desktop a modelos semánticos de Microsoft Fabric / Power BI.

## Herramientas disponibles

- **listar_workspaces** — Lista los workspaces accesibles
- **listar_datasets** — Lista todos los datasets (modelos semánticos)
- **datasets_en_workspace** — Lista datasets de un workspace específico
- **listar_tablas** — Lista las tablas de un dataset
- **explorar_modelo** — Muestra tablas, columnas y medidas DAX del modelo
- **consultar_dax** — Ejecuta consultas DAX y devuelve resultados

## Instalación (Windows)

### 1. Instalar dependencias

Ejecuta `setup.bat` o manualmente:

```
pip install mcp[cli] msal requests
```

### 2. Configurar Claude Desktop

Copia `claude_desktop_config.example.json` y edita:
- Cambia la ruta `C:\\ruta\\a\\fabric-mcp-server\\server.py` a donde descargaste los archivos
- Los IDs de cliente y tenant ya están configurados

Luego en Claude Desktop: Settings > Developer > Edit Config, y pega el contenido.

### 3. Reinicia Claude Desktop

Al reiniciar, verás un icono de herramientas (martillo) que indica que el servidor MCP está conectado.

### 4. Autenticación

La primera vez que uses una herramienta, aparecerá un código en los logs de Claude Desktop.
Abre el navegador en https://microsoft.com/devicelogin e ingresa el código para autenticarte.
El token se guarda en caché para no repetir este paso.

## Uso

Una vez conectado, puedes pedirle a Claude cosas como:
- "Lista mis datasets disponibles"
- "Explora el modelo Modelo de Datos Centralizado"
- "Consulta las ventas por país del 2023"
- "Ejecuta esta medida DAX: [Mi Medida]"
