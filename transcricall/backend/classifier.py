import re
from typing import List


class HotLeadClassifier:
    def __init__(self):
        # Simple Spanish keyword list with weights
        self.weighted_keywords = [
            (r"\bme interesa(n)?\b", 1.5),
            (r"\bestoy interesado(a)?\b", 1.5),
            (r"\bquiero (comprar|contratar|adquirir)\b", 2.0),
            (r"\b(cerrar|agendar) (la )?cita\b", 1.5),
            (r"\b(crédito|prestamo|préstamo)\b", 1.0),
            (r"\btarjeta (de )?crédito\b", 1.0),
            (r"\b(hacer|realizar) pago\b", 1.2),
            (r"\bme (conviene|gusta)\b", 0.8),
            (r"\b(enviar|mándame|mandame) información\b", 0.8),
            (r"\b(cómo|como) (funciona|aplico|aplicar)\b", 0.8),
            (r"\bpromoción\b", 0.6),
            (r"\bdescuento\b", 0.6),
            (r"\bacepto\b", 1.2),
            (r"\bcuando puedo\b", 0.7),
            (r"\b(dónde|donde) firmo\b", 1.5),
        ]
        self.threshold = 2.0

    def score_text(self, text: str) -> float:
        t = (text or "").lower()
        score = 0.0
        for pattern, weight in self.weighted_keywords:
            if re.search(pattern, t):
                score += weight
        return round(score, 3)