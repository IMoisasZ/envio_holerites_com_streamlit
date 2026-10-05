import os
import re
import time
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr
import pymupdf
import streamlit as st

pymupdf.TOOLS.mupdf_display_errors(False)
logging.getLogger("pypdf").setLevel(logging.CRITICAL)

HOST_SMTP_FIXO = "smtp.injetaq.com.br"
PORTA_SMTP_FIXA = 587


def conectar_smtp(remetente, senha):
    """Conecta ao servidor SMTP interno fixo (smtp.injetaq.com.br:465) usando SSL/TLS flexível."""
    contexto_ssl = ssl.create_default_context()
    # Desativa verificação estrita de certificado caso o servidor interno use certificado autoassinado/local
    contexto_ssl.check_hostname = False
    contexto_ssl.verify_mode = ssl.CERT_NONE

    # Modo 1: SSL implícito na porta 465 (Padrão correto para SSL na 465)
    try:
        server = smtplib.SMTP_SSL(HOST_SMTP_FIXO, PORTA_SMTP_FIXA, context=contexto_ssl, timeout=25)
        server.ehlo()
        if senha and senha.strip():
            server.login(remetente, senha)
        return server
    except Exception as e_ssl:
        # Modo 2: Fallback para conexão SMTP com STARTTLS na porta 587 caso a 465 feche o socket
        try:
            server = smtplib.SMTP(HOST_SMTP_FIXO, 587, timeout=25)
            server.ehlo()
            if server.has_extn("STARTTLS"):
                server.starttls(context=contexto_ssl)
                server.ehlo()
            if senha and senha.strip():
                server.login(remetente, senha)
            return server
        except Exception as e_tls:
            # Modo 3: Conexão direta sem criptografia (Porta 25/587)
            try:
                server = smtplib.SMTP(HOST_SMTP_FIXO, 25, timeout=25)
                server.ehlo()
                if senha and senha.strip():
                    server.login(remetente, senha)
                return server
            except Exception as e_plain:
                raise Exception(
                    f"Falha ao conectar no servidor '{HOST_SMTP_FIXO}'.\n"
                    f"Detalhes -> SSL (465): {e_ssl} | TLS (587): {e_tls} | Direto (25): {e_plain}"
                )


def extrair_matricula_logo_apos_nome_funcionario(texto_pagina):
    """Extrai os dígitos da matrícula que aparecem logo após 'Nome do Funcionário'."""
    texto_upper = texto_pagina.upper()

    match = re.search(r'NOME\s+DO\s+FUNCION[A-ZÁ-Ú]*\s*[:\.-]?\s*(\d+)', texto_upper)
    if match:
        return match.group(1).lstrip('0')

    match_func = re.search(r'FUNCION[A-ZÁ-Ú]*\s*[:\.-]?\s*(\d+)', texto_upper)
    if match_func:
        return match_func.group(1).lstrip('0')

    return None


def enviar_relatorio_erros(server_smtp, remetente_formatado, remetente_email, empresa, mes_referencia, erros):
    """Envia um e-mail resumo ao remetente informando falhas de envio ou holerites não cadastrados."""
    if not erros:
        return

    msg = MIMEMultipart()
    msg['From'] = remetente_formatado
    msg['To'] = remetente_email
    msg['Subject'] = f"⚠️ [RELATÓRIO DE ERROS] Holerites {empresa} - {mes_referencia}"

    linhas_erro = "\n".join([f"- {item}" for item in erros])
    corpo = f"""Atenção, RH / Processamento de Holerites!

Foram identificadas inconsistências ou pendências durante o envio dos holerites da empresa {empresa} referentes ao mês de {mes_referencia}:

{linhas_erro}

Por favor, verifique o cadastro do sistema ou o arquivo PDF original.

Atenciosamente,
Sistema Automático de Holerites
"""
    msg.attach(MIMEText(corpo, 'plain'))

    try:
        server_smtp.send_message(msg)
        st.warning(f"📧 Relatório com {len(erros)} erro(s)/pendência(s) foi enviado para **{remetente_email}**.")
    except Exception as e:
        st.error(f"Não foi possível enviar o e-mail de relatório de erros ao remetente: {e}")


