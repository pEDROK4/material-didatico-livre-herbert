import uuid
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from PIL import Image, UnidentifiedImageError

from .forms import LETRAS_ALTERNATIVAS, AssuntoForm, QuestaoForm
from .models import Assunto, Disciplina, Frente, Questao
from .sanitizacao import sanitizar_html_enunciado

# Cores do gráfico de disciplinas — ciclam nessa ordem se houver mais
# disciplinas do que cores (não deveria acontecer nas 9 do cursinho).
CORES_DISCIPLINAS = [
    "#2952e3", "#0a7d2c", "#c2410c", "#7c3aed", "#0891b2",
    "#be185d", "#a15c00", "#4d7c0f", "#475569",
]


@login_required
def planejamento(request):
    """
    Tabela de planejamento: para cada disciplina, uma tabela por
    frente com os assuntos cadastrados (ordenados por aula) e quantas
    questões cada um já tem. Clicar no número da aula abre o mesmo
    modal do cadastro, preenchido, com os botões Salvar e Excluir
    (tudo por GET/POST na mesma página, sem depender de JavaScript
    para abrir/fechar).

    Cada professor só vê (e só pode cadastrar/editar/excluir em) as
    frentes que a coordenação atribuiu a ele em Frente.professores —
    exceto coordenadores (superusuários), que sempre veem tudo.

    Duas aulas com o mesmo número na mesma frente não convivem: ao
    salvar uma aula com número já ocupado, a tela pede confirmação e,
    se confirmada, a aula antiga é apagada. Se a antiga já tem
    questões, não dá pra substituir (as questões ficariam órfãs) — a
    pessoa precisa escolher outro número.
    """
    usuario = request.user

    if usuario.is_superuser:
        frentes_permitidas = Frente.objects.all()
    else:
        frentes_permitidas = Frente.objects.filter(professores=usuario)

    abrir_formulario = request.GET.get("cadastrar") == "1"
    assunto_em_edicao = None
    conflito = None
    dados_reenvio = []

    if request.method == "POST":
        if request.POST.get("acao") == "excluir":
            assunto = get_object_or_404(
                Assunto, pk=request.POST.get("assunto_id"), frente__in=frentes_permitidas
            )
            num_questoes = assunto.questoes.count()
            if num_questoes:
                messages.error(
                    request,
                    f"A aula {assunto.aula} — {assunto.nome} já tem {num_questoes} "
                    f"questão(ões) e não pode ser excluída.",
                )
            else:
                assunto.delete()
                messages.success(request, f"Aula {assunto.aula} excluída.")
            return redirect("core:planejamento")

        assunto_id = request.POST.get("assunto_id")
        if assunto_id:
            assunto_em_edicao = get_object_or_404(
                Assunto, pk=assunto_id, frente__in=frentes_permitidas
            )
        form = AssuntoForm(request.POST, instance=assunto_em_edicao, usuario=usuario)

        if form.is_valid():
            ocupando_o_numero = Assunto.objects.filter(
                frente=form.cleaned_data["frente"], aula=form.cleaned_data["aula"]
            )
            if assunto_em_edicao is not None:
                ocupando_o_numero = ocupando_o_numero.exclude(pk=assunto_em_edicao.pk)
            existente = ocupando_o_numero.first()

            if existente is None:
                form.save()
                messages.success(
                    request,
                    "Aula atualizada." if assunto_em_edicao else "Assunto cadastrado com sucesso.",
                )
                return redirect("core:planejamento")

            num_questoes = existente.questoes.count()
            if num_questoes:
                form.add_error(
                    None,
                    f"A aula {existente.aula} ({existente.nome}) já tem {num_questoes} "
                    f"questão(ões) e não pode ser substituída. Escolha outro número "
                    f"de aula ou edite a aula existente.",
                )
                abrir_formulario = True
            elif request.POST.get("confirmar_substituicao") == "1":
                with transaction.atomic():
                    existente.delete()
                    form.save()
                messages.success(request, f"Aula {existente.aula} substituída.")
                return redirect("core:planejamento")
            else:
                conflito = existente
                dados_reenvio = [
                    (campo, request.POST.get(campo, ""))
                    for campo in ("assunto_id", "disciplina", "frente", "nome", "descricao", "aula")
                ]
        else:
            abrir_formulario = True
    elif request.GET.get("editar"):
        assunto_em_edicao = get_object_or_404(
            Assunto, pk=request.GET["editar"], frente__in=frentes_permitidas
        )
        form = AssuntoForm(instance=assunto_em_edicao, usuario=usuario)
        abrir_formulario = True
    else:
        form = AssuntoForm(usuario=usuario)

    assuntos_com_contagem = Assunto.objects.annotate(
        num_questoes=Count("questoes")
    ).order_by("aula", "nome")

    disciplinas = (
        Disciplina.objects.filter(frentes__in=frentes_permitidas)
        .distinct()
        .prefetch_related(
            Prefetch(
                "frentes",
                queryset=frentes_permitidas.order_by("letra").prefetch_related(
                    Prefetch("assuntos", queryset=assuntos_com_contagem)
                ),
            )
        )
        .order_by("nome")
    )

    return render(
        request,
        "questoes/planejamento.html",
        {
            "disciplinas": disciplinas,
            "form": form,
            "abrir_formulario": abrir_formulario,
            "assunto_em_edicao": assunto_em_edicao,
            "num_questoes_edicao": assunto_em_edicao.questoes.count() if assunto_em_edicao else 0,
            "conflito": conflito,
            "dados_reenvio": dados_reenvio,
            "sem_frentes_atribuidas": not usuario.is_superuser
            and not frentes_permitidas.exists(),
        },
    )


