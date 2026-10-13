from django.conf import settings

from .models import Assunto, Frente, Questao


def _percentual(parte, total):
    return min(100, round(parte * 100 / total)) if total else 0


def calcular_metas():
    """
    Metas do banco de questões, para o card "Metas" da página inicial.

    A meta de aulas é preencher todas as aulas possíveis (soma do limite de
    aulas de cada frente: 30, ou 15 em Sociologia/Filosofia e Português). A
    meta de questões é `META_QUESTOES_POR_AULA` (13) por aula possível.
    """
    por_aula = settings.META_QUESTOES_POR_AULA
    aulas_possiveis = sum(frente.limite_aula for frente in Frente.objects.all())
    aulas_cadastradas = Assunto.objects.count()
    questoes = Questao.objects.count()
    meta_questoes = aulas_possiveis * por_aula

    return {
        "por_aula": por_aula,
        "aulas_possiveis": aulas_possiveis,
        "aulas_cadastradas": aulas_cadastradas,
        "aulas_percentual": _percentual(aulas_cadastradas, aulas_possiveis),
        "questoes": questoes,
        "meta_questoes": meta_questoes,
        "questoes_percentual": _percentual(questoes, meta_questoes),
        "questoes_faltando": max(0, meta_questoes - questoes),
        "media_atual": round(questoes / aulas_cadastradas, 1) if aulas_cadastradas else 0,
    }
