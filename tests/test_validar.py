"""Cada regla de control, con historial simulado."""
from bandeja.modelos import Documento, Item
from bandeja.validar import validar


def doc(**cambios):
    base = dict(tipo="factura", proveedor="Proveedor SA", cuit="30-11111111-1", numero="0001-00000001",
                fecha="2026-11-10", items=[Item(descripcion="Yerba mate 1 kg", cantidad=10, precio_unitario=1000,
                                                subtotal=10000)], impuestos=2100, total=12100)
    base.update(cambios)
    return Documento(**base)


def tipos(d, duplicado=None, precio=None, conocido=True):
    alertas = validar(d, es_duplicado=lambda p, n: duplicado, ultimo_precio=lambda p, desc: precio,
                      proveedor_conocido=lambda p, c: conocido)
    return [a.tipo for a in alertas]


def test_documento_correcto_no_tiene_alertas():
    assert tipos(doc()) == []


def test_total_que_no_cierra():
    assert tipos(doc(total=13100)) == ["total"]


def test_diferencia_de_redondeo_se_tolera():
    assert tipos(doc(total=12100.6)) == []


def test_linea_mal_calculada():
    d = doc(items=[Item(descripcion="Azúcar", cantidad=3, precio_unitario=500, subtotal=1600)], impuestos=None,
            total=1600)
    assert tipos(d) == ["linea"]


def test_duplicado():
    assert tipos(doc(), duplicado=4) == ["duplicado"]


def test_aumento_mayor_al_umbral():
    assert tipos(doc(), precio=850) == ["aumento"]       # 1000 vs 850 = +17,6 %


def test_aumento_chico_no_avisa():
    assert tipos(doc(), precio=950) == []                # +5,3 %


def test_pedido_no_se_compara_contra_precios():
    assert tipos(doc(tipo="pedido"), precio=500) == []


def test_proveedor_fuera_del_padron():
    assert tipos(doc(), conocido=False) == ["proveedor_nuevo"]


def test_factura_sin_cuit_ni_numero():
    assert tipos(doc(cuit=None, numero=None)) == ["dato_faltante"]


def test_observacion_de_la_lectura_se_muestra():
    assert tipos(doc(observaciones="Hay una tachadura en el total")) == ["revisar"]