@login_required
def estatisticas(request):
    """
    Painel de "andamento geral" — pensado pra caber numa tela só, sem
    scroll: uns números grandes no topo e dois gráficos embaixo
    (ranking de disciplinas e fatia de questões por disciplina). Todo
    mundo logado vê a mesma coisa, não é restrito por frente — é uma
    visão do banco inteiro, não do que cada professor cadastrou.
    """
    total_questoes = Questao.objects.count()
    total_assuntos = Assunto.objects.count()

    capacidade_total_aulas = sum(frente.limite_aula for frente in Frente.objects.all())
    cobertura_aulas = round(total_assuntos * 100 / capacidade_total_aulas) if capacidade_total_aulas else 0

    disciplinas = list(
        Disciplina.objects.annotate(
            num_questoes=Count("frentes__assuntos__questoes", distinct=True),
            num_assuntos=Count("frentes__assuntos", distinct=True),
        ).order_by("-num_questoes", "nome")
    )
    total_disciplinas_com_conteudo = sum(1 for d in disciplinas if d.num_questoes > 0)

    # Capacidade de aulas de cada disciplina (soma do limite de aula das
    # frentes dela), pra medir o quanto do conteúdo possível já foi
    # cadastrado em cada uma.
    capacidade_por_disciplina = {}
    for frente in Frente.objects.all():
        capacidade_por_disciplina[frente.disciplina_id] = (
            capacidade_por_disciplina.get(frente.disciplina_id, 0) + frente.limite_aula
        )

    disciplinas_completas = 0
    disciplinas_sem_conteudo = 0
    for disciplina in disciplinas:
        capacidade = capacidade_por_disciplina.get(disciplina.pk, 0)
        disciplina.cobertura_percentual = (
            round(disciplina.num_assuntos * 100 / capacidade) if capacidade else 0
        )
        if disciplina.num_assuntos == 0:
            disciplinas_sem_conteudo += 1
        elif capacidade and disciplina.num_assuntos >= capacidade:
            disciplinas_completas += 1
    disciplinas_em_andamento = (
        len(disciplinas) - disciplinas_completas - disciplinas_sem_conteudo
    )

    maior_contagem = max((d.num_questoes for d in disciplinas), default=0) or 1
    for disciplina in disciplinas:
        disciplina.percentual_do_maior = round(disciplina.num_questoes * 100 / maior_contagem)

    # Gradiente cônico do "donut" já pronto, calculado com percentuais
    # em ponto flutuante (não arredondados) pra não sobrar nem faltar
    # nenhum grau entre uma fatia e a próxima.
    fatias = []
    partes_gradiente = []
    acumulado = 0.0
    disciplinas_com_questoes = [d for d in disciplinas if d.num_questoes > 0]
    for indice, disciplina in enumerate(disciplinas_com_questoes):
        cor = CORES_DISCIPLINAS[indice % len(CORES_DISCIPLINAS)]
        fatia_percentual = disciplina.num_questoes * 100 / total_questoes if total_questoes else 0
        fim = acumulado + fatia_percentual
        partes_gradiente.append(f"{cor} {acumulado:.3f}% {fim:.3f}%")
        fatias.append(
            {
                "nome": disciplina.nome,
                "quantidade": disciplina.num_questoes,
                "percentual": round(fatia_percentual),
                "cor": cor,
            }
        )
        acumulado = fim
    if acumulado < 100 and disciplinas_com_questoes:
        partes_gradiente.append(f"var(--cor-borda) {acumulado:.3f}% 100%")
    donut_gradiente = ", ".join(partes_gradiente)

    assuntos_sem_questao = Assunto.objects.annotate(num_questoes=Count("questoes")).filter(
        num_questoes=0
    ).count()

    def percentual(quantidade, total):
        return round(quantidade * 100 / total) if total else 0

    total_autoria_propria = Questao.objects.filter(autoria_propria=True).count()
    total_vestibular = total_questoes - total_autoria_propria
    barra_origem = [
        {
            "rotulo": "Autoria própria",
            "quantidade": total_autoria_propria,
            "percentual": percentual(total_autoria_propria, total_questoes),
            "cor": "#2952e3",
        },
        {
            "rotulo": "De vestibular",
            "quantidade": total_vestibular,
            "percentual": percentual(total_vestibular, total_questoes),
            "cor": "#0a7d2c",
        },
    ]

    barra_cobertura = [
        {
            "rotulo": "Completa",
            "quantidade": disciplinas_completas,
            "percentual": percentual(disciplinas_completas, len(disciplinas)),
            "cor": "#0a7d2c",
        },
        {
            "rotulo": "Em andamento",
            "quantidade": disciplinas_em_andamento,
            "percentual": percentual(disciplinas_em_andamento, len(disciplinas)),
            "cor": "#a15c00",
        },
        {
            "rotulo": "Sem conteúdo",
            "quantidade": disciplinas_sem_conteudo,
            "percentual": percentual(disciplinas_sem_conteudo, len(disciplinas)),
            "cor": "#b00020",
        },
    ]

    return render(
        request,
        "questoes/estatisticas.html",
        {
            "total_questoes": total_questoes,
            "total_assuntos": total_assuntos,
            "capacidade_total_aulas": capacidade_total_aulas,
            "cobertura_aulas": cobertura_aulas,
            "total_disciplinas": len(disciplinas),
            "total_disciplinas_com_conteudo": total_disciplinas_com_conteudo,
            "ranking_disciplinas": disciplinas,
            "fatias_donut": fatias,
            "donut_gradiente": donut_gradiente,
            "assuntos_sem_questao": assuntos_sem_questao,
            "barra_origem": barra_origem,
            "barra_cobertura": barra_cobertura,
        },
    )


