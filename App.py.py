import hashlib
import json
import hmac
import time
from datetime import datetime, date, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st


# =========================================================
# CONFIGURAÇÃO
# =========================================================

LOGO_PATH = Path("logo.png")

st.set_page_config(
    page_title="Running",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "🏃",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    :root {
        --flu-grena: #7A263A;
        --flu-verde: #006B54;
        --flu-verde-escuro: #00513F;
        --flu-offwhite: #F8F7F4;
        --flu-borda: rgba(122, 38, 58, 0.18);
    }

    .stApp {
        background:
            linear-gradient(
                180deg,
                rgba(122, 38, 58, 0.035) 0px,
                rgba(0, 107, 84, 0.025) 170px,
                transparent 360px
            );
    }

    .block-container {
        max-width: 840px;
        padding-top: 1.1rem;
        padding-bottom: 4rem;
    }

    h1 {
        letter-spacing: -0.04em;
        color: var(--flu-grena);
    }

    h2, h3 {
        letter-spacing: -0.02em;
    }

    div[data-testid="stMetric"] {
        border: 1px solid var(--flu-borda);
        padding: 14px;
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.72);
        box-shadow: 0 3px 14px rgba(0, 0, 0, 0.035);
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 18px;
        border-color: rgba(0, 107, 84, 0.18);
    }

    /* Botões principais */
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {
        background: var(--flu-grena);
        border-color: var(--flu-grena);
        color: white;
    }

    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover {
        background: #651F30;
        border-color: #651F30;
        color: white;
    }

    /* Botões normais */
    .stButton > button,
    .stFormSubmitButton > button,
    .stLinkButton > a {
        border-radius: 12px;
    }

    /* Abas */
    button[data-baseweb="tab"] {
        font-weight: 650;
    }

    button[data-baseweb="tab"][aria-selected="true"] {
        color: var(--flu-grena);
    }

    div[data-baseweb="tab-highlight"] {
        background-color: var(--flu-verde) !important;
    }

    /* Barras de progresso */
    div[data-testid="stProgress"] > div > div > div > div {
        background-color: var(--flu-verde);
    }

    /* Inputs focados */
    input:focus,
    textarea:focus {
        border-color: var(--flu-verde) !important;
    }

    /* Pequeno detalhe tricolor no topo */
    .flu-strip {
        height: 5px;
        border-radius: 999px;
        margin-bottom: 14px;
        background: linear-gradient(
            90deg,
            var(--flu-grena) 0 38%,
            white 38% 62%,
            var(--flu-verde) 62% 100%
        );
        box-shadow: 0 1px 5px rgba(0,0,0,0.08);
    }
    </style>

    <div class="flu-strip"></div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# SECRETS
# =========================================================

try:
    SUPABASE_URL = st.secrets["supabase"]["url"].rstrip("/")
    SUPABASE_SECRET = st.secrets["supabase"]["secret_key"]

    STRAVA_CLIENT_ID = str(st.secrets["strava"]["client_id"])
    STRAVA_CLIENT_SECRET = st.secrets["strava"]["client_secret"]
    STRAVA_REDIRECT_URI = st.secrets["strava"]["redirect_uri"]

    APP_PASSWORD = st.secrets["app"]["password"]

except Exception:
    st.error(
        "Faltam configurações em Settings → Secrets. "
        "Confira as seções [supabase], [strava] e [app]."
    )
    st.stop()


# OpenAI é opcional: o restante do app continua funcionando sem a chave.
try:
    OPENAI_API_KEY = st.secrets["openai"]["api_key"]
except Exception:
    OPENAI_API_KEY = None

try:
    OPENAI_MODEL = st.secrets["openai"]["model"]
except Exception:
    OPENAI_MODEL = "gpt-5.6-terra"


# =========================================================
# MARCA
# =========================================================

def mostrar_marca(subtitulo=None):
    if LOGO_PATH.exists():
        col_logo, col_titulo = st.columns([1, 5])

        with col_logo:
            st.image(
                str(LOGO_PATH),
                width=72,
            )

        with col_titulo:
            st.title("Running")

            if subtitulo:
                st.caption(subtitulo)

    else:
        st.title("🏃 Running")

        if subtitulo:
            st.caption(subtitulo)


# =========================================================
# LOGIN
# =========================================================

def autenticar_app():
    if st.session_state.get("autenticado"):
        return

    mostrar_marca("Área privada")

    senha = st.text_input(
        "Senha",
        type="password",
        placeholder="Digite a senha do app",
    )

    if st.button("Entrar", width="stretch"):
        if hmac.compare_digest(str(senha), str(APP_PASSWORD)):
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")

    st.stop()


autenticar_app()


# =========================================================
# SUPABASE REST
# =========================================================

REST_URL = f"{SUPABASE_URL}/rest/v1"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SECRET,
    "Content-Type": "application/json",
}


def supabase_get(tabela, params=None):
    resposta = requests.get(
        f"{REST_URL}/{tabela}",
        headers=SUPABASE_HEADERS,
        params=params or {},
        timeout=20,
    )
    resposta.raise_for_status()
    return resposta.json()


def supabase_insert(tabela, dados):
    headers = {
        **SUPABASE_HEADERS,
        "Prefer": "return=representation",
    }

    resposta = requests.post(
        f"{REST_URL}/{tabela}",
        headers=headers,
        json=dados,
        timeout=20,
    )
    resposta.raise_for_status()
    return resposta.json()


def supabase_update(tabela, filtros, dados):
    headers = {
        **SUPABASE_HEADERS,
        "Prefer": "return=representation",
    }

    resposta = requests.patch(
        f"{REST_URL}/{tabela}",
        headers=headers,
        params=filtros,
        json=dados,
        timeout=20,
    )
    resposta.raise_for_status()
    return resposta.json()


def supabase_delete(tabela, filtros):
    resposta = requests.delete(
        f"{REST_URL}/{tabela}",
        headers=SUPABASE_HEADERS,
        params=filtros,
        timeout=20,
    )
    resposta.raise_for_status()


# =========================================================
# DADOS
# =========================================================

def carregar_planejamento():
    dados = supabase_get(
        "planejamento",
        {
            "select": "*",
            "order": "data.asc,id.asc",
        },
    )

    df = pd.DataFrame(dados)

    if not df.empty:
        df["data_dt"] = pd.to_datetime(
            df["data"],
            errors="coerce",
        ).dt.date

        df["distancia"] = pd.to_numeric(
            df["distancia"],
            errors="coerce",
        ).fillna(0.0)

    return df


def carregar_historico():
    dados = supabase_get(
        "treinos",
        {
            "select": "*",
            "order": "data.desc,id.desc",
        },
    )

    df = pd.DataFrame(dados)

    if not df.empty:
        df["data_dt"] = pd.to_datetime(
            df["data"],
            errors="coerce",
        ).dt.date

        df["distancia"] = pd.to_numeric(
            df["distancia"],
            errors="coerce",
        ).fillna(0.0)

        if "esforco" in df.columns:
            df["esforco"] = pd.to_numeric(
                df["esforco"],
                errors="coerce",
            )

    return df


def salvar_planejamento(
    data_treino,
    tipo,
    distancia,
    pace_alvo,
    descricao,
):
    return supabase_insert(
        "planejamento",
        {
            "data": str(data_treino),
            "tipo": tipo,
            "distancia": float(distancia),
            "pace_alvo": pace_alvo.strip() if pace_alvo else "",
            "descricao": descricao.strip() if descricao else "",
        },
    )


def excluir_planejamento(id_treino):
    supabase_delete(
        "planejamento",
        {
            "id": f"eq.{int(id_treino)}",
        },
    )


def salvar_treino(
    data_treino,
    tipo,
    distancia,
    pace=None,
    esforco=None,
    observacao=None,
    planejamento_id=None,
    origem="manual",
    strava_activity_id=None,
    duracao_seg=None,
    elevacao_m=None,
    frequencia_cardiaca_media=None,
):
    dados = {
        "data": str(data_treino),
        "tipo": tipo,
        "distancia": float(distancia),
        "pace": pace.strip() if pace else None,
        "esforco": int(esforco) if esforco is not None else None,
        "observacao": observacao.strip() if observacao else None,
        "planejamento_id": (
            int(planejamento_id)
            if planejamento_id is not None
            else None
        ),
        "origem": origem,
        "strava_activity_id": (
            int(strava_activity_id)
            if strava_activity_id is not None
            else None
        ),
        "duracao_seg": (
            int(duracao_seg)
            if duracao_seg is not None
            else None
        ),
        "elevacao_m": (
            float(elevacao_m)
            if elevacao_m is not None
            else None
        ),
        "frequencia_cardiaca_media": (
            float(frequencia_cardiaca_media)
            if frequencia_cardiaca_media is not None
            else None
        ),
    }

    return supabase_insert("treinos", dados)


def excluir_treino(id_treino):
    supabase_delete(
        "treinos",
        {
            "id": f"eq.{int(id_treino)}",
        },
    )


# =========================================================
# PACE / TEMPO
# =========================================================

def pace_para_segundos(pace):
    if pace is None:
        return None

    texto = str(pace).strip()

    if not texto:
        return None

    texto = (
        texto.replace("'", ":")
        .replace('"', "")
        .replace("/km", "")
        .strip()
    )

    try:
        partes = texto.split(":")

        if len(partes) != 2:
            return None

        minutos = int(partes[0])
        segundos = int(partes[1])

        if minutos < 0 or segundos < 0 or segundos >= 60:
            return None

        return minutos * 60 + segundos

    except (ValueError, TypeError):
        return None


def segundos_para_pace(segundos):
    if segundos is None or pd.isna(segundos):
        return "-"

    valor = int(round(float(segundos)))
    return f"{valor // 60}:{valor % 60:02d}"


