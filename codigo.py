import sys
import os
import asyncio
import pandas as pd
import streamlit as st

from email_config import desmembrar_e_enviar_holerites

# Patch para evitar erro de socket no Windows
if sys.platform == 'win32':
    from asyncio.proactor_events import _ProactorBasePipeTransport
    _orig_connection_lost = _ProactorBasePipeTransport._call_connection_lost

    def _call_connection_lost_silencioso(self, exc=None):
        try:
            _orig_connection_lost(self, exc)
        except (ConnectionResetError, OSError):
            pass

    _ProactorBasePipeTransport._call_connection_lost = _call_connection_lost_silencioso

st.set_page_config(page_title="Envio de Holerites", layout="wide")
st.title("📄 Sistema de Envio de Holerites")

# ----------------------------------------------------
# 1. GERENCIAMENTO E INICIALIZAÇÃO DOS ARQUIVOS CSV
# ----------------------------------------------------

# A) empresas.csv
if not os.path.exists("empresas.csv"):
    pd.DataFrame(columns=["Nome"]).to_csv("empresas.csv", index=False)
else:
    df_emp_temp = pd.read_csv("empresas.csv")
    if "Ativo" in df_emp_temp.columns:
        df_emp_temp = df_emp_temp[["Nome"]]
        df_emp_temp.to_csv("empresas.csv", index=False)

def carregar_empresas():
    try:
        df = pd.read_csv("empresas.csv")
        return df[["Nome"]]
    except Exception:
        return pd.DataFrame(columns=["Nome"])

def obter_lista_empresas():
    df_emp = carregar_empresas()
    empresas = df_emp["Nome"].dropna().str.strip().tolist()
    return empresas if empresas else []

# B) colaboradores.csv
if not os.path.exists("colaboradores.csv"):
    pd.DataFrame(columns=["Empresa", "Matricula", "Nome", "Email", "Ativo"]).to_csv("colaboradores.csv", index=False)

# ----------------------------------------------------
# 2. FUNÇÕES DE SUPORTE - EMPRESAS
# ----------------------------------------------------
def resetar_formulario_empresa():
    st.session_state["tabela_empresas"] = {"selection": {"rows": [], "columns": []}}
    st.session_state["Nome_empresa_input"] = ""

def salvar_empresa():
    Nome_emp = str(st.session_state.get("Nome_empresa_input", "")).strip().upper()
    selecao_emp = st.session_state.get("tabela_empresas", {}).get("selection", {}).get("rows", [])

    if Nome_emp:
        df_atual = carregar_empresas()

        if selecao_emp:
            idx = selecao_emp[0]
            df_atual.loc[idx, "Nome"] = Nome_emp
            st.session_state["msg_sucesso_emp"] = f"Empresa '{Nome_emp}' atualizada com sucesso!"
        else:
            if Nome_emp in df_atual["Nome"].str.upper().values:
                st.session_state["msg_aviso_emp"] = f"A empresa '{Nome_emp}' já está cadastrada!"
            else:
                nova_emp = pd.DataFrame([{"Nome": Nome_emp}])
                df_atual = pd.concat([df_atual, nova_emp], ignore_index=True)
                st.session_state["msg_sucesso_emp"] = f"Empresa '{Nome_emp}' cadastrada com sucesso!"

        df_atual.to_csv("empresas.csv", index=False)
        resetar_formulario_empresa()
    else:
        st.session_state["msg_aviso_emp"] = "Digite o Nome da empresa!"

def remover_empresa():
    selecao_emp = st.session_state.get("tabela_empresas", {}).get("selection", {}).get("rows", [])
    if selecao_emp:
        idx = selecao_emp[0]
        df_atual = carregar_empresas()
        Nome_removido = df_atual.loc[idx, "Nome"]
        df_atual = df_atual.drop(index=idx).reset_index(drop=True)
        df_atual.to_csv("empresas.csv", index=False)
        st.session_state["msg_sucesso_emp"] = f"Empresa '{Nome_removido}' removida com sucesso!"
        resetar_formulario_empresa()
    else:
        st.session_state["msg_aviso_emp"] = "Selecione uma empresa na tabela para remover!"

