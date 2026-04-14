"""Parser de mensajes de pedido tipo WhatsApp."""

from __future__ import annotations

import re
from typing import Any


def parse_whatsapp_message(texto: str, catalogo: list) -> list[dict]:
    """
    Parsea un mensaje de WhatsApp extrayendo productos y cantidades.
    
    Args:
        texto: Mensaje de texto a parsear
        catalogo: Lista de diccionarios con productos {id, nombre, precio}
    
    Returns:
        Lista de diccionarios con keys: producto_id, nombre, cantidad (int), precio_unitario, total
    """
    if not texto or not catalogo:
        return []
    
    texto_lower = texto.lower()
    
    numeros_palabras = {
        "un": 1, "una": 1, "uno": 1,
        "dos": 2,
        "tres": 3,
        "cuatro": 4,
        "cinco": 5,
        "seis": 6,
        "siete": 7,
        "ocho": 8,
        "nueve": 9,
        "diez": 10,
    }
    
    separadores = [r'\s+y\s+', r',\s*', r'\s+por\s+favor\s*', r'\s+por\s+fa', r'\s+por\s+']
    
    resultados = []
    
    pattern = r'(\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+([a-zA-ZáéíóúñÁÉÍÓÚÑ][\w\s]*[\wáéíóúñÁÉÍÓÚÑ]?)'
    
    matches = re.findall(pattern, texto_lower)
    
    productos_procesados = set()
    
    for cantidad_palabra, producto_mencionado in matches:
        producto_mencionado = producto_mencionado.strip()
        
        if cantidad_palabra.isdigit():
            cantidad_base = int(cantidad_palabra)
        elif cantidad_palabra in numeros_palabras:
            cantidad_base = numeros_palabras[cantidad_palabra]
        else:
            continue
        
        if cantidad_base <= 0:
            continue
        
        sub_partes = re.split(r'\s+[y,]\s+', producto_mencionado)
        
        i = 0
        while i < len(sub_partes):
            sub_parte = sub_partes[i].strip()
            if not sub_parte or len(sub_parte) < 2:
                i += 1
                continue
            
            num_match = re.match(r'^(\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+(.+)$', sub_parte)
            if num_match:
                cantidad_str = num_match.group(1)
                producto_text = num_match.group(2).strip()
                
                if cantidad_str.isdigit():
                    cantidad = int(cantidad_str)
                elif cantidad_str in numeros_palabras:
                    cantidad = numeros_palabras[cantidad_str]
                else:
                    cantidad = cantidad_base
                    producto_text = sub_parte
            else:
                cantidad = cantidad_base
                producto_text = sub_parte
            
            if not producto_text or len(producto_text) < 2:
                i += 1
                continue
            
            clave = producto_text[:10]
            if clave in productos_procesados:
                i += 1
                continue
            productos_procesados.add(clave)
            
            mejor_match = None
            mejor_score = 0
            
            for prod in catalogo:
                nombre_prod = prod.get("nombre", "").lower().strip()
                
                if nombre_prod in producto_text:
                    score = len(nombre_prod)
                elif producto_text in nombre_prod:
                    score = len(producto_text)
                else:
                    palabras_prod = set(nombre_prod.split())
                    palabras_men = set(producto_text.split())
                    interseccion = palabras_prod & palabras_men
                    if interseccion:
                        score = sum(len(p) for p in interseccion)
                    else:
                        continue
                
                if score > mejor_score:
                    mejor_score = score
                    mejor_match = prod
            
            if mejor_match:
                precio_unitario = float(mejor_match.get("precio_unitario", 0))
                total = cantidad * precio_unitario
                
                resultados.append({
                    "producto_id": mejor_match.get("id"),
                    "nombre": mejor_match.get("nombre"),
                    "cantidad": cantidad,
                    "precio_unitario": precio_unitario,
                    "total": total,
                })
            
            i += 1
    
    return resultados


def parse_whatsapp_message_items(text: str) -> dict[str, Any]:
    """
    Extrae ítems de líneas de texto (pedidos por chat).

    Devuelve:
        badge: 'ok' | 'warning' | 'error'
        mensaje: texto para el usuario
        items: lista de dicts con claves Producto, Cantidad, Precio Unitario, Total
    """
    raw = (text or "").strip()
    if not raw:
        return {
            "badge": "error",
            "mensaje": "El mensaje está vacío.",
            "items": [],
        }

    items: list[dict[str, float | str]] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[-*•]\s*", "", line)
        parsed = _parse_line(line)
        if parsed:
            items.append(parsed)

    if not items:
        return {
            "badge": "warning",
            "mensaje": "No se detectaron productos. Use líneas como: 2 x Arepa 5000 o Combo ejecutivo x1 19000",
            "items": [],
        }

    sin_precio = sum(
        1
        for it in items
        if float(it["Precio Unitario"]) <= 0 or float(it["Total"]) <= 0
    )
    if sin_precio:
        return {
            "badge": "warning",
            "mensaje": f"Se detectaron {len(items)} ítem(s); {sin_precio} sin precio claro. Revise y complete en la tabla.",
            "items": items,
        }

    return {
        "badge": "ok",
        "mensaje": f"Se detectaron {len(items)} producto(s). Revise cantidades y precios antes de confirmar.",
        "items": items,
    }