def segundos_para_tempo(segundos):
    if segundos is None or pd.isna(segundos):
        return "-"

    valor = int(round(float(segundos)))
    horas = valor // 3600
    minutos = (valor % 3600) // 60
    resto = valor % 60

    if horas > 0:
        return f"{horas}:{minutos:02d}:{resto:02d}"

    return f"{minutos}:{resto:02d}"


# =========================================================
# PLANEJADO x REALIZADO
# =========================================================

def realizado_do_planejado(treino_planejado, historico_df):
    if historico_df.empty:
        return None

    if "planejamento_id" in historico_df.columns:
        ids = pd.to_numeric(
            historico_df["planejamento_id"],
            errors="coerce",
        )

        direto = historico_df[
            ids == int(treino_planejado["id"])
        ]

        if not direto.empty:
            return direto.iloc[0]

    fallback = historico_df[
        (historico_df["data"] == treino_planejado["data"])
        & (historico_df["tipo"] == treino_planejado["tipo"])
    ]

    if not fallback.empty:
        return fallback.iloc[0]

    return None


def achar_planejamento_para_strava(
    data_atividade,
    distancia_km,
    planejamento_df,
    historico_df,
):
    if planejamento_df.empty:
        return None

    candidatos = planejamento_df[
        planejamento_df["data"] == str(data_atividade)
    ].copy()

    if candidatos.empty:
        return None

    livres = []

    for _, treino in candidatos.iterrows():
        if realizado_do_planejado(treino, historico_df) is None:
            livres.append(treino)

    if not livres:
        return None

    livres_df = pd.DataFrame(livres)

    livres_df["dif_dist"] = (
        livres_df["distancia"].astype(float) - float(distancia_km)
    ).abs()

    return livres_df.sort_values("dif_dist").iloc[0]


# =========================================================
# STRAVA OAUTH
# =========================================================

def carregar_strava_auth():
    dados = supabase_get(
        "strava_auth",
        {
            "select": "*",
            "id": "eq.1",
            "limit": "1",
        },
    )

    return dados[0] if dados else None


def salvar_strava_auth(token_data):
    atual = carregar_strava_auth()

    athlete_id = token_data.get("athlete", {}).get("id")

    if athlete_id is None and atual:
        athlete_id = atual.get("athlete_id")

    dados = {
        "athlete_id": athlete_id,
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": int(token_data["expires_at"]),
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }

    if atual:
        supabase_update(
            "strava_auth",
            {"id": "eq.1"},
            dados,
        )
    else:
        dados["id"] = 1
        supabase_insert("strava_auth", dados)


def oauth_state():
    return hmac.new(
        str(APP_PASSWORD).encode("utf-8"),
        b"running-strava-oauth",
        hashlib.sha256,
    ).hexdigest()


def strava_authorize_url():
    params = {
        "client_id": STRAVA_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": STRAVA_REDIRECT_URI,
        "approval_prompt": "auto",
        "scope": "read,activity:read_all",
        "state": oauth_state(),
    }

    return (
        "https://www.strava.com/oauth/authorize?"
        + urlencode(params)
    )


def trocar_codigo_por_token(code):
    resposta = requests.post(
        "https://www.strava.com/api/v3/oauth/token",
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )

    resposta.raise_for_status()
    return resposta.json()


def refresh_strava_token(refresh_token):
    resposta = requests.post(
        "https://www.strava.com/api/v3/oauth/token",
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=20,
    )

    resposta.raise_for_status()
    return resposta.json()


def access_token_valido():
    auth = carregar_strava_auth()

    if not auth:
        return None

    expires_at = int(auth["expires_at"])

    if expires_at <= int(time.time()) + 3600:
        novo = refresh_strava_token(
            auth["refresh_token"]
        )

        salvar_strava_auth(novo)
        return novo["access_token"]

    return auth["access_token"]


# =========================================================
# STRAVA ATIVIDADES
# =========================================================

def buscar_atividades_strava(dias=45):
    token = access_token_valido()

    if not token:
        raise RuntimeError(
            "Strava ainda não está conectado."
        )

    after = int(
        time.time() - dias * 24 * 60 * 60
    )

    resposta = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={
            "Authorization": f"Bearer {token}",
        },
        params={
            "after": after,
            "per_page": 100,
            "page": 1,
        },
        timeout=25,
    )

    resposta.raise_for_status()
    return resposta.json()


def importar_atividades_strava():
    atividades = buscar_atividades_strava(dias=45)

    planejamento_df = carregar_planejamento()
    historico_df = carregar_historico()

    ids_existentes = set()

    if (
        not historico_df.empty
        and "strava_activity_id" in historico_df.columns
    ):
        for valor in historico_df["strava_activity_id"].dropna():
            try:
                ids_existentes.add(int(valor))
            except Exception:
                pass

    importadas = 0
    ignoradas = 0

    esportes_corrida = {
        "Run",
        "TrailRun",
        "VirtualRun",
    }

    for atividade in atividades:
        sport_type = atividade.get("sport_type")
        tipo_antigo = atividade.get("type")

        if (
            sport_type not in esportes_corrida
            and tipo_antigo != "Run"
        ):
            continue

        activity_id = int(atividade["id"])

        if activity_id in ids_existentes:
            ignoradas += 1
            continue

        distancia_m = float(
            atividade.get("distance", 0) or 0
        )

        moving_time = int(
            atividade.get("moving_time", 0) or 0
        )

        if distancia_m <= 0 or moving_time <= 0:
            ignoradas += 1
            continue

        distancia_km = distancia_m / 1000
        pace_seg = moving_time / distancia_km
        pace = segundos_para_pace(pace_seg)

        data_local = str(
            atividade.get("start_date_local", "")
        )[:10]

        if not data_local:
            ignoradas += 1
            continue

        data_atividade = pd.to_datetime(
            data_local
        ).date()

        planejado = achar_planejamento_para_strava(
            data_atividade,
            distancia_km,
            planejamento_df,
            historico_df,
        )

        planejamento_id = None
        tipo = "Corrida"

        if planejado is not None:
            planejamento_id = int(planejado["id"])
            tipo = planejado["tipo"]

        salvar_treino(
            data_treino=data_atividade,
            tipo=tipo,
            distancia=distancia_km,
            pace=pace,
            esforco=None,
            observacao=(
                "Importado do Strava: "
                + atividade.get("name", "Atividade")
            ),
            planejamento_id=planejamento_id,
            origem="strava",
            strava_activity_id=activity_id,
            duracao_seg=moving_time,
            elevacao_m=atividade.get(
                "total_elevation_gain"
            ),
            frequencia_cardiaca_media=atividade.get(
                "average_heartrate"
            ),
        )

        importadas += 1
        ids_existentes.add(activity_id)

        historico_df = carregar_historico()

    return importadas, ignoradas


# =========================================================
# COACH ADAPTATIVO V2
# =========================================================

def deduplicar_historico_coach(historico_df):
    """
    Evita que a mesma corrida conte duas vezes no motor do Coach
    quando ela existe manualmente e também veio do Strava.
    """
    if historico_df.empty:
        return historico_df.copy()

    df = historico_df.copy()

    df["data_plot"] = pd.to_datetime(
        df["data"],
        errors="coerce",
    )

    df["pace_segundos"] = df["pace"].apply(
        pace_para_segundos
    )

    df["distancia"] = pd.to_numeric(
        df["distancia"],
        errors="coerce",
    ).fillna(0.0)

    # Distâncias próximas entram no mesmo agrupamento.
    df["dist_key"] = (
        df["distancia"] * 2
    ).round() / 2

    # Se houver duplicata manual + Strava, preferimos Strava.
    df["origem_rank"] = (
        df["origem"]
        .fillna("manual")
        .map(
            {
                "strava": 0,
                "manual": 1,
            }
        )
        .fillna(2)
    )

    df = df.sort_values(
        [
            "data_plot",
            "dist_key",
            "origem_rank",
            "id",
        ],
        ascending=[
            False,
            True,
            True,
            False,
        ],
    )

    df = df.drop_duplicates(
        subset=[
            "data",
            "dist_key",
        ],
        keep="first",
    )

    return df


def volume_periodo(df, inicio, fim):
    if df.empty:
        return 0.0

    mask = (
        (df["data_dt"] >= inicio)
        & (df["data_dt"] <= fim)
    )

    return float(
        df.loc[
            mask,
            "distancia",
        ].sum()
    )


def pace_referencia_recente(
    historico_df,
    hoje_local,
):
    """
    Usa apenas corridas recentes e dá preferência às rodagens
    contínuas, evitando que tiros e testes distorçam o pace-base.
    """
    if historico_df.empty:
        return 380  # 6:20/km

    df = deduplicar_historico_coach(
        historico_df
    )

    limite = (
        hoje_local
        - timedelta(days=28)
    )

    df = df[
        df["data_dt"] >= limite
    ].copy()

    if df.empty:
        return 380

    preferidos = df[
        ~df["tipo"].isin(
            [
                "Intervalado",
                "Teste 5 km",
            ]
        )
    ].dropna(
        subset=[
            "pace_segundos"
        ]
    )

    if preferidos.empty:
        preferidos = df.dropna(
            subset=[
                "pace_segundos"
            ]
        )

    if preferidos.empty:
        return 380

    # Só os cinco treinos contínuos mais recentes.
    preferidos = preferidos.sort_values(
        "data_plot",
        ascending=False,
    ).head(5)

    mediana = int(
        preferidos[
            "pace_segundos"
        ].median()
    )

    # Limites defensivos.
    return max(
        300,
        min(
            450,
            mediana,
        ),
    )


