"""
MCP Server for Microsoft Fabric Semantic Models.

Connects Claude Desktop to Power BI / Fabric semantic models
via the Power BI REST API, using device code authentication.
"""

import json
import os
import sys
import logging
from pathlib import Path
from typing import Any

import msal
import requests
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CLIENT_ID = os.environ.get("FABRIC_CLIENT_ID", "")
TENANT_ID = os.environ.get("FABRIC_TENANT_ID", "")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://analysis.windows.net/powerbi/api/Dataset.Read.All"]
PBI_BASE = "https://api.powerbi.com/v1.0/myorg"

TOKEN_CACHE_FILE = Path(__file__).parent / ".token_cache.json"

# Logging
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("fabric-mcp")

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _build_msal_app() -> msal.PublicClientApplication:
    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_FILE.exists():
        cache.deserialize(TOKEN_CACHE_FILE.read_text())
    app = msal.PublicClientApplication(
        CLIENT_ID, authority=AUTHORITY, token_cache=cache,
    )
    return app, cache


def _save_cache(cache: msal.SerializableTokenCache):
    if cache.has_state_changed:
        TOKEN_CACHE_FILE.write_text(cache.serialize())


def get_access_token() -> str:
    """Get a valid Power BI access token, using cache or device code flow."""
    app, cache = _build_msal_app()

    # Try cached token first
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(cache)
            return result["access_token"]

    # Device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow failed: {flow.get('error_description', 'unknown error')}")

    # Print to stderr so the user sees it (stdout is MCP transport)
    msg = (
        f"\n{'='*60}\n"
        f"AUTENTICACION REQUERIDA\n"
        f"{'='*60}\n"
        f"1. Abre tu navegador en: {flow['verification_uri']}\n"
        f"2. Ingresa el codigo: {flow['user_code']}\n"
        f"3. Inicia sesion con tu cuenta de Microsoft\n"
        f"{'='*60}\n"
    )
    print(msg, file=sys.stderr, flush=True)

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Auth failed: {result.get('error_description', 'unknown error')}")

    _save_cache(cache)
    return result["access_token"]


def pbi_request(method: str, url: str, **kwargs) -> requests.Response:
    """Make an authenticated request to the Power BI REST API."""
    token = get_access_token()
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    headers.setdefault("Content-Type", "application/json")
    resp = requests.request(method, url, headers=headers, **kwargs)
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("Fabric Semantic Model")


@mcp.tool()
def listar_datasets() -> str:
    """
    Lista todos los datasets (modelos semánticos) a los que tienes acceso.
    Devuelve nombre, ID y workspace de cada uno.
    """
    resp = pbi_request("GET", f"{PBI_BASE}/datasets")
    datasets = resp.json().get("value", [])
    if not datasets:
        return "No se encontraron datasets accesibles."

    lines = []
    for ds in datasets:
        lines.append(
            f"- {ds['name']}\n"
            f"  ID: {ds['id']}\n"
            f"  Configured By: {ds.get('configuredBy', 'N/A')}\n"
            f"  Is Effective Identity Required: {ds.get('isEffectiveIdentityRequired', False)}"
        )
    return "Datasets disponibles:\n\n" + "\n\n".join(lines)


@mcp.tool()
def listar_tablas(dataset_id: str) -> str:
    """
    Lista las tablas de un dataset específico.

    Args:
        dataset_id: El ID del dataset (usa listar_datasets para obtenerlo)
    """
    resp = pbi_request("GET", f"{PBI_BASE}/datasets/{dataset_id}/tables")
    tables = resp.json().get("value", [])
    if not tables:
        return "No se encontraron tablas en este dataset."

    lines = []
    for t in tables:
        cols = t.get("columns", [])
        col_names = [c["name"] for c in cols] if cols else []
        lines.append(
            f"- {t['name']}\n"
            f"  Columnas: {', '.join(col_names) if col_names else '(no disponibles via API, usa consultar_dax con COLUMNSTATISTICS)'}"
        )
    return f"Tablas en dataset {dataset_id}:\n\n" + "\n\n".join(lines)


@mcp.tool()
def consultar_dax(dataset_id: str, dax_query: str) -> str:
    """
    Ejecuta una consulta DAX contra un modelo semántico y devuelve los resultados.

    Usa EVALUATE para consultar tablas. Ejemplos:
    - EVALUATE TOPN(10, 'Ventas')
    - EVALUATE SUMMARIZECOLUMNS('Producto'[Categoria], "Total", SUM('Ventas'[Monto]))
    - EVALUATE { [Mi Medida DAX] }

    Para explorar el modelo:
    - EVALUATE INFO.TABLES()  -- lista todas las tablas
    - EVALUATE INFO.COLUMNS()  -- lista todas las columnas
    - EVALUATE INFO.MEASURES()  -- lista todas las medidas DAX

    Args:
        dataset_id: El ID del dataset
        dax_query: La consulta DAX a ejecutar (debe empezar con EVALUATE)
    """
    body = {
        "queries": [{"query": dax_query}],
        "serializerSettings": {"includeNulls": True},
    }
    resp = pbi_request(
        "POST",
        f"{PBI_BASE}/datasets/{dataset_id}/executeQueries",
        json=body,
    )
    data = resp.json()

    # Check for errors
    results = data.get("results", [])
    if not results:
        return "No se obtuvieron resultados."

    first = results[0]
    if "error" in first:
        return f"Error DAX: {json.dumps(first['error'], indent=2, ensure_ascii=False)}"

    tables = first.get("tables", [])
    if not tables:
        return "La consulta no devolvió tablas."

    # Format results
    rows = tables[0].get("rows", [])
    if not rows:
        return "La consulta se ejecutó correctamente pero no devolvió filas."

    # Get column names from first row
    columns = list(rows[0].keys())

    # Build text table
    output_lines = [" | ".join(columns)]
    output_lines.append(" | ".join(["---"] * len(columns)))
    for row in rows[:500]:  # Limit to 500 rows
        values = [str(row.get(c, "")) for c in columns]
        output_lines.append(" | ".join(values))

    total = len(rows)
    header = f"Resultados ({total} filas"
    if total > 500:
        header += ", mostrando primeras 500"
    header += "):\n\n"

    return header + "\n".join(output_lines)