@login_required
def adicionar_questao(request):
    """
    Formulário de cadastro de questão: assunto (restrito ao que o
    professor pode usar), enunciado rico com imagem e fórmula, origem
    (vestibular ou autoria própria) e alternativas com a correta
    marcada. Um professor sem nenhum assunto disponível vê um aviso em
    vez do formulário — sem assunto não tem onde encaixar a questão.
    """
    usuario = request.user

    if usuario.is_superuser:
        tem_assunto_disponivel = Assunto.objects.exists()
    else:
        tem_assunto_disponivel = Assunto.objects.filter(
            frente__professores=usuario
        ).exists()

    enunciado_inicial = ""
    if request.method == "POST":
        form = QuestaoForm(request.POST, usuario=usuario)
        if form.is_valid():
            form.save(autor=usuario)
            messages.success(request, "Questão cadastrada com sucesso.")
            return redirect("core:questoes_adicionar")
        # Se sobrou erro em outro campo (ex: alternativas), o enunciado
        # digitado não pode se perder — mas reexibimos a versão já
        # sanitizada, nunca o HTML cru que veio no POST.
        enunciado_inicial = sanitizar_html_enunciado(request.POST.get("enunciado", ""))
    else:
        form = QuestaoForm(usuario=usuario)

    alternativas_com_letra = [
        (letra, form[f"alternativa_{letra}"]) for letra in LETRAS_ALTERNATIVAS
    ]

    return render(
        request,
        "questoes/adicionar_questao.html",
        {
            "form": form,
            "tem_assunto_disponivel": tem_assunto_disponivel,
            "enunciado_inicial": enunciado_inicial,
            "alternativas_com_letra": alternativas_com_letra,
        },
    )


@login_required
def editar_questao(request, pk):
    """
    Edita uma questão já cadastrada, reaproveitando o formulário e a
    tela de cadastro. Só o autor da questão ou a coordenação pode editar.
    """
    questao = get_object_or_404(
        Questao.objects.select_related("assunto__frente__disciplina"), pk=pk
    )
    usuario = request.user
    if not (usuario.is_superuser or questao.autor_id == usuario.pk):
        messages.error(request, "Você só pode editar as questões que cadastrou.")
        return redirect("core:questoes_listar")

    enunciado_inicial = questao.enunciado
    if request.method == "POST":
        form = QuestaoForm(request.POST, instance=questao, usuario=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, "Questão atualizada com sucesso.")
            return redirect("core:questoes_listar")
        enunciado_inicial = sanitizar_html_enunciado(request.POST.get("enunciado", ""))
    else:
        form = QuestaoForm(instance=questao, usuario=usuario)

    return render(
        request,
        "questoes/adicionar_questao.html",
        {
            "form": form,
            "tem_assunto_disponivel": True,
            "enunciado_inicial": enunciado_inicial,
            "alternativas_com_letra": [
                (letra, form[f"alternativa_{letra}"]) for letra in LETRAS_ALTERNATIVAS
            ],
            "editando": questao,
        },
    )


