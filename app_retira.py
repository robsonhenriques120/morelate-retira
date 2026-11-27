
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import os

st.set_page_config(
    page_title="Morelate - Controle de Retira",
    page_icon="🏪",
    layout="wide"
)

# Identidade Visual Morelate (Mesma paleta do app de entregas)
st.markdown("""
    <style>
    .header-card {
        background-color: #0B6E31;
        padding: 18px 15px 14px 15px;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .header-title {
        color: #FFFFFF;
        font-size: 26px;
        font-weight: 700;
        margin: 0;
    }
    .header-subtitle {
        color: #D9F2E2;
        font-size: 14px;
        margin-top: 4px;
    }
    div.stButton > button:first-child {
        background-color: #0B6E31;
        color: white;
        font-size: 16px;
        font-weight: bold;
        border-radius: 10px;
        padding: 10px 20px;
        border: none;
    }
    div.stButton > button:first-child:hover {
        background-color: #085224;
        color: white;
    }
    div[role="radiogroup"] label {
        font-size: 16px !important;
        padding: 4px 0px;
    }
    </style>
""", unsafe_allow_html=True)

# Conexão com a mesma planilha da Morelate usando abas dedicadas ao Retira
@st.cache_resource
def conectar_planilha_retira():
    base_url = "https://www.googleapis.com" + "/auth/"
    escopos = [base_url + "spreadsheets", base_url + "drive"]
    credenciais_dict = dict(st.secrets["connections"]["gsheets"])
    creds = Credentials.from_service_account_info(credenciais_dict, scopes=escopos)
    cliente = gspread.authorize(creds)
    
    planilha = cliente.open_by_key("1I3V8UxkeQyP1tO7TZIVbQk7HQrxv-FSsz5l3ChCMsV4")
    
    abas_existentes = [aba.title for aba in planilha.worksheets()]
    
    if "Retira_Conferidos" not in abas_existentes:
        aba_conf = planilha.add_worksheet(title="Retira_Conferidos", rows="2000", cols="10")
        aba_conf.append_row([
            "Requisicao", "Dt_Cadastro", "Cliente", "Transportador", 
            "Valor", "Conferente", "Fim_Conferencia", "Data_Importacao"
        ])
    else:
        aba_conf = planilha.worksheet("Retira_Conferidos")
        
    if "Retira_Baixas" not in abas_existentes:
        aba_baixas = planilha.add_worksheet(title="Retira_Baixas", rows="2000", cols="8")
        aba_baixas.append_row([
            "Data_Hora_Retirada", "Requisicao", "Cliente", 
            "Retirado_Por", "Conferente_Balcao", "Observacao",
            "Status", "Motivo_Cancelamento"
        ])
    else:
        aba_baixas = planilha.worksheet("Retira_Baixas")
        
    return aba_conf, aba_baixas

# Função de limpeza blindada do CSV do Jacsys (cns_251_01)
def processar_csv_jacsys(arquivo_csv):
    df = pd.read_csv(arquivo_csv, sep=";", encoding="latin1", dtype=str)
    
    # 1. Remove linha de totalização e linhas sem Requisição
    df = df.dropna(subset=["Requisição"]).copy()
    df["Requisição"] = df["Requisição"].str.strip()
    df = df[df["Requisição"].str.isdigit()]
    
    # 2. Filtra apenas modalidades RETIRA e BALCAO
    df["Transportador"] = df["Transportador"].fillna("").str.strip()
    df = df[df["Transportador"].str.contains("RETIRA|BALCAO", case=False, na=False)]
    
    # 3. Remove duplicidades geradas por múltiplos separadores/pisos
    df = df.drop_duplicates(subset=["Requisição"], keep="first")
    
    # 4. Seleciona e organiza as colunas limpas
    colunas_finais = pd.DataFrame({
        "Requisicao": df["Requisição"],
        "Dt_Cadastro": df["Dt.Cadastro"].fillna("").str.strip(),
        "Cliente": df["Cliente"].fillna("").str.strip(),
        "Transportador": df["Transportador"],
        "Valor": df["Vlr.Total"].fillna("0,00").str.strip(),
        "Conferente": df["Conferente"].fillna("").str.strip(),
        "Fim_Conferencia": df["Fim Conf."].fillna("").str.strip()
    })
    return colunas_finais

# Logo opcional
if os.path.exists("logo.png"):
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("logo.png", use_container_width=True)

# Cabeçalho
st.markdown("""
    <div class="header-card">
        <p class="header-title">🏪 Controle de Retira & Balcão</p>
        <p class="header-subtitle">Painel de Pedidos Prontos, Baixas e Ocorrências</p>
    </div>
""", unsafe_allow_html=True)

aba_conf, aba_baixas = conectar_planilha_retira()

# Carrega dados atuais das duas abas
dados_conf = aba_conf.get_all_records()
dados_baixas = aba_baixas.get_all_records()

df_conf = pd.DataFrame(dados_conf)
df_baixas = pd.DataFrame(dados_baixas)

# Filtra o que está PRONTO mas ainda NÃO FOI BAIXADO (nem entregue, nem cancelado)
if not df_conf.empty:
    df_conf["Requisicao"] = df_conf["Requisicao"].astype(str).str.strip()
    reqs_baixadas = set()
    if not df_baixas.empty:
        reqs_baixadas = set(df_baixas["Requisicao"].astype(str).str.strip())
    
    df_pendentes = df_conf[~df_conf["Requisicao"].isin(reqs_baixadas)].copy()