def analisar_estado_coach(
    historico_df,
    hoje_local,
):
    df = deduplicar_historico_coach(
        historico_df
    )

    inicio_semana_atual = (
        hoje_local
        - timedelta(
            days=hoje_local.weekday()
        )
    )

    # Últimos 28 dias
    inicio_28 = (
        hoje_local
        - timedelta(days=27)
    )

    recentes_28 = (
        df[
            df["data_dt"] >= inicio_28
        ].copy()
        if not df.empty
        else pd.DataFrame()
    )

    volume_28 = (
        float(
            recentes_28[
                "distancia"
            ].sum()
        )
        if not recentes_28.empty
        else 0.0
    )

    treinos_28 = len(
        recentes_28
    )

    # Semanas completas anteriores, sem usar a semana corrente.
    semanas = []

    for i in range(
        1,
        5,
    ):
        fim = (
            inicio_semana_atual
            - timedelta(
                days=1 + 7 * (i - 1)
            )
        )

        inicio = (
            fim
            - timedelta(days=6)
        )

        vol = volume_periodo(
            df,
            inicio,
            fim,
        )

        qtd = 0

        if not df.empty:
            qtd = len(
                df[
                    (df["data_dt"] >= inicio)
                    & (df["data_dt"] <= fim)
                ]
            )

        semanas.append(
            {
                "inicio": inicio,
                "fim": fim,
                "volume": vol,
                "treinos": qtd,
            }
        )

    semanas_ativas = [
        s
        for s in semanas
        if s["treinos"] > 0
    ]

    ultima_semana = (
        semanas_ativas[0]
        if semanas_ativas
        else None
    )

    volume_ultima_semana = (
        ultima_semana[
            "volume"
        ]
        if ultima_semana
        else 0.0
    )

    # Rolling 7 dias funciona bem quando a pessoa voltou no meio
    # de uma semana ou ainda não completou uma semana fechada.
    inicio_7 = (
        hoje_local
        - timedelta(days=6)
    )

    volume_ultimos_7 = (
        volume_periodo(
            df,
            inicio_7,
            hoje_local,
        )
    )

    # Detecta fase de retorno / pouco histórico recente.
    semanas_ativas_21 = 0

    for s in semanas[:3]:
        if s["treinos"] > 0:
            semanas_ativas_21 += 1

    modo_retorno = (
        treinos_28 < 10
        or semanas_ativas_21 <= 1
    )

    # Base principal: semana completa mais recente.
    # Se não existir, usa rolling 7.
    volume_base = (
        volume_ultima_semana
        if volume_ultima_semana > 0
        else volume_ultimos_7
    )

    # Se os dois existem e divergem demais, usa o menor valor
    # para não transformar um pico isolado em nova referência.
    if (
        volume_ultima_semana > 0
        and volume_ultimos_7 > 0
    ):
        maior = max(
            volume_ultima_semana,
            volume_ultimos_7,
        )

        menor = min(
            volume_ultima_semana,
            volume_ultimos_7,
        )

        if maior > menor * 1.35:
            volume_base = menor

    if volume_base <= 0:
        volume_base = 20.0

    # Maior corrida dos últimos 14 dias:
    # usada para limitar o longão da semana seguinte.
    inicio_14 = (
        hoje_local
        - timedelta(days=13)
    )

    recentes_14 = (
        df[
            df["data_dt"] >= inicio_14
        ]
        if not df.empty
        else pd.DataFrame()
    )

    maior_corrida_14 = (
        float(
            recentes_14[
                "distancia"
            ].max()
        )
        if not recentes_14.empty
        else 6.0
    )

    if pd.isna(
        maior_corrida_14
    ):
        maior_corrida_14 = 6.0

    pace_ref = (
        pace_referencia_recente(
            df,
            hoje_local,
        )
    )

    return {
        "volume_ultima_semana": float(
            volume_ultima_semana
        ),
        "volume_ultimos_7": float(
            volume_ultimos_7
        ),
        "volume_28": float(
            volume_28
        ),
        "treinos_28": int(
            treinos_28
        ),
        "volume_base": float(
            volume_base
        ),
        "maior_corrida_14": float(
            maior_corrida_14
        ),
        "pace_ref": int(
            pace_ref
        ),
        "modo_retorno": bool(
            modo_retorno
        ),
    }


def arredondar_meio_km(valor):
    return round(
        float(valor) * 2
    ) / 2


def calcular_volume_alvo(
    estado,
    intensidade_semana,
    fadiga,
):
    base = estado[
        "volume_base"
    ]

    multiplicadores = {
        "Leve": 0.88,
        "Normal": 1.00,
        "Progressiva": 1.05,
    }

    alvo = (
        base
        * multiplicadores[
            intensidade_semana
        ]
    )

    if fadiga >= 8:
        alvo *= 0.78

    elif fadiga >= 6:
        alvo *= 0.90

    # Durante retorno, uma semana progressiva sobe no máximo 5%.
    # Fora do retorno, no máximo 8%.
    limite_crescimento = (
        1.05
        if estado[
            "modo_retorno"
        ]
        else 1.08
    )

    if alvo > base:
        alvo = min(
            alvo,
            base
            * limite_crescimento,
            base + 2.5,
        )

    # Não inventa volume quando a base é baixa.
    alvo = max(
        base * 0.78,
        alvo,
    )

    return arredondar_meio_km(
        alvo
    )


def construir_sessoes(
    volume_alvo,
    n_treinos,
    estado,
    fadiga,
):
    """
    Diferente da V1, cada tipo de treino tem um tamanho coerente.
    A distância do intervalado deixa de ser um simples percentual
    do volume semanal.
    """
    maior_recente = estado[
        "maior_corrida_14"
    ]

    # Longão: no máximo +1 km sobre a maior corrida recente
    # e no máximo ~32% da semana.
    longao = min(
        maior_recente + 1.0,
        volume_alvo * 0.32,
    )

    longao = max(
        5.5,
        arredondar_meio_km(
            longao
        ),
    )

    if n_treinos == 3:
        # Intervalado = ~4.5-5 km totais de corrida,
        # dependendo da recuperação.
        intervalado = 4.5

        leve = (
            volume_alvo
            - intervalado
            - longao
        )

        leve = max(
            4.5,
            arredondar_meio_km(
                leve
            ),
        )

        sessoes = [
            (
                "Rodagem leve",
                leve,
            ),
            (
                "Intervalado",
                intervalado,
            ),
            (
                "Longão",
                longao,
            ),
        ]

    elif n_treinos == 4:
        intervalado = 4.5

        progressivo = min(
            6.0,
            max(
                5.0,
                arredondar_meio_km(
                    volume_alvo
                    * 0.26
                ),
            ),
        )

        leve = (
            volume_alvo
            - intervalado
            - progressivo
            - longao
        )

        leve = max(
            4.5,
            arredondar_meio_km(
                leve
            ),
        )

        # Se os mínimos empurraram o volume para cima,
        # reduzimos primeiro o progressivo.
        excesso = (
            leve
            + progressivo
            + intervalado
            + longao
            - volume_alvo
        )

        if excesso > 0:
            progressivo = max(
                5.0,
                arredondar_meio_km(
                    progressivo
                    - excesso
                ),
            )

        sessoes = [
            (
                "Rodagem leve",
                leve,
            ),
            (
                "Progressivo",
                progressivo,
            ),
            (
                "Intervalado",
                intervalado,
            ),
            (
                "Longão",
                longao,
            ),
        ]

    else:
        intervalado = 4.5

        progressivo = min(
            6.0,
            max(
                5.0,
                arredondar_meio_km(
                    volume_alvo
                    * 0.22
                ),
            ),
        )

        recuperacao = 4.0

        restante = (
            volume_alvo
            - intervalado
            - progressivo
            - recuperacao
            - longao
        )

        leve = max(
            4.5,
            arredondar_meio_km(
                restante
            ),
        )

        sessoes = [
            (
                "Rodagem leve",
                leve,
            ),
            (
                "Intervalado",
                intervalado,
            ),
            (
                "Rodagem leve",
                recuperacao,
            ),
            (
                "Progressivo",
                progressivo,
            ),
            (
                "Longão",
                longao,
            ),
        ]

    # Cansaço alto: tira os estímulos fortes.
    if fadiga >= 8:
        sessoes = [
            (
                (
                    "Rodagem leve"
                    if tipo in {
                        "Intervalado",
                        "Progressivo",
                    }
                    else tipo
                ),
                distancia,
            )
            for tipo, distancia
            in sessoes
        ]

    return sessoes


