import calendar
from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from questoes.metas import calcular_metas
from questoes.models import Disciplina, Frente

from .forms import AvisoForm, EventoForm, PerfilForm
from .middleware import manutencao_ativa
from .models import Aviso, ConfiguracaoSistema, Evento, PerfilProfessor


def raiz(request):
    """
    A raiz do site ("/"). Quem já está logado vai direto para a
    dashboard; quem não está, vai para a tela de login.
    """
    destino = "core:painel" if request.user.is_authenticated else "core:login"
    return HttpResponseRedirect(reverse(destino))


def status(request):
    """
    Página de diagnóstico (não fica em nenhum menu). Existe só para
    confirmarmos rapidamente que o deploy está de pé e conectando no
    banco — útil pra nós, não é algo que os professores vão acessar.
    """
    db_ok = None
    db_error = None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        db_ok = True
    except Exception as exc:  # noqa: BLE001 - queremos mostrar qualquer erro
        db_ok = False
        db_error = str(exc)

    context = {
        "db_ok": db_ok,
        "db_error": db_error,
        "db_engine": connection.settings_dict.get("ENGINE", ""),
    }
    return render(request, "core/status.html", context)


def healthz(request):
    """
    Rota simples de 'saúde' do app, sem depender do banco. Útil para
    checagens automáticas de disponibilidade.
    """
    return HttpResponse("ok", content_type="text/plain")


def contato(request):
    """
    Página pública para quem não tem acesso pedir para ser cadastrado.
    Por enquanto é só uma página com informações de contato — o fluxo
    de pedido de acesso de verdade (formulário, notificação etc.) fica
    para depois.
    """
    return render(request, "core/contato.html")


def _rotulo_do_prazo(evento, hoje):
    if evento.data > hoje:
        dias = (evento.data - hoje).days
        return "Amanhã" if dias == 1 else f"Em {dias} dias"
    return "Hoje" if evento.data == hoje else "Em andamento"


@login_required
def painel(request):
    """
    Página inicial, com três cards:

    - Avisos: todos os próximos compromissos do cronograma (eventos que
      ainda não terminaram, em ordem de data).
    - Metas: objetivo de aulas e de questões (13 por aula) e o quanto já foi
      cadastrado.
    - Informações: o quadro de recados que a coordenação escreve na tela
      "Avisos" do menu.
    """
    hoje = timezone.localdate()

    eventos = Evento.objects.filter(Q(data__gte=hoje) | Q(data_fim__gte=hoje)).order_by(
        "data", "hora"
    )
    proximos_compromissos = [
        {"evento": evento, "rotulo": _rotulo_do_prazo(evento, hoje)} for evento in eventos
    ]

    return render(
        request,
        "core/painel.html",
        {
            "proximos_compromissos": proximos_compromissos,
            "metas": calcular_metas(),
            "avisos": Aviso.objects.all(),
        },
    )


@login_required
@user_passes_test(lambda usuario: usuario.is_superuser, login_url="core:painel")
def avisos(request):
    """
    Tela só da coordenação: escreve e apaga os recados que aparecem no
    quadro "Informações" da página inicial.
    """
    form = AvisoForm()

    if request.method == "POST":
        if request.POST.get("acao") == "excluir":
            aviso = get_object_or_404(Aviso, pk=request.POST.get("aviso_id"))
            aviso.delete()
            messages.success(request, "Aviso apagado.")
            return redirect("core:avisos")

        form = AvisoForm(request.POST)
        if form.is_valid():
            aviso = form.save(commit=False)
            aviso.criado_por = request.user
            aviso.save()
            messages.success(request, "Aviso publicado.")
            return redirect("core:avisos")

    return render(request, "core/avisos.html", {"form": form, "avisos": Aviso.objects.all()})


@login_required
def perfil(request):
    """
    Dados do professor que vão compor o material didático impresso
    (nome completo, faculdade, foto, descrição) — não é o cadastro de
    acesso ao sistema. Cada pessoa só edita o próprio perfil; o objeto
    é criado na hora, na primeira vez que a pessoa abre esta tela.
    """
    perfil_professor, _ = PerfilProfessor.objects.get_or_create(usuario=request.user)

    if request.method == "POST":
        form = PerfilForm(request.POST, request.FILES, instance=perfil_professor)
        if form.is_valid():
            form.save()
            messages.success(request, "Perfil atualizado com sucesso.")
            return redirect("core:perfil")
    else:
        form = PerfilForm(instance=perfil_professor)

    return render(
        request,
        "core/perfil.html",
        {"form": form, "perfil": perfil_professor},
    )


