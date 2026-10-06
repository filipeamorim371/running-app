import hashlib
import hmac
import time
from datetime import date, timedelta
from urllib.parse import urlencode

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st


# =========================================================
# CONFIGURAÇÃO
# =========================================================

st.set_page_config(
    page_title="Running",
    page_icon="🏃",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 820px;
        padding-top: 1.1rem;
        padding-bottom: 4rem;
    }

    h1 { letter-spacing: -0.04em; }
    h2, h3 { letter-spacing: -0.02em; }

    div[data-testid="stMetric"] {
        border: 1px solid rgba(128, 128, 128, 0.22);
        padding: 14px;
        border-radius: 16px;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 18px;
    }
    </style>
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


# =========================================================
# LOGIN DO APP
# =========================================================

def autenticar_app():
    if st.session_state.get("autenticado"):
        return

    st.title("🏃 Running")
    st.caption("Área privada")

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
            "pace_alvo": pace_alvo.strip(),
            "descricao": descricao.strip(),
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
# PACE E TEMPO
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
    segundos_restantes = valor % 60

    if horas > 0:
        return f"{horas}:{minutos:02d}:{segundos_restantes:02d}"

    return f"{minutos}:{segundos_restantes:02d}"


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
        supabase_insert(
            "strava_auth",
            dados,
        )


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

        # Recarrega para evitar associar duas atividades
        # ao mesmo treino planejado.
        historico_df = carregar_historico()

    return importadas, ignoradas


# =========================================================
# CALLBACK DO STRAVA
# =========================================================

query = st.query_params

if query.get("error") == "access_denied":
    st.error("A autorização do Strava foi cancelada.")
    st.query_params.clear()

elif query.get("code"):
    codigo = query.get("code")
    state_recebido = query.get("state", "")

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

            salvar_strava_auth(token_data)

            st.query_params.clear()
            st.session_state["mensagem"] = (
                "Strava conectado com sucesso."
            )
            st.rerun()

        except Exception as erro:
            st.error(
                f"Não foi possível conectar ao Strava: {erro}"
            )


# =========================================================
# CONSTANTES E DATAS
# =========================================================

hoje = date.today()

inicio_semana = hoje - timedelta(
    days=hoje.weekday()
)

fim_semana = inicio_semana + timedelta(days=6)

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
PACE_RECORDE_5K = RECORDE_5K_SEG / 5


# =========================================================
# CARREGAMENTO DOS DADOS
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
        (planejamento["data_dt"] >= inicio_semana)
        & (planejamento["data_dt"] <= fim_semana)
    ].copy()
else:
    semana_planejada = pd.DataFrame()


if not historico.empty:
    semana_realizada = historico[
        (historico["data_dt"] >= inicio_semana)
        & (historico["data_dt"] <= fim_semana)
    ].copy()
else:
    semana_realizada = pd.DataFrame()


# =========================================================
# CABEÇALHO
# =========================================================

st.title("🏃 Running")
st.caption("Treino, evolução e consistência.")

mensagem = st.session_state.pop(
    "mensagem",
    None,
)

if mensagem:
    st.success(mensagem)


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
        c1, c2 = st.columns([2, 1])

        c1.markdown("### Strava conectado")
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

                st.session_state["mensagem"] = (
                    f"Sincronização concluída: "
                    f"{importadas} nova(s) corrida(s) "
                    f"importada(s)."
                )

                st.rerun()

            except Exception as erro:
                st.error(
                    f"Erro ao sincronizar Strava: {erro}"
                )

    else:
        st.markdown("### Conectar Strava")
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
) = st.tabs(
    [
        "Hoje",
        "Semana",
        "Planejar",
        "Histórico",
        "Evolução",
    ]
)


# =========================================================
# HOJE
# =========================================================