def gerar_plano_coach(
    historico_df,
    hoje_local,
    n_treinos,
    dias_escolhidos,
    intensidade_semana,
    fadiga,
):
    estado = analisar_estado_coach(
        historico_df,
        hoje_local,
    )

    volume_alvo = (
        calcular_volume_alvo(
            estado,
            intensidade_semana,
            fadiga,
        )
    )

    sessoes = construir_sessoes(
        volume_alvo,
        n_treinos,
        estado,
        fadiga,
    )

    # O total real das sessões prevalece sobre o volume-alvo
    # caso os mínimos técnicos do treino exijam pequena diferença.
    volume_real_plano = arredondar_meio_km(
        sum(
            distancia
            for _, distancia
            in sessoes
        )
    )

    pace_ref = estado[
        "pace_ref"
    ]

    # Faixas centradas no estado atual, não no recorde antigo.
    easy_min = max(
        315,
        pace_ref - 5,
    )

    easy_max = min(
        450,
        pace_ref + 25,
    )

    progressivo_inicio = min(
        450,
        pace_ref + 15,
    )

    progressivo_fim = max(
        315,
        pace_ref - 35,
    )

    # Para objetivo sub-25: estímulo curto próximo/levemente
    # abaixo de 5:00/km, sem transformar o treino em teste.
    intervalo_rapido = (
        4 * 60
        + 50
    )

    intervalo_lento = (
        5 * 60
    )

    proxima_segunda = (
        hoje_local
        + timedelta(
            days=(
                7
                - hoje_local.weekday()
            )
        )
    )

    offsets = {
        "Seg": 0,
        "Ter": 1,
        "Qua": 2,
        "Qui": 3,
        "Sex": 4,
        "Sáb": 5,
        "Dom": 6,
    }

    datas = sorted(
        [
            proxima_segunda
            + timedelta(
                days=offsets[
                    dia
                ]
            )
            for dia in dias_escolhidos
        ]
    )

    plano = []

    for (
        data_treino,
        sessao,
    ) in zip(
        datas,
        sessoes,
    ):
        tipo, distancia = (
            sessao
        )

        if tipo == "Rodagem leve":
            pace_alvo = (
                f"{segundos_para_pace(easy_min)}"
                f"–"
                f"{segundos_para_pace(easy_max)}/km"
            )

            descricao = (
                "Corrida confortável, em esforço leve. "
                "Se o pace ficar um pouco mais lento em subida "
                "ou calor, mantenha o esforço e não force o relógio."
            )

        elif tipo == "Progressivo":
            pace_alvo = (
                f"{segundos_para_pace(progressivo_inicio)}"
                f" → "
                f"{segundos_para_pace(progressivo_fim)}/km"
            )

            descricao = (
                "Divida o treino em três blocos semelhantes: "
                "leve no início, ritmo estável no meio e firme no final. "
                "Termine controlado, sem sprint."
            )

        elif tipo == "Intervalado":
            pace_alvo = (
                f"{segundos_para_pace(intervalo_rapido)}"
                f"–"
                f"{segundos_para_pace(intervalo_lento)}/km"
            )

            reps = 6

            if (
                not estado[
                    "modo_retorno"
                ]
                and estado[
                    "treinos_28"
                ] >= 14
                and fadiga <= 4
            ):
                reps = 7

            descricao = (
                f"1 km leve + {reps} × 400 m a "
                f"{segundos_para_pace(intervalo_rapido)}–"
                f"{segundos_para_pace(intervalo_lento)}/km, "
                "com 1 min caminhando ou trotando entre as repetições, "
                "e 1 km leve no final. A distância exibida é aproximada."
            )

        else:  # Longão
            pace_alvo = (
                f"{segundos_para_pace(pace_ref)}"
                f"–"
                f"{segundos_para_pace(min(450, pace_ref + 30))}/km"
            )

            descricao = (
                "Rodagem longa confortável. "
                "O objetivo é ampliar a duração sem acelerar no final. "
                "Termine com sensação de reserva."
            )

        plano.append(
            {
                "data": data_treino,
                "tipo": tipo,
                "distancia": float(
                    distancia
                ),
                "pace_alvo": pace_alvo,
                "descricao": descricao,
            }
        )

    return (
        plano,
        estado,
        volume_real_plano,
    )


def salvar_plano_coach(
    plano,
    planejamento_df,
):
    datas_existentes = set()

    if not planejamento_df.empty:
        datas_existentes = set(
            planejamento_df[
                "data"
            ].astype(str)
        )

    salvos = 0
    pulados = 0

    for treino in plano:
        data_texto = str(
            treino[
                "data"
            ]
        )

        if data_texto in datas_existentes:
            pulados += 1
            continue

        salvar_planejamento(
            treino[
                "data"
            ],
            treino[
                "tipo"
            ],
            treino[
                "distancia"
            ],
            treino[
                "pace_alvo"
            ],
            treino[
                "descricao"
            ],
        )

        salvos += 1

        datas_existentes.add(
            data_texto
        )

    return (
        salvos,
        pulados,
    )



# =========================================================
# COACH IA
# =========================================================

DIAS_OFFSET = {
    "Seg": 0,
    "Ter": 1,
    "Qua": 2,
    "Qui": 3,
    "Sex": 4,
    "Sáb": 5,
    "Dom": 6,
}


def proxima_segunda(hoje_local):
    return hoje_local + timedelta(
        days=(7 - hoje_local.weekday())
    )


def datas_disponiveis_coach(hoje_local, dias_escolhidos):
    inicio = proxima_segunda(hoje_local)
    return sorted(
        [
            inicio + timedelta(days=DIAS_OFFSET[dia])
            for dia in dias_escolhidos
        ]
    )


def resumo_semanal_coach(historico_df, hoje_local, semanas=8):
    df = deduplicar_historico_coach(historico_df)
    inicio_semana_atual = hoje_local - timedelta(days=hoje_local.weekday())
    resultado = []

    for i in range(semanas, 0, -1):
        inicio = inicio_semana_atual - timedelta(days=7 * i)
        fim = inicio + timedelta(days=6)

        if df.empty:
            bloco = pd.DataFrame()
        else:
            bloco = df[
                (df["data_dt"] >= inicio)
                & (df["data_dt"] <= fim)
            ]

        if bloco.empty:
            resultado.append(
                {
                    "inicio": str(inicio),
                    "fim": str(fim),
                    "treinos": 0,
                    "km": 0.0,
                    "maior_corrida_km": 0.0,
                }
            )
            continue

        resultado.append(
            {
                "inicio": str(inicio),
                "fim": str(fim),
                "treinos": int(len(bloco)),
                "km": round(float(bloco["distancia"].sum()), 1),
                "maior_corrida_km": round(float(bloco["distancia"].max()), 1),
            }
        )

    return resultado


def atividades_recentes_coach(historico_df, hoje_local, limite=24):
    if historico_df.empty:
        return []

    df = deduplicar_historico_coach(historico_df)
    df = df[df["data_dt"] >= hoje_local - timedelta(days=56)].copy()
    df = df.sort_values("data_plot", ascending=False).head(limite)

    itens = []

    for _, treino in df.iterrows():
        item = {
            "data": str(treino.get("data", "")),
            "tipo_registrado": str(treino.get("tipo", "Corrida")),
            "distancia_km": round(float(treino.get("distancia", 0) or 0), 2),
            "pace_medio": treino.get("pace") or None,
            "origem": treino.get("origem") or None,
        }

        for origem_coluna, destino in [
            ("duracao_seg", "duracao_seg"),
            ("elevacao_m", "elevacao_m"),
            ("frequencia_cardiaca_media", "fc_media"),
            ("esforco", "rpe"),
        ]:
            valor = treino.get(origem_coluna)
            if valor is not None and not pd.isna(valor):
                try:
                    item[destino] = round(float(valor), 1)
                except Exception:
                    item[destino] = valor

        itens.append(item)

    return itens


def aderencia_recente_coach(planejamento_df, historico_df, hoje_local):
    if planejamento_df.empty:
        return {
            "planejados": 0,
            "concluidos": 0,
            "aderencia_pct": None,
        }

    inicio = hoje_local - timedelta(days=28)
    planos = planejamento_df[
        (planejamento_df["data_dt"] >= inicio)
        & (planejamento_df["data_dt"] <= hoje_local)
    ]

    if planos.empty:
        return {
            "planejados": 0,
            "concluidos": 0,
            "aderencia_pct": None,
        }

    concluidos = 0

    for _, treino in planos.iterrows():
        if realizado_do_planejado(treino, historico_df) is not None:
            concluidos += 1

    return {
        "planejados": int(len(planos)),
        "concluidos": int(concluidos),
        "aderencia_pct": round(100 * concluidos / len(planos)),
    }


def limites_coach_ia(estado, perfil_semana, fadiga, desconforto):
    base = max(float(estado["volume_base"]), 1.0)

    if perfil_semana == "Conservador":
        minimo = base * 0.75
        maximo = min(base * 1.03, base + 2.0)
    elif perfil_semana == "Agressivo":
        minimo = base * 0.90
        maximo = min(base * 1.18, base + 5.0)
    else:
        minimo = base * 0.82
        maximo = min(base * 1.12, base + 4.0)

    if fadiga >= 8:
        maximo = min(maximo, base * 0.82)
        minimo = min(minimo, maximo * 0.85)
    elif fadiga >= 6:
        maximo = min(maximo, base * 0.98)

    if desconforto == "Moderado/forte":
        maximo = min(maximo, base * 0.75)
        minimo = min(minimo, maximo * 0.85)
        max_fortes = 0
    elif desconforto == "Leve":
        max_fortes = 1
    else:
        max_fortes = 2 if fadiga <= 6 else 1

    longao_max = min(
        max(float(estado["maior_corrida_14"]) + 2.0, 6.0),
        maximo * 0.36,
    )

    return {
        "volume_min_km": round(max(8.0, minimo), 1),
        "volume_max_km": round(max(10.0, maximo), 1),
        "longao_max_km": round(max(5.0, longao_max), 1),
        "max_sessoes_fortes": int(max_fortes),
        "min_intervalo_horas_entre_fortes": 48,
    }


def contexto_coach_ia(
    historico_df,
    planejamento_df,
    hoje_local,
    n_treinos,
    dias_escolhidos,
    perfil_semana,
    fadiga,
    desconforto,
    mensagem_coach,
):
    estado = analisar_estado_coach(historico_df, hoje_local)
    datas = datas_disponiveis_coach(hoje_local, dias_escolhidos)
    limites = limites_coach_ia(
        estado,
        perfil_semana,
        fadiga,
        desconforto,
    )

    return {
        "data_atual": str(hoje_local),
        "objetivo": {
            "prova": "5 km",
            "meta": "sub-25:00",
            "pace_meta": "4:59/km ou mais rápido",
            "recorde_pessoal_informado": "24:20",
        },
        "pedido_para_proxima_semana": {
            "numero_de_treinos": int(n_treinos),
            "datas_disponiveis": [str(x) for x in datas],
            "perfil": perfil_semana,
            "fadiga_1a10": int(fadiga),
            "desconforto": desconforto,
            "mensagem_do_corredor": mensagem_coach.strip() or None,
        },
        "estado_calculado": {
            "volume_base_km": round(float(estado["volume_base"]), 1),
            "volume_ultimos_7_km": round(float(estado["volume_ultimos_7"]), 1),
            "volume_ultimos_28_km": round(float(estado["volume_28"]), 1),
            "treinos_ultimos_28": int(estado["treinos_28"]),
            "maior_corrida_14_dias_km": round(float(estado["maior_corrida_14"]), 1),
            "pace_referencia": segundos_para_pace(estado["pace_ref"]),
            "pouco_historico_recente": bool(estado["modo_retorno"]),
        },
        "semanas_anteriores": resumo_semanal_coach(historico_df, hoje_local, 8),
        "atividades_recentes": atividades_recentes_coach(historico_df, hoje_local, 24),
        "aderencia_28_dias": aderencia_recente_coach(
            planejamento_df,
            historico_df,
            hoje_local,
        ),
        "limites_obrigatorios": limites,
    }