@login_required
def trocar_senha(request):
    """
    Página obrigatória pra quem ainda está com a senha genérica
    (perfil.senha_provisoria = True) — o ForcarTrocaSenhaMiddleware
    redireciona pra cá antes de qualquer outra página. Usa SetPasswordForm
    (sem pedir a senha atual) porque a pessoa acabou de provar que sabe
    a senha genérica ao fazer login, um passo antes.
    """
    perfil_professor, _ = PerfilProfessor.objects.get_or_create(usuario=request.user)

    if request.method == "POST":
        form = SetPasswordForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            perfil_professor.senha_provisoria = False
            perfil_professor.save(update_fields=["senha_provisoria"])
            update_session_auth_hash(request, request.user)
            messages.success(request, "Senha alterada com sucesso.")
            return redirect("core:painel")
    else:
        form = SetPasswordForm(request.user)

    return render(request, "core/trocar_senha.html", {"form": form})


# Mesmo caso especial de questoes.models.NOMES_DISCIPLINAS_LIMITE_15_AULAS:
# em Sociologia/Filosofia cada frente já é a matéria em si, então o
# nome pra exibir vem da frente, não da disciplina "guarda-chuva".
NOME_DISCIPLINA_FRENTES_INDEPENDENTES = "Sociologia/Filosofia"


def _funcao_do_colaborador(usuario):
    if usuario.is_superuser:
        return "Coordenador"

    nomes_materias = set()
    for frente in usuario.frentes_atribuidas.all():
        if frente.disciplina.nome == NOME_DISCIPLINA_FRENTES_INDEPENDENTES:
            nomes_materias.add(frente.nome)
        else:
            nomes_materias.add(frente.disciplina.nome)

    materias = sorted(nomes_materias)
    if not materias:
        return "Professor"
    if len(materias) == 1:
        return f"Professor de {materias[0]}"
    return f"Professor de {', '.join(materias[:-1])} e {materias[-1]}"


@login_required
def colaboradores(request):
    """
    Diretório com todo mundo que tem acesso ao sistema — pensado pra
    virar uma página de "quem é quem" do cursinho. A função de cada um
    é calculada na hora (coordenador vira superusuário; professor vira
    a lista de disciplinas das frentes atribuídas a ele), não é um
    campo cadastrado à parte.
    """
    Usuario = get_user_model()
    usuarios = (
        Usuario.objects.filter(is_active=True)
        .select_related("perfil")
        .prefetch_related("frentes_atribuidas__disciplina")
        .order_by("-is_superuser", "username")
    )

    cartoes = [
        {
            "usuario": usuario,
            "perfil": getattr(usuario, "perfil", None),
            "nome": (
                usuario.perfil.nome_completo
                if getattr(usuario, "perfil", None) and usuario.perfil.nome_completo
                else usuario.get_username()
            ),
            "funcao": _funcao_do_colaborador(usuario),
        }
        for usuario in usuarios
    ]

    return render(request, "core/colaboradores.html", {"cartoes": cartoes})


@login_required
@user_passes_test(lambda usuario: usuario.is_superuser, login_url="core:painel")
def configuracoes(request):
    """
    Tela só da coordenação (superusuários) com duas áreas:

    1. Modo de manutenção: liga/desliga, na hora, a página de manutenção
       para todo mundo que não é coordenação (sem deploy nem painel da
       hospedagem). A coordenação continua usando o site normalmente.
    2. Professores e frentes: quais frentes cada professor pode ver e
       cadastrar. Cada professor tem seu próprio modal/formulário — o POST
       troca as frentes daquele professor pelas que vieram marcadas
       (`frentes_atribuidas.set(...)`).
    """
    if request.method == "POST":
        if request.POST.get("acao") == "manutencao":
            configuracao = ConfiguracaoSistema.carregar()
            configuracao.manutencao_ativa = request.POST.get("ligar") == "1"
            configuracao.save()
            if configuracao.manutencao_ativa:
                messages.success(request, "Modo de manutenção ligado.")
            else:
                messages.success(request, "Modo de manutenção desligado.")
            return redirect("core:configuracoes")

        professor = get_object_or_404(
            get_user_model(), pk=request.POST.get("professor_id"), is_superuser=False
        )
        ids_selecionados = request.POST.getlist("frentes")
        professor.frentes_atribuidas.set(Frente.objects.filter(pk__in=ids_selecionados))
        messages.success(request, f"Frentes de {professor.username} atualizadas.")
        return redirect("core:configuracoes")

    professores = (
        get_user_model()
        .objects.filter(is_superuser=False)
        .order_by("username")
        .prefetch_related("frentes_atribuidas__disciplina")
    )
    disciplinas = Disciplina.objects.prefetch_related("frentes").order_by("nome")

    return render(
        request,
        "core/configuracoes.html",
        {
            "professores": professores,
            "disciplinas": disciplinas,
            "manutencao_ativa": manutencao_ativa(),
            "manutencao_forcada": settings.MODO_MANUTENCAO,
        },
    )