@mcp.tool()
def explorar_modelo(dataset_id: str) -> str:
    """
    Explora la estructura completa de un modelo semántico: tablas, columnas y medidas.
    Útil como primer paso para entender qué datos hay disponibles.

    Args:
        dataset_id: El ID del dataset
    """
    output_parts = []

    # Get tables info
    try:
        body = {"queries": [{"query": "EVALUATE INFO.TABLES()"}], "serializerSettings": {"includeNulls": True}}
        resp = pbi_request("POST", f"{PBI_BASE}/datasets/{dataset_id}/executeQueries", json=body)
        data = resp.json()
        tables = data["results"][0]["tables"][0]["rows"]
        output_parts.append(f"TABLAS ({len(tables)}):")
        for t in tables:
            name = t.get("[Name]", "?")
            output_parts.append(f"  - {name}")
    except Exception as e:
        output_parts.append(f"Error obteniendo tablas: {e}")

    output_parts.append("")

    # Get measures
    try:
        body = {"queries": [{"query": "EVALUATE INFO.MEASURES()"}], "serializerSettings": {"includeNulls": True}}
        resp = pbi_request("POST", f"{PBI_BASE}/datasets/{dataset_id}/executeQueries", json=body)
        data = resp.json()
        measures = data["results"][0]["tables"][0]["rows"]
        output_parts.append(f"MEDIDAS DAX ({len(measures)}):")
        for m in measures:
            name = m.get("[Name]", "?")
            table = m.get("[TableID]", "?")
            expr = m.get("[Expression]", "")
            output_parts.append(f"  - {name}")
            if expr:
                # Truncate long expressions
                expr_short = expr[:200] + "..." if len(expr) > 200 else expr
                output_parts.append(f"    Expresión: {expr_short}")
    except Exception as e:
        output_parts.append(f"Error obteniendo medidas: {e}")

    output_parts.append("")

    # Get columns
    try:
        body = {"queries": [{"query": "EVALUATE INFO.COLUMNS()"}], "serializerSettings": {"includeNulls": True}}
        resp = pbi_request("POST", f"{PBI_BASE}/datasets/{dataset_id}/executeQueries", json=body)
        data = resp.json()
        columns = data["results"][0]["tables"][0]["rows"]
        output_parts.append(f"COLUMNAS ({len(columns)}):")

        # Group by table
        by_table: dict[str, list] = {}
        for c in columns:
            tid = str(c.get("[TableID]", "?"))
            by_table.setdefault(tid, []).append(c)

        for tid, cols in by_table.items():
            output_parts.append(f"  Tabla ID {tid}:")
            for c in cols:
                name = c.get("[ExplicitName]", c.get("[InferredName]", "?"))
                dtype = c.get("[ExplicitDataType]", c.get("[InferredDataType]", "?"))
                output_parts.append(f"    - {name} ({dtype})")
    except Exception as e:
        output_parts.append(f"Error obteniendo columnas: {e}")

    return "\n".join(output_parts)


@mcp.tool()
def listar_workspaces() -> str:
    """
    Lista los workspaces (grupos) a los que tienes acceso en Power BI / Fabric.
    """
    resp = pbi_request("GET", f"{PBI_BASE}/groups")
    groups = resp.json().get("value", [])
    if not groups:
        return "No se encontraron workspaces accesibles."

    lines = []
    for g in groups:
        lines.append(f"- {g['name']} (ID: {g['id']})")
    return "Workspaces disponibles:\n\n" + "\n".join(lines)


@mcp.tool()
def datasets_en_workspace(workspace_id: str) -> str:
    """
    Lista los datasets de un workspace específico.

    Args:
        workspace_id: El ID del workspace (usa listar_workspaces para obtenerlo)
    """
    resp = pbi_request("GET", f"{PBI_BASE}/groups/{workspace_id}/datasets")
    datasets = resp.json().get("value", [])
    if not datasets:
        return "No se encontraron datasets en este workspace."

    lines = []
    for ds in datasets:
        lines.append(f"- {ds['name']} (ID: {ds['id']})")
    return f"Datasets en workspace {workspace_id}:\n\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not CLIENT_ID or not TENANT_ID:
        print(
            "ERROR: Define las variables de entorno FABRIC_CLIENT_ID y FABRIC_TENANT_ID",
            file=sys.stderr,
        )
        sys.exit(1)
    mcp.run(transport="stdio")