else:
    df_pendentes = pd.DataFrame()

# Abas principais da operação
tab_painel, tab_baixa, tab_historico = st.tabs([
    "🟢 Prontos para Retirar", 
    "✅ Registrar Retirada / Ocorrência", 
    "📋 Histórico de Movimentações"
])

# --- ABA 1: PAINEL DO BALCÃO ---
with tab_painel:
    col_m1, col_m2, col_m3, col_b = st.columns([2, 2, 2, 1])
    with col_m1:
        st.metric("📦 Aguardando Cliente", len(df_pendentes))
    
    # Calcula métricas separadas se a coluna Status já existir nos registros
    qtd_entregues = 0
    qtd_cancelados = 0
    if not df_baixas.empty:
        if "Status" in df_baixas.columns:
            qtd_cancelados = df_baixas["Status"].astype(str).str.contains("Cancelado", case=False, na=False).sum()
            qtd_entregues = len(df_baixas) - qtd_cancelados
        else:
            qtd_entregues = len(df_baixas)

    with col_m2:
        st.metric("✅ Retiradas OK", qtd_entregues)
    with col_m3:
        st.metric("🔴 NF Cancelada / Recusa", qtd_cancelados)
    with col_b:
        if st.button("🔄 Atualizar"):
            st.rerun()

    if not df_pendentes.empty:
        busca = st.text_input("🔍 Buscar por Número da Requisição ou Nome do Cliente:")
        df_exibir = df_pendentes.copy()
        if busca:
            df_exibir = df_exibir[
                df_exibir["Requisicao"].str.contains(busca, case=False, na=False) |
                df_exibir["Cliente"].str.contains(busca, case=False, na=False)
            ]
        # Exibe apenas colunas operacionais (sem Valor)
        cols_mostrar = [c for c in ["Requisicao", "Dt_Cadastro", "Cliente", "Transportador", "Conferente", "Fim_Conferencia"] if c in df_exibir.columns]
        st.dataframe(
            df_exibir[cols_mostrar],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Nenhum pedido conferido aguardando retirada no momento. Suba o CSV do Jacsys na barra lateral para atualizar.")

# --- ABA 2: BAIXA NO BALCÃO (OK OU CANCELAMENTO/RECUSA) ---
with tab_baixa:
    if "enviando_retira" not in st.session_state:
        st.session_state.enviando_retira = False

    if not df_pendentes.empty:
        opcoes_req = ["Selecione o pedido..."] + [
            f"{row['Requisicao']} - {row['Cliente']}" for _, row in df_pendentes.iterrows()
        ]
        escolha = st.selectbox("📋 Selecione a Requisição Pronta:", opcoes_req)
        req_manual = ""
    else:
        escolha = "Selecione o pedido..."
        req_manual = st.text_input("📋 Digite o Número da Requisição:")

    # Seletor de Status (Padrão do App de Entregas)
    status_balcao = st.radio(
        "📌 Situação no Balcão:",
        ["🟢 Pedido Entregue OK", "🔴 Cancelado / Recusado (NF Cancelada)"],
        horizontal=True
    )

    retirado_por = ""
    motivo_selecionado = "N/A"

    if status_balcao == "🟢 Pedido Entregue OK":
        retirado_por = st.text_input(
            "👤 Nome / CPF / Placa de quem retirou:", 
            placeholder="Ex: João Silva - CPF 123.456... ou Placa ABC-1234"
        )
    else:
        motivo_selecionado = st.selectbox(
            "⚠️ Motivo do Cancelamento / Recusa:",
            [
                "Selecione...",
                "Nota Fiscal Cancelada no Jacsys",
                "Erro na nota / Boleto / Preço divergente",
                "Pedido Duplicado / Cliente não pediu",
                "Mercadoria errada / Faltando / Avariada",
                "Demora na separação / Cliente não quis esperar",
                "Cliente desistiu da compra / Sem limite"
            ]
        )
        retirado_por = "N/A (Cancelado/Recusado)"

    conferente_balcao = st.text_input("🏷️ Conferente / Atendente do Balcão:", placeholder="Seu nome")
    obs_retira = st.text_area("📝 Observações (opcional):", placeholder="Ex: Número da NF cancelada, detalhe da ocorrência...")

    st.write("")

    if st.button("✅ Confirmar Registro no Balcão", use_container_width=True, disabled=st.session_state.enviando_retira):
        if escolha != "Selecione o pedido...":
            req_final = escolha.split(" - ")[0].strip()
            cliente_final = escolha.split(" - ", 1)[1].strip()
        else:
            req_final = req_manual.strip()
            cliente_final = "Informado Manualmente"

        # Validações específicas por tipo de ocorrência
        erro_validacao = None
        if not req_final:
            erro_validacao = "❌ Selecione ou digite o número da Requisição."
        elif not conferente_balcao.strip():
            erro_validacao = "❌ Informe o nome do Conferente / Atendente do Balcão."
        elif status_balcao == "🟢 Pedido Entregue OK" and not retirado_por.strip():
            erro_validacao = "❌ Informe o Nome, CPF ou Placa de quem retirou o pedido."