def _semana_com_barras(semana_datas, eventos_da_semana, mes_atual, hoje, dia_selecionado):
    """
    Monta uma semana pro calendário: os 7 dias (pra numeração e pro
    link de selecionar o dia) e as "barras" dos eventos que aparecem
    nela — cada barra já com a coluna de início/fim (1 a 7, domingo a
    sábado) e a "pista" (linha) em que deve ficar, calculada aqui pra
    duas barras que se sobrepõem em dias nunca caírem na mesma linha.
    Eventos de um dia só viram barras de largura 1, então tudo (evento
    de um dia ou de vários) usa o mesmo jeito de desenhar.
    """
    inicio_semana, fim_semana = semana_datas[0], semana_datas[-1]

    barras = []
    for evento in eventos_da_semana:
        inicio_visivel = max(evento.data, inicio_semana)
        fim_visivel = min(evento.ultimo_dia, fim_semana)
        barras.append(
            {
                "evento": evento,
                "col_inicio": (inicio_visivel - inicio_semana).days + 1,
                "col_fim": (fim_visivel - inicio_semana).days + 1,
                "continua_antes": evento.data < inicio_semana,
                "continua_depois": evento.ultimo_dia > fim_semana,
            }
        )

    # Preenche as pistas de cima pra baixo: pega a primeira pista livre
    # (cujo último evento já termina antes da barra atual começar) —
    # senão abre uma pista nova.
    barras.sort(key=lambda b: (b["col_inicio"], b["col_inicio"] - b["col_fim"]))
    fim_ocupado_por_pista = []
    for barra in barras:
        pista = next(
            (i for i, fim in enumerate(fim_ocupado_por_pista) if fim < barra["col_inicio"]),
            len(fim_ocupado_por_pista),
        )
        if pista == len(fim_ocupado_por_pista):
            fim_ocupado_por_pista.append(barra["col_fim"])
        else:
            fim_ocupado_por_pista[pista] = barra["col_fim"]
        barra["pista"] = pista

    dias = [
        {
            "data": dia,
            "no_mes": dia.month == mes_atual.month,
            "hoje": dia == hoje,
            "selecionado": dia == dia_selecionado,
        }
        for dia in semana_datas
    ]

    return {
        "dias": dias,
        "barras": barras,
        "total_pistas": len(fim_ocupado_por_pista),
    }


