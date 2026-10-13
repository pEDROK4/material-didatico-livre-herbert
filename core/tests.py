from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import TestCase, override_settings
from django.utils import timezone

from questoes.models import Assunto, Frente, Questao

from .models import Aviso, ConfiguracaoSistema, Evento, PerfilProfessor

Usuario = get_user_model()


@override_settings(MODO_MANUTENCAO=True)
class ModoManutencaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prof = Usuario.objects.create_user("prof", password="x")
        cls.coord = Usuario.objects.create_superuser("coord", password="x")

    def assertManutencao(self, resposta):
        self.assertContains(resposta, "Estamos em manutenção")

    def test_visitante_ve_pagina_de_manutencao(self):
        self.assertManutencao(self.client.get("/painel/"))

    def test_professor_logado_ve_manutencao(self):
        self.client.force_login(self.prof)
        self.assertManutencao(self.client.get("/painel/"))
        self.assertManutencao(self.client.get("/painel/planejamento/"))

    def test_coordenacao_continua_usando_o_site(self):
        self.client.force_login(self.coord)
        self.assertNotContains(self.client.get("/painel/"), "Estamos em manutenção")

    def test_login_continua_acessivel_para_a_coordenacao_entrar(self):
        self.assertEqual(self.client.get("/login/").status_code, 200)
        resposta = self.client.post("/login/", {"username": "coord", "password": "x"})
        self.assertEqual(resposta.status_code, 302)
        self.assertNotContains(self.client.get("/painel/"), "Estamos em manutenção")

    def test_rotas_de_saude_ficam_liberadas(self):
        self.assertEqual(self.client.get("/healthz/").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 302)


@override_settings(MODO_MANUTENCAO=False)
class SemManutencaoTests(TestCase):
    def test_site_normal_quando_desligado(self):
        prof = Usuario.objects.create_user("prof", password="x")
        self.client.force_login(prof)
        self.assertEqual(self.client.get("/painel/").status_code, 200)


class ConfiguracoesTests(TestCase):
    """Tela Configurações: botão de manutenção e frentes dos professores."""

    @classmethod
    def setUpTestData(cls):
        cls.prof = Usuario.objects.create_user("prof", password="x")
        cls.coord = Usuario.objects.create_superuser("coord", password="x")
        cls.url = "/painel/configuracoes/"

    def test_so_a_coordenacao_acessa(self):
        self.client.force_login(self.prof)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(resposta["Location"].startswith("/painel/"))
        self.assertNotContains(self.client.get("/painel/"), "Modo de manutenção")

    def test_item_do_menu_so_para_coordenacao(self):
        self.client.force_login(self.prof)
        self.assertNotContains(self.client.get("/painel/"), "Configurações")
        self.client.force_login(self.coord)
        self.assertContains(self.client.get("/painel/"), "Configurações")

    def test_endereco_antigo_redireciona(self):
        self.client.force_login(self.coord)
        resposta = self.client.get("/painel/professores/")
        self.assertRedirects(resposta, self.url, fetch_redirect_response=False)

    def test_ligar_e_desligar_manutencao_pelo_botao(self):
        self.client.force_login(self.coord)
        self.client.post(self.url, {"acao": "manutencao", "ligar": "1"})
        self.assertTrue(ConfiguracaoSistema.carregar().manutencao_ativa)

        # Professor passa a ver a manutenção; coordenação segue normal.
        professor = self.client_class()
        professor.force_login(self.prof)
        self.assertContains(professor.get("/painel/"), "Estamos em manutenção")
        self.assertNotContains(self.client.get("/painel/"), "Estamos em manutenção")

        self.client.post(self.url, {"acao": "manutencao", "ligar": "0"})
        self.assertFalse(ConfiguracaoSistema.carregar().manutencao_ativa)
        self.assertNotContains(professor.get("/painel/"), "Estamos em manutenção")

    def test_professor_nao_consegue_ligar_a_manutencao(self):
        self.client.force_login(self.prof)
        self.client.post(self.url, {"acao": "manutencao", "ligar": "1"})
        self.assertFalse(ConfiguracaoSistema.carregar().manutencao_ativa)

    def test_atribuir_frentes_a_um_professor(self):
        frente = Frente.objects.get(disciplina__nome="Biologia", letra="A")
        self.client.force_login(self.coord)
        self.client.post(self.url, {"professor_id": self.prof.pk, "frentes": [frente.pk]})
        self.assertEqual(list(self.prof.frentes_atribuidas.all()), [frente])

        self.client.post(self.url, {"professor_id": self.prof.pk})
        self.assertEqual(self.prof.frentes_atribuidas.count(), 0)

    def test_manutencao_forcada_pela_variavel_aparece_na_tela(self):
        self.client.force_login(self.coord)
        with override_settings(MODO_MANUTENCAO=True):
            self.assertContains(self.client.get(self.url), "forçada")

    def test_site_nao_cai_se_a_tabela_de_configuracao_nao_existir(self):
        self.client.force_login(self.prof)
        with mock.patch.object(
            ConfiguracaoSistema.objects, "filter", side_effect=OperationalError("sem tabela")
        ):
            self.assertEqual(self.client.get("/painel/").status_code, 200)


