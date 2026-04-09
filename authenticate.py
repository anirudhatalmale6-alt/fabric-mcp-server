"""
Run this script ONCE to authenticate with Microsoft.
After authenticating, the token is cached and the MCP server
will use it automatically without needing to authenticate again.
"""

import os
import sys
from pathlib import Path

# Set env vars for the auth
CLIENT_ID = os.environ.get("FABRIC_CLIENT_ID", "7f67af8a-fedc-4b08-8b4e-37c4d127b6cf")
TENANT_ID = os.environ.get("FABRIC_TENANT_ID", "f25bg3e8-cd4c-4de5-ba62-ac45f605318d")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://analysis.windows.net/powerbi/api/Dataset.Read.All"]
TOKEN_CACHE_FILE = Path(__file__).parent / ".token_cache.json"

try:
    import msal
except ImportError:
    print("ERROR: msal no esta instalado. Ejecuta: pip install msal")
    sys.exit(1)

def main():
    print("=" * 60)
    print("  Autenticacion con Microsoft para Fabric MCP Server")
    print("=" * 60)
    print()

    # Build MSAL app with cache
    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_FILE.exists():
        cache.deserialize(TOKEN_CACHE_FILE.read_text())

    app = msal.PublicClientApplication(
        CLIENT_ID, authority=AUTHORITY, token_cache=cache,
    )

    # Check if already authenticated
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            if cache.has_state_changed:
                TOKEN_CACHE_FILE.write_text(cache.serialize())
            print(f"Ya estas autenticado como: {accounts[0].get('username', 'unknown')}")
            print("El token esta vigente. El servidor MCP deberia funcionar correctamente.")
            print()
            input("Presiona Enter para salir...")
            return

    # Start device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        print(f"ERROR: No se pudo iniciar la autenticacion: {flow.get('error_description', 'unknown')}")
        input("Presiona Enter para salir...")
        sys.exit(1)

    print(f"Para autenticarte, sigue estos pasos:")
    print()
    print(f"  1. Abre tu navegador en: {flow['verification_uri']}")
    print(f"  2. Ingresa este codigo: {flow['user_code']}")
    print(f"  3. Inicia sesion con tu cuenta de Microsoft")
    print()
    print("Esperando a que completes la autenticacion en el navegador...")
    print()

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        # Save cache
        if cache.has_state_changed:
            TOKEN_CACHE_FILE.write_text(cache.serialize())

        print("=" * 60)
        print("  AUTENTICACION EXITOSA!")
        print("=" * 60)
        print()
        print(f"  Usuario: {result.get('id_token_claims', {}).get('preferred_username', 'OK')}")
        print(f"  Token guardado en: {TOKEN_CACHE_FILE}")
        print()
        print("  Ahora reinicia Claude Desktop y prueba de nuevo.")
        print("  El servidor MCP usara este token automaticamente.")
        print()
    else:
        print(f"ERROR: {result.get('error_description', 'Autenticacion fallida')}")

    input("Presiona Enter para salir...")


if __name__ == "__main__":
    main()