def esquema_resposta_coach_ia(datas_permitidas):
    return {
        "type": "object",
        "properties": {
            "leitura_da_fase": {"type": "string"},
            "estrategia_da_semana": {"type": "string"},
            "volume_semana_km": {"type": "number"},
            "alerta": {"type": "string"},
            "treinos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "string",
                            "enum": datas_permitidas,
                        },
                        "tipo": {
                            "type": "string",
                            "enum": [
                                "Rodagem leve",
                                "Recuperação",
                                "Progressivo",
                                "Intervalado",
                                "Tempo Run",
                                "Longão",
                                "Teste 5 km",
                            ],
                        },
                        "distancia_km": {"type": "number"},
                        "pace_alvo": {"type": "string"},
                        "estrutura": {"type": "string"},
                        "intensidade": {
                            "type": "string",
                            "enum": ["leve", "moderada", "forte"],
                        },
                        "objetivo": {"type": "string"},
                        "justificativa": {"type": "string"},
                    },
                    "required": [
                        "data",
                        "tipo",
                        "distancia_km",
                        "pace_alvo",
                        "estrutura",
                        "intensidade",
                        "objetivo",
                        "justificativa",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "leitura_da_fase",
            "estrategia_da_semana",
            "volume_semana_km",
            "alerta",
            "treinos",
        ],
        "additionalProperties": False,
    }


def extrair_texto_responses_api(payload_resposta):
    for item in payload_resposta.get("output", []):
        if item.get("type") != "message":
            continue

        for conteudo in item.get("content", []):
            if conteudo.get("type") == "output_text":
                return conteudo.get("text", "")

            if conteudo.get("type") == "refusal":
                raise RuntimeError(
                    conteudo.get("refusal")
                    or "A IA recusou gerar o plano."
                )

    raise RuntimeError("A API não retornou um plano em texto estruturado.")


def chamar_openai_coach(contexto):
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "A chave da OpenAI ainda não foi configurada nos Secrets."
        )

    datas_permitidas = contexto["pedido_para_proxima_semana"]["datas_disponiveis"]
    schema = esquema_resposta_coach_ia(datas_permitidas)

    instrucoes = """
Você é o motor de planejamento de um aplicativo pessoal de corrida.
Sua função é criar UMA semana de treino coerente com os dados fornecidos.

Princípios obrigatórios:
- Use o histórico real como contexto. Não trate recorde pessoal antigo como condicionamento atual.
- Priorize consistência e especificidade para 5 km, não volume por volume.
- Diferencie pace médio de uma atividade de pace das repetições de um intervalado.
- Não invente dados ausentes (FC, RPE, lesões, provas recentes).
- Respeite exatamente as datas disponíveis e o número de treinos solicitado.
- Respeite todos os limites obrigatórios recebidos no JSON.
- No máximo o número permitido de sessões fortes.
- Sessões fortes devem ficar separadas por pelo menos 48 horas.
- O longão não pode ultrapassar longao_max_km.
- O volume semanal deve ficar entre volume_min_km e volume_max_km.
- A distância mostrada para intervalados deve representar aproximadamente o total corrido, incluindo aquecimento e desaquecimento.
- Pace de rodagem leve deve ser confortável. Não force pace apenas para cumprir número.
- Para meta sub-25, use trabalho específico de forma progressiva, sem transformar toda semana em teste.
- Se fadiga estiver alta ou houver desconforto moderado/forte, reduza ou remova intensidade.
- Não diagnostique nem trate condições médicas. Se houver desconforto relevante, use o campo alerta para recomendar cautela.
- Explique de modo breve por que a semana faz sentido à luz do histórico.
- Responda somente no schema estruturado solicitado.
""".strip()

    resposta = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "reasoning": {"effort": "medium"},
            "instructions": instrucoes,
            "input": json.dumps(contexto, ensure_ascii=False),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "running_coach_week",
                    "schema": schema,
                    "strict": True,
                }
            },
        },
        timeout=75,
    )

    if not resposta.ok:
        detalhe = resposta.text[:800]
        raise RuntimeError(
            f"OpenAI API respondeu {resposta.status_code}: {detalhe}"
        )

    texto = extrair_texto_responses_api(resposta.json())
    return json.loads(texto)


def validar_plano_coach_ia(plano, contexto):
    erros = []
    pedido = contexto["pedido_para_proxima_semana"]
    limites = contexto["limites_obrigatorios"]
    datas_permitidas = set(pedido["datas_disponiveis"])
    treinos = plano.get("treinos", [])

    if len(treinos) != pedido["numero_de_treinos"]:
        erros.append(
            f"Quantidade de treinos: esperado {pedido['numero_de_treinos']}, recebido {len(treinos)}."
        )

    datas = [str(t.get("data", "")) for t in treinos]

    if len(set(datas)) != len(datas):
        erros.append("Há dois treinos na mesma data.")

    if any(data not in datas_permitidas for data in datas):
        erros.append("O plano usou uma data não autorizada.")

    try:
        volume = sum(float(t.get("distancia_km", 0)) for t in treinos)
    except Exception:
        volume = -1

    if volume < limites["volume_min_km"] - 0.6:
        erros.append(
            f"Volume {volume:.1f} km abaixo do mínimo {limites['volume_min_km']:.1f} km."
        )

    if volume > limites["volume_max_km"] + 0.6:
        erros.append(
            f"Volume {volume:.1f} km acima do máximo {limites['volume_max_km']:.1f} km."
        )

    fortes = [t for t in treinos if t.get("intensidade") == "forte"]

    if len(fortes) > limites["max_sessoes_fortes"]:
        erros.append(
            f"Há {len(fortes)} sessões fortes; o máximo é {limites['max_sessoes_fortes']}."
        )

    longoes = [t for t in treinos if t.get("tipo") == "Longão"]
    for t in longoes:
        if float(t.get("distancia_km", 0)) > limites["longao_max_km"] + 0.1:
            erros.append(
                f"Longão de {float(t.get('distancia_km', 0)):.1f} km excede o limite de {limites['longao_max_km']:.1f} km."
            )

    fortes_ordenados = sorted(
        fortes,
        key=lambda x: x.get("data", ""),
    )

    for anterior, atual in zip(fortes_ordenados, fortes_ordenados[1:]):
        try:
            d1 = pd.to_datetime(anterior["data"]).date()
            d2 = pd.to_datetime(atual["data"]).date()
            if (d2 - d1).days < 2:
                erros.append("Duas sessões fortes ficaram com menos de 48 h de intervalo.")
        except Exception:
            erros.append("Não foi possível validar as datas das sessões fortes.")

    return erros


def plano_ia_para_planejamento(plano_ia):
    saida = []

    for treino in plano_ia.get("treinos", []):
        descricao = (
            f"{treino['estrutura']} | Objetivo: {treino['objetivo']} | "
            f"Por quê: {treino['justificativa']}"
        )

        saida.append(
            {
                "data": pd.to_datetime(treino["data"]).date(),
                "tipo": treino["tipo"],
                "distancia": float(treino["distancia_km"]),
                "pace_alvo": treino["pace_alvo"],
                "descricao": descricao,
                "intensidade": treino["intensidade"],
                "objetivo": treino["objetivo"],
                "justificativa": treino["justificativa"],
                "estrutura": treino["estrutura"],
            }
        )

    return saida


def gerar_plano_com_ia(contexto):
    plano = chamar_openai_coach(contexto)
    erros = validar_plano_coach_ia(plano, contexto)

    if erros:
        raise RuntimeError(
            "A proposta da IA foi bloqueada pelo validador: "
            + " ".join(erros)
        )

    return plano


# =========================================================
# CALLBACK STRAVA
# =========================================================

query = st.query_params

if query.get("error") == "access_denied":
    st.error(
        "A autorização do Strava foi cancelada."
    )
    st.query_params.clear()

elif query.get("code"):
    codigo = query.get("code")
    state_recebido = query.get(
        "state",
        "",
    )

    if not hmac.compare_digest(
        str(state_recebido),
        oauth_state(),
    ):
        st.error(
            "Falha na validação da conexão com o Strava."
        )
    else:
        try:
            token_data = trocar_codigo_por_token(
                codigo
            )

            salvar_strava_auth(
                token_data
            )

            st.query_params.clear()

            st.session_state[
                "mensagem"
            ] = (
                "Strava conectado com sucesso."
            )

            st.rerun()

        except Exception as erro:
            st.error(
                "Não foi possível conectar ao Strava: "
                f"{erro}"
            )


# =========================================================
# DATAS / CONSTANTES
# =========================================================

FUSO = ZoneInfo(
    "America/Sao_Paulo"
)

hoje = datetime.now(
    FUSO
).date()

inicio_semana = hoje - timedelta(
    days=hoje.weekday()
)

fim_semana = inicio_semana + timedelta(
    days=6
)

dias_completos = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo",
}

dias_curtos = {
    0: "SEG",
    1: "TER",
    2: "QUA",
    3: "QUI",
    4: "SEX",
    5: "SÁB",
    6: "DOM",
}

tipos_treino = [
    "Rodagem leve",
    "Progressivo",
    "Intervalado",
    "Longão",
    "Tempo Run",
    "Teste 5 km",
    "Outro",
]

