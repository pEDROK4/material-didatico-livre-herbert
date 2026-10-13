from django.urls import reverse

# (nome da url, ícone, rótulo, só para coordenador) — a ordem aqui é a
# ordem que aparece no menu lateral. Pra adicionar um item novo no
# menu, basta adicionar uma linha aqui (e a URL correspondente em
# core/urls.py). Itens com "só para coordenador" marcado só aparecem
# para superusuários.
ITENS_MENU_LATERAL = [
    ("questoes_adicionar", "plus", "Adicionar questões", False),
    ("questoes_listar", "file-text", "Ver questões", False),
    ("cronograma", "calendar", "Ver cronograma", False),
    ("estatisticas", "bar-chart", "Ver estatísticas", False),
    ("planejamento", "folder", "Ver planejamento", False),
    ("colaboradores", "users", "Colaboradores", False),
    ("avisos", "bell", "Avisos", True),
    ("configuracoes", "settings", "Configurações", True),
    ("perfil", "user", "Ver perfil", False),
]


def menu_lateral(request):
    """
    Disponibiliza `menu_lateral` em todos os templates, já marcando
    qual item é o da página atual (para o destaque visual). Só tem
    efeito de verdade nas páginas que usam core/layout_painel.html.
    """
    url_atual = None
    if request.resolver_match:
        url_atual = request.resolver_match.url_name

    eh_coordenador = getattr(request.user, "is_superuser", False)

    itens = [
        {
            "url": reverse(f"core:{nome_url}"),
            "icone": icone,
            "rotulo": rotulo,
            "ativo": nome_url == url_atual,
        }
        for nome_url, icone, rotulo, so_coordenador in ITENS_MENU_LATERAL
        if not so_coordenador or eh_coordenador
    ]
    return {"menu_lateral": itens}


def nome_usuario(request):
    """
    `nome_usuario` (nome completo cadastrado no perfil) e `primeiro_nome`
    pra mostrar no lugar do login técnico (prof_bio1, prof_mat3...). Se a
    pessoa ainda não preencheu o perfil, cai pro nome de usuário.
    """
    usuario = request.user
    if not usuario.is_authenticated:
        return {}
    perfil = getattr(usuario, "perfil", None)
    nome = ((perfil.nome_completo if perfil else "") or "").strip() or usuario.get_username()
    return {"nome_usuario": nome, "primeiro_nome": nome.split()[0]}
