DYNAMIC_FIELDS_BY_PROCEDURE = {
    "Pensión Alimentaria": [
        {"name": "nombre_menor", "label": "Nombre del menor", "type": "text", "required": True},
        {"name": "fecha_nacimiento", "label": "Fecha de nacimiento", "type": "date", "required": True},
        {"name": "cantidad_hijos", "label": "Cantidad de hijos", "type": "number", "required": True},
        {"name": "representante_legal", "label": "Representante Legal", "type": "text", "required": True},
        {"name": "demandante", "label": "Demandante", "type": "text", "required": True},
        {"name": "demandado", "label": "Demandado", "type": "text", "required": True},
        {"name": "monto_solicitado", "label": "Monto solicitado (RD$)", "type": "number", "required": True},
        {"name": "monto_fijado", "label": "Monto fijado por sentencia (RD$)", "type": "number", "required": False},
        {"name": "numero_hijos_beneficiarios", "label": "Número de hijos beneficiarios", "type": "number", "required": False},
        {"name": "observaciones", "label": "Observaciones", "type": "textarea", "required": False}
    ],
    "Custodia": [
        {"name": "menor_involucrado", "label": "Menor involucrado", "type": "text", "required": True},
        {"name": "padre", "label": "Padre", "type": "text", "required": True},
        {"name": "madre", "label": "Madre", "type": "text", "required": True},
        {"name": "custodia_actual", "label": "Custodia actual", "type": "text", "required": True},
        {"name": "custodia_solicitada", "label": "Custodia solicitada", "type": "text", "required": True},
        {"name": "existe_acuerdo", "label": "Existe acuerdo", "type": "select", "options": ["Sí", "No"], "required": True},
        {"name": "regimen_visitas", "label": "Régimen de visitas", "type": "text", "required": False},
        {"name": "medidas_provisionales", "label": "Medidas provisionales", "type": "text", "required": False}
    ],
    "Cobro de Pesos": [
        {"name": "monto_demandado", "label": "Monto demandado (RD$)", "type": "number", "required": True},
        {"name": "contrato_origen", "label": "Contrato origen", "type": "text", "required": True},
        {"name": "fecha_incumplimiento", "label": "Fecha del incumplimiento", "type": "date", "required": True},
        {"name": "existe_pagare", "label": "Existe pagaré", "type": "select", "options": ["Sí", "No"], "required": True},
        {"name": "existe_garantia", "label": "Existe garantía", "type": "select", "options": ["Sí", "No"], "required": True}
    ],
    "Residencia Temporal": [
        {"name": "nacionalidad", "label": "Nacionalidad", "type": "text", "required": True},
        {"name": "tipo_residencia", "label": "Tipo de residencia", "type": "text", "required": True},
        {"name": "categoria_migratoria", "label": "Categoría migratoria", "type": "text", "required": True},
        {"name": "numero_expediente_dgm", "label": "Número de expediente DGM", "type": "text", "required": True},
        {"name": "fecha_vencimiento", "label": "Fecha de vencimiento", "type": "date", "required": True},
        {"name": "estado_tramite", "label": "Estado del trámite", "type": "text", "required": True}
    ]
}