@login_required
def listar_questoes(request):
    """
    Lista todas as questões cadastradas, de qualquer professor e
    qualquer frente — diferente de Planejamento/Adicionar questão, essa
    tela não é restrita por atribuição, porque é pra todo mundo revisar
    o banco inteiro. Os filtros (disciplina, assunto, texto) existem só
    pra facilitar de achar uma questão específica no meio de muitas.
    """
    questoes = (
        Questao.objects.select_related("assunto__frente__disciplina", "autor")
        .prefetch_related("alternativas")
        .order_by("-criado_em")
    )

    disciplina_id = request.GET.get("disciplina", "")
    assunto_id = request.GET.get("assunto", "")
    busca = request.GET.get("busca", "").strip()

    if disciplina_id:
        questoes = questoes.filter(assunto__frente__disciplina_id=disciplina_id)
    if assunto_id:
        questoes = questoes.filter(assunto_id=assunto_id)
    if busca:
        questoes = questoes.filter(enunciado__icontains=busca)

    paginator = Paginator(questoes, 10)
    pagina = paginator.get_page(request.GET.get("pagina"))

    # Querystring dos filtros ativos, sem a página — pra montar os
    # links de paginação sem perder o que já estava filtrado.
    parametros_filtro = request.GET.copy()
    parametros_filtro.pop("pagina", None)

    assuntos = Assunto.objects.select_related("frente", "frente__disciplina").order_by(
        "frente__disciplina__nome", "frente__letra", "aula", "nome"
    )
    assuntos_agrupados = {}
    for assunto in assuntos:
        rotulo_grupo = f"{assunto.frente.disciplina.nome} — {assunto.frente.nome}"
        assuntos_agrupados.setdefault(rotulo_grupo, []).append(assunto)

    return render(
        request,
        "questoes/listar_questoes.html",
        {
            "pagina": pagina,
            "disciplinas": Disciplina.objects.order_by("nome"),
            "assuntos_agrupados": assuntos_agrupados,
            "filtros": {
                "disciplina": disciplina_id,
                "assunto": assunto_id,
                "busca": busca,
            },
            "parametros_filtro": parametros_filtro.urlencode(),
            "tem_filtro_ativo": any([disciplina_id, assunto_id, busca]),
        },
    )


TIPOS_IMAGEM_PERMITIDOS = {"image/png", "image/jpeg", "image/webp", "image/gif"}
TAMANHO_MAXIMO_IMAGEM = 8 * 1024 * 1024  # 8 MB


@login_required
@require_POST
def upload_imagem_editor(request):
    """
    Endpoint chamado pelo JavaScript do editor (Quill) quando o
    professor cola, arrasta ou escolhe uma imagem pra colocar no meio
    do enunciado. Salva no storage padrão do projeto (Spaces em
    produção, pasta media/ local em desenvolvimento) e devolve a URL,
    que o editor insere na posição do cursor.
    """
    arquivo = request.FILES.get("imagem")
    if arquivo is None:
        return JsonResponse({"erro": "Nenhum arquivo enviado."}, status=400)

    if arquivo.content_type not in TIPOS_IMAGEM_PERMITIDOS:
        return JsonResponse({"erro": "Formato de imagem não suportado."}, status=400)

    if arquivo.size > TAMANHO_MAXIMO_IMAGEM:
        return JsonResponse({"erro": "Imagem maior que 8 MB."}, status=400)

    try:
        imagem_pil = Image.open(arquivo)
        imagem_pil.verify()
    except (UnidentifiedImageError, OSError):
        return JsonResponse({"erro": "Arquivo não é uma imagem válida."}, status=400)
    arquivo.seek(0)

    extensao = Path(arquivo.name).suffix.lower() or ".png"
    nome_arquivo = f"questoes/editor/{uuid.uuid4().hex}{extensao}"
    caminho_salvo = default_storage.save(nome_arquivo, arquivo)
    return JsonResponse({"url": default_storage.url(caminho_salvo)})