# ----------------------------------------------------
# 3. FUNÇÕES DE SUPORTE - COLABORADORES
# ----------------------------------------------------
def resetar_formulario_e_tabela_colaborador():
    st.session_state["tabela_usuarios"] = {"selection": {"rows": [], "columns": []}}
    empresas_disponiveis = obter_lista_empresas()
    st.session_state["empresa_cad"] = empresas_disponiveis[0] if empresas_disponiveis else ""
    st.session_state["Matricula"] = ""
    st.session_state["Nome"] = ""
    st.session_state["Email"] = ""
    st.session_state["ativo_colab"] = True

def processar_salvamento_colaborador():
    empresas_disponiveis = obter_lista_empresas()
    empresa_val = st.session_state.get("empresa_cad", empresas_disponiveis[0] if empresas_disponiveis else "")
    mat_val = str(st.session_state.get("Matricula", "")).strip()
    Nome_val = str(st.session_state.get("Nome", "")).strip()
    email_val = str(st.session_state.get("Email", "")).strip()
    ativo_val = st.session_state.get("ativo_colab", True)

    if empresa_val and mat_val and Nome_val and email_val:
        selecao_linhas = st.session_state.get("tabela_usuarios", {}).get("selection", {}).get("rows", [])

        try:
            df = pd.read_csv("colaboradores.csv", dtype={"Matricula": str})
        except Exception:
            df = pd.DataFrame(columns=["Empresa", "Matricula", "Nome", "Email", "Ativo"])

        if not selecao_linhas:
            novo = pd.DataFrame([{
                "Empresa": empresa_val,
                "Matricula": mat_val,
                "Nome": Nome_val,
                "Email": email_val,
                "Ativo": ativo_val
            }])
            df = pd.concat([df, novo], ignore_index=True)
            st.session_state["mensagem_sucesso_colab"] = "Colaborador cadastrado com sucesso!"
        else:
            idx = selecao_linhas[0]
            df.loc[idx, "Empresa"] = empresa_val
            df.loc[idx, "Matricula"] = mat_val
            df.loc[idx, "Nome"] = Nome_val
            df.loc[idx, "Email"] = email_val
            df.loc[idx, "Ativo"] = ativo_val
            st.session_state["mensagem_sucesso_colab"] = "Colaborador atualizado com sucesso!"

        df.to_csv("colaboradores.csv", index=False)
        resetar_formulario_e_tabela_colaborador()
    else:
        st.session_state["mensagem_aviso_colab"] = "Selecione uma Empresa e preencha Matrícula, Nome e E-mail!"

def atualizar_Nome_remetente():
    """Callback para sincronizar o Nome do remetente com a empresa selecionada."""
    emp_sel = st.session_state.get("empresa_envio", "")
    if emp_sel:
        st.session_state["Nome_rem_envio"] = f"Recursos Humanos - {emp_sel}"

# ----------------------------------------------------
# 4. BARRA LATERAL (LISTA DE COLABORADORES)
# ----------------------------------------------------
st.sidebar.write("## Usuários Cadastrados")
selecao = st.sidebar.dataframe(
    data=pd.read_csv("colaboradores.csv", dtype={"Matricula": str}),
    on_select="rerun",
    selection_mode="single-row",
    hide_index=False,
    key="tabela_usuarios"
)

colaborador_selecionado = selecao["selection"]["rows"]