def _parse_num(s: str) -> float:
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_line(line: str) -> dict[str, float | str] | None:
    # "2 x Producto 5000" o "2x Producto 5.000"
    m = re.match(
        r"^(\d+(?:[.,]\d+)?)\s*x\s+(.+?)(?:\s+([\d.,]+))?\s*$",
        line,
        re.IGNORECASE,
    )
    if m:
        cant = _parse_num(m.group(1))
        nombre = m.group(2).strip()
        precio_txt = m.group(3)
        if precio_txt:
            pu = _parse_num(precio_txt)
        else:
            pu = 0.0
        total = cant * pu if pu > 0 else 0.0
        return {
            "Producto": nombre,
            "Cantidad": float(cant),
            "Precio Unitario": float(pu),
            "Total": float(total),
        }

    # "Producto x2 5000"
    m = re.match(
        r"^(.+?)\s+x\s*(\d+(?:[.,]\d+)?)(?:\s+([\d.,]+))?\s*$",
        line,
        re.IGNORECASE,
    )
    if m:
        nombre = m.group(1).strip()
        cant = _parse_num(m.group(2))
        precio_txt = m.group(3)
        pu = _parse_num(precio_txt) if precio_txt else 0.0
        total = cant * pu if pu > 0 else 0.0
        return {
            "Producto": nombre,
            "Cantidad": float(cant),
            "Precio Unitario": float(pu),
            "Total": float(total),
        }

    # "2 Producto 5000" (cantidad al inicio, precio al final)
    m = re.match(
        r"^(\d+(?:[.,]\d+)?)\s+(.+?)\s+([\d.,]+)\s*$",
        line,
    )
    if m:
        cant = _parse_num(m.group(1))
        nombre = m.group(2).strip()
        pu = _parse_num(m.group(3))
        total = cant * pu
        return {
            "Producto": nombre,
            "Cantidad": float(cant),
            "Precio Unitario": float(pu),
            "Total": float(total),
        }

    # Una sola palabra o frase sin números -> ignorar
    if re.search(r"\d", line):
        # intento genérico: último número como precio, primero como cantidad
        nums = re.findall(r"[\d.,]+", line)
        if len(nums) >= 2:
            cant = _parse_num(nums[0])
            pu = _parse_num(nums[-1])
            resto = line
            for n in nums:
                resto = resto.replace(n, " ", 1)
            nombre = re.sub(r"\s+", " ", resto).strip(" -•*")
            if nombre and cant > 0 and pu >= 0:
                total = cant * pu
                return {
                    "Producto": nombre,
                    "Cantidad": float(cant),
                    "Precio Unitario": float(pu),
                    "Total": float(total),
                }

    return None


if __name__ == "__main__":
    catalogo_ejemplo = [
        {"id": 1, "nombre": "Arepa con queso", "precio": 5000},
        {"id": 2, "nombre": "Hamburguesa", "precio": 12000},
        {"id": 3, "nombre": "Papas fritas", "precio": 6000},
        {"id": 4, "nombre": "Gaseosa", "precio": 2500},
        {"id": 5, "nombre": "Combo ejecutivo", "precio": 19000},
    ]
    
    mensajes_prueba = [
        "Quiero 2 arepas con queso y una hamburguesa",
        "orden: 3 papas fritas, 2 gaseosas",
        "Me gustaría cinco combos ejecutivos por favor",
        "Necesito cuatro hamburguesas",
        " nada aquí",
        "Solo texto sin productos",
    ]
    
    print("=== Pruebas de parse_whatsapp_message ===\n")
    
    for i, msg in enumerate(mensajes_prueba, 1):
        print(f"Prueba {i}: '{msg}'")
        resultado = parse_whatsapp_message(msg, catalogo_ejemplo)
        if resultado:
            for item in resultado:
                print(f"  - {item['cantidad']} x {item['nombre']} = ${item['total']}")
        else:
            print("  (sin resultados)")
        print()