META_5K_SEG = 25 * 60
RECORDE_5K_SEG = 24 * 60 + 20
PACE_RECORDE_5K = (
    RECORDE_5K_SEG / 5
)


# =========================================================
# CARREGAMENTO
# =========================================================

try:
    planejamento = carregar_planejamento()
    historico = carregar_historico()

except Exception as erro:
    st.error(
        "Não foi possível acessar o Supabase. "
        f"Detalhe: {erro}"
    )
    st.stop()


if not planejamento.empty:
    semana_planejada = planejamento[
        (
            planejamento["data_dt"]
            >= inicio_semana
        )
        &
        (
            planejamento["data_dt"]
            <= fim_semana
        )
    ].copy()

else:
    semana_planejada = pd.DataFrame()


if not historico.empty:
    semana_realizada = historico[
        (
            historico["data_dt"]
            >= inicio_semana
        )
        &
        (
            historico["data_dt"]
            <= fim_semana
        )
    ].copy()

else:
    semana_realizada = pd.DataFrame()


# =========================================================
# CABEÇALHO
# =========================================================

mostrar_marca(
    "Treino, evolução e consistência. 🇭🇺"
)

mensagem = st.session_state.pop(
    "mensagem",
    None,
)

if mensagem:
    st.success(
        mensagem
    )


# =========================================================
# STRAVA
# =========================================================

with st.container(border=True):
    try:
        auth_strava = carregar_strava_auth()

    except Exception as erro:
        auth_strava = None
        st.error(
            f"Erro ao verificar Strava: {erro}"
        )

    if auth_strava:
        c1, c2 = st.columns(
            [2, 1]
        )

        c1.markdown(
            "### Strava conectado"
        )

        c1.caption(
            "Importe novas corridas e marque "
            "treinos planejados automaticamente."
        )

        if c2.button(
            "Sincronizar",
            width="stretch",
        ):
            try:
                importadas, ignoradas = (
                    importar_atividades_strava()
                )

                st.session_state[
                    "mensagem"
                ] = (
                    f"Sincronização concluída: "
                    f"{importadas} nova(s) corrida(s) "
                    f"importada(s)."
                )

                st.rerun()

            except Exception as erro:
                st.error(
                    "Erro ao sincronizar Strava: "
                    f"{erro}"
                )

    else:
        st.markdown(
            "### Conectar Strava"
        )

        st.caption(
            "Autorize o Running a ler suas atividades."
        )

        st.link_button(
            "Conectar com Strava",
            strava_authorize_url(),
            width="stretch",
        )


# =========================================================
# ABAS
# =========================================================

(
    hoje_tab,
    semana_tab,
    planejar_tab,
    historico_tab,
    evolucao_tab,
    coach_tab,
) = st.tabs(
    [
        "Hoje",
        "Semana",
        "Planejar",
        "Histórico",
        "Evolução",
        "Coach",
    ]
)


# =========================================================
# HOJE
# =========================================================

with hoje_tab:
    st.write("")

    with st.container(border=True):
        st.caption(
            dias_completos[
                hoje.weekday()
            ].upper()
        )

        st.markdown(
            f"# {hoje.strftime('%d/%m')}"
        )

        if not semana_planejada.empty:
            treino_hoje_df = (
                semana_planejada[
                    semana_planejada[
                        "data_dt"
                    ]
                    == hoje
                ]
            )

        else:
            treino_hoje_df = pd.DataFrame()

        if treino_hoje_df.empty:
            st.write(
                "Dia sem treino planejado."
            )

        else:
            pendentes = 0

            for _, treino in (
                treino_hoje_df.iterrows()
            ):
                realizado = (
                    realizado_do_planejado(
                        treino,
                        historico,
                    )
                )

                if realizado is None:
                    pendentes += 1

            if pendentes == 0:
                st.success(
                    "Treino de hoje concluído."
                )

            else:
                st.write(
                    "Você tem treino planejado para hoje."
                )

    st.write("")
    st.subheader(
        "Treino de hoje"
    )

    if treino_hoje_df.empty:
        st.info(
            "Hoje não há treino planejado."
        )

    else:
        for _, treino in (
            treino_hoje_df.iterrows()
        ):
            realizado = (
                realizado_do_planejado(
                    treino,
                    historico,
                )
            )

            with st.container(
                border=True
            ):
                topo1, topo2 = (
                    st.columns([3, 1])
                )

                topo1.markdown(
                    f"### {treino['tipo']}"
                )

                topo2.write(
                    "✅ Feito"
                    if realizado is not None
                    else "○ Pendente"
                )

                c1, c2 = st.columns(2)

                c1.metric(
                    "Planejado",
                    (
                        f"{treino['distancia']:.1f} km"
                        if treino[
                            "distancia"
                        ] > 0
                        else "-"
                    ),
                )

                c2.metric(
                    "Pace alvo",
                    (
                        treino[
                            "pace_alvo"
                        ]
                        if treino[
                            "pace_alvo"
                        ]
                        else "-"
                    ),
                )

                if treino[
                    "descricao"
                ]:
                    st.caption(
                        treino[
                            "descricao"
                        ]
                    )

                if realizado is not None:
                    st.divider()

                    r1, r2, r3 = (
                        st.columns(3)
                    )

                    r1.metric(
                        "Realizado",
                        f"{realizado['distancia']:.1f} km",
                    )

                    r2.metric(
                        "Pace real",
                        (
                            realizado[
                                "pace"
                            ]
                            if realizado[
                                "pace"
                            ]
                            else "-"
                        ),
                    )

                    r3.metric(
                        "Origem",
                        (
                            "Strava"
                            if realizado.get(
                                "origem"
                            )
                            == "strava"
                            else "Manual"
                        ),
                    )

                else:
                    with st.expander(
                        "Concluir manualmente"
                    ):
                        with st.form(
                            f"concluir_{int(treino['id'])}"
                        ):
                            distancia_real = (
                                st.number_input(
                                    "Distância realizada (km)",
                                    min_value=0.0,
                                    value=float(
                                        treino[
                                            "distancia"
                                        ]
                                    ),
                                    step=0.1,
                                    key=(
                                        f"dist_real_"
                                        f"{int(treino['id'])}"
                                    ),
                                )
                            )

                            pace_real = (
                                st.text_input(
                                    "Pace médio",
                                    placeholder="Ex.: 6:15",
                                    key=(
                                        f"pace_real_"
                                        f"{int(treino['id'])}"
                                    ),
                                )
                            )

                            esforco_real = (
                                st.slider(
                                    "Esforço percebido",
                                    min_value=1,
                                    max_value=10,
                                    value=5,
                                    key=(
                                        f"esf_real_"
                                        f"{int(treino['id'])}"
                                    ),
                                )
                            )

                            obs_real = (
                                st.text_area(
                                    "Observações",
                                    key=(
                                        f"obs_real_"
                                        f"{int(treino['id'])}"
                                    ),
                                )
                            )

                            concluir = (
                                st.form_submit_button(
                                    "Salvar como concluído",
                                    width="stretch",
                                )
                            )

                            if concluir:
                                if (
                                    distancia_real
                                    <= 0
                                ):
                                    st.warning(
                                        "Informe a distância."
                                    )

                                elif (
                                    pace_real
                                    and pace_para_segundos(
                                        pace_real
                                    )
                                    is None
                                ):
                                    st.warning(
                                        "Use o formato min:seg. Ex.: 6:15"
                                    )

                                else:
                                    salvar_treino(
                                        treino[
                                            "data"
                                        ],
                                        treino[
                                            "tipo"
                                        ],
                                        distancia_real,
                                        pace_real,
                                        esforco_real,
                                        obs_real,
                                        int(
                                            treino[
                                                "id"
                                            ]
                                        ),
                                    )

                                    st.rerun()

    st.write("")

    with st.expander(
        "Registrar treino extra"
    ):
        with st.form(
            "treino_extra"
        ):
            data_extra = st.date_input(
                "Data",
                value=hoje,
            )

            tipo_extra = st.selectbox(
                "Tipo",
                tipos_treino,
                key="tipo_extra",
            )

            distancia_extra = (
                st.number_input(
                    "Distância (km)",
                    min_value=0.0,
                    step=0.1,
                    key="dist_extra",
                )
            )

            pace_extra = (
                st.text_input(
                    "Pace médio",
                    placeholder="Ex.: 6:15",
                    key="pace_extra",
                )
            )

            esforco_extra = (
                st.slider(
                    "Esforço",
                    1,
                    10,
                    5,
                    key="esforco_extra",
                )
            )

            obs_extra = (
                st.text_area(
                    "Observações",
                    key="obs_extra",
                )
            )

            salvar_extra = (
                st.form_submit_button(
                    "Salvar treino extra",
                    width="stretch",
                )
            )

            if salvar_extra:
                if distancia_extra <= 0:
                    st.warning(
                        "Informe a distância."
                    )

                elif (
                    pace_extra
                    and pace_para_segundos(
                        pace_extra
                    )
                    is None
                ):
                    st.warning(
                        "Use o formato min:seg. Ex.: 6:15"
                    )

                else:
                    salvar_treino(
                        data_extra,
                        tipo_extra,
                        distancia_extra,
                        pace_extra,
                        esforco_extra,
                        obs_extra,
                    )

                    st.rerun()


# =========================================================
# SEMANA
# =========================================================