if colaborador_selecionado:
    df_colab_atual = pd.read_csv("colaboradores.csv", dtype={"Matricula": str})
    idx = colaborador_selecionado[0]
    emp_atual = str(df_colab_atual.loc[idx].get("Empresa", ""))
    lista_emp = obter_lista_empresas()
    st.session_state["empresa_cad"] = emp_atual if emp_atual in lista_emp else (lista_emp[0] if lista_emp else "")
    st.session_state["Matricula"] = str(df_colab_atual.loc[idx].get("Matricula", ""))
    st.session_state["Nome"] = str(df_colab_atual.loc[idx]["Nome"])
    st.session_state["Email"] = str(df_colab_atual.loc[idx]["Email"])
    st.session_state["ativo_colab"] = bool(df_colab_atual.loc[idx]["Ativo"])
else:
    lista_emp = obter_lista_empresas()
    if "empresa_cad" not in st.session_state:
        st.session_state["empresa_cad"] = lista_emp[0] if lista_emp else ""
    if "Matricula" not in st.session_state:
        st.session_state["Matricula"] = ""
    if "Nome" not in st.session_state:
        st.session_state["Nome"] = ""
    if "Email" not in st.session_state:
        st.session_state["Email"] = ""
    if "ativo_colab" not in st.session_state:
        st.session_state["ativo_colab"] = True

# ----------------------------------------------------
# 5. CRIAÇÃO DAS ABAS DA APLICAÇÃO
# ----------------------------------------------------
tab_empresa, tab_colaborador, tab_disparo = st.tabs([
    "🏢 Cadastro de Empresa", 
    "👤 Cadastro de Colaborador", 
    "🚀 Disparo de Holerites"
])

# ----------------------------------------------------
# ABA 1: CADASTRO DE EMPRESA
# ----------------------------------------------------
with tab_empresa:

    selecao_grid = st.session_state.get("tabela_empresas", {}).get("selection", {}).get("rows", [])
    df_emp_carregadas = carregar_empresas()

    if selecao_grid and selecao_grid[0] < len(df_emp_carregadas):
        st.session_state["Nome_empresa_input"] = str(df_emp_carregadas.loc[selecao_grid[0]]["Nome"])
    elif "Nome_empresa_input" not in st.session_state:
        st.session_state["Nome_empresa_input"] = ""

    if st.session_state.get("msg_sucesso_emp"):
        st.success(st.session_state["msg_sucesso_emp"])
        st.session_state["msg_sucesso_emp"] = ""

    if st.session_state.get("msg_aviso_emp"):
        st.warning(st.session_state["msg_aviso_emp"])
        st.session_state["msg_aviso_emp"] = ""

    with st.form("form_empresa"):
        st.header("Cadastro de Empresas")
        st.text_input(label="Nome da Empresa", key="Nome_empresa_input", placeholder="Informe o Nome da empresa")

        col_salvar, col_nova, col_remover = st.columns(3)
        with col_salvar:
            st.form_submit_button(
                label="Editar" if selecao_grid else "Salvar Empresa",
                on_click=salvar_empresa,
                use_container_width=True
            )
        with col_nova:
            st.form_submit_button(
                label="Nova Empresa",
                on_click=resetar_formulario_empresa,
                use_container_width=True
            )
        with col_remover:
            st.form_submit_button(
                label="Remover Empresa",
                on_click=remover_empresa,
                use_container_width=True
            )

    st.subheader("📋 Empresas Cadastradas")
    st.dataframe(
        data=df_emp_carregadas,
        use_container_width=True,
        hide_index=False,
        on_select="rerun",
        selection_mode="single-row",
        key="tabela_empresas"
    )