@login_required
def cronograma(request):
    """
    Calendário mensal do cronograma. Todo mundo logado vê os eventos;
    só a coordenação (superusuário) tem os botões de criar, editar e
    apagar — o POST também é bloqueado no backend pra quem não é
    coordenador, mesmo que a pessoa tente forjar a requisição.

    Navegação e seleção de dia são tudo por GET (?mes=AAAA-MM&dia=AAAA-MM-DD),
    então funciona igual sem JavaScript nenhum — o calendário é só uma
    grade de links.
    """
    eh_coordenador = request.user.is_superuser
    hoje = date.today()

    try:
        ano, mes = (int(parte) for parte in request.GET.get("mes", "").split("-"))
        mes_atual = date(ano, mes, 1)
    except (TypeError, ValueError):
        mes_atual = date(hoje.year, hoje.month, 1)

    dia_selecionado = None
    if request.GET.get("dia"):
        try:
            dia_selecionado = date.fromisoformat(request.GET["dia"])
        except ValueError:
            dia_selecionado = None

    form = EventoForm()
    abrir_formulario = False

    if request.method == "POST":
        if not eh_coordenador:
            raise PermissionDenied("Só a coordenação pode alterar o cronograma.")

        if request.POST.get("acao") == "excluir":
            evento = get_object_or_404(Evento, pk=request.POST.get("evento_id"))
            evento.delete()
            messages.success(request, "Evento removido.")
            return redirect(
                f"{reverse('core:cronograma')}?mes={mes_atual:%Y-%m}&dia={request.POST.get('data_evento', '')}"
            )

        evento_id = request.POST.get("evento_id")
        instancia = get_object_or_404(Evento, pk=evento_id) if evento_id else None
        form = EventoForm(request.POST, instance=instancia)
        if form.is_valid():
            evento = form.save(commit=False)
            if instancia is None:
                evento.criado_por = request.user
            evento.save()
            messages.success(request, "Evento salvo com sucesso.")
            return redirect(
                f"{reverse('core:cronograma')}?mes={evento.data:%Y-%m}&dia={evento.data:%Y-%m-%d}"
            )
        abrir_formulario = True

    elif eh_coordenador and request.GET.get("editar"):
        evento_edicao = get_object_or_404(Evento, pk=request.GET["editar"])
        form = EventoForm(instance=evento_edicao)
        abrir_formulario = True
    elif eh_coordenador and request.GET.get("criar") == "1":
        if dia_selecionado:
            form = EventoForm(initial={"data": dia_selecionado})
        abrir_formulario = True

    # Grade do mês (semanas começando no domingo), com os dias "de
    # fora" do mês (final do mês anterior / início do seguinte) que
    # completam a primeira e a última semana.
    dias_do_mes = calendar.Calendar(firstweekday=6).monthdatescalendar(
        mes_atual.year, mes_atual.month
    )
    primeiro_dia_grade = dias_do_mes[0][0]
    ultimo_dia_grade = dias_do_mes[-1][-1]

    # Um evento aparece na grade se o intervalo [data, ultimo_dia] dele
    # cruza com [primeiro_dia_grade, ultimo_dia_grade] — inclui tanto
    # eventos de um dia só (data_fim em branco) quanto os que atravessam
    # vários dias.
    eventos_da_grade = Evento.objects.filter(data__lte=ultimo_dia_grade).filter(
        Q(data_fim__gte=primeiro_dia_grade)
        | Q(data_fim__isnull=True, data__gte=primeiro_dia_grade)
    )

    eventos_por_dia = {}
    for evento in eventos_da_grade:
        primeiro_dia_evento = max(evento.data, primeiro_dia_grade)
        ultimo_dia_evento = min(evento.ultimo_dia, ultimo_dia_grade)
        dia = primeiro_dia_evento
        while dia <= ultimo_dia_evento:
            eventos_por_dia.setdefault(dia, []).append(evento)
            dia += timedelta(days=1)

    semanas = []
    for semana_datas in dias_do_mes:
        eventos_da_semana = {}
        for dia in semana_datas:
            for evento in eventos_por_dia.get(dia, []):
                eventos_da_semana[evento.pk] = evento
        semanas.append(
            _semana_com_barras(
                semana_datas, eventos_da_semana.values(), mes_atual, hoje, dia_selecionado
            )
        )

    mes_anterior = (mes_atual - timedelta(days=1)).replace(day=1)
    mes_seguinte = (mes_atual + timedelta(days=31)).replace(day=1)

    # URL da página tal como está agora (mês + dia selecionado, sem
    # "criar"/"editar"/"#fragmento") — usada como `action` dos
    # formulários, pra evitar que o navegador carregue o fragmento do
    # link que abriu o modal para a página seguinte ao salvar/apagar e
    # deixe o modal preso aberto depois do redirect.
    url_pagina_atual = f"{reverse('core:cronograma')}?mes={mes_atual:%Y-%m}"
    if dia_selecionado:
        url_pagina_atual += f"&dia={dia_selecionado:%Y-%m-%d}"

    return render(
        request,
        "core/cronograma.html",
        {
            "semanas": semanas,
            "nomes_dias_semana": dias_do_mes[0],
            "mes_atual": mes_atual,
            "mes_anterior": mes_anterior,
            "mes_seguinte": mes_seguinte,
            "dia_selecionado": dia_selecionado,
            "eventos_do_dia": eventos_por_dia.get(dia_selecionado, []) if dia_selecionado else [],
            "eh_coordenador": eh_coordenador,
            "form": form,
            "abrir_formulario": abrir_formulario,
            "editando_evento_id": request.GET.get("editar"),
            "url_pagina_atual": url_pagina_atual,
        },
    )


class StubView(LoginRequiredMixin, TemplateView):
    """
    Página "em construção" para cada item do menu lateral que ainda
    não foi implementado. Uma view só, reaproveitada em todas as
    entradas do menu — quando cada uma for construída de verdade, ela
    troca essa view por uma própria.
    """

    template_name = "core/stub.html"
    login_url = "core:login"
    titulo = "Em construção"
    icone = "tool"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"] = self.titulo
        context["icone"] = self.icone
        return context