def desmembrar_e_enviar_holerites(
    pdf_bytes, 
    dados_usuarios, 
    empresa_selecionada, 
    mes_referencia, 
    nome_remetente,
    remetente_email, 
    senha_app
):
    """Lê o PDF, desmembra apenas os cadastrados e envia relatório de divergências ao remetente."""
    
    mes_sanitizado = mes_referencia.strip().replace('/', '_').replace('\\', '_').replace(' ', '_')
    pasta_destino = os.path.join("holerites", empresa_selecionada, mes_sanitizado)
    os.makedirs(pasta_destino, exist_ok=True)

    # Filtra empresa selecionada + ativos
    filtro_empresa = (dados_usuarios["Empresa"] == empresa_selecionada) & (dados_usuarios["Ativo"] == True)
    colaboradores_alvo = dados_usuarios[filtro_empresa].reset_index(drop=True)

    # Cria dicionário de consulta rápida por matrícula limpa
    mapa_colaboradores_cadastrados = {}
    for _, row in colaboradores_alvo.iterrows():
        mat_raw = str(row.get("matricula", "")).strip()
        mat_limpa = re.sub(r'\D', '', mat_raw).lstrip('0')
        if mat_limpa:
            mapa_colaboradores_cadastrados[mat_limpa] = row

    # Abre o PDF fornecido
    conteudo_pdf = pdf_bytes.read()
    doc = pymupdf.open(stream=conteudo_pdf, filetype="pdf")
    total_paginas = len(doc)

    if total_paginas == 0:
        st.error("O arquivo PDF enviado está vazio ou não pôde ser lido.")
        return

    # Conecta ao servidor SMTP fixo
    try:
        server_smtp = conectar_smtp(remetente=remetente_email, senha=senha_app)
    except Exception as e:
        st.error(f"❌ Falha ao conectar ao servidor SMTP corporativo ({HOST_SMTP_FIXO}): {e}")
        return

    remetente_formatado = formataddr((nome_remetente, remetente_email))
    erros_pendencias = []
    holerites_enviados_com_sucesso = 0

    progresso = st.progress(0)

    # 1. Varre cada página do PDF
    for idx_pag in range(total_paginas):
        texto_pag = doc[idx_pag].get_text("text")
        mat_encontrada = extrair_matricula_logo_apos_nome_funcionario(texto_pag)

        # Se não capturou pela regex do rótulo, tenta buscar qualquer número de matrícula cadastrado que apareça na página
        if not mat_encontrada:
            numeros_pag = [re.sub(r'\D', '', n).lstrip('0') for n in re.findall(r'\b\d+\b', texto_pag)]
            for m_cad in mapa_colaboradores_cadastrados.keys():
                if m_cad in numeros_pag:
                    mat_encontrada = m_cad
                    break

        # Caso a página do PDF NÃO corresponda a nenhum funcionário cadastrado no sistema
        if not mat_encontrada or mat_encontrada not in mapa_colaboradores_cadastrados:
            id_pagina = f"Página {idx_pag + 1}"
            detalhe = f"{id_pagina}: Holerite no PDF com matrícula '{mat_encontrada or 'Não Identificada'}' NÃO cadastrado/ativo para {empresa_selecionada}."
            erros_pendencias.append(detalhe)
            st.warning(f"⚠️ {detalhe}")
            progresso.progress((idx_pag + 1) / total_paginas)
            continue

        # Dados do colaborador localizado
        colaborador = mapa_colaboradores_cadastrados[mat_encontrada]
        matricula_raw = str(colaborador["matricula"]).strip()
        nome = str(colaborador["nome"]).strip()
        email_destino = str(colaborador["email"]).strip()

        # Desmembra apenas esta página
        novo_doc = pymupdf.open()
        novo_doc.insert_pdf(doc, from_page=idx_pag, to_page=idx_pag)

        nome_sanitizado = nome.replace(' ', '_')
        mes_arquivo = mes_referencia.replace('/', '-').replace('\\', '-')
        nome_arquivo = f"Holerite_{empresa_selecionada}_{matricula_raw}_{nome_sanitizado}_{mes_arquivo}.pdf"
        caminho_anexo = os.path.join(pasta_destino, nome_arquivo)

        novo_doc.save(caminho_anexo, deflate=True, clean=True)
        novo_doc.close()

        # Monta a mensagem
        msg = MIMEMultipart()
        msg['From'] = remetente_formatado
        msg['To'] = email_destino
        msg['Subject'] = f"[{empresa_selecionada}] Holerite - {mes_referencia} - {nome}"

        corpo = f"""Prezado(a) {nome},

Segue em anexo o seu demonstrativo de pagamento (holerite) referente ao mês de {mes_referencia}.

Atenciosamente,
{nome_remetente}
"""
        msg.attach(MIMEText(corpo, 'plain'))

        with open(caminho_anexo, "rb") as f:
            anexo = MIMEApplication(f.read(), _subtype="pdf")
            anexo.add_header('Content-Disposition', 'attachment', filename=nome_arquivo)
            msg.attach(anexo)

        # Dispara o e-mail
        try:
            server_smtp.send_message(msg)
            st.write(f"✅ [{empresa_selecionada}] Enviado para **{nome}** (Matrícula `{matricula_raw}` | Pág. {idx_pag + 1}) → `{email_destino}`")
            holerites_enviados_com_sucesso += 1
            time.sleep(1)
        except Exception as err:
            msg_erro = f"Falha no envio para {nome} (Matrícula: {matricula_raw} | E-mail: {email_destino}): {err}"
            st.error(f"❌ {msg_erro}")
            erros_pendencias.append(msg_erro)

        progresso.progress((idx_pag + 1) / total_paginas)

    # 2. Envia o e-mail de relatório ao remetente caso haja divergências
    if erros_pendencias:
        enviar_relatorio_erros(
            server_smtp=server_smtp,
            remetente_formatado=remetente_formatado,
            remetente_email=remetente_email,
            empresa=empresa_selecionada,
            mes_referencia=mes_referencia,
            erros=erros_pendencias
        )

    doc.close()
    try:
        server_smtp.quit()
    except Exception:
        pass

    st.success(f"Disparo concluído! **{holerites_enviados_com_sucesso}** e-mail(s) enviado(s) com sucesso. PDFs salvos em: `{pasta_destino}`")