# ----------------------------------------------------
# ABA 2: CADASTRO DE COLABORADOR
# ----------------------------------------------------
with tab_colaborador:
    if st.session_state.get("mensagem_sucesso_colab"):
        st.success(st.session_state["mensagem_sucesso_colab"])
        st.session_state["mensagem_sucesso_colab"] = ""

    if st.session_state.get("mensagem_aviso_colab"):
        st.warning(st.session_state["mensagem_aviso_colab"])
        st.session_state["mensagem_aviso_colab"] = ""

    empresas_opcoes = obter_lista_empresas()

    with st.form("form_cadastro_colab"):
        st.header("Cadastro de Colaboradores")
        if empresas_opcoes:
            st.selectbox(label="Empresa", options=empresas_opcoes, key="empresa_cad")
        else:
            st.warning("⚠️ Nenhuma empresa cadastrada. Cadastre uma empresa na aba 'Cadastro de Empresa' primeiro.")

        st.text_input(label="Nº Cadastro / Matrícula", key="Matricula")
        st.text_input(label="Nome completo", key="Nome")
        st.text_input(label="E-mail do Colaborador", key="Email")
        st.checkbox(label="Ativo", key="ativo_colab")

        col1, col2 = st.columns(2)
        with col1:
            st.form_submit_button(
                label="Editar" if colaborador_selecionado else "Cadastrar", 
                on_click=processar_salvamento_colaborador,
                use_container_width=True
            )
        with col2:
            st.form_submit_button(
                label="Novo", 
                on_click=resetar_formulario_e_tabela_colaborador, 
                use_container_width=True
            )

# ----------------------------------------------------
# ABA 3: DISPARO DE HOLERITES
# ----------------------------------------------------
with tab_disparo:
    st.header("Disparo de Holerites")

    empresas_opcoes_envio = obter_lista_empresas()

    col_emp, col_mes = st.columns(2)
    with col_emp:
        if empresas_opcoes_envio:
            empresa_selecionada = st.selectbox(
                "Selecione a Empresa", 
                options=empresas_opcoes_envio, 
                key="empresa_envio",
                on_change=atualizar_Nome_remetente
            )
        else:
            st.warning("⚠️ Nenhuma empresa disponível.")
            empresa_selecionada = ""
            
    with col_mes:
        mes_referencia = st.text_input("Mês de Referência", value="Setembro/2026", key="mes_envio")

    # Inicializa o valor padrão caso a chave ainda não exista na sessão
    if "Nome_rem_envio" not in st.session_state:
        st.session_state["Nome_rem_envio"] = f"Recursos Humanos - {empresa_selecionada}" if empresa_selecionada else "Recursos Humanos"

    rotulo_pdf = f"Selecione o PDF com os holerites ({empresa_selecionada})" if empresa_selecionada else "Selecione o PDF com os holerites"
    arquivo_pdf = st.file_uploader(rotulo_pdf, type=["pdf"], key="pdf_envio")

    col_Nome_rem, col_email_rem, col_senha = st.columns([2, 2, 2])
    with col_Nome_rem:
        Nome_remetente = st.text_input("Nome do Remetente", key="Nome_rem_envio")
    with col_email_rem:
        remetente = st.text_input("E-mail Remetente", placeholder="ex: rh@suaempresa.com.br", key="email_rem_envio")
    with col_senha:
        senha_app = st.text_input("Senha do E-mail", type="password", key="senha_app_envio")

    rotulo_btn = f"Enviar Holerites ({empresa_selecionada})" if empresa_selecionada else "Enviar Holerites"
    if st.button(rotulo_btn, use_container_width=True, key="btn_disparar"):
        mes_val = str(mes_referencia or "").strip()
        rem_val = str(remetente or "").strip()
        senha_val = str(senha_app or "").strip()
        Nome_rem_val = str(Nome_remetente or "").strip()

        if empresa_selecionada and arquivo_pdf is not None and mes_val and rem_val and senha_val:
            with st.spinner(f"Processando e enviando holerites da empresa {empresa_selecionada} ({mes_val})..."):
                desmembrar_e_enviar_holerites(
                    pdf_bytes=arquivo_pdf,
                    dados_usuarios=pd.read_csv("colaboradores.csv", dtype={"Matricula": str}),
                    empresa_selecionada=empresa_selecionada,
                    mes_referencia=mes_val,
                    nome_remetente=Nome_rem_val,
                    remetente_email=rem_val,
                    senha_app=senha_val
                )
        else:
            st.warning("Selecione a Empresa, Mês de Referência, E-mail Remetente, Senha e selecione o PDF do lote!")