with hoje_tab:
    st.write("")

    with st.container(border=True):
        st.caption(
            dias_completos[hoje.weekday()].upper()
        )

        st.markdown(
            f"# {hoje.strftime('%d/%m')}"
        )

        if not semana_planejada.empty:
            treino_hoje_df = semana_planejada[
                semana_planejada["data_dt"] == hoje
            ]
        else:
            treino_hoje_df = pd.DataFrame()

        if treino_hoje_df.empty:
            st.write("Dia sem treino planejado.")
        else:
            pendentes = 0

            for _, treino in treino_hoje_df.iterrows():
                if (
                    realizado_do_planejado(
                        treino,
                        historico,
                    )
                    is None
                ):
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
    st.subheader("Treino de hoje")

    if treino_hoje_df.empty:
        st.info(
            "Hoje não há treino planejado."
        )

    else:
        for _, treino in treino_hoje_df.iterrows():
            realizado = realizado_do_planejado(
                treino,
                historico,
            )

            with st.container(border=True):
                topo1, topo2 = st.columns([3, 1])

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
                        if treino["distancia"] > 0
                        else "-"
                    ),
                )

                c2.metric(
                    "Pace alvo",
                    (
                        treino["pace_alvo"]
                        if treino["pace_alvo"]
                        else "-"
                    ),
                )

                if treino["descricao"]:
                    st.caption(
                        treino["descricao"]
                    )

                if realizado is not None:
                    st.divider()

                    r1, r2, r3 = st.columns(3)

                    r1.metric(
                        "Realizado",
                        f"{realizado['distancia']:.1f} km",
                    )

                    r2.metric(
                        "Pace real",
                        (
                            realizado["pace"]
                            if realizado["pace"]
                            else "-"
                        ),
                    )

                    r3.metric(
                        "Origem",
                        (
                            "Strava"
                            if realizado.get("origem")
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
                            distancia_real = st.number_input(
                                "Distância realizada (km)",
                                min_value=0.0,
                                value=float(
                                    treino["distancia"]
                                ),
                                step=0.1,
                                key=(
                                    f"dist_real_"
                                    f"{int(treino['id'])}"
                                ),
                            )

                            pace_real = st.text_input(
                                "Pace médio",
                                placeholder="Ex.: 6:15",
                                key=(
                                    f"pace_real_"
                                    f"{int(treino['id'])}"
                                ),
                            )

                            esforco_real = st.slider(
                                "Esforço percebido",
                                min_value=1,
                                max_value=10,
                                value=5,
                                key=(
                                    f"esf_real_"
                                    f"{int(treino['id'])}"
                                ),
                            )

                            obs_real = st.text_area(
                                "Observações",
                                key=(
                                    f"obs_real_"
                                    f"{int(treino['id'])}"
                                ),
                            )

                            concluir = st.form_submit_button(
                                "Salvar como concluído",
                                width="stretch",
                            )

                            if concluir:
                                if distancia_real <= 0:
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
                                        treino["data"],
                                        treino["tipo"],
                                        distancia_real,
                                        pace_real,
                                        esforco_real,
                                        obs_real,
                                        int(treino["id"]),
                                    )

                                    st.rerun()

    st.write("")

    with st.expander(
        "Registrar treino extra"
    ):
        with st.form("treino_extra"):
            data_extra = st.date_input(
                "Data",
                value=hoje,
            )

            tipo_extra = st.selectbox(
                "Tipo",
                tipos_treino,
                key="tipo_extra",
            )

            distancia_extra = st.number_input(
                "Distância (km)",
                min_value=0.0,
                step=0.1,
                key="dist_extra",
            )

            pace_extra = st.text_input(
                "Pace médio",
                placeholder="Ex.: 6:15",
                key="pace_extra",
            )

            esforco_extra = st.slider(
                "Esforço",
                1,
                10,
                5,
                key="esforco_extra",
            )

            obs_extra = st.text_area(
                "Observações",
                key="obs_extra",
            )

            salvar_extra = st.form_submit_button(
                "Salvar treino extra",
                width="stretch",
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
    st.subheader("Sua semana")

    st.caption(
        f"{inicio_semana.strftime('%d/%m')} "
        f"até {fim_semana.strftime('%d/%m')}"
    )

    total_planejados = len(
        semana_planejada
    )

    concluidos = 0

    if not semana_planejada.empty:
        for _, treino in semana_planejada.iterrows():
            if (
                realizado_do_planejado(
                    treino,
                    historico,
                )
                is not None
            ):
                concluidos += 1

    km_planejados = (
        semana_planejada["distancia"].sum()
        if not semana_planejada.empty
        else 0
    )

    km_realizados = (
        semana_realizada["distancia"].sum()
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
            concluidos / total_planejados
        )

        st.progress(progresso)

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
        for _, treino in semana_planejada.iterrows():
            data_treino = treino["data_dt"]

            realizado = realizado_do_planejado(
                treino,
                historico,
            )

            with st.container(border=True):
                topo1, topo2 = st.columns([3, 1])

                topo1.caption(
                    f"{dias_curtos[data_treino.weekday()]} "
                    f"· {data_treino.strftime('%d/%m')}"
                )

                topo1.markdown(
                    f"### {treino['tipo']}"
                )

                topo2.write(
                    "✅ Feito"
                    if realizado is not None
                    else "○ Pendente"
                )

                p1, p2 = st.columns(2)

                p1.metric(
                    "Planejado",
                    (
                        f"{treino['distancia']:.1f} km"
                        if treino["distancia"] > 0
                        else "-"
                    ),
                )

                p2.metric(
                    "Pace alvo",
                    (
                        treino["pace_alvo"]
                        if treino["pace_alvo"]
                        else "-"
                    ),
                )

                if realizado is not None:
                    st.divider()

                    r1, r2, r3 = st.columns(3)

                    r1.metric(
                        "Real",
                        f"{realizado['distancia']:.1f} km",
                    )

                    r2.metric(
                        "Pace",
                        (
                            realizado["pace"]
                            if realizado["pace"]
                            else "-"
                        ),
                    )

                    r3.metric(
                        "Origem",
                        (
                            "Strava"
                            if realizado.get("origem")
                            == "strava"
                            else "Manual"
                        ),
                    )


# =========================================================
# PLANEJAR
# =========================================================

with planejar_tab:
    st.subheader("Novo treino")

    with st.form(
        "planejamento_form",
        clear_on_submit=True,
    ):
        data_planejada = st.date_input(
            "Data",
            value=hoje,
        )

        tipo_planejado = st.selectbox(
            "Tipo",
            tipos_treino,
            key="tipo_planejado",
        )

        distancia_planejada = st.number_input(
            "Distância prevista (km)",
            min_value=0.0,
            step=0.1,
        )

        pace_planejado = st.text_input(
            "Pace alvo",
            placeholder="Ex.: 6:20, 4:55 ou Livre",
        )

        descricao_planejada = st.text_area(
            "Orientações",
            placeholder=(
                "Ex.: 1 km leve + 6 x 400 m "
                "+ 1 km leve."
            ),
        )

        adicionar = st.form_submit_button(
            "Adicionar treino",
            width="stretch",
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
    st.subheader("Próximos treinos")

    futuros = (
        planejamento[
            planejamento["data_dt"] >= hoje
        ]
        if not planejamento.empty
        else pd.DataFrame()
    )

    if futuros.empty:
        st.info(
            "Nenhum treino futuro."
        )
    else:
        for _, treino in futuros.iterrows():
            realizado = realizado_do_planejado(
                treino,
                historico,
            )

            with st.container(border=True):
                st.caption(
                    treino["data_dt"].strftime(
                        "%d/%m/%Y"
                    )
                )

                st.markdown(
                    f"### {treino['tipo']}"
                )

                st.write(
                    (
                        f"📏 {treino['distancia']:.1f} km"
                        if treino["distancia"] > 0
                        else "📏 Distância livre"
                    )
                )

                if treino["pace_alvo"]:
                    st.write(
                        f"🎯 {treino['pace_alvo']}"
                    )

                if treino["descricao"]:
                    st.caption(
                        treino["descricao"]
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
    st.subheader("Histórico")

    if historico.empty:
        st.info(
            "Nenhum treino registrado."
        )
    else:
        for _, treino in historico.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])

                c1.caption(
                    treino["data_dt"].strftime(
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

                m1, m2, m3 = st.columns(3)

                m1.metric(
                    "Distância",
                    f"{treino['distancia']:.1f} km",
                )

                m2.metric(
                    "Pace",
                    (
                        treino["pace"]
                        if treino.get("pace")
                        else "-"
                    ),
                )

                m3.metric(
                    "Origem",
                    (
                        "Strava"
                        if treino.get("origem")
                        == "strava"
                        else "Manual"
                    ),
                )

                detalhes = []

                duracao = treino.get("duracao_seg")
                elevacao = treino.get("elevacao_m")
                fc_media = treino.get(
                    "frequencia_cardiaca_media"
                )

                if (
                    duracao is not None
                    and not pd.isna(duracao)
                ):
                    detalhes.append(
                        "Tempo: "
                        + segundos_para_tempo(duracao)
                    )

                if (
                    elevacao is not None
                    and not pd.isna(elevacao)
                ):
                    detalhes.append(
                        f"Elevação: {float(elevacao):.0f} m"
                    )

                if (
                    fc_media is not None
                    and not pd.isna(fc_media)
                ):
                    detalhes.append(
                        f"FC média: {float(fc_media):.0f} bpm"
                    )

                if detalhes:
                    st.caption(
                        " · ".join(detalhes)
                    )

                if treino.get("observacao"):
                    st.caption(
                        treino["observacao"]
                    )


# =========================================================
# EVOLUÇÃO
# =========================================================

with evolucao_tab:
    st.subheader("Meta 5 km")

    meta1, meta2, meta3 = st.columns(3)

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
        total_km = historico["distancia"].sum()
        quantidade = len(historico)

        e1, e2 = st.columns(2)

        e1.metric(
            "Treinos",
            quantidade,
        )

        e2.metric(
            "Km acumulados",
            f"{total_km:.1f}",
        )

        grafico_pace = historico.copy()

        grafico_pace["data_plot"] = pd.to_datetime(
            grafico_pace["data"]
        )

        grafico_pace["pace_segundos"] = (
            grafico_pace["pace"]
            .apply(pace_para_segundos)
        )

        grafico_pace = (
            grafico_pace.dropna(
                subset=["pace_segundos"]
            )
            .sort_values("data_plot")
        )

        if not grafico_pace.empty:
            st.write("")
            st.subheader("Pace por treino")

            fig = go.Figure()

            fig.add_trace(
                go.Scatter(
                    x=grafico_pace["data_plot"],
                    y=grafico_pace["pace_segundos"],
                    mode="lines+markers",
                    customdata=grafico_pace[
                        [
                            "tipo",
                            "distancia",
                            "pace",
                        ]
                    ],
                    hovertemplate=(
                        "<b>%{customdata[0]}</b>"
                        "<br>%{customdata[1]:.1f} km"
                        "<br>%{customdata[2]}/km"
                        "<extra></extra>"
                    ),
                )
            )

            min_pace = int(
                grafico_pace["pace_segundos"].min()
            )

            max_pace = int(
                grafico_pace["pace_segundos"].max()
            )

            inicio = max(
                0,
                ((min_pace - 30) // 15) * 15,
            )

            fim = (
                ((max_pace + 30 + 14) // 15)
                * 15
            )

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
                    segundos_para_pace(x)
                    for x in ticks
                ],
            )

            st.plotly_chart(
                fig,
                width="stretch",
            )

        st.divider()
        st.subheader("Volume semanal")

        volume = historico.copy()

        volume["data_plot"] = pd.to_datetime(
            volume["data"]
        )

        volume["semana"] = (
            volume["data_plot"]
            - pd.to_timedelta(
                volume["data_plot"].dt.weekday,
                unit="D",
            )
        )

        volume_semanal = (
            volume.groupby(
                "semana",
                as_index=False,
            )["distancia"]
            .sum()
            .sort_values("semana")
        )

        st.bar_chart(
            volume_semanal.set_index(
                "semana"
            )["distancia"],
            width="stretch",
        )

        testes = grafico_pace[
            grafico_pace["tipo"] == "Teste 5 km"
        ].copy()

        if not testes.empty:
            testes["tempo_5k"] = (
                testes["pace_segundos"] * 5
            )

            melhor = testes.loc[
                testes["tempo_5k"].idxmin()
            ]

            melhor_tempo = melhor["tempo_5k"]

            st.divider()
            st.subheader("Teste de 5 km")

            t1, t2 = st.columns(2)

            t1.metric(
                "Melhor teste",
                segundos_para_tempo(
                    melhor_tempo
                ),
            )

            diferenca = (
                melhor_tempo - META_5K_SEG
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