with semana_tab:
    st.subheader(
        "Sua semana"
    )

    st.caption(
        f"{inicio_semana.strftime('%d/%m')} "
        f"até "
        f"{fim_semana.strftime('%d/%m')}"
    )

    total_planejados = len(
        semana_planejada
    )

    concluidos = 0

    if not semana_planejada.empty:
        for _, treino in (
            semana_planejada.iterrows()
        ):
            if (
                realizado_do_planejado(
                    treino,
                    historico,
                )
                is not None
            ):
                concluidos += 1

    km_planejados = (
        semana_planejada[
            "distancia"
        ].sum()
        if not semana_planejada.empty
        else 0
    )

    km_realizados = (
        semana_realizada[
            "distancia"
        ].sum()
        if not semana_realizada.empty
        else 0
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Concluídos",
        f"{concluidos}/{total_planejados}",
    )

    c2.metric(
        "Planejado",
        f"{km_planejados:.1f} km",
    )

    c3.metric(
        "Realizado",
        f"{km_realizados:.1f} km",
    )

    if total_planejados > 0:
        progresso = (
            concluidos
            / total_planejados
        )

        st.progress(
            progresso
        )

        st.caption(
            f"{progresso * 100:.0f}% "
            "dos treinos concluídos"
        )

    st.write("")

    if semana_planejada.empty:
        st.info(
            "Nenhum treino planejado nesta semana."
        )

    else:
        for _, treino in (
            semana_planejada.iterrows()
        ):
            data_treino = treino[
                "data_dt"
            ]

            realizado = (
                realizado_do_planejado(
                    treino,
                    historico,
                )
            )

            with st.container(
                border=True
            ):
                topo1, topo2 = (
                    st.columns([3, 1])
                )

                topo1.caption(
                    f"{dias_curtos[data_treino.weekday()]} "
                    f"· "
                    f"{data_treino.strftime('%d/%m')}"
                )

                topo1.markdown(
                    f"### {treino['tipo']}"
                )

                topo2.write(
                    "✅ Feito"
                    if realizado is not None
                    else "○ Pendente"
                )

                p1, p2 = (
                    st.columns(2)
                )

                p1.metric(
                    "Planejado",
                    (
                        f"{treino['distancia']:.1f} km"
                        if treino[
                            "distancia"
                        ] > 0
                        else "-"
                    ),
                )

                p2.metric(
                    "Pace alvo",
                    (
                        treino[
                            "pace_alvo"
                        ]
                        if treino[
                            "pace_alvo"
                        ]
                        else "-"
                    ),
                )

                if realizado is not None:
                    st.divider()

                    r1, r2, r3 = (
                        st.columns(3)
                    )

                    r1.metric(
                        "Real",
                        f"{realizado['distancia']:.1f} km",
                    )

                    r2.metric(
                        "Pace",
                        (
                            realizado[
                                "pace"
                            ]
                            if realizado[
                                "pace"
                            ]
                            else "-"
                        ),
                    )

                    r3.metric(
                        "Origem",
                        (
                            "Strava"
                            if realizado.get(
                                "origem"
                            )
                            == "strava"
                            else "Manual"
                        ),
                    )


# =========================================================
# PLANEJAR
# =========================================================

with planejar_tab:
    st.subheader(
        "Novo treino"
    )

    with st.form(
        "planejamento_form",
        clear_on_submit=True,
    ):
        data_planejada = (
            st.date_input(
                "Data",
                value=hoje,
            )
        )

        tipo_planejado = (
            st.selectbox(
                "Tipo",
                tipos_treino,
                key="tipo_planejado",
            )
        )

        distancia_planejada = (
            st.number_input(
                "Distância prevista (km)",
                min_value=0.0,
                step=0.1,
            )
        )

        pace_planejado = (
            st.text_input(
                "Pace alvo",
                placeholder=(
                    "Ex.: 6:20, 4:55 ou Livre"
                ),
            )
        )

        descricao_planejada = (
            st.text_area(
                "Orientações",
                placeholder=(
                    "Ex.: 1 km leve + 6 x 400 m "
                    "+ 1 km leve."
                ),
            )
        )

        adicionar = (
            st.form_submit_button(
                "Adicionar treino",
                width="stretch",
            )
        )

        if adicionar:
            salvar_planejamento(
                data_planejada,
                tipo_planejado,
                distancia_planejada,
                pace_planejado,
                descricao_planejada,
            )

            st.rerun()

    st.divider()

    st.subheader(
        "Próximos treinos"
    )

    futuros = (
        planejamento[
            planejamento[
                "data_dt"
            ]
            >= hoje
        ]
        if not planejamento.empty
        else pd.DataFrame()
    )

    if futuros.empty:
        st.info(
            "Nenhum treino futuro."
        )

    else:
        for _, treino in (
            futuros.iterrows()
        ):
            realizado = (
                realizado_do_planejado(
                    treino,
                    historico,
                )
            )

            with st.container(
                border=True
            ):
                st.caption(
                    treino[
                        "data_dt"
                    ].strftime(
                        "%d/%m/%Y"
                    )
                )

                st.markdown(
                    f"### {treino['tipo']}"
                )

                st.write(
                    (
                        f"📏 {treino['distancia']:.1f} km"
                        if treino[
                            "distancia"
                        ] > 0
                        else "📏 Distância livre"
                    )
                )

                if treino[
                    "pace_alvo"
                ]:
                    st.write(
                        f"🎯 {treino['pace_alvo']}"
                    )

                if treino[
                    "descricao"
                ]:
                    st.caption(
                        treino[
                            "descricao"
                        ]
                    )

                if realizado is None:
                    if st.button(
                        "Excluir",
                        key=(
                            f"excluir_plan_"
                            f"{int(treino['id'])}"
                        ),
                        width="stretch",
                    ):
                        excluir_planejamento(
                            treino["id"]
                        )

                        st.rerun()

                else:
                    st.success(
                        "Treino concluído."
                    )


# =========================================================
# HISTÓRICO
# =========================================================

with historico_tab:
    st.subheader(
        "Histórico"
    )

    if historico.empty:
        st.info(
            "Nenhum treino registrado."
        )

    else:
        for _, treino in (
            historico.iterrows()
        ):
            with st.container(
                border=True
            ):
                c1, c2 = (
                    st.columns([4, 1])
                )

                c1.caption(
                    treino[
                        "data_dt"
                    ].strftime(
                        "%d/%m/%Y"
                    )
                )

                c1.markdown(
                    f"### {treino['tipo']}"
                )

                if c2.button(
                    "🗑️",
                    key=(
                        f"del_real_"
                        f"{int(treino['id'])}"
                    ),
                    help="Excluir treino",
                ):
                    excluir_treino(
                        treino["id"]
                    )

                    st.rerun()

                m1, m2, m3 = (
                    st.columns(3)
                )

                m1.metric(
                    "Distância",
                    f"{treino['distancia']:.1f} km",
                )

                m2.metric(
                    "Pace",
                    (
                        treino["pace"]
                        if treino.get(
                            "pace"
                        )
                        else "-"
                    ),
                )

                m3.metric(
                    "Origem",
                    (
                        "Strava"
                        if treino.get(
                            "origem"
                        )
                        == "strava"
                        else "Manual"
                    ),
                )

                detalhes = []

                duracao = treino.get(
                    "duracao_seg"
                )

                elevacao = treino.get(
                    "elevacao_m"
                )

                fc_media = treino.get(
                    "frequencia_cardiaca_media"
                )

                if (
                    duracao is not None
                    and not pd.isna(
                        duracao
                    )
                ):
                    detalhes.append(
                        "Tempo: "
                        + segundos_para_tempo(
                            duracao
                        )
                    )

                if (
                    elevacao is not None
                    and not pd.isna(
                        elevacao
                    )
                ):
                    detalhes.append(
                        f"Elevação: "
                        f"{float(elevacao):.0f} m"
                    )

                if (
                    fc_media is not None
                    and not pd.isna(
                        fc_media
                    )
                ):
                    detalhes.append(
                        f"FC média: "
                        f"{float(fc_media):.0f} bpm"
                    )

                if detalhes:
                    st.caption(
                        " · ".join(
                            detalhes
                        )
                    )

                if treino.get(
                    "observacao"
                ):
                    st.caption(
                        treino[
                            "observacao"
                        ]
                    )


# =========================================================
# EVOLUÇÃO
# =========================================================