class NomeDeExibicaoTests(TestCase):
    def test_menu_e_saudacao_mostram_o_nome_cadastrado_e_nao_o_login(self):
        prof = Usuario.objects.create_user("prof_bio1", password="x")
        PerfilProfessor.objects.create(usuario=prof, nome_completo="Maria da Silva Souza")
        self.client.force_login(prof)
        resposta = self.client.get("/painel/")
        self.assertContains(resposta, "Maria da Silva Souza")
        self.assertContains(resposta, "Olá, Maria")
        self.assertNotContains(resposta, "prof_bio1")

    def test_sem_perfil_preenchido_usa_o_nome_de_usuario(self):
        prof = Usuario.objects.create_user("prof_mat3", password="x")
        self.client.force_login(prof)
        resposta = self.client.get("/painel/")
        self.assertContains(resposta, "Olá, prof_mat3")


@override_settings(MODO_MANUTENCAO=True)
class BotaoSairNaManutencaoTests(TestCase):
    def test_professor_logado_ve_botao_sair_e_nao_o_link_de_entrar(self):
        prof = Usuario.objects.create_user("prof", password="x")
        self.client.force_login(prof)
        resposta = self.client.get("/painel/")
        self.assertContains(resposta, 'action="/logout/"')
        self.assertContains(resposta, ">Sair<")
        self.assertNotContains(resposta, "Coordenação?")

    def test_sair_encerra_a_sessao(self):
        prof = Usuario.objects.create_user("prof", password="x")
        self.client.force_login(prof)
        resposta = self.client.post("/logout/")
        self.assertEqual(resposta.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_visitante_sem_login_nao_ve_botao_nem_link(self):
        resposta = self.client.get("/painel/")
        self.assertNotContains(resposta, ">Sair<")
        self.assertNotContains(resposta, "Coordenação?")


class PainelCompromissosTests(TestCase):
    """Card "Avisos" da página inicial: próximos compromissos do calendário."""

    def setUp(self):
        self.hoje = timezone.localdate()
        self.client.force_login(Usuario.objects.create_user("prof", password="x"))

    def evento(self, titulo, dias_inicio, dias_fim=None):
        return Evento.objects.create(
            titulo=titulo,
            data=self.hoje + timedelta(days=dias_inicio),
            data_fim=self.hoje + timedelta(days=dias_fim) if dias_fim is not None else None,
        )

    def test_so_aparecem_compromissos_que_ainda_nao_terminaram(self):
        self.evento("Evento passado", -5)
        self.evento("Evento multi-dia que já acabou", -5, -2)
        self.evento("Evento de hoje", 0)
        resposta = self.client.get("/painel/")
        self.assertContains(resposta, "Evento de hoje")
        self.assertNotContains(resposta, "Evento passado")
        self.assertNotContains(resposta, "já acabou")

    def test_rotulos_e_ordem_por_data(self):
        self.evento("C-longe", 10)
        self.evento("B-amanha", 1)
        self.evento("A-hoje", 0)
        self.evento("Z-andamento", -1, 2)
        resposta = self.client.get("/painel/")
        compromissos = resposta.context["proximos_compromissos"]
        self.assertEqual(
            [(c["evento"].titulo, c["rotulo"]) for c in compromissos],
            [
                ("Z-andamento", "Em andamento"),
                ("A-hoje", "Hoje"),
                ("B-amanha", "Amanhã"),
                ("C-longe", "Em 10 dias"),
            ],
        )

    def test_sem_compromissos_mostra_mensagem(self):
        self.assertContains(self.client.get("/painel/"), "Nenhum compromisso marcado")


class PainelMetasTests(TestCase):
    def test_metas_de_aulas_e_questoes_com_13_por_aula(self):
        autor = Usuario.objects.create_user("autor", password="x")
        frente = Frente.objects.get(disciplina__nome="Biologia", letra="A")
        assunto = Assunto.objects.create(frente=frente, nome="Citologia", aula=1)
        for i in range(26):
            Questao.objects.create(assunto=assunto, enunciado=f"q{i}", autor=autor)

        self.client.force_login(autor)
        metas = self.client.get("/painel/").context["metas"]

        possiveis = sum(f.limite_aula for f in Frente.objects.all())
        self.assertEqual(metas["por_aula"], 13)
        self.assertEqual(metas["aulas_possiveis"], possiveis)
        self.assertEqual(metas["aulas_cadastradas"], 1)
        self.assertEqual(metas["meta_questoes"], possiveis * 13)
        self.assertEqual(metas["questoes"], 26)
        self.assertEqual(metas["questoes_faltando"], possiveis * 13 - 26)
        self.assertEqual(metas["media_atual"], 26.0)

    def test_pagina_abre_sem_nenhuma_aula_cadastrada(self):
        self.client.force_login(Usuario.objects.create_user("p", password="x"))
        resposta = self.client.get("/painel/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["metas"]["media_atual"], 0)


class AvisosTests(TestCase):
    """Quadro "Informações" e a tela de avisos (só coordenação)."""

    @classmethod
    def setUpTestData(cls):
        cls.prof = Usuario.objects.create_user("prof", password="x")
        cls.coord = Usuario.objects.create_superuser("coord", password="x")
        cls.url = "/painel/avisos/"

    def test_coordenacao_publica_e_todos_veem_no_painel(self):
        self.client.force_login(self.coord)
        resposta = self.client.post(self.url, {"titulo": "Reunião", "texto": "Sexta às 19h"})
        self.assertRedirects(resposta, self.url, fetch_redirect_response=False)
        aviso = Aviso.objects.get()
        self.assertEqual(aviso.criado_por, self.coord)

        self.client.force_login(self.prof)
        painel = self.client.get("/painel/")
        self.assertContains(painel, "Reunião")
        self.assertContains(painel, "Sexta às 19h")
        self.assertNotContains(painel, "Gerenciar avisos")

    def test_titulo_e_opcional_mas_texto_nao(self):
        self.client.force_login(self.coord)
        self.client.post(self.url, {"titulo": "", "texto": "só o texto"})
        self.assertEqual(Aviso.objects.count(), 1)
        self.client.post(self.url, {"titulo": "sem texto", "texto": ""})
        self.assertEqual(Aviso.objects.count(), 1)

    def test_texto_com_html_nao_e_executado(self):
        Aviso.objects.create(texto="<script>alert(1)</script>")
        self.client.force_login(self.prof)
        resposta = self.client.get("/painel/")
        self.assertNotContains(resposta, "<script>alert(1)</script>")
        self.assertContains(resposta, "&lt;script&gt;")

    def test_coordenacao_apaga_aviso(self):
        aviso = Aviso.objects.create(texto="apagar")
        self.client.force_login(self.coord)
        self.client.post(self.url, {"acao": "excluir", "aviso_id": aviso.pk})
        self.assertFalse(Aviso.objects.exists())

    def test_professor_nao_acessa_nem_cria_nem_apaga(self):
        aviso = Aviso.objects.create(texto="fica")
        self.client.force_login(self.prof)
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.post(self.url, {"texto": "invasão"})
        self.client.post(self.url, {"acao": "excluir", "aviso_id": aviso.pk})
        self.assertEqual(list(Aviso.objects.values_list("texto", flat=True)), ["fica"])

    def test_menu_avisos_so_para_coordenacao(self):
        self.client.force_login(self.prof)
        self.assertNotContains(self.client.get("/painel/"), 'href="/painel/avisos/"')
        self.client.force_login(self.coord)
        self.assertContains(self.client.get("/painel/"), 'href="/painel/avisos/"')
