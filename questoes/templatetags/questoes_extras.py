import re
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from django import template
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.safestring import mark_safe

register = template.Library()

# As imagens coladas no editor são salvas em "questoes/editor/<uuid>.<ext>"
# (ver upload_imagem_editor em views.py).
CHAVE_IMAGEM_EDITOR = re.compile(r"(questoes/editor/[^?#]+)")


def renovar_urls_imagens(html):
    """
    No Spaces o bucket é privado, então a URL devolvida no upload é
    ASSINADA e expira (SPACES_URL_EXPIRE_SECONDS, 1 hora por padrão).
    Essa URL ia parar dentro do enunciado gravado no banco — e depois
    de expirar a imagem quebrava. Aqui, na hora de exibir, cada <img>
    que aponta para o nosso storage tem o endereço refeito a partir do
    caminho do arquivo (a parte fixa), com uma assinatura nova.

    Serve também para as questões antigas, sem precisar mexer no banco.
    Imagens de outros sites e imagens "data:" ficam como estão.
    """
    if not html or "<img" not in html:
        return html

    sopa = BeautifulSoup(html, "html.parser")
    mudou = False
    for imagem in sopa.find_all("img"):
        origem = imagem.get("src", "")
        if origem.startswith("data:"):
            continue
        endereco = urlparse(origem)
        # Endereço de fora (outro site): não mexe. Relativo ("/media/...")
        # ou do Spaces/CDN: refaz.
        if endereco.netloc and not endereco.netloc.endswith("digitaloceanspaces.com"):
            cdn = getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None)
            if not cdn or endereco.netloc != cdn:
                continue
        achou = CHAVE_IMAGEM_EDITOR.search(unquote(endereco.path))
        if not achou:
            continue
        imagem["src"] = default_storage.url(achou.group(1))
        mudou = True

    return str(sopa) if mudou else html


@register.filter
def enunciado_html(html):
    """Uso no template: {{ questao.enunciado|enunciado_html }}"""
    return mark_safe(renovar_urls_imagens(html))