with evolucao_tab:
    st.subheader(
        "Meta 5 km"
    )

    meta1, meta2, meta3 = (
        st.columns(3)
    )

    meta1.metric(
        "Objetivo",
        "< 25:00",
    )

    meta2.metric(
        "Pace-alvo",
        "< 5:00/km",
    )

    meta3.metric(
        "Recorde",
        "24:20",
    )

    st.caption(
        "Seu recorde equivale a aproximadamente "
        f"{segundos_para_pace(PACE_RECORDE_5K)}/km."
    )

    st.divider()

    if historico.empty:
        st.info(
            "Registre ou sincronize treinos "
            "para acompanhar sua evolução."
        )

    else:
        total_km = historico[
            "distancia"
        ].sum()

        quantidade = len(
            historico
        )

        e1, e2 = (
            st.columns(2)
        )

        e1.metric(
            "Treinos",
            quantidade,
        )

        e2.metric(
            "Km acumulados",
            f"{total_km:.1f}",
        )

        grafico_pace = (
            historico.copy()
        )

        grafico_pace[
            "data_plot"
        ] = pd.to_datetime(
            grafico_pace[
                "data"
            ]
        )

        grafico_pace[
            "pace_segundos"
        ] = grafico_pace[
            "pace"
        ].apply(
            pace_para_segundos
        )

        grafico_pace = (
            grafico_pace.dropna(
                subset=[
                    "pace_segundos"
                ]
            )
            .sort_values(
                "data_plot"
            )
        )

        if not grafico_pace.empty:
            st.write("")

            st.subheader(
                "Pace por treino"
            )

            fig = go.Figure()

            fig.add_trace(
                go.Scatter(
                    x=grafico_pace[
                        "data_plot"
                    ],
                    y=grafico_pace[
                        "pace_segundos"
                    ],
                    mode="lines+markers",
                    customdata=(
                        grafico_pace[
                            [
                                "tipo",
                                "distancia",
                                "pace",
                            ]
                        ]
                    ),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b>"
                        "<br>%{customdata[1]:.1f} km"
                        "<br>%{customdata[2]}/km"
                        "<extra></extra>"
                    ),
                )
            )

            min_pace = int(
                grafico_pace[
                    "pace_segundos"
                ].min()
            )

            max_pace = int(
                grafico_pace[
                    "pace_segundos"
                ].max()
            )

            inicio = max(
                0,
                (
                    (min_pace - 30)
                    // 15
                )
                * 15,
            )

            fim = (
                (
                    max_pace
                    + 30
                    + 14
                )
                // 15
            ) * 15

            ticks = list(
                range(
                    inicio,
                    fim + 15,
                    15,
                )
            )

            fig.update_layout(
                height=350,
                margin=dict(
                    l=10,
                    r=10,
                    t=20,
                    b=10,
                ),
                xaxis_title=None,
                yaxis_title="Pace",
                hovermode="x unified",
            )

            fig.update_yaxes(
                autorange="reversed",
                tickmode="array",
                tickvals=ticks,
                ticktext=[
                    segundos_para_pace(
                        x
                    )
                    for x in ticks
                ],
            )

            st.plotly_chart(
                fig,
                width="stretch",
            )

        st.divider()

        st.subheader(
            "Volume semanal"
        )

        volume = (
            historico.copy()
        )

        volume[
            "data_plot"
        ] = pd.to_datetime(
            volume[
                "data"
            ]
        )

        volume[
            "semana"
        ] = (
            volume[
                "data_plot"
            ]
            - pd.to_timedelta(
                volume[
                    "data_plot"
                ].dt.weekday,
                unit="D",
            )
        )

        volume_semanal = (
            volume.groupby(
                "semana",
                as_index=False,
            )[
                "distancia"
            ]
            .sum()
            .sort_values(
                "semana"
            )
        )

        st.bar_chart(
            volume_semanal.set_index(
                "semana"
            )[
                "distancia"
            ],
            width="stretch",
        )

        testes = (
            grafico_pace[
                grafico_pace[
                    "tipo"
                ]
                == "Teste 5 km"
            ].copy()
        )

        if not testes.empty:
            testes[
                "tempo_5k"
            ] = (
                testes[
                    "pace_segundos"
                ]
                * 5
            )

            melhor = testes.loc[
                testes[
                    "tempo_5k"
                ].idxmin()
            ]

            melhor_tempo = (
                melhor[
                    "tempo_5k"
                ]
            )

            st.divider()

            st.subheader(
                "Teste de 5 km"
            )

            t1, t2 = (
                st.columns(2)
            )

            t1.metric(
                "Melhor teste",
                segundos_para_tempo(
                    melhor_tempo
                ),
            )

            diferenca = (
                melhor_tempo
                - META_5K_SEG
            )

            if diferenca > 0:
                t2.metric(
                    "Faltam",
                    f"{int(round(diferenca))} s",
                )

            else:
                t2.metric(
                    "Meta",
                    "Sub-25 ✅",
                )


# =========================================================
# COACH
# =========================================================

with coach_tab:
    st.subheader("Coach IA")

    st.caption(
        "O Coach cruza seu histórico sincronizado, carga recente, disponibilidade "
        "e check-in. A IA propõe a semana; um validador independente bloqueia "
        "planos fora dos limites definidos pelo app."
    )

    estado_coach = analisar_estado_coach(
        historico,
        hoje,
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Base recente",
        f"{estado_coach['volume_base']:.1f} km",
    )

    c2.metric(
        "Últimos 28 dias",
        f"{estado_coach['volume_28']:.1f} km",
    )

    c3.metric(
        "Pace referência",
        f"{segundos_para_pace(estado_coach['pace_ref'])}/km",
    )

    if not OPENAI_API_KEY:
        st.warning(
            "A IA ainda não está conectada. Adicione a seção [openai] nos "
            "Secrets do Streamlit para ativar o botão de geração."
        )

        st.code(
            '[openai]\napi_key = "SUA_CHAVE_AQUI"\nmodel = "gpt-5.6-terra"',
            language="toml",
        )

        st.caption(
            "A chave deve ficar somente nos Secrets do Streamlit; não coloque "
            "a chave no GitHub nem envie no chat."
        )

    st.write("")

    with st.form("coach_ia_form"):
        n_treinos = st.select_slider(
            "Quantos dias você pode correr na próxima semana?",
            options=[3, 4, 5],
            value=4,
        )

        perfil_semana = st.radio(
            "Perfil da semana",
            [
                "Conservador",
                "Equilibrado",
                "Agressivo",
            ],
            horizontal=True,
            index=1,
            help=(
                "Isso orienta a IA, mas não multiplica o volume de forma cega. "
                "O histórico continua sendo o principal sinal."
            ),
        )

        fadiga = st.slider(
            "Cansaço geral hoje",
            min_value=1,
            max_value=10,
            value=4,
            help="1 = muito descansado; 10 = muito cansado.",
        )

        desconforto = st.radio(
            "Dor ou desconforto para correr hoje",
            [
                "Nenhum",
                "Leve",
                "Moderado/forte",
            ],
            horizontal=True,
            index=0,
        )

        opcoes_dias = [
            "Seg",
            "Ter",
            "Qua",
            "Qui",
            "Sex",
            "Sáb",
            "Dom",
        ]

        defaults = {
            3: ["Ter", "Qui", "Dom"],
            4: ["Seg", "Qua", "Sex", "Dom"],
            5: ["Seg", "Ter", "Qui", "Sáb", "Dom"],
        }

        dias_escolhidos = st.multiselect(
            "Dias disponíveis",
            options=opcoes_dias,
            default=defaults[n_treinos],
        )

        mensagem_coach = st.text_area(
            "Recado para o Coach (opcional)",
            placeholder=(
                "Ex.: domingo quero correr com amigos; quarta tenho pouco tempo; "
                "prefiro não fazer tiros na sexta."
            ),
        )

        gerar_ia = st.form_submit_button(
            "✨ Gerar semana com IA",
            type="primary",
            width="stretch",
            disabled=not bool(OPENAI_API_KEY),
        )

        if gerar_ia:
            if len(dias_escolhidos) != n_treinos:
                st.warning(
                    f"Escolha exatamente {n_treinos} dias."
                )
            else:
                contexto = contexto_coach_ia(
                    historico,
                    planejamento,
                    hoje,
                    n_treinos,
                    dias_escolhidos,
                    perfil_semana,
                    fadiga,
                    desconforto,
                    mensagem_coach,
                )

                try:
                    with st.spinner(
                        "Analisando seu histórico e montando a semana..."
                    ):
                        plano_ia = gerar_plano_com_ia(contexto)

                    st.session_state["coach_ia_resultado"] = plano_ia
                    st.session_state["coach_ia_contexto"] = contexto
                    st.session_state["plano_coach"] = plano_ia_para_planejamento(plano_ia)
                    st.rerun()

                except Exception as erro:
                    st.error(
                        "O Coach não conseguiu gerar um plano válido. "
                        f"Detalhe: {erro}"
                    )

    resultado_ia = st.session_state.get("coach_ia_resultado")
    plano_coach = st.session_state.get("plano_coach")
    contexto_ia = st.session_state.get("coach_ia_contexto")

    if resultado_ia and plano_coach:
        st.divider()
        st.subheader("Próxima semana sugerida")

        st.markdown(
            f"**Leitura da sua fase:** {resultado_ia['leitura_da_fase']}"
        )
        st.markdown(
            f"**Estratégia:** {resultado_ia['estrategia_da_semana']}"
        )

        total_calculado = sum(
            treino["distancia"]
            for treino in plano_coach
        )

        m1, m2 = st.columns(2)
        m1.metric("Volume sugerido", f"{total_calculado:.1f} km")

        if contexto_ia:
            limites = contexto_ia["limites_obrigatorios"]
            m2.metric(
                "Faixa validada",
                f"{limites['volume_min_km']:.1f}–{limites['volume_max_km']:.1f} km",
            )

        if resultado_ia.get("alerta"):
            st.info(resultado_ia["alerta"])

        for treino in plano_coach:
            with st.container(border=True):
                st.caption(
                    f"{dias_completos[treino['data'].weekday()]} · "
                    f"{treino['data'].strftime('%d/%m')} · "
                    f"{treino['intensidade'].upper()}"
                )

                st.markdown(f"### {treino['tipo']}")

                a1, a2 = st.columns(2)
                a1.metric(
                    "Distância",
                    f"{treino['distancia']:.1f} km",
                )
                a2.metric(
                    "Pace / referência",
                    treino["pace_alvo"],
                )

                st.write(treino["estrutura"])
                st.caption(
                    f"Objetivo: {treino['objetivo']}"
                )
                st.caption(
                    f"Por que entrou: {treino['justificativa']}"
                )

        st.write("")

        if st.button(
            "Aceitar e salvar plano",
            type="primary",
            width="stretch",
        ):
            try:
                salvos, pulados = salvar_plano_coach(
                    plano_coach,
                    planejamento,
                )

                for chave in [
                    "plano_coach",
                    "coach_ia_resultado",
                    "coach_ia_contexto",
                ]:
                    st.session_state.pop(chave, None)

                texto = f"{salvos} treino(s) salvo(s) na próxima semana."

                if pulados:
                    texto += (
                        f" {pulados} data(s) já tinham treino e foram preservadas."
                    )

                st.session_state["mensagem"] = texto
                st.rerun()

            except Exception as erro:
                st.error(
                    "Não foi possível salvar o plano: "
                    f"{erro}"
                )

        if st.button(
            "Gerar outra proposta",
            width="stretch",
        ):
            for chave in [
                "plano_coach",
                "coach_ia_resultado",
                "coach_ia_contexto",
            ]:
                st.session_state.pop(chave, None)
            st.rerun()

    st.divider()
    st.caption(
        "O Coach usa IA para interpretar contexto, mas não deixa a IA gravar "
        "treinos diretamente. O plano só entra no calendário depois da sua aprovação."
    